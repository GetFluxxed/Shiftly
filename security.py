"""Legacy HTTP helpers and late-bound wrappers over shared admission rules."""

import json
import time
from threading import RLock

from backend.shiftly.identity import AdmissionControl
from backend.shiftly.identity.primitives import clean, hash_store_code, password_hash

REQUESTS = {}
LOGIN_FAILURES = {}
LOGIN_IN_FLIGHT = {}
SIGNUP_ATTEMPTS = {}
LOGIN_FAILURE_LOCK = RLock()
LOGIN_FAILURE_LIMIT = 10
LOGIN_WINDOW_SECONDS = 900


def admission_control():
    # Existing fixtures replace these dictionaries and clock at call time.
    return AdmissionControl(clock=time.time, requests=REQUESTS, failures=LOGIN_FAILURES,
                            in_flight=LOGIN_IN_FLIGHT, signups=SIGNUP_ATTEMPTS,
                            lock=LOGIN_FAILURE_LOCK, login_limit=LOGIN_FAILURE_LIMIT,
                            login_window=LOGIN_WINDOW_SECONDS)


def session_token(handler):
    cookie = handler.headers.get("Cookie", "")
    for item in cookie.split(";"):
        name, separator, value = item.strip().partition("=")
        if separator and name == "shiftly_manager_session":
            return value
    return ""


def cookie_token(handler, cookie_name):
    cookie = handler.headers.get("Cookie", "")
    for item in cookie.split(";"):
        name, separator, value = item.strip().partition("=")
        if separator and name == cookie_name:
            return value
    return ""


def named_account_token(handler):
    """Preserve absence versus a supplied empty/malformed/duplicate named cookie."""
    values = []
    for item in handler.headers.get("Cookie", "").split(";"):
        name, separator, value = item.strip().partition("=")
        if name == "shiftly_account_session":
            values.append(value if separator else "")
    if not values:
        return None
    return values[0] if len(values) == 1 else ""


def parse_json(handler, *, max_body=100_000):
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > max_body:
        raise ValueError("Request is empty or too large.")
    try:
        payload = json.loads(handler.rfile.read(length))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("Invalid report format.") from error
    if not isinstance(payload, dict):
        raise ValueError("Invalid report format.")
    return payload


def client_key(handler):
    return handler.client_address[0]


def rate_limited(handler):
    return admission_control().report_limited(client_key(handler))


def signup_rate_limited(handler):
    return admission_control().signup_limited(client_key(handler))


def record_signup_attempt(handler):
    return admission_control().record_signup(client_key(handler))


def _login_key(handler, store_code):
    return admission_control().login_key(client_key(handler), store_code)


def login_rate_limited(handler, store_code, role=None):
    return admission_control().login_limited(client_key(handler), store_code)


def reserve_login_attempt(handler, store_code):
    return admission_control().reserve_login(client_key(handler), store_code)


def finish_login_attempt(handler, store_code, *, failed):
    return admission_control().finish_login(client_key(handler), store_code, failed=failed)


def record_login_failure(handler, store_code, role=None):
    return admission_control().record_login_failure(client_key(handler), store_code)
