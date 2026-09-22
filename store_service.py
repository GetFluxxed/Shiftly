"""Legacy adapters over store and identity repositories."""

from backend.shiftly.identity import IdentityRepository
from backend.shiftly.stores import StoresRepository, StoresService
from auth import is_manager, session_store_id, request_principal
from database import db_connection
from security import cookie_token


def _stores():
    return StoresService(StoresRepository(db_connection))


def manager_username(manager_id):
    if hasattr(manager_id, "user_id"):
        return manager_id.username
    return _stores().manager_username(manager_id)


def store_for_code(store_code):
    return _stores().store_for_code(store_code)


def heads_up(store_id):
    return _stores().heads_up(store_id)


def manager_accounts(store_id):
    return _stores().manager_accounts(store_id)


def is_crew(handler):
    principal = request_principal(handler)
    if principal and (not principal.named or 'reports.submit' in principal.actor.capabilities):
        return principal.store_id
    return None
