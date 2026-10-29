"""Leased invoice extraction with provider work outside database transactions."""
from .photo_provider import InvoicePhotoNotConfigured
from .photo_repository import InvoicePhotoRepository
from .photo_validation import proposal

class InvoicePhotoWorker:
    def __init__(self, connect, provider, *, model=None):
        self.connect = connect
        self.provider = provider
        self.model = model
        self.repository = InvoicePhotoRepository()

    def run_one(self):
        with self.connect() as connection:
            claim = self.repository.claim(connection)
        if not claim:
            return False
        row, token, attempt = claim
        try:
            with self.connect() as connection:
                if not self.repository.authorized(connection, row):
                    self.repository.fail(
                        connection, row['id'], token, attempt,
                        'Invoice photo access changed.', False,
                    )
                    return False
            result = proposal(
                self.provider(bytes(row['image_bytes']), model=row['model'])
            )
            with self.connect() as connection:
                if not self.repository.authorized(connection, row):
                    self.repository.fail(
                        connection, row['id'], token, attempt,
                        'Invoice photo access changed.', False,
                    )
                    return False
                return self.repository.complete(connection, row['id'], token, result)
        except Exception as error:
            not_configured = isinstance(error, InvoicePhotoNotConfigured)
            message = (
                'Invoice photo reading is not configured.'
                if not_configured else 'Invoice photo reading failed.'
            )
            with self.connect() as connection:
                self.repository.fail(
                    connection, row['id'], token, attempt, message, not not_configured,
                )
            return False
