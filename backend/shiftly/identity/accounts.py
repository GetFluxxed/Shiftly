"""Public framework-free account module consumed by either HTTP adapter."""
from .accounts_core import AccountActor, AccountCore
from .accounts_lifecycle import AccountLifecycle
from .accounts_administration import AccountAdministration


class AccountsService(AccountAdministration, AccountLifecycle, AccountCore):
    """Named identities, scoped policy and lifecycle in one transactional service."""


__all__ = ['AccountsService', 'AccountActor']
