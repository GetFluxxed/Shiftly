import hashlib
import json
import re
import time
from threading import Lock

REQUESTS = {}
LOGIN_FAILURES = {}
LOGIN_IN_FLIGHT = {}
SIGNUP_ATTEMPTS = {}
LOGIN_FAILURE_LOCK = Lock()
LOGIN_FAILURE_LIMIT = 10
LOGIN_WINDOW_SECONDS = 900


def clean(value, limit):
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


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


def parse_json(handler, *, max_body=100_000):
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > max_body:
        raise ValueError("Request is empty or too large.")
    try:
        payload = json.loads(handler.rfile.read(length))
    except json.JSONDecodeError as error:
        raise ValueError("Invalid report format.") from error
    if not isinstance(payload, dict):
        raise ValueError("Invalid report format.")
    return payload


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240000).hex()


def hash_store_code(store_code):
    return hashlib.sha256(store_code.casefold().encode()).hexdigest()


def client_key(handler):
    return handler.client_address[0]


def rate_limited(handler):
    now = time.time()
    key = client_key(handler)
    recent = [stamp for stamp in REQUESTS.get(key, []) if now - stamp < 3600]
    if len(recent) >= 30:
        REQUESTS[key] = recent
        return True
    recent.append(now)
    REQUESTS[key] = recent
    return False


def signup_rate_limited(handler):
    now = time.time()
    key = client_key(handler)
    recent = [stamp for stamp in SIGNUP_ATTEMPTS.get(key, []) if now - stamp < 3600]
    SIGNUP_ATTEMPTS[key] = recent
    return len(recent) >= 5


def record_signup_attempt(handler):
    SIGNUP_ATTEMPTS.setdefault(client_key(handler), []).append(time.time())


def _login_key(handler, store_code):
    return f"{client_key(handler)}:{hash_store_code(store_code)}"


def login_rate_limited(handler, store_code, role=None):
    now = time.time()
    key = _login_key(handler, store_code)
    with LOGIN_FAILURE_LOCK:
        recent = [stamp for stamp in LOGIN_FAILURES.get(key, []) if now - stamp < LOGIN_WINDOW_SECONDS]
        LOGIN_FAILURES[key] = recent
        return len(recent) + LOGIN_IN_FLIGHT.get(key, 0) >= LOGIN_FAILURE_LIMIT


def reserve_login_attempt(handler, store_code):
    """Count in-flight checks against the budget before verifying a password."""
    key = _login_key(handler, store_code)
    with LOGIN_FAILURE_LOCK:
        now = time.time()
        recent = [stamp for stamp in LOGIN_FAILURES.get(key, []) if now - stamp < LOGIN_WINDOW_SECONDS]
        LOGIN_FAILURES[key] = recent
        active = LOGIN_IN_FLIGHT.get(key, 0)
        if len(recent) + active >= LOGIN_FAILURE_LIMIT:
            return False
        LOGIN_IN_FLIGHT[key] = active + 1
        return True


def finish_login_attempt(handler, store_code, *, failed):
    key = _login_key(handler, store_code)
    with LOGIN_FAILURE_LOCK:
        if failed:
            LOGIN_FAILURES.setdefault(key, []).append(time.time())
        remaining = LOGIN_IN_FLIGHT[key] - 1
        if remaining:
            LOGIN_IN_FLIGHT[key] = remaining
        else:
            del LOGIN_IN_FLIGHT[key]


def record_login_failure(handler, store_code, role=None):
    key = _login_key(handler, store_code)
    with LOGIN_FAILURE_LOCK:
        LOGIN_FAILURES.setdefault(key, []).append(time.time())
