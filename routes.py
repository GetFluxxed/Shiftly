import hashlib
import hmac
import json
import secrets
from urllib.parse import urlparse

import psycopg

from auth import is_manager, session_store_id
from database import db_connection
from security import clean, finish_login_attempt, hash_store_code, parse_json, password_hash, rate_limited, reserve_login_attempt
from store_service import heads_up, manager_username, store_for_code


def _server_module():
    import server
    return server


def login(handler, store_code=None, role=None, password=None):
    if store_code is None or role is None or password is None:
        try:
            payload = parse_json(handler, max_body=10_000)
            raw_store_code = payload.get("storeCode")
            if raw_store_code is not None and not isinstance(raw_store_code, str):
                raise ValueError("Store code must be text.")
            store_code = clean(raw_store_code, 40)
            role = str(payload.get("role", "auto")).strip().casefold()
            password = str(payload.get("password", ""))
        except (ValueError, TypeError, UnicodeError):
            handler.send_json(400, {"error": "Invalid login request."})
            return
    if role not in {"auto", "crew", "manager"}:
        handler.send_json(400, {"error": "Invalid sign-in role."})
        return
    if not reserve_login_attempt(handler, store_code):
        handler.send_json(429, {"error": "Too many failed sign-in attempts. Try again later."})
        return
    authenticated = False
    try:
        authenticated = _login_reserved(handler, store_code, role, password)
    finally:
        finish_login_attempt(handler, store_code, failed=not authenticated)


def _login_reserved(handler, store_code, role, password):
    server = _server_module()
    store = store_for_code(store_code)
    if not store or not password:
        handler.send_json(401, {"error": "Incorrect store code or password."})
        return
    store_id, store_name = store
    if role == "auto":
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT m.password_salt, m.password_hash
                    FROM manager_users m
                    JOIN store_memberships sm ON sm.manager_user_id = m.id
                    WHERE sm.store_id = %s AND m.active
                    """,
                    (store_id,),
                )
                manager_credentials = cursor.fetchall()
        if any(
            hmac.compare_digest(candidate_hash, password_hash(password, salt))
            for salt, candidate_hash in manager_credentials
        ):
            role = "manager"
        else:
            role = "crew"
    if role == "crew":
        candidate_hash = password_hash(password, f"shiftly-crew:{hash_store_code(store_code)}")
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM stores WHERE id = %s AND crew_password_hash = %s AND active", (store_id, candidate_hash))
                authenticated = cursor.fetchone() is not None
        if not authenticated:
            handler.send_json(401, {"error": "Incorrect store code or password."})
            return
        token = secrets.token_urlsafe(32)
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO crew_sessions (token_hash, store_id, expires_at) VALUES (%s, %s, NOW() + (%s * INTERVAL '1 second'))",
                    (hashlib.sha256(token.encode()).hexdigest(), store_id, server.SESSION_TTL),
                )
            connection.commit()
        cookie_name = "shiftly_crew_session"
        response = {"authenticated": True, "role": "crew", "storeName": store_name}
    elif role == "manager":
        password_candidates = []
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT m.id, m.password_salt, m.password_hash
                    FROM manager_users m
                    JOIN store_memberships sm ON sm.manager_user_id = m.id
                    WHERE sm.store_id = %s AND m.active
                    """,
                    (store_id,),
                )
                password_candidates = cursor.fetchall()
        manager = next(
            (candidate for candidate in password_candidates if hmac.compare_digest(candidate[2], password_hash(password, candidate[1]))),
            None,
        )
        if not manager:
            handler.send_json(401, {"error": "Incorrect store code or password."})
            return
        token = secrets.token_urlsafe(32)
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO manager_sessions (token_hash, manager_user_id, store_id, expires_at) VALUES (%s, %s, %s, NOW() + (%s * INTERVAL '1 second'))",
                    (hashlib.sha256(token.encode()).hexdigest(), manager[0], store_id, server.SESSION_TTL),
                )
                cursor.execute("UPDATE manager_users SET last_sign_in_at = NOW() WHERE id = %s", (manager[0],))
            connection.commit()
        cookie_name = "shiftly_manager_session"
        response = {"authenticated": True, "role": "manager", "managerName": manager_username(manager[0]), "storeName": store_name}
    else:
        handler.send_json(400, {"error": "Invalid sign-in role."})
        return
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    secure = "; Secure" if server.SECURE_COOKIES else ""
    handler.send_header("Set-Cookie", f"{cookie_name}={token}; Path=/; HttpOnly; SameSite=Strict{secure}; Max-Age={server.SESSION_TTL}")
    handler.end_headers()
    handler.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    return True


def signup(handler):
    server = _server_module()
    if not server.ADMIN_SIGNUP_KEY:
        handler.send_json(503, {"error": "Workspace creation is not configured."})
        return
    if server.signup_rate_limited(handler):
        handler.send_json(429, {"error": "Too many sign-up attempts. Try again later."})
        return
    server.record_signup_attempt(handler)
    try:
        payload = parse_json(handler)
        store_name = clean(payload.get("storeName"), 120)
        store_code = clean(payload.get("storeCode"), 40)
        crew_password = str(payload.get("crewPassword", ""))
        manager_name = clean(payload.get("managerUsername"), 80)
        manager_password = str(payload.get("managerPassword", ""))
        confirm_password = str(payload.get("confirmPassword", ""))
        admin_key = str(payload.get("adminKey", ""))
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
        return
    if not hmac.compare_digest(admin_key, server.ADMIN_SIGNUP_KEY):
        handler.send_json(403, {"error": "The admin key is incorrect."})
        return
    if not store_name or not store_code or not manager_name:
        handler.send_json(400, {"error": "Store name, store code, and manager name are required."})
        return
    if len(store_code) < 2 or len(crew_password) < 8:
        handler.send_json(400, {"error": "Store code must be at least 2 characters and the crew password at least 8 characters."})
        return
    if len(manager_name) < 2 or len(manager_password) < 8:
        handler.send_json(400, {"error": "Manager name must be at least 2 characters and the manager password at least 8 characters."})
        return
    if manager_password != confirm_password:
        handler.send_json(400, {"error": "Manager passwords do not match."})
        return
    code_hash = hash_store_code(store_code)
    crew_hash = password_hash(crew_password, f"shiftly-crew:{code_hash}")
    manager_salt = secrets.token_urlsafe(24)
    manager_hash = password_hash(manager_password, manager_salt)
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO stores (name, access_code_hash, crew_password_hash) VALUES (%s, %s, %s) RETURNING id",
                    (store_name, code_hash, crew_hash),
                )
                store_id = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO manager_users (username, email, password_salt, password_hash) VALUES (%s, NULL, %s, %s) RETURNING id",
                    (manager_name, manager_salt, manager_hash),
                )
                manager_id = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO store_memberships (manager_user_id, store_id, role) VALUES (%s, %s, 'manager')",
                    (manager_id, store_id),
                )
            connection.commit()
    except psycopg.errors.UniqueViolation:
        handler.send_json(409, {"error": "That store code or manager name is already in use."})
        return
    token = secrets.token_urlsafe(32)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO manager_sessions (token_hash, manager_user_id, store_id, expires_at) VALUES (%s, %s, %s, NOW() + (%s * INTERVAL '1 second'))",
                (hashlib.sha256(token.encode()).hexdigest(), manager_id, store_id, server.SESSION_TTL),
            )
            cursor.execute("UPDATE manager_users SET last_sign_in_at = NOW() WHERE id = %s", (manager_id,))
        connection.commit()
    secure = "; Secure" if server.SECURE_COOKIES else ""
    handler.send_response(201)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Set-Cookie", f"shiftly_manager_session={token}; Path=/; HttpOnly; SameSite=Strict{secure}; Max-Age={server.SESSION_TTL}")
    handler.end_headers()
    handler.wfile.write(json.dumps({"authenticated": True, "role": "manager", "managerName": manager_name, "storeName": store_name}, ensure_ascii=False).encode("utf-8"))


def add_manager(handler):
    server = _server_module()
    if not server.ADMIN_SIGNUP_KEY:
        handler.send_json(503, {"error": "Manager creation is not configured."})
        return
    if server.signup_rate_limited(handler):
        handler.send_json(429, {"error": "Too many account creation attempts. Try again later."})
        return
    server.record_signup_attempt(handler)
    try:
        payload = parse_json(handler)
        admin_key = str(payload.get("adminKey", ""))
        store_code = clean(payload.get("storeCode"), 40)
        manager_name = clean(payload.get("managerUsername"), 80)
        manager_password = str(payload.get("managerPassword", ""))
        confirm_password = str(payload.get("confirmPassword", ""))
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
        return
    if not hmac.compare_digest(admin_key, server.ADMIN_SIGNUP_KEY):
        handler.send_json(403, {"error": "The admin key is incorrect."})
        return
    if not store_code or not manager_name:
        handler.send_json(400, {"error": "Store code and manager name are required."})
        return
    if len(manager_name) < 2 or len(manager_password) < 8:
        handler.send_json(400, {"error": "Manager name must be at least 2 characters and the manager password at least 8 characters."})
        return
    if manager_password != confirm_password:
        handler.send_json(400, {"error": "Manager passwords do not match."})
        return
    store = store_for_code(store_code)
    if not store:
        handler.send_json(404, {"error": "That store could not be found."})
        return
    store_id, store_name = store
    manager_salt = secrets.token_urlsafe(24)
    manager_hash = password_hash(manager_password, manager_salt)
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO manager_users (username, email, password_salt, password_hash) VALUES (%s, NULL, %s, %s) RETURNING id",
                    (manager_name, manager_salt, manager_hash),
                )
                manager_id = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO store_memberships (manager_user_id, store_id, role) VALUES (%s, %s, 'manager')",
                    (manager_id, store_id),
                )
            connection.commit()
    except psycopg.errors.UniqueViolation:
        handler.send_json(409, {"error": "That manager name is already in use."})
        return
    token = secrets.token_urlsafe(32)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO manager_sessions (token_hash, manager_user_id, store_id, expires_at) VALUES (%s, %s, %s, NOW() + (%s * INTERVAL '1 second'))",
                (hashlib.sha256(token.encode()).hexdigest(), manager_id, store_id, server.SESSION_TTL),
            )
            cursor.execute("UPDATE manager_users SET last_sign_in_at = NOW() WHERE id = %s", (manager_id,))
        connection.commit()
    secure = "; Secure" if server.SECURE_COOKIES else ""
    handler.send_response(201)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Set-Cookie", f"shiftly_manager_session={token}; Path=/; HttpOnly; SameSite=Strict{secure}; Max-Age={server.SESSION_TTL}")
    handler.end_headers()
    handler.wfile.write(json.dumps({"authenticated": True, "role": "manager", "managerName": manager_name, "storeName": store_name}, ensure_ascii=False).encode("utf-8"))


def save_heads_up(handler):
    manager_id = is_manager(handler)
    store_id = session_store_id(handler, manager_id)
    if not store_id:
        handler.send_json(401, {"error": "Manager sign-in required."})
        return
    message = clean(parse_json(handler).get("message"), 1000)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM store_heads_up WHERE store_id = %s", (store_id,))
            cursor.execute("INSERT INTO store_heads_up (store_id, message, updated_at) VALUES (%s, %s, NOW())", (store_id, message))
        connection.commit()
    handler.send_json(200, heads_up(store_id))


def submit_report(handler):
    if urlparse(handler.path).path != "/api/reports":
        handler.send_json(404, {"error": "Not found."})
        return
    server = _server_module()
    store_id = server.is_crew(handler)
    if not store_id:
        handler.send_json(401, {"error": "Crew sign-in required."})
        return
    if rate_limited(handler):
        handler.send_json(429, {"error": "Too many submissions. Try again later."})
        return
    try:
        fields = parse_json(handler)
        employee = clean(fields.get("employee"), 80)
        shift = clean(fields.get("shift"), 20)
        notes = clean(fields.get("notes"), 2000)
        if not employee or not notes:
            raise ValueError("Enter your name and meaningful shift notes.")
        if shift not in {"opening", "midday", "closing", "other"}:
            raise ValueError("Choose a valid shift.")
        report = {"employee": employee, "shift": shift, "notes": notes}
        server.ensure_submission_allowed(store_id, employee, notes)
        quality = server.validate_report(report)
        if quality.get("status") != "accepted":
            handler.send_json(422, {"error": quality.get("reason") or "Please add meaningful shift details and try again."})
            return
        _, created_at = server.queue_report(employee, shift, notes, store_id)
        handler.send_json(202, {"date": created_at.isoformat(), "status": "pending"})
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
    except RuntimeError as error:
        handler.send_json(503, {"error": str(error)})
    except (json.JSONDecodeError, UnicodeError):
        handler.send_json(400, {"error": "The report format was invalid."})
