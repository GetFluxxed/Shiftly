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
    """Invalid named credentials never fall through to older cookies.

    A valid named+legacy manager pair is allowed only for the exact same mapped
    person and store. Shared crew identity cannot prove equivalence to a person.
    Two valid legacy cookie types are ambiguous even at one store. An expired
    legacy cookie carries no identity and does not suppress a valid legacy peer;
    this compatibility rule never applies when a named cookie is present.
    """
    if account_token is not None:
        if not isinstance(account_token, str) or not account_token:
            raise IdentityError('unauthenticated', 'Named sign-in required.')
        actor = identity.accounts.resolve_actor(account_token)
        if crew_token:
            raise IdentityError('unauthenticated', 'Conflicting sign-in sessions. Sign in again.')
        if manager_token:
            manager_id = identity.repository.manager_id(manager_token)
            selected = identity.repository.selected_store(manager_token, manager_id)
            if not manager_id or manager_id != actor.legacy_manager_id or selected != actor.store_id:
                raise IdentityError('unauthenticated', 'Conflicting sign-in sessions. Sign in again.')
        return RequestPrincipal(actor.store_id, actor.legacy_manager_id, actor)
    if manager_token and crew_token:
        legacy_manager = identity.repository.manager_id(manager_token)
        manager_store = identity.repository.selected_store(manager_token, legacy_manager) if legacy_manager else None
        crew_store = identity.repository.crew_store(crew_token)
        if legacy_manager and manager_store and crew_store:
            raise IdentityError('unauthenticated', 'Conflicting sign-in sessions. Sign in again.')
        if legacy_manager and manager_store:
            return RequestPrincipal(manager_store, legacy_manager)
        if crew_store:
            return RequestPrincipal(crew_store)
        raise IdentityError('unauthenticated', 'Sign-in required.')
    if manager_token:
        manager_id = identity.repository.manager_id(manager_token)
        store_id = identity.repository.selected_store(manager_token, manager_id)
        if not manager_id or not store_id:
            raise IdentityError('unauthenticated', 'Sign-in required.')
        return RequestPrincipal(store_id, manager_id)
    if crew_token:
        store_id = identity.repository.crew_store(crew_token)
        if not store_id:
            raise IdentityError('unauthenticated', 'Sign-in required.')
        return RequestPrincipal(store_id)
    return None
