"""Reviewed invoice-photo proposal workflow; never mutates invoice fields or stock."""
import hashlib
import json
from uuid import UUID

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.movements import MovementRepository

from .photo_repository import InvoicePhotoRepository, public
from .photo_validation import sanitized_image


def identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError) as error:
        raise IdentityError('invalid', 'Invalid invoice photo request.') from error


def conflict(message):
    raise IdentityError('conflict', message, reason='state_conflict')


class InvoicePhotoService:
    def __init__(self, connect, accounts, *, model, provider_available=True):
        self.connect = connect
        self.accounts = accounts
        self.model = model
        self.provider_available = provider_available
        self.repository = InvoicePhotoRepository()

    def _actor(self, connection, token, expected=None, writing=False):
        if writing:
            actor = self.accounts.require_selected_store(
                token, 'receipts.draft', connection=connection, expected_store_id=expected,
            )
        else:
            actor = self.accounts.require(token, 'receipts.draft', connection=connection)
        required = {'receipts.post', 'inventory.view'}
        if actor.role not in {'manager', 'owner'} or not required <= actor.capabilities:
            raise IdentityError(
                'forbidden', 'Manager or owner invoice access is required.',
                reason='permission_denied',
            )
        return actor

    def _invoice(self, connection, actor, invoice_id, *, lock=False):
        invoice = self.repository.invoice(connection, actor, invoice_id, lock)
        if invoice is None:
            raise IdentityError('not_found', 'This invoice is unavailable in your store.')
        return invoice

    def _result(self, connection, actor, row):
        matches = None
        if row:
            matches = self.repository.matches(connection, actor.business_id, row.get('proposal') or {})
        return public(row, matches)

    def _replay(self, connection, actor, request_id, fingerprint, invoice_id):
        replay = self.repository.replay(connection, actor, request_id)
        if replay is None:
            return None
        if replay[0] != fingerprint:
            conflict('This request already describes another change.')
        row = self.repository.photo(connection, actor, replay[1], invoice_id)
        if row is None:
            conflict('This invoice photo request is no longer available.')
        return self._result(connection, actor, row)

    def available(self):
        return bool(self.provider_available)

    def analysis(self, token, invoice_id):
        invoice_id = identifier(invoice_id)
        with self.connect() as connection:
            actor = self._actor(connection, token)
            self._invoice(connection, actor, invoice_id)
            row = self.repository.latest(connection, actor, invoice_id)
            return self._result(connection, actor, row)

    def upload(self, token, invoice_id, fields):
        invoice_id = identifier(invoice_id)
        request_id = identifier(fields.get('requestId'))
        with self.connect() as connection:
            actor = self._actor(connection, token)
            self._invoice(connection, actor, invoice_id)
        if not self.provider_available:
            raise IdentityError(
                'conflict', 'Invoice photo reading is not configured.', reason='state_conflict',
            )

        image = sanitized_image(fields.get('imageBase64'))
        image_hash = hashlib.sha256(image).hexdigest()
        fingerprint = hashlib.sha256(json.dumps([
            'photo.upload', invoice_id, image_hash,
            fields.get('expectedStoreId'), fields.get('version'),
        ], separators=(',', ':')).encode()).hexdigest()

        with self.connect() as connection:
            actor = self._actor(connection, token, fields.get('expectedStoreId'), writing=True)
            MovementRepository.lock_store(connection, actor)
            invoice = self._invoice(connection, actor, invoice_id, lock=True)
            replay = self._replay(connection, actor, request_id, fingerprint, invoice_id)
            if replay is not None:
                return replay
            if invoice['state'] != 'draft':
                conflict('This invoice is closed.')
            if type(fields.get('version')) is not int or invoice['version'] != fields['version']:
                raise IdentityError(
                    'conflict', 'This invoice changed. Reload and try again.', reason='stale_record',
                )
            duplicate = self.repository.duplicate(connection, actor, invoice_id, image_hash)
            if duplicate is None and self.repository.daily_count(connection, actor) >= 10:
                conflict('This store has reached today’s invoice photo limit.')
            photo_id = self.repository.enqueue(
                connection, actor, invoice, image, image_hash, request_id,
                fingerprint, self.model, prior=duplicate,
            )
            row = self.repository.photo(connection, actor, photo_id, invoice_id)
            return self._result(connection, actor, row)

    def retry(self, token, invoice_id, fields):
        invoice_id = identifier(invoice_id)
        request_id = identifier(fields.get('requestId'))
        fingerprint = hashlib.sha256(json.dumps([
            'photo.retry', invoice_id,
            fields.get('expectedStoreId'), fields.get('version'),
        ], separators=(',', ':')).encode()).hexdigest()
        with self.connect() as connection:
            actor = self._actor(connection, token, fields.get('expectedStoreId'), writing=True)
            MovementRepository.lock_store(connection, actor)
            invoice = self._invoice(connection, actor, invoice_id, lock=True)
            replay = self._replay(connection, actor, request_id, fingerprint, invoice_id)
            if replay is not None:
                return replay
            if invoice['state'] != 'draft':
                conflict('This invoice is closed.')
            if invoice['version'] != fields.get('version'):
                raise IdentityError(
                    'conflict', 'This invoice changed. Reload and try again.', reason='stale_record',
                )
            row = self.repository.latest(connection, actor, invoice_id)
            if row is None or not self.repository.retry(connection, row):
                conflict('This invoice photo cannot be retried.')
            self.repository.record_request(connection, actor, request_id, fingerprint, row['id'])
            retried = self.repository.photo(connection, actor, row['id'], invoice_id)
            return self._result(connection, actor, retried)
