"""Catalog and shelf transactions; accounts supply public authorization only."""
import hashlib
import json
from uuid import uuid4

import psycopg
from backend.shiftly.identity.contracts import IdentityError
from .repository import InventoryRepository
from . import validation as valid
from .quantities import container_amount


class InventoryService:
    def __init__(self, connect, accounts):
        self.connect, self.accounts = connect, accounts
        self.repository = InventoryRepository()

    def _actor(self, connection, token, capability='inventory.view', expected=None, *, writing=False):
        actor = (self.accounts.require_selected_store(token, capability, connection=connection, expected_store_id=expected)
                 if writing else self.accounts.require(token, capability, connection=connection))
        if actor.business_id is None or 'inventory.view' not in actor.capabilities:
            raise IdentityError('forbidden', 'Inventory access is required for this store.', reason='permission_denied')
        return actor

    @staticmethod
    def _found(record):
        if record is None:
            raise IdentityError('not_found', 'This inventory record is not available in your current workspace.')
        return record

    def products(self, token, *, query='', after=None, state='active'):
        query, _ = valid.page(query, None)
        after = valid.product_cursor(after)
        if state not in ('active', 'archived', 'all'):
            valid.invalid('Choose active, archived or all products.')
        with self.connect() as connection:
            actor = self._actor(connection, token)
            return self.repository.products(connection, actor.business_id, query, after, state)

    def product(self, token, product_id):
        product_id = valid.identifier(product_id)
        with self.connect() as connection:
            actor = self._actor(connection, token)
            return self._found(self.repository.product(connection, actor.business_id, product_id))

    def shelves(self, token, *, after=None):
        _, after = valid.page('', after)
        with self.connect() as connection:
            actor = self._actor(connection, token)
            return self.repository.shelves(connection, actor.store_id, after)

    def shelf(self, token, shelf_id, *, after=None):
        shelf_id = valid.identifier(shelf_id)
        _, after = valid.page('', after)
        with self.connect() as connection:
            actor = self._actor(connection, token)
            row = self._found(self.repository.shelf(connection, actor.store_id, shelf_id))
            return {**row, 'products': self.repository.placements(connection, actor.store_id, shelf_id, after)}

    def _write(self, token, fields, capability, operation, payload, change):
        request_id = valid.identifier(fields.get('requestId'))
        fingerprint = hashlib.sha256(json.dumps([operation, payload], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        try:
            with self.connect() as connection:
                actor = self._actor(connection, token, capability, fields.get('expectedStoreId'), writing=True)
                replay = self.repository.replay(connection, actor, request_id)
                if replay:
                    if replay[0] != fingerprint:
                        raise IdentityError('conflict', 'This request was already used for a different change. Refresh before trying again.', reason='state_conflict')
                    return replay[1]
                target, before, after, result = change(connection, actor)
                self.repository.record(connection, actor, request_id, fingerprint, operation, target, before, after, result)
                # The closing connection context commits all configuration, audit and replay data together.
                return result
        except psycopg.errors.UniqueViolation as error:
            raise IdentityError('conflict', 'That SKU or shelf name is already in use. Choose another value.', reason='duplicate_identifier') from error

    def create_product(self, token, fields):
        data = valid.product_fields(fields, creating=True)
        if 'containerAmount' in data:
            data['containerAmount'] = container_amount(data['containerAmount'], data['baseUnit'])
        def change(connection, actor):
            product_id = str(uuid4())
            self.repository.create_product(connection, actor, product_id, data)
            self._reserve(connection, actor, product_id, data['sku'])
            saved = self.repository.product(connection, actor.business_id, product_id)
            return product_id, None, saved, saved
        return self._write(token, fields, 'catalog.manage', 'product.created', data, change)

    def _reserve(self, connection, actor, product_id, sku):
        if not self.repository.reserve_sku(connection, actor.business_id, product_id, sku):
            raise IdentityError('conflict', 'This SKU belongs to another product, including its previous SKUs.', reason='duplicate_identifier')

    def edit_product(self, token, product_id, fields):
        product_id = valid.identifier(product_id)
        data = valid.product_fields(fields)
        expected = valid.version(fields.get('version'))
        def change(connection, actor):
            before = self._found(self.repository.product(connection, actor.business_id, product_id))
            valid.current(before, expected)
            self._reserve(connection, actor, product_id, data['sku'])
            updated = {**data, 'containerAmount': container_amount(
                data.get('containerAmount', before['containerAmount']), before['baseUnit'])}
            self.repository.edit_product(connection, actor, product_id, updated)
            saved = self.repository.product(connection, actor.business_id, product_id)
            return product_id, before, saved, saved
        return self._write(token, fields, 'catalog.manage', 'product.edited', [product_id, expected, data], change)

    def product_state(self, token, product_id, fields):
        product_id = valid.identifier(product_id)
        expected = valid.version(fields.get('version'))
        active = fields.get('active')
        if type(active) is not bool:
            valid.invalid('Active must be true or false.')
        def change(connection, actor):
            before = self._found(self.repository.product(connection, actor.business_id, product_id))
            valid.current(before, expected)
            if before['active'] != active:
                self.repository.product_state(connection, actor, product_id, active)
            saved = self.repository.product(connection, actor.business_id, product_id)
            return product_id, before, saved, saved
        return self._write(token, fields, 'catalog.manage', 'product.state_changed', [product_id, expected, active], change)

    def create_shelf(self, token, fields):
        name = valid.text(fields.get('name'), 'Shelf name', 120)
        def change(connection, actor):
            shelf_id = str(uuid4())
            self.repository.create_shelf(connection, actor, shelf_id, name)
            saved = self.repository.shelf(connection, actor.store_id, shelf_id)
            return shelf_id, None, saved, saved
        return self._write(token, fields, 'configuration.manage', 'shelf.created', name, change)

    def edit_shelf(self, token, shelf_id, fields):
        shelf_id = valid.identifier(shelf_id)
        name, expected = valid.text(fields.get('name'), 'Shelf name', 120), valid.version(fields.get('version'))
        def change(connection, actor):
            before = self._found(self.repository.shelf(connection, actor.store_id, shelf_id))
            valid.current(before, expected)
            self.repository.edit_shelf(connection, actor, shelf_id, name)
            saved = self.repository.shelf(connection, actor.store_id, shelf_id)
            return shelf_id, before, saved, saved
        return self._write(token, fields, 'configuration.manage', 'shelf.edited', [shelf_id, expected, name], change)

    def place(self, token, shelf_id, product_id, fields):
        shelf_id, product_id = valid.identifier(shelf_id), valid.identifier(product_id)
        expected, active = valid.version(fields.get('version')), fields.get('active')
        if type(active) is not bool:
            valid.invalid('Active must be true or false.')
        def change(connection, actor):
            row = self._found(self.repository.shelf(connection, actor.store_id, shelf_id))
            item = self._found(self.repository.product(connection, actor.business_id, product_id))
            valid.current(row, expected)
            if active and not item['active']:
                raise IdentityError('conflict', 'This product is archived. Restore it before assigning it.', reason='state_conflict')
            before = self.repository.placement(connection, actor, shelf_id, product_id, active)
            saved = self.repository.shelf(connection, actor.store_id, shelf_id)
            result = {'shelf': saved, 'productId': product_id, 'assigned': active}
            return shelf_id, {'productId': product_id, 'assigned': before}, result, result
        return self._write(token, fields, 'configuration.manage', 'shelf.assignment_changed', [shelf_id, product_id, expected, active], change)
