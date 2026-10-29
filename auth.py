"""Legacy request adapters using the same principal rules as named services."""
from backend.shiftly.identity import IdentityError, IdentityRepository, IdentityService
from backend.shiftly.stores import StoresRepository, StoresService
from database import db_connection
from security import cookie_token, named_account_token


def request_principal(handler, *, strict=False):
    identity = IdentityService(IdentityRepository(db_connection), StoresService(StoresRepository(db_connection)))
    try:
        return identity.resolve_principal(
            account_token=named_account_token(handler),
            manager_token=cookie_token(handler, 'shiftly_manager_session'),
            crew_token=cookie_token(handler, 'shiftly_crew_session'),
        )
    except IdentityError:
        if strict:
            raise
        return None


def is_manager(handler):
    principal = request_principal(handler)
    if not principal or not principal.can_manage:
        return None
    return principal.actor if principal.named else principal.manager_id


def session_store_id(handler, manager_id):
    principal = request_principal(handler)
    if not principal or not principal.can_manage:
        return None
    if principal.named:
        return principal.store_id if manager_id == principal.actor else None
    return principal.store_id if manager_id == principal.manager_id else None
