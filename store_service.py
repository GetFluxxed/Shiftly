"""Legacy adapters over store and identity repositories."""

from backend.shiftly.identity import IdentityRepository
from backend.shiftly.stores import StoresRepository, StoresService
from auth import is_manager, session_store_id
from database import db_connection
from security import cookie_token


def _stores():
    return StoresService(StoresRepository(db_connection))


def manager_username(manager_id):
    return _stores().manager_username(manager_id)


def store_for_code(store_code):
    return _stores().store_for_code(store_code)


def heads_up(store_id):
    return _stores().heads_up(store_id)


def manager_accounts(store_id):
    return _stores().manager_accounts(store_id)


def is_crew(handler):
    store_id = IdentityRepository(db_connection).crew_store(cookie_token(handler, "shiftly_crew_session"))
    if store_id:
        return store_id
    manager_id = is_manager(handler)
    return session_store_id(handler, manager_id) if manager_id else None
