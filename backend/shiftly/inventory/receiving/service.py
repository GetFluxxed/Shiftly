"""Reviewed invoice drafts and exact incoming projections without stock mutation."""
import hashlib
import json
from decimal import Decimal, localcontext
from uuid import uuid4

import psycopg

from backend.shiftly.identity.contracts import IdentityError
from ..movements import MovementRepository
from ..quantities import decimal_text
from ..repository import InventoryRepository
from .repository import ReceivingRepository
from . import validation as valid

REQUIRED = {'receipts.draft', 'receipts.post', 'inventory.view'}
MAX_NORMALIZED = Decimal('999999999999999.999999999')


def conflict(message, reason='state_conflict'):
    raise IdentityError('conflict', message, reason=reason)


def found(value):
    if value is None:
        raise IdentityError('not_found', 'This invoice is unavailable in your store.')
    return value


class ReceivingService:
    def __init__(self, connect, accounts, *, photo_reading_available=False):
        self.connect, self.accounts = connect, accounts
        self.photo_reading_available = bool(photo_reading_available)
        self.repository = ReceivingRepository()
        self.audit = InventoryRepository()

    def actor(self, connection, token, expected=None, *, writing=False):
        actor = (self.accounts.require_selected_store(token, 'receipts.draft', connection=connection,
                                                      expected_store_id=expected)
                 if writing else self.accounts.require(token, 'receipts.draft', connection=connection))
        if actor.business_id is None or actor.role not in {'manager', 'owner'} or not REQUIRED.issubset(actor.capabilities):
            raise IdentityError('forbidden', 'Manager or owner invoice access is required for this store.',
                                reason='permission_denied')
        return actor

    @staticmethod
    def fingerprint(operation, payload):
        return hashlib.sha256(json.dumps([operation, payload], sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    @staticmethod
    def payload(fields):
        return {key: ([{**line, 'quantity': decimal_text(line['quantity']) if line['quantity'] is not None else None}
                       for line in value] if key == 'lines' else value)
                for key, value in fields.items() if key != 'requestId'}

    def write(self, token, fields, operation, payload, change):
        fingerprint = self.fingerprint(operation, payload)
        try:
            with self.connect() as connection:
                actor = self.actor(connection, token, fields['expectedStoreId'], writing=True)
                MovementRepository.lock_store(connection, actor)
                replay = self.audit.replay(connection, actor, fields['requestId'])
                if replay:
                    if replay[0] != fingerprint:
                        conflict('This request already describes another change. Reload before changing it.')
                    return replay[1]
                target, before, result = change(connection, actor)
                self.audit.record(connection, actor, fields['requestId'], fingerprint, operation, target, before, result, result)
                return result
        except psycopg.errors.UniqueViolation as error:
            conflict('An active invoice already uses this supplier and invoice number.', 'duplicate_identifier')

    def invoices(self, token, query='', after=None):
        query, after = valid.query(query), valid.decode_cursor(after)
        with self.connect() as connection:
            actor = self.actor(connection, token)
            return self.repository.summaries(connection, actor, query, after,
                                             photo_reading_available=self.photo_reading_available)

    def invoice(self, token, invoice_id):
        invoice_id = valid.identifier(invoice_id)
        with self.connect() as connection:
            actor = self.actor(connection, token)
            result = found(self.repository.draft(connection, actor, invoice_id))
            return {**result, 'photoReadingAvailable': self.photo_reading_available}

    def snapshot(self, connection, actor, item, existing=None):
        if not item['productId']:
            return {}
        catalog = self.repository.catalog(connection, actor, item['productId'], item['packageId'])
        if not catalog or not catalog['active']:
            conflict('A matched product is no longer active in this catalog. Remove or rematch the invoice line.')
        if item['packageId'] and (not catalog['package_id'] or not catalog['package_active']):
            conflict('A matched package is no longer active. Remove or rematch the invoice line.')
        unchanged = existing and str(existing['product_id']) == item['productId'] and \
            (str(existing['package_id']) if existing['package_id'] else None) == item['packageId'] and \
            existing['quantity'] == item['quantity'] and existing['unit'] == item['unit']
        if unchanged:
            if str(catalog['id']) != str(existing['product_id']) or catalog['base_unit'] != existing['base_unit'] or \
               (item['packageId'] and catalog['package_amount'] != existing['package_amount']):
                conflict('This product or package changed after it was matched. Remove or rematch the invoice line.')
            return {'productId': str(existing['product_id']), 'packageId': str(existing['package_id']) if existing['package_id'] else None,
                    'productName': existing['product_name'], 'baseUnit': existing['base_unit'],
                    'normalizedQuantity': existing['normalized_quantity'], 'packageName': existing['package_name'],
                    'packageAmount': existing['package_amount'], 'productVersion': existing['product_version'],
                    'packageVersion': existing['package_version']}
        if existing and str(existing['product_id']) == str(catalog['id']):
            old_package = str(existing['package_id']) if existing['package_id'] else None
            new_package = str(catalog['package_id']) if catalog['package_id'] else None
            if old_package == new_package and (existing['base_unit'] != catalog['base_unit'] or
               existing['package_amount'] != catalog['package_amount']):
                conflict('This product or package changed after it was matched. Remove or rematch the invoice line.')
        amount = item['quantity']
        base = catalog['base_unit']
        with localcontext() as context:
            context.prec = 60
            if item['unit'] == 'package':
                if amount != amount.to_integral_value():
                    valid.invalid('Package quantities must be whole numbers.')
                normalized = amount * catalog['package_amount']
            elif base == 'each':
                if item['unit'] != 'each' or amount != amount.to_integral_value():
                    valid.invalid('Item quantities must be whole each units.')
                normalized = amount
            elif base == 'kg' and item['unit'] == 'kg':
                normalized = amount
            elif base == 'kg' and item['unit'] == 'g':
                normalized = amount / Decimal('1000')
            elif base == 'kg' and item['unit'] == 'lb':
                normalized = amount * Decimal('0.45359237')
            elif base == 'g' and item['unit'] == 'g':
                normalized = amount
            elif base == 'g' and item['unit'] == 'kg':
                normalized = amount * Decimal('1000')
            elif base == 'g' and item['unit'] == 'lb':
                normalized = amount * Decimal('453.59237')
            else:
                valid.invalid('The selected unit does not match the product base unit.')
        decimal_tuple = normalized.as_tuple()
        trailing = next((index for index, digit in enumerate(reversed(decimal_tuple.digits)) if digit), len(decimal_tuple.digits))
        effective_scale = max(0, -decimal_tuple.exponent - trailing)
        if normalized <= 0 or normalized > MAX_NORMALIZED or effective_scale > 9:
            valid.invalid('The normalized invoice quantity exceeds the supported stock range or precision.')
        with localcontext() as context:
            context.prec = 60
            normalized = normalized.quantize(Decimal(1).scaleb(-effective_scale))
        return {'productId': str(catalog['id']), 'packageId': str(catalog['package_id']) if catalog['package_id'] else None,
                'productName': catalog['name'], 'baseUnit': base, 'normalizedQuantity': normalized,
                'packageName': catalog['package_name'], 'packageAmount': catalog['package_amount'],
                'productVersion': catalog['version'], 'packageVersion': catalog['package_version']}

    def create(self, token, fields):
        fields = valid.draft_fields(fields)
        payload = self.payload(fields)
        def change(connection, actor):
            invoice_id = str(uuid4())
            baseline = self.repository.baseline(connection, actor)
            snapshots = [self.snapshot(connection, actor, item) for item in fields['lines']]
            self.repository.create(connection, actor, invoice_id, fields, baseline)
            self.repository.replace(connection, actor, invoice_id, fields, snapshots, bump=False)
            if self.repository.incoming_overflow(connection, actor):
                valid.invalid('The open invoice total exceeds the supported stock range for a product.')
            result = self.repository.draft(connection, actor, invoice_id)
            return invoice_id, None, result
        return self.write(token, fields, 'invoice.create', payload, change)

    def edit(self, token, invoice_id, fields):
        invoice_id, fields = valid.identifier(invoice_id), valid.draft_fields(fields, editing=True)
        payload = {'invoiceId': invoice_id, **self.payload(fields)}
        def change(connection, actor):
            before = found(self.repository.draft(connection, actor, invoice_id, lock=True))
            if before['state'] != 'draft':
                conflict('Closed invoice history cannot be changed.')
            if before['version'] != fields['version']:
                conflict('This invoice changed elsewhere. Reload it before saving.', 'stale_record')
            existing = self.repository.lines_raw(connection, invoice_id)
            snapshots = [self.snapshot(connection, actor, item, existing.get(item['id'])) for item in fields['lines']]
            self.repository.replace(connection, actor, invoice_id, fields, snapshots)
            if self.repository.incoming_overflow(connection, actor):
                valid.invalid('The open invoice total exceeds the supported stock range for a product.')
            return invoice_id, before, self.repository.draft(connection, actor, invoice_id)
        return self.write(token, fields, 'invoice.edit', payload, change)

    def close(self, token, invoice_id, fields):
        invoice_id, fields = valid.identifier(invoice_id), valid.action_fields(fields)
        payload = {'invoiceId': invoice_id, 'version': fields['version'], 'expectedStoreId': fields['expectedStoreId']}
        def change(connection, actor):
            before = found(self.repository.draft(connection, actor, invoice_id, lock=True))
            if before['state'] != 'draft':
                conflict('This invoice is already closed.')
            if before['version'] != fields['version']:
                conflict('This invoice changed elsewhere. Reload it before closing.', 'stale_record')
            self.repository.close(connection, actor, invoice_id)
            return invoice_id, before, self.repository.draft(connection, actor, invoice_id)
        return self.write(token, fields, 'invoice.close', payload, change)

    def rebase(self, token, invoice_id, fields):
        invoice_id, fields = valid.identifier(invoice_id), valid.action_fields(fields)
        payload = {'invoiceId': invoice_id, 'version': fields['version'], 'expectedStoreId': fields['expectedStoreId']}
        def change(connection, actor):
            before = found(self.repository.draft(connection, actor, invoice_id, lock=True))
            if before['state'] != 'draft':
                conflict('Closed invoice history cannot be rebased.')
            if before['version'] != fields['version']:
                conflict('This invoice changed elsewhere. Reload it before rebasing.', 'stale_record')
            self.repository.rebase(connection, invoice_id, self.repository.baseline(connection, actor))
            return invoice_id, before, self.repository.draft(connection, actor, invoice_id)
        return self.write(token, fields, 'invoice.rebase', payload, change)

    def incoming(self, token, query='', after=None):
        query, after = valid.query(query), valid.decode_product_cursor(after)
        with self.connect() as connection:
            actor = self.actor(connection, token)
            return self.repository.incoming(connection, actor, query, after)
