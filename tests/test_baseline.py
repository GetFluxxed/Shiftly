import hashlib
import io
import json

import psycopg
import pytest

import reporting
import routes
import security
import store_service

import server
from auth import is_manager, session_store_id
from config import load_settings
from database import db_connection


class DummyHandler:
    def __init__(self, payload=None, cookies=None, client_ip="127.0.0.1"):
        self.client_address = (client_ip, 12345)
        self.headers = {}
        self.response = {}
        self.wfile = io.BytesIO()
        self.path = "/api/reports"
        if cookies:
            self.headers["Cookie"] = cookies
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            self.headers["Content-Length"] = str(len(data))
            self.rfile = io.BytesIO(data)
        else:
            self.rfile = io.BytesIO(b"")

    def send_response(self, status):
        self.response["status"] = status

    def send_header(self, name, value):
        self.response.setdefault("headers", {})[name] = value

    def end_headers(self):
        return None

    def send_json(self, status, value):
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.seek(0)
        self.response["body"] = self.wfile.getvalue()

    def log_message(self, *args, **kwargs):
        return None


@pytest.fixture(scope="function")
def reset_db():
    security.REQUESTS.clear()
    security.LOGIN_FAILURES.clear()
    security.SIGNUP_ATTEMPTS.clear()
    server.initialize_database()
    with psycopg.connect(server.DB_URL) as connection:
        with connection.cursor() as cursor:
            for table in [
                "store_heads_up",
                "crew_sessions",
                "manager_sessions",
                "briefings",
                "briefing_jobs",
                "reports",
                "store_memberships",
                "manager_users",
                "stores",
            ]:
                cursor.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
            cursor.execute("DELETE FROM schema_migrations")
        connection.commit()
    server.initialize_database()
    yield


def test_reporting_module_exposes_queue_and_validation_api():
    assert callable(reporting.queue_report)
    assert callable(reporting.claim_job)
    assert callable(reporting.job_report)
    assert callable(reporting.complete_job)
    assert callable(reporting.validate_report)
    assert callable(reporting.worker_loop)


def test_store_service_exposes_store_and_identity_api():
    assert callable(store_service.manager_username)
    assert callable(store_service.store_for_code)
    assert callable(store_service.heads_up)
    assert callable(store_service.manager_accounts)
    assert callable(store_service.is_crew)


def test_security_module_exposes_request_and_password_helpers():
    assert callable(security.clean)
    assert callable(security.parse_json)
    assert callable(security.password_hash)
    assert callable(security.rate_limited)
    assert callable(security.login_rate_limited)


def test_session_token_reads_manager_cookie():
    handler = DummyHandler(cookies="other=value; shiftly_manager_session=manager-token; trailing=value")

    assert security.session_token(handler) == "manager-token"
    assert security.session_token(DummyHandler(cookies="shiftly_crew_session=crew-token")) == ""


def test_hash_store_code_normalizes_case_deterministically():
    assert security.hash_store_code("TestStore123") == security.hash_store_code("teststore123")
    assert len(security.hash_store_code("TestStore123")) == 64


def test_routes_module_exposes_http_handlers():
    assert callable(routes.login)
    assert callable(routes.signup)
    assert callable(routes.add_manager)
    assert callable(routes.save_heads_up)
    assert callable(routes.submit_report)


def test_load_settings_reads_env_and_defaults(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "4242")
    settings = load_settings()
    assert settings.host == "0.0.0.0"
    assert settings.port == 4242
    assert settings.secure_cookies is False


def test_db_connection_uses_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://shiftly:change-me@localhost:55432/shiftly")
    connection = db_connection()
    assert connection is not None
    connection.close()


def test_session_helpers_resolve_manager_store(reset_db, monkeypatch):
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "test-admin-key")
    payload = {
        "storeName": "Aster Creek",
        "storeCode": "Aster1",
        "crewPassword": "crewpass123",
        "managerUsername": "manager1",
        "managerPassword": "managerpass123",
        "confirmPassword": "managerpass123",
        "adminKey": "test-admin-key",
    }
    handler = DummyHandler(payload)
    server.ShiftlyHandler.signup(handler)
    cookie_value = handler.response["headers"]["Set-Cookie"].split("=")[1].split(";")[0]
    manager_cookie = DummyHandler(cookies=f"shiftly_manager_session={cookie_value}")
    manager_id = is_manager(manager_cookie)
    assert manager_id is not None
    assert session_store_id(manager_cookie, manager_id) is not None


def test_signup_creates_store_and_manager_session(reset_db, monkeypatch):
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "test-admin-key")
    payload = {
        "storeName": "Aster Creek",
        "storeCode": "Aster1",
        "crewPassword": "crewpass123",
        "managerUsername": "manager1",
        "managerPassword": "managerpass123",
        "confirmPassword": "managerpass123",
        "adminKey": "test-admin-key",
    }
    handler = DummyHandler(payload)

    server.ShiftlyHandler.signup(handler)

    assert handler.response["status"] == 201
    store = server.store_for_code("Aster1")
    assert store is not None
    store_id, _ = store
    cookie_value = handler.response["headers"]["Set-Cookie"].split("=")[1].split(";")[0]
    manager_cookie = DummyHandler(cookies=f"shiftly_manager_session={cookie_value}")
    manager_id = server.is_manager(manager_cookie)
    assert manager_id is not None
    assert server.session_store_id(manager_cookie, manager_id) == store_id

def test_crew_login_after_signup_uses_store_code_boundary(reset_db, monkeypatch):
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "test-admin-key")
    signup_handler = DummyHandler({
        "storeName": "Aster Creek",
        "storeCode": "Aster1",
        "crewPassword": "crewpass123",
        "managerUsername": "manager1",
        "managerPassword": "managerpass123",
        "confirmPassword": "managerpass123",
        "adminKey": "test-admin-key",
    })
    server.ShiftlyHandler.signup(signup_handler)

    login_handler = DummyHandler({
        "storeCode": "aster1",
        "role": "crew",
        "password": "crewpass123",
    })
    server.ShiftlyHandler.login(login_handler)

    assert login_handler.response["status"] == 200
    assert "shiftly_crew_session" in login_handler.response["headers"]["Set-Cookie"]
    assert json.loads(login_handler.wfile.getvalue())["role"] == "crew"


def test_manager_logout_invalidates_session(reset_db, monkeypatch):
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "test-admin-key")
    signup_handler = DummyHandler({
        "storeName": "Aster Creek",
        "storeCode": "Aster1",
        "crewPassword": "crewpass123",
        "managerUsername": "manager1",
        "managerPassword": "managerpass123",
        "confirmPassword": "managerpass123",
        "adminKey": "test-admin-key",
    })
    server.ShiftlyHandler.signup(signup_handler)
    cookie_value = signup_handler.response["headers"]["Set-Cookie"].split("=")[1].split(";")[0]
    manager_cookie = f"shiftly_manager_session={cookie_value}"

    assert server.is_manager(DummyHandler(cookies=manager_cookie)) is not None

    logout_handler = DummyHandler(cookies=manager_cookie)
    logout_handler.path = "/api/auth/logout"
    server.ShiftlyHandler.do_POST(logout_handler)

    assert logout_handler.response["status"] == 200
    assert server.is_manager(DummyHandler(cookies=manager_cookie)) is None


def test_add_manager_creates_second_manager_session(reset_db, monkeypatch):
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "test-admin-key")
    signup_handler = DummyHandler({
        "storeName": "Aster Creek",
        "storeCode": "Aster1",
        "crewPassword": "crewpass123",
        "managerUsername": "manager1",
        "managerPassword": "managerpass123",
        "confirmPassword": "managerpass123",
        "adminKey": "test-admin-key",
    })
    server.ShiftlyHandler.signup(signup_handler)

    add_handler = DummyHandler({
        "storeCode": "aster1",
        "managerUsername": "manager2",
        "managerPassword": "managerpass456",
        "confirmPassword": "managerpass456",
        "adminKey": "test-admin-key",
    })
    add_handler.path = "/api/auth/add-manager"
    server.ShiftlyHandler.do_POST(add_handler)

    assert add_handler.response["status"] == 201
    assert json.loads(add_handler.wfile.getvalue())["managerName"] == "manager2"

    login_handler = DummyHandler({
        "storeCode": "Aster1",
        "role": "manager",
        "password": "managerpass456",
    })
    server.ShiftlyHandler.login(login_handler)
    assert login_handler.response["status"] == 200
    assert json.loads(login_handler.wfile.getvalue())["managerName"] == "manager2"


def test_reports_listing_requires_manager_and_returns_reports(reset_db, monkeypatch):
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "test-admin-key")
    signup_handler = DummyHandler({
        "storeName": "Aster Creek",
        "storeCode": "Aster1",
        "crewPassword": "crewpass123",
        "managerUsername": "manager1",
        "managerPassword": "managerpass123",
        "confirmPassword": "managerpass123",
        "adminKey": "test-admin-key",
    })
    server.ShiftlyHandler.signup(signup_handler)
    manager_token = signup_handler.response["headers"]["Set-Cookie"].split("=")[1].split(";")[0]
    manager_cookie = f"shiftly_manager_session={manager_token}"
    manager_id = server.is_manager(DummyHandler(cookies=manager_cookie))
    store_id = server.session_store_id(DummyHandler(cookies=manager_cookie), manager_id)
    server.queue_report("Alice", "opening", "Restocked cooler", store_id)
    server.queue_report("Bob", "closing", "Cleaned floors", store_id)

    reports_handler = DummyHandler(cookies=manager_cookie)
    reports_handler.path = "/api/reports"
    server.ShiftlyHandler.do_GET(reports_handler)
    reports = json.loads(reports_handler.response["body"])["reports"]
    assert reports_handler.response["status"] == 200
    assert {report["employee"] for report in reports} == {"Alice", "Bob"}

    anonymous_handler = DummyHandler()
    anonymous_handler.path = "/api/reports"
    server.ShiftlyHandler.do_GET(anonymous_handler)
    assert anonymous_handler.response["status"] == 401


def test_auth_status_reports_current_role(reset_db, monkeypatch):
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "test-admin-key")
    signup_handler = DummyHandler({
        "storeName": "Aster Creek",
        "storeCode": "Aster1",
        "crewPassword": "crewpass123",
        "managerUsername": "manager1",
        "managerPassword": "managerpass123",
        "confirmPassword": "managerpass123",
        "adminKey": "test-admin-key",
    })
    server.ShiftlyHandler.signup(signup_handler)
    manager_token = signup_handler.response["headers"]["Set-Cookie"].split("=")[1].split(";")[0]

    manager_status = DummyHandler(cookies=f"shiftly_manager_session={manager_token}")
    manager_status.path = "/api/auth/status"
    server.ShiftlyHandler.do_GET(manager_status)
    assert json.loads(manager_status.response["body"]) == {
        "authenticated": True,
        "role": "manager",
        "managerName": "manager1",
    }

    crew_login = DummyHandler({"storeCode": "aster1", "role": "crew", "password": "crewpass123"})
    server.ShiftlyHandler.login(crew_login)
    crew_token = crew_login.response["headers"]["Set-Cookie"].split("=")[1].split(";")[0]
    crew_status = DummyHandler(cookies=f"shiftly_crew_session={crew_token}")
    crew_status.path = "/api/auth/status"
    server.ShiftlyHandler.do_GET(crew_status)
    assert json.loads(crew_status.response["body"]) == {
        "authenticated": True,
        "role": "crew",
        "managerName": None,
    }

    anonymous_status = DummyHandler()
    anonymous_status.path = "/api/auth/status"
    server.ShiftlyHandler.do_GET(anonymous_status)
    assert json.loads(anonymous_status.response["body"]) == {
        "authenticated": False,
        "role": None,
        "managerName": None,
    }


def test_heads_up_manager_write_crew_read(reset_db, monkeypatch):
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "test-admin-key")
    signup_handler = DummyHandler({
        "storeName": "Aster Creek",
        "storeCode": "Aster1",
        "crewPassword": "crewpass123",
        "managerUsername": "manager1",
        "managerPassword": "managerpass123",
        "confirmPassword": "managerpass123",
        "adminKey": "test-admin-key",
    })
    server.ShiftlyHandler.signup(signup_handler)
    manager_token = signup_handler.response["headers"]["Set-Cookie"].split("=")[1].split(";")[0]

    crew_login = DummyHandler({"storeCode": "aster1", "role": "crew", "password": "crewpass123"})
    server.ShiftlyHandler.login(crew_login)
    crew_token = crew_login.response["headers"]["Set-Cookie"].split("=")[1].split(";")[0]

    write_handler = DummyHandler(
        {"message": "Store closed early today."},
        cookies=f"shiftly_manager_session={manager_token}",
    )
    write_handler.path = "/api/heads-up"
    server.ShiftlyHandler.do_POST(write_handler)
    assert write_handler.response["status"] == 200
    assert json.loads(write_handler.response["body"])["message"] == "Store closed early today."

    read_handler = DummyHandler(cookies=f"shiftly_crew_session={crew_token}")
    read_handler.path = "/api/heads-up"
    server.ShiftlyHandler.do_GET(read_handler)
    assert read_handler.response["status"] == 200
    assert json.loads(read_handler.response["body"])["message"] == "Store closed early today."


def test_report_submission_queues_job_and_completes(reset_db, monkeypatch):
    code_hash = hashlib.sha256("Aster2".casefold().encode()).hexdigest()
    crew_hash = server.password_hash("crewpass123", f"shiftly-crew:{code_hash}")
    with psycopg.connect(server.DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO stores (name, access_code_hash, crew_password_hash) VALUES (%s, %s, %s) RETURNING id",
                ("Aster Two", code_hash, crew_hash),
            )
            store_id = cursor.fetchone()[0]
            token = "crew-session-token"
            cursor.execute(
                "INSERT INTO crew_sessions (token_hash, store_id, expires_at) VALUES (%s, %s, NOW() + INTERVAL '1 hour')",
                (hashlib.sha256(token.encode()).hexdigest(), store_id),
            )
        connection.commit()

    monkeypatch.setattr(server, "validate_report", lambda report: {"status": "accepted", "reason": "ok"})
    report_payload = {
        "employee": "Nina",
        "shift": "closing",
        "notes": "The rush was busy, but we closed the floor and restocked the cooler before the end of shift.",
    }
    handler = DummyHandler(report_payload, cookies=f"shiftly_crew_session={token}")

    server.ShiftlyHandler.submit_report(handler)

    assert handler.response["status"] == 202
    with psycopg.connect(server.DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM reports")
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT COUNT(*) FROM briefing_jobs WHERE status = 'pending'")
            assert cursor.fetchone()[0] == 1

    job = server.claim_job()
    assert job is not None
    report_id = job[1]
    report = server.job_report(report_id)
    server.complete_job(job[0], report, {
        "status": "accepted",
        "summary": "Strong closeout with restock complete.",
        "wins": ["Restocked the cooler"],
        "risks": [],
        "follow_up": "No follow-up needed.",
    })

    with psycopg.connect(server.DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT status FROM briefing_jobs WHERE report_id = %s", (report_id,))
            assert cursor.fetchone()[0] == "completed"
            cursor.execute("SELECT summary FROM briefings WHERE report_id = %s", (report_id,))
            assert cursor.fetchone()[0] == "Strong closeout with restock complete."


def test_report_submission_rejected_by_quality_gate(reset_db, monkeypatch):
    code_hash = hashlib.sha256("Aster3".casefold().encode()).hexdigest()
    crew_hash = server.password_hash("crewpass123", f"shiftly-crew:{code_hash}")
    with psycopg.connect(server.DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO stores (name, access_code_hash, crew_password_hash) VALUES (%s, %s, %s) RETURNING id",
                ("Aster Three", code_hash, crew_hash),
            )
            store_id = cursor.fetchone()[0]
            token = "crew-session-token-rejected"
            cursor.execute(
                "INSERT INTO crew_sessions (token_hash, store_id, expires_at) VALUES (%s, %s, NOW() + INTERVAL '1 hour')",
                (hashlib.sha256(token.encode()).hexdigest(), store_id),
            )
        connection.commit()

    monkeypatch.setattr(server, "validate_report", lambda report: {"status": "rejected", "reason": "Not enough detail."})
    handler = DummyHandler(
        {"employee": "Nina", "shift": "closing", "notes": "Too brief."},
        cookies=f"shiftly_crew_session={token}",
    )

    server.ShiftlyHandler.submit_report(handler)

    assert handler.response["status"] == 422
    assert json.loads(handler.response["body"])["error"] == "Not enough detail."
    with psycopg.connect(server.DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM reports")
            assert cursor.fetchone()[0] == 0
