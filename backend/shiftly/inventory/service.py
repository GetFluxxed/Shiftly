"""Catalog and shelf transactions; accounts supply public authorization only."""
import hashlib
import json
from uuid import uuid4

import psycopg
from backend.shiftly.identity.contracts import IdentityError
from .repository import InventoryRepository
from . import validation as valid
from .quantities import package_amount
from .barcodes import identity as barcode_identity
from .packages import PackageRepository
from .quantities import amount, decimal_text
from . import package_links
from . import measurement_corrections


class InventoryService:
    def __init__(self, connect, accounts):
        self.connect, self.accounts = connect, accounts
        self.repository = InventoryRepository()
        self.package_repository = PackageRepository()

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

    @staticmethod
    def _unlinked(record):
        if record.get('canonicalProductId') is not None:
            raise IdentityError(
                'conflict', 'This product has been combined into another catalog product.',
                reason='state_conflict')
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

    def lookup_product(self, token, *, sku, barcode_type=None):
        canonical, aliases = barcode_identity(sku, barcode_type)
        with self.connect() as connection:
            actor = self._actor(connection, token)
            matches = self.repository.lookup_by_skus(connection, actor.business_id, aliases)
            product_ids = {item[0]['id'] for item in matches}
            package_ids = {item[1] for item in matches}
            if len(product_ids) > 1 or len(package_ids) > 1:
                raise IdentityError(
                    'conflict',
                    'This barcode matches more than one catalog product. Resolve the duplicate SKUs before scanning again.',
                    reason='state_conflict')
            found = matches[0] if matches else None
            linked = (self.package_repository.one(connection, actor.business_id, found[0]['id'], found[1])
                      if found and found[1] else None)
            return {'sku': canonical, 'product': found[0] if found else None, 'package': linked}

    def package_options(self, connection, business_id, product_id, active_only=False):
        return self.package_repository.packages(connection, business_id, product_id, active_only)

    def packages(self, token, product_id):
        product_id = valid.identifier(product_id)
        with self.connect() as connection:
            actor = self._actor(connection, token)
            self._found(self.repository.product(connection, actor.business_id, product_id))
            return {'items': self.package_options(connection, actor.business_id, product_id), 'nextCursor': None}

    def preview_product_combine(self, token, source_id, target_id):
        return package_links.preview(self, token, source_id, target_id)

    def combine_product(self, token, source_id, fields):
        return package_links.combine(self, token, source_id, fields)

    def measurement_correction(self, token, product_id):
        return measurement_corrections.preview(self, token, product_id)

    def correct_measurement(self, token, product_id, fields):
        return measurement_corrections.correct(self, token, product_id, fields)

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

    def _write(self, token, fields, capability, operation, payload, change, *, authorize=None):
        request_id = valid.identifier(fields.get('requestId'))
        fingerprint = hashlib.sha256(json.dumps([operation, payload], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        try:
            with self.connect() as connection:
                actor = self._actor(connection, token, capability, fields.get('expectedStoreId'), writing=True)
                if authorize is not None:
                    authorize(actor)
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
        except psycopg.errors.CheckViolation as error:
            raise IdentityError('conflict', 'This package change violates the catalog limits. Refresh and try again.', reason='state_conflict') from error

    def create_product(self, token, fields):
        data = valid.product_fields(fields, creating=True)
        if 'containerAmount' in data:
            canonical, label, unit = package_amount(data['containerAmount'], data['baseUnit'], data.get('containerUnit'))
            data['containerAmount'] = canonical
            if 'containerUnit' in data:
                data.update(containerLabelAmount=label, containerLabelUnit=unit)
        def change(connection, actor):
            aliases = data.get('barcodeAliases', (data['sku'],))
            if 'barcodeType' in data:
                matches = self.repository.products_by_skus(connection, actor.business_id, aliases)
                if len(matches) > 1:
                    raise IdentityError(
                        'conflict',
                        'This barcode matches more than one catalog product. Resolve the duplicate SKUs before trying again.',
                        reason='state_conflict')
                if matches:
                    raise IdentityError(
                        'conflict', 'This barcode already belongs to a catalog product.', reason='duplicate_identifier')
            product_id = str(uuid4())
            self.repository.create_product(connection, actor, product_id, data)
            package_id = None
            if data.get('containerAmount') is not None:
                package_id = str(uuid4())
                self.package_repository.create(connection, actor.business_id, product_id, package_id,
                    {'name':'Container','amount':data['containerAmount'],'kind':'container',
                     'labelAmount':data.get('containerLabelAmount'),'labelUnit':data.get('containerLabelUnit')}, default=True)
            for alias in sorted(set(aliases), key=lambda value: (value.casefold(), value)):
                self._reserve(connection, actor, product_id, alias, package_id)
            saved = self.repository.product(connection, actor.business_id, product_id)
            return product_id, None, saved, saved
        return self._write(token, fields, 'catalog.manage', 'product.created', data, change)

    def _reserve(self, connection, actor, product_id, sku, package_id=None):
        reserved = (self.package_repository.assign_alias(connection, actor.business_id, product_id, package_id, sku)
                    if package_id else self.repository.reserve_sku(connection, actor.business_id, product_id, sku))
        if not reserved:
            raise IdentityError('conflict', 'This SKU belongs to another product, including its previous SKUs.', reason='duplicate_identifier')

    def edit_product(self, token, product_id, fields):
        product_id = valid.identifier(product_id)
        data = valid.product_fields(fields)
        expected = valid.version(fields.get('version'))
        def change(connection, actor):
            before = self._unlinked(self._found(self.repository.product(connection, actor.business_id, product_id)))
            valid.current(before, expected)
            self._reserve(connection, actor, product_id, data['sku'])
            if 'containerAmount' not in data:
                canonical, label, unit = before['containerAmount'], before['containerLabelAmount'], before['containerLabelUnit']
            elif data['containerAmount'] is None:
                canonical, label, unit = None, None, None
            else:
                canonical, label, unit = package_amount(data['containerAmount'], before['baseUnit'], data.get('containerUnit'))
                if 'containerUnit' not in data and canonical == before['containerAmount']:
                    label, unit = before['containerLabelAmount'], before['containerLabelUnit']
            updated = {**data, 'containerAmount': canonical,
                       'containerLabelAmount': label, 'containerLabelUnit': unit}
            self.repository.edit_product(connection, actor, product_id, updated)
            default = self.package_repository.default(connection, actor.business_id, product_id)
            if updated['containerAmount'] is not None:
                if default:
                    amount_changed = decimal_text(default['amount']) != updated['containerAmount']
                    if amount_changed:
                        if self.package_repository.referencing_case(connection, actor.business_id, product_id, str(default['id'])):
                            raise IdentityError('conflict', 'Archive dependent cases before changing this package amount.', reason='state_conflict')
                    labels_changed = ((decimal_text(default['label_amount']) if default['label_amount'] is not None else None) != label
                                      or default['label_unit'] != unit)
                    if amount_changed or labels_changed or not default['active']:
                        connection.execute('''UPDATE inventory_packages SET amount=%s,active=true,
                            label_amount=%s,label_unit=%s,version=version+1,updated_at=NOW() WHERE id=%s''',
                            (updated['containerAmount'],label,unit,default['id']))
                else:
                    default_id = str(uuid4())
                    self.package_repository.create(connection, actor.business_id, product_id, default_id,
                        {'name':'Container','amount':updated['containerAmount'],'kind':'container',
                         'labelAmount':label,'labelUnit':unit}, default=True)
                    connection.execute('''UPDATE inventory_product_skus SET package_id=%s
                        WHERE business_id=%s AND product_id=%s AND package_id IS NULL''',
                        (default_id,actor.business_id,product_id))
            elif default and default['active']:
                if self.package_repository.referencing_case(connection, actor.business_id, product_id, str(default['id'])):
                    raise IdentityError('conflict', 'Archive dependent cases before clearing the default package.', reason='state_conflict')
                connection.execute('''UPDATE inventory_packages SET active=false,version=version+1,updated_at=NOW()
                    WHERE id=%s''', (default['id'],))
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
            before = self._unlinked(self._found(self.repository.product(connection, actor.business_id, product_id)))
            valid.current(before, expected)
            if before['active'] != active:
                self.repository.product_state(connection, actor, product_id, active)
            saved = self.repository.product(connection, actor.business_id, product_id)
            return product_id, before, saved, saved
        return self._write(token, fields, 'catalog.manage', 'product.state_changed', [product_id, expected, active], change)

    def _package_data(self, connection, actor, product_id, fields, before=None):
        data = valid.package_fields(fields)
        parent = self._unlinked(self._found(self.repository.product(connection, actor.business_id, product_id)))
        if data['containedPackageId']:
            child = self._found(self.package_repository.raw(connection, actor.business_id, product_id, data['containedPackageId']))
            if child['contained_package_id'] is not None:
                valid.invalid('A case must contain a leaf package option.')
            if not child['active']:
                raise IdentityError('conflict', 'Restore the contained package before using it in a case.', reason='state_conflict')
            computed = child['amount'] * data['containedCount']
            amount(decimal_text(computed), label='Package amount')
            if parent['baseUnit'] == 'each' and computed != computed.to_integral_value():
                valid.invalid('An item package must contain a whole number of items.')
            data['amount'] = decimal_text(computed)
            data['labelAmount'] = data['labelUnit'] = None
        else:
            if data['amount'] is None and before is None:
                valid.invalid('A full package amount is required.')
            if data['amount'] is None and before is not None and before['containedPackageId'] is not None:
                valid.invalid('Supply a full package amount when changing a case to a leaf package.')
            if data['amount'] is None:
                data['amount'] = before['amount']
                data['labelAmount'], data['labelUnit'] = before['labelAmount'], before['labelUnit']
            else:
                canonical, label, unit = package_amount(data['amount'], parent['baseUnit'], data.get('amountUnit'))
                if before is not None and 'amountUnit' not in data and canonical == before['amount']:
                    label, unit = before['labelAmount'], before['labelUnit']
                data.update(amount=canonical,labelAmount=label,labelUnit=unit)
        return data

    def create_package(self, token, product_id, fields):
        product_id = valid.identifier(product_id)
        def change(connection, actor):
            self._unlinked(self._found(self.repository.product(connection, actor.business_id, product_id)))
            if len(self.package_options(connection, actor.business_id, product_id)) >= 40:
                raise IdentityError('conflict', 'A product can have at most 40 package options, including archived options.', reason='state_conflict')
            data = self._package_data(connection, actor, product_id, fields)
            package_id = str(uuid4())
            self.package_repository.create(connection, actor.business_id, product_id, package_id, data)
            for alias in sorted(set(data.get('barcodeAliases', ()))):
                if not self.package_repository.assign_alias(connection, actor.business_id, product_id, package_id, alias):
                    raise IdentityError('conflict', 'This barcode already belongs to another package or product.', reason='duplicate_identifier')
            self.package_repository.bump_product(connection, actor.business_id, product_id)
            saved = self.package_repository.one(connection, actor.business_id, product_id, package_id)
            return package_id, None, saved, saved
        payload = [product_id, valid.package_fields(fields)]
        return self._write(token, fields, 'catalog.manage', 'package.created', payload, change)

    def edit_package(self, token, product_id, package_id, fields):
        product_id, package_id = valid.identifier(product_id), valid.identifier(package_id)
        expected = valid.version(fields.get('version'))
        def change(connection, actor):
            self._unlinked(self._found(self.repository.product(connection, actor.business_id, product_id)))
            before = self._found(self.package_repository.one(connection, actor.business_id, product_id, package_id))
            locked = self._found(self.package_repository.raw(connection, actor.business_id, product_id, package_id))
            if locked['version'] != expected:
                raise IdentityError('conflict', 'This record changed. Reload the latest version before saving.', reason='stale_record')
            if fields.get('containedPackageId') == package_id:
                valid.invalid('A package cannot contain itself.')
            data = self._package_data(connection, actor, product_id, fields, before)
            if before['isDefault'] and data['containedPackageId'] is not None:
                raise IdentityError(
                    'conflict', 'The legacy default package cannot contain another package option.',
                    reason='state_conflict')
            referenced = self.package_repository.referencing_case(
                connection, actor.business_id, product_id, package_id)
            if referenced and (before['amount'] != data['amount'] or data['containedPackageId'] is not None):
                raise IdentityError('conflict', 'Archive dependent cases before changing this package.', reason='state_conflict')
            self.package_repository.edit(connection, actor.business_id, product_id, package_id, data)
            for alias in sorted(set(data.get('barcodeAliases', ()))):
                if not self.package_repository.assign_alias(connection, actor.business_id, product_id, package_id, alias):
                    raise IdentityError('conflict', 'This barcode already belongs to another package or product.', reason='duplicate_identifier')
            self.package_repository.bump_product(
                connection, actor.business_id, product_id,
                data['amount'] if before['isDefault'] and before['active'] else None,
                sync_default=before['isDefault'],
                label_amount=data['labelAmount'] if before['isDefault'] and before['active'] else None,
                label_unit=data['labelUnit'] if before['isDefault'] and before['active'] else None)
            saved = self.package_repository.one(connection, actor.business_id, product_id, package_id)
            return package_id, before, saved, saved
        payload = [product_id,package_id,expected,valid.package_fields(fields)]
        return self._write(token, fields, 'catalog.manage', 'package.edited', payload, change)

    def package_state(self, token, product_id, package_id, fields):
        product_id, package_id = valid.identifier(product_id), valid.identifier(package_id)
        expected, active = valid.version(fields.get('version')), fields.get('active')
        if type(active) is not bool:
            valid.invalid('Active must be true or false.')
        def change(connection, actor):
            self._unlinked(self._found(self.repository.product(connection, actor.business_id, product_id)))
            before = self._found(self.package_repository.one(connection, actor.business_id, product_id, package_id))
            locked = self._found(self.package_repository.raw(connection, actor.business_id, product_id, package_id))
            if locked['version'] != expected:
                raise IdentityError('conflict', 'This record changed. Reload the latest version before saving.', reason='stale_record')
            if not active and self.package_repository.referencing_case(
                    connection, actor.business_id, product_id, package_id):
                raise IdentityError('conflict', 'Archive dependent cases before archiving this package.', reason='state_conflict')
            if active and before['containedPackageId']:
                child = self._found(self.package_repository.raw(connection, actor.business_id, product_id, before['containedPackageId']))
                if not child['active']:
                    raise IdentityError('conflict', 'Restore the contained package before restoring this case.', reason='state_conflict')
                if decimal_text(child['amount'] * before['containedCount']) != before['amount']:
                    raise IdentityError('conflict', 'Update this case conversion before restoring it.', reason='state_conflict')
            if before['active'] != active:
                self.package_repository.state(connection, actor.business_id, product_id, package_id, active)
                self.package_repository.bump_product(
                    connection, actor.business_id, product_id,
                    before['amount'] if before['isDefault'] and active else None,
                    sync_default=before['isDefault'],
                    label_amount=before['labelAmount'] if before['isDefault'] and active else None,
                    label_unit=before['labelUnit'] if before['isDefault'] and active else None)
            saved = self.package_repository.one(connection, actor.business_id, product_id, package_id)
            return package_id, before, saved, saved
        return self._write(token, fields, 'catalog.manage', 'package.state_changed',
                           [product_id,package_id,expected,active], change)

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
            item = self._unlinked(self._found(self.repository.product(connection, actor.business_id, product_id)))
            valid.current(row, expected)
            if active and not item['active']:
                raise IdentityError('conflict', 'This product is archived. Restore it before assigning it.', reason='state_conflict')
            before = self.repository.placement(connection, actor, shelf_id, product_id, active)
            saved = self.repository.shelf(connection, actor.store_id, shelf_id)
            result = {'shelf': saved, 'productId': product_id, 'assigned': active}
            return shelf_id, {'productId': product_id, 'assigned': before}, result, result
        return self._write(token, fields, 'configuration.manage', 'shelf.assignment_changed', [shelf_id, product_id, expected, active], change)
