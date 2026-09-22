"""Legacy HTTP adapters with explicit, replaceable service composition."""

import json
from urllib.parse import urlparse

import psycopg

import reporting
from backend.shiftly.identity import IdentityError, IdentityRepository, IdentityService
from backend.shiftly.reports import ReportRejected, ReportSubmission
from backend.shiftly.stores import StoresRepository, StoresService
from auth import is_manager, session_store_id, request_principal
from config import load_settings
from database import db_connection
from security import admission_control, clean, client_key, cookie_token, named_account_token, parse_json, password_hash, rate_limited
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
    cookie_name = ("shiftly_account_session" if result.role == "account" else
                   "shiftly_manager_session" if result.role == "manager" else "shiftly_crew_session")
    handler.send_header("Set-Cookie", f"{cookie_name}={result.token}; Path=/; HttpOnly; SameSite=Strict{secure}; Max-Age={result.ttl}")
    if result.role == "account":
        for old_cookie in ("shiftly_manager_session", "shiftly_crew_session"):
            handler.send_header("Set-Cookie", f"{old_cookie}=; Path=/; HttpOnly; SameSite=Strict{secure}; Max-Age=0")
    handler.send_header("Cache-Control", "no-store")
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
    try:
        account_token = named_account_token(handler)
        fields = parse_json(handler)
        if account_token:
            _same_origin_account_mutation(handler)
            result = stores.save_heads_up(store_id, fields.get("message"), actor_token=account_token,
                                          accounts=make_identity_service().accounts)
        else:
            result = stores.save_heads_up(store_id, fields.get("message"), legacy_credentials={
                "manager_token": cookie_token(handler, "shiftly_manager_session"),
                "crew_token": cookie_token(handler, "shiftly_crew_session"),
            })
    except IdentityError as error:
        _identity_error(handler, error)
        return
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
        return
    except RuntimeError as error:
        handler.send_json(503, {"error": str(error)})
        return
    handler.send_json(200, result)


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
        account_token = named_account_token(handler)
        if account_token:
            _same_origin_account_mutation(handler)
            principal = request_principal(handler, strict=True)
            if not principal or not principal.named:
                raise IdentityError("unauthenticated", "Named sign-in required.")
            _, created_at = submission.submit(store_id, fields, actor_token=account_token,
                                               accounts=make_identity_service().accounts)
        else:
            credentials = {"manager_token": cookie_token(handler, "shiftly_manager_session"),
                           "crew_token": cookie_token(handler, "shiftly_crew_session")}
            if any(credentials.values()):
                _, created_at = submission.submit(store_id, fields, legacy_credentials=credentials)
            else:
                _, created_at = submission.submit(store_id, fields)
        handler.send_json(202, {"date": created_at.isoformat(), "status": "pending"})
    except IdentityError as error:
        _identity_error(handler, error)
    except ReportRejected as error:
        handler.send_json(422, {"error": error.reason})
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
    except RuntimeError as error:
        handler.send_json(503, {"error": str(error)})
    except (json.JSONDecodeError, UnicodeError):
        handler.send_json(400, {"error": "The report format was invalid."})


ACCOUNT_COOKIES = ('shiftly_account_session', 'shiftly_manager_session', 'shiftly_crew_session')


def _account_json(handler, value, *, clear=False, secure_cookies=False, status=200):
    body = json.dumps(value, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store')
    if clear:
        secure = '; Secure' if secure_cookies else ''
        for name in ACCOUNT_COOKIES:
            handler.send_header('Set-Cookie', f'{name}=; Path=/; HttpOnly; SameSite=Strict{secure}; Max-Age=0')
    handler.end_headers()
    handler.wfile.write(body)


def _same_origin_account_mutation(handler):
    origin = handler.headers.get('Origin')
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme not in {'http', 'https'} or parsed.netloc != handler.headers.get('Host'):
            raise IdentityError('forbidden', 'Cross-origin account changes are not permitted.')
    if handler.headers.get('Sec-Fetch-Site') == 'cross-site':
        raise IdentityError('forbidden', 'Cross-origin account changes are not permitted.')


def account_route(handler, *, method, identity=None, secure_cookies=False):
    """Legacy adapter contract for the named accounts namespace; no policy SQL."""
    path = urlparse(handler.path).path
    if not path.startswith('/api/accounts/'):
        return False
    identity = identity if identity is not None else make_identity_service()
    accounts = identity.accounts
    token = named_account_token(handler)
    try:
        if method == 'POST':
            _same_origin_account_mutation(handler)
        if path == '/api/accounts/status' and method == 'GET':
            principal = identity.resolve_principal(
                account_token=token, manager_token=cookie_token(handler, 'shiftly_manager_session'),
                crew_token=cookie_token(handler, 'shiftly_crew_session'))
            if not principal or not principal.named:
                _account_json(handler, {'authenticated': False, 'reauthenticationRequired': bool(principal)})
            else:
                _account_json(handler, {'authenticated': True, 'actor': principal.actor.as_dict(),
                                        'stores': accounts.authorized_stores(token)})
            return True
        if path == '/api/accounts/team' and method == 'GET':
            principal = request_principal(handler, strict=True)
            if not principal or not principal.named:
                raise IdentityError('unauthenticated', 'Named sign-in required.')
            _account_json(handler, accounts.roster(token))
            return True
        if method != 'POST':
            handler.send_json(404, {'error': 'Not found.'})
            return True
        if path == '/api/accounts/logout':
            accounts.logout(token)
            identity.logout(cookie_token(handler, 'shiftly_manager_session'), cookie_token(handler, 'shiftly_crew_session'))
            _account_json(handler, {'authenticated': False}, clear=True, secure_cookies=secure_cookies)
            return True
        fields = parse_json(handler, max_body=20_000)
        if path == '/api/accounts/login':
            result = accounts.login_payload(fields, client_key=client_key(handler))
            _session_response(handler, result, 200, secure_cookies)
            return True
        if path == '/api/accounts/activate':
            result = accounts.activate_invitation(fields.get('token'), fields.get('password'), client_key=client_key(handler))
            _session_response(handler, result, 200, secure_cookies)
            return True
        if path == '/api/accounts/reset-password':
            result = accounts.reset_password(fields.get('token'), fields.get('password'), client_key=client_key(handler))
            _account_json(handler, result, clear=True, secure_cookies=secure_cookies)
            return True
        principal = request_principal(handler, strict=True)
        if not principal or not principal.named:
            raise IdentityError('unauthenticated', 'Named sign-in required.')
        clear = False
        reason = fields.get('reason', '')
        if path == '/api/accounts/logout-all':
            result = accounts.logout_all(token)
            clear = True
        elif path == '/api/accounts/switch-store':
            result = accounts.switch_store(token, fields.get('storeId'))
            if hasattr(result, 'token'):
                _session_response(handler, result, 200, secure_cookies)
                return True
        elif path == '/api/accounts/invitations':
            result = accounts.invite(token, username=fields.get('username'), display_name=fields.get('displayName', ''),
                                     role=fields.get('role', 'crew'), capabilities=fields.get('capabilities', []),
                                     store_id=fields.get('storeId'), expires_in=fields.get('expiresIn', 86400), reason=reason)
        elif path == '/api/accounts/invitations/reissue':
            result = accounts.reissue_invitation(token, user_id=fields.get('userId'),
                                                  expires_in=fields.get('expiresIn', 86400),
                                                  store_id=fields.get('storeId'), reason=reason)
        elif path == '/api/accounts/memberships':
            result = accounts.set_membership(token, user_id=fields.get('userId'), role=fields.get('role'),
                                              capabilities=fields.get('capabilities', []), active=fields.get('active', True),
                                              store_id=fields.get('storeId'), reason=reason)
        elif path == '/api/accounts/business-memberships':
            result = accounts.set_business_membership(token, user_id=fields.get('userId'), role=fields.get('role'),
                                                      capabilities=fields.get('capabilities', []),
                                                      active=fields.get('active', True), reason=reason)
        elif path == '/api/accounts/transfer-ownership':
            result = accounts.transfer_ownership(token, user_id=fields.get('userId'), reason=reason)
            clear = True
        elif path == '/api/accounts/suspend':
            result = accounts.suspend_user(token, user_id=fields.get('userId'), suspended=fields.get('suspended', True), reason=reason)
        elif path == '/api/accounts/password':
            result = accounts.change_password(token, current_password=fields.get('currentPassword'), new_password=fields.get('newPassword'))
            clear = True
        elif path == '/api/accounts/cutover':
            result = accounts.cutover_store(token, store_id=fields.get('storeId'), reason=reason)
        else:
            handler.send_json(404, {'error': 'Not found.'})
            return True
        _account_json(handler, result, clear=clear, secure_cookies=secure_cookies)
    except IdentityError as error:
        _identity_error(handler, error)
    except (ValueError, TypeError, UnicodeError):
        handler.send_json(400, {'error': 'Invalid account request.'})
    except (psycopg.Error, RuntimeError):
        handler.send_json(503, {'error': 'Account service is temporarily unavailable.'})
    return True
