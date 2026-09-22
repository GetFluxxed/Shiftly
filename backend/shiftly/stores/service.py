"""Store operations take trusted identifiers from the authentication adapter."""

from backend.shiftly.identity.primitives import clean


class StoresService:
    def __init__(self, repository):
        self.repository = repository

    def store_for_code(self, code):
        return self.repository.store_for_code(code)

    def manager_username(self, manager_id):
        return self.repository.manager_username(manager_id)

    def manager_accounts(self, store_id):
        return self.repository.manager_accounts(store_id)

    def heads_up(self, store_id):
        return self.repository.heads_up(store_id)

    def save_heads_up(self, store_id, message, *, actor_token=None, accounts=None, legacy_credentials=None):
        if actor_token is not None or legacy_credentials is not None:
            return self.repository.save_heads_up(store_id, clean(message, 1000), actor_token=actor_token, accounts=accounts,
                                                  legacy_credentials=legacy_credentials)
        return self.repository.save_heads_up(store_id, clean(message, 1000))
