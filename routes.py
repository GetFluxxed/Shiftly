"""Legacy HTTP adapters with explicit, replaceable service composition."""

import json
from urllib.parse import urlparse

import reporting
from backend.shiftly.identity import IdentityError, IdentityRepository, IdentityService
from backend.shiftly.reports import ReportRejected, ReportSubmission
from backend.shiftly.stores import StoresRepository, StoresService
from auth import is_manager, session_store_id
from config import load_settings
from database import db_connection
from security import admission_control, clean, client_key, parse_json, password_hash, rate_limited
from store_service import heads_up, is_crew, manager_username, store_for_code

# Retired test-injection hook. No route calls it or discovers server globals.
_server_module = None

IDENTITY_STATUS = {"invalid": 400, "unauthenticated": 401, "forbidden": 403,
                   "not_found": 404, "conflict": 409, "limited": 429, "unavailable": 503}


def make_identity_service(*, admin_key=None, session_ttl=28800):
    if admin_key is None:
        admin_key = load_settings().admin_signup_key
    return IdentityService(
        IdentityRepository(db_connection), StoresService(StoresRepository(db_connection)),
        admin_key=admin_key, session_ttl=session_ttl, admission=admission_control(),
        password_hasher=password_hash, store_lookup=store_for_code, username_lookup=manager_username,
    )


def _identity_error(handler, error):
    handler.send_json(IDENTITY_STATUS[error.code], {"error": str(error)})


def _session_response(handler, result, status, secure_cookies):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    secure = "; Secure" if secure_cookies else ""
    cookie_name = "shiftly_manager_session" if result.role == "manager" else "shiftly_crew_session"
    handler.send_header("Set-Cookie", f"{cookie_name}={result.token}; Path=/; HttpOnly; SameSite=Strict{secure}; Max-Age={result.ttl}")
    handler.end_headers()
    handler.wfile.write(json.dumps(result.response, ensure_ascii=False).encode("utf-8"))


def login(handler, store_code=None, role=None, password=None, *, identity=None, secure_cookies=None):
    identity = identity if identity is not None else make_identity_service()
    if secure_cookies is None:
        secure_cookies = load_settings().secure_cookies
    try:
        if store_code is None or role is None or password is None:
            try:
                payload = parse_json(handler, max_body=10_000)
            except (ValueError, TypeError, UnicodeError):
                handler.send_json(400, {"error": "Invalid login request."})
                return
            result = identity.login_payload(payload, client_key=client_key(handler))
        else:
            result = identity.login(store_code, role, password, client_key=client_key(handler))
    except IdentityError as error:
        _identity_error(handler, error)
        return
    _session_response(handler, result, 200, secure_cookies)


def _create_account(handler, *, identity, secure_cookies, action):
    identity = identity if identity is not None else make_identity_service()
    if secure_cookies is None:
        secure_cookies = load_settings().secure_cookies
    try:
        identity.admit_account_creation(client_key(handler), action=action)
        payload = parse_json(handler)
        result = identity.signup(payload) if action == "signup" else identity.add_manager(payload)
    except IdentityError as error:
        _identity_error(handler, error)
        return
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
        return
    _session_response(handler, result, 201, secure_cookies)


def signup(handler, *, identity=None, secure_cookies=None):
    return _create_account(handler, identity=identity, secure_cookies=secure_cookies, action="signup")


def add_manager(handler, *, identity=None, secure_cookies=None):
    return _create_account(handler, identity=identity, secure_cookies=secure_cookies, action="add_manager")


def save_heads_up(handler):
    manager_id = is_manager(handler)
    store_id = session_store_id(handler, manager_id)
    if not store_id:
        handler.send_json(401, {"error": "Manager sign-in required."})
        return
    stores = StoresService(StoresRepository(db_connection))
    handler.send_json(200, stores.save_heads_up(store_id, parse_json(handler).get("message")))


def submit_report(handler, *, submission=None, resolve_store=None):
    if urlparse(handler.path).path != "/api/reports":
        handler.send_json(404, {"error": "Not found."})
        return
    # Server composition supplies these explicitly. Defaults retain direct route
    # callers without making report handling import the server module.
    resolve_store = is_crew if resolve_store is None else resolve_store
    store_id = resolve_store(handler)
    if not store_id:
        handler.send_json(401, {"error": "Crew sign-in required."})
        return
    if rate_limited(handler):
        handler.send_json(429, {"error": "Too many submissions. Try again later."})
        return
    try:
        fields = parse_json(handler)
        if submission is None:
            submission = ReportSubmission(
                ensure_allowed=reporting.ensure_submission_allowed,
                quality_gate=reporting.validate_report, enqueue=reporting.queue_report,
            )
        _, created_at = submission.submit(store_id, fields)
        handler.send_json(202, {"date": created_at.isoformat(), "status": "pending"})
    except ReportRejected as error:
        handler.send_json(422, {"error": error.reason})
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
    except RuntimeError as error:
        handler.send_json(503, {"error": str(error)})
    except (json.JSONDecodeError, UnicodeError):
        handler.send_json(400, {"error": "The report format was invalid."})
