import hashlib
import json
import re

REQUESTS = {}
LOGIN_FAILURES = {}
SIGNUP_ATTEMPTS = {}


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


def parse_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > 100_000:
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
    import time
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
    import time
    now = time.time()
    key = client_key(handler)
    recent = [stamp for stamp in SIGNUP_ATTEMPTS.get(key, []) if now - stamp < 3600]
    SIGNUP_ATTEMPTS[key] = recent
    return len(recent) >= 5


def record_signup_attempt(handler):
    import time
    SIGNUP_ATTEMPTS.setdefault(client_key(handler), []).append(time.time())


def login_rate_limited(handler, store_code, role):
    import time
    now = time.time()
    key = f"{client_key(handler)}:{role}:{hashlib.sha256(store_code.encode()).hexdigest()}"
    recent = [stamp for stamp in LOGIN_FAILURES.get(key, []) if now - stamp < 900]
    LOGIN_FAILURES[key] = recent
    return len(recent) >= 10


def record_login_failure(handler, store_code, role):
    import time
    key = f"{client_key(handler)}:{role}:{hashlib.sha256(store_code.encode()).hexdigest()}"
    LOGIN_FAILURES.setdefault(key, []).append(time.time())
