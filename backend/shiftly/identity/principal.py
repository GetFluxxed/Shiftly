"""One principal per request, shared by HTTP adapters without cookie precedence."""
from dataclasses import dataclass

from .contracts import IdentityError


@dataclass(frozen=True)
class RequestPrincipal:
    store_id: int
    manager_id: int | None = None
    actor: object | None = None

    @property
    def named(self):
        return self.actor is not None

    @property
    def can_manage(self):
        return ('reports.view' in self.actor.capabilities) if self.named else bool(self.manager_id)


def resolve_principal(identity, *, account_token=None, manager_token='', crew_token=''):
    """Release accounts have one individual identity; shared cookies are retired."""
    if manager_token or crew_token:
        raise IdentityError('unauthenticated', 'Sign in with your individual username and password.')
    if account_token is None:
        return None
    if not isinstance(account_token, str) or not account_token:
        raise IdentityError('unauthenticated', 'Individual sign-in required.')
    actor = identity.accounts.resolve_actor(account_token)
    return RequestPrincipal(actor.store_id, actor.legacy_manager_id, actor)
