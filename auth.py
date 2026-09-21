"""Legacy cookie adapters; identity SQL lives in the shared repository."""

from backend.shiftly.identity import IdentityRepository
from database import db_connection
from security import cookie_token


def is_manager(handler):
    return IdentityRepository(db_connection).manager_id(cookie_token(handler, "shiftly_manager_session"))


def session_store_id(handler, manager_id):
    return IdentityRepository(db_connection).selected_store(cookie_token(handler, "shiftly_manager_session"), manager_id)
