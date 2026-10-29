"""HTTP and test-safety regressions found during the origin review."""

import hashlib
import http.client
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

import psycopg
import pytest

import reporting
import routes
import security
import server
from database import db_connection


@pytest.fixture
def client(isolated_database):
    errors = []
    class TestHTTPServer(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            errors.append(repr(sys.exc_info()[1]))

    httpd = TestHTTPServer(("127.0.0.1", 0), server.ShiftlyHandler)
    thread = Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()

    def request(method, path, *, cookie=None, payload=None, raw=None, headers=None):
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        if cookie:
            request_headers["Cookie"] = cookie
        body = raw if raw is not None else json.dumps(payload) if payload is not None else None
        connection = http.client.HTTPConnection(*httpd.server_address, timeout=5)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    try:
        yield request
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not errors, f"Unhandled HTTP errors: {errors}"


@pytest.fixture
def manager_session(client, monkeypatch):
    from tests.account_fixtures import seed_workspace
    fixture=seed_workspace(store_code='test-store',manager_name='test-manager',
                           manager_password='test-manager-password',crew_password='test-crew-password')
    return fixture['manager_cookie'],fixture['user_id'],fixture['store_id']


@pytest.mark.parametrize("raw", ["{", "", "[]", '"text"', "null", "x" * 10001, b"\xff", '{"storeCode":{}}'])
def test_malformed_login_returns_400(client, raw):
    status, _, body = client("POST", "/api/auth/login", raw=raw)
    assert status == 400 and "error" in json.loads(body)


@pytest.mark.parametrize("length", ["invalid", "-1", "10001"])
def test_invalid_login_length_returns_400(client, length):
    status, _, body = client("POST", "/api/auth/login", raw="{}", headers={"Content-Length": length})
    assert status == 400 and "error" in json.loads(body)


def test_invalid_login_role_is_rejected_before_store_lookup(client, monkeypatch):
    import routes
    def unexpected_lookup(*args):
        pytest.fail("Invalid roles must be rejected before querying stores.")
    monkeypatch.setattr(routes, "store_for_code", unexpected_lookup)
    status, _, body = client("POST", "/api/auth/login", payload={"storeCode": "missing", "role": "owner", "password": "password"})
    assert (status, json.loads(body)) == (400, {"error": "Username must be text."})


@pytest.mark.parametrize("error_type", [psycopg.OperationalError, RuntimeError])
def test_database_failure_returns_degraded_health(client, monkeypatch, error_type):
    def unavailable():
        raise error_type("simulated failure")
    monkeypatch.setattr(server, "db_connection", unavailable)
    status, _, body = client("GET", "/api/health")
    health = json.loads(body)
    assert status == 503
    assert health["status"] == "degraded"
    assert health["databaseConfigured"] is False


def test_healthy_database_returns_200(client):
    status, _, body = client("GET", "/api/health")
    assert status == 200
    assert json.loads(body)["databaseConfigured"] is True


@pytest.mark.parametrize("stale_crew_cookie", [False, True])
def test_manager_report_cannot_be_redirected_by_payload(client, manager_session, monkeypatch, stale_crew_cookie):
    cookie,uid,sid=manager_session
    if stale_crew_cookie:
        cookie+='; shiftly_crew_session=expired-crew'
        assert client('GET','/crew.html',cookie=cookie)[0]==302
        assert client('POST','/api/reports',cookie=cookie,payload={})[0]==401
        return
    monkeypatch.setattr(server,'validate_report',lambda report:{'status':'accepted'})
    assert client('GET','/crew.html',cookie=cookie)[0]==200
    response=client('POST','/api/reports',cookie=cookie,payload={'employee':'Manager','shift':'closing','notes':'Restocked the freezer.','storeId':sid+999})
    assert response[0]==202
    with db_connection() as c:
        assert c.execute('SELECT store_id,actor_user_id FROM reports').fetchall()==[(sid,uid)]


@pytest.mark.parametrize("revocation", ["expired", "inactive_manager", "inactive_store", "missing_membership"])
def test_invalid_manager_cannot_use_employee_access(client, manager_session, revocation):
    cookie, manager_id, store_id = manager_session
    statements = {
        "expired": ("UPDATE account_sessions SET expires_at = NOW() - INTERVAL '1 second' WHERE user_id = %s", manager_id),
        "inactive_manager": ("UPDATE account_users SET state = 'suspended' WHERE id = %s", manager_id),
        "inactive_store": ("UPDATE stores SET active = false WHERE id = %s", store_id),
        "missing_membership": ("DELETE FROM account_store_memberships WHERE user_id = %s", manager_id),
    }
    query, value = statements[revocation]
    with db_connection() as connection:
        connection.execute(query, (value,))
    assert client("GET", "/crew.html", cookie=cookie)[0] == 302
    assert client("POST", "/api/reports", cookie=cookie, payload={})[0] == 401


def test_anonymous_user_cannot_submit_reports(client):
    assert client("GET", "/crew.html")[0] == 302
    assert client("POST", "/api/reports", payload={})[0] == 401


def test_duplicate_http_submission_keeps_normal_client_error(client, manager_session, monkeypatch):
    cookie, _, _ = manager_session
    monkeypatch.setattr(server, "validate_report", lambda report: {"status": "accepted"})
    # Bypass cooldown to exercise the database duplicate path used by racing requests.
    monkeypatch.setattr(server, "ensure_submission_allowed", lambda *args: None)
    payload = {"employee": "Manager", "shift": "closing", "notes": "Restocked the freezer."}
    assert client("POST", "/api/reports", cookie=cookie, payload=payload)[0] == 202
    status, _, body = client("POST", "/api/reports", cookie=cookie, payload=payload)
    assert (status, json.loads(body)) == (400, {"error": "This report matches a previous submission and was not sent again."})


def test_weekly_overview_deduplicates_cached_generation(manager_session, monkeypatch):
    _, _, store_id = manager_session
    reporting.queue_report("Manager", "closing", "Restocked the freezer.", store_id)
    calls = []
    started = Event()
    release = Event()

    def fake_call(report, system_prompt):
        calls.append(report)
        started.set()
        assert release.wait(timeout=5)
        return {"summary": "Restock complete.", "wins": [], "risks": [], "follow_up": "None."}

    monkeypatch.setattr(reporting, "call_openai", fake_call)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(reporting.weekly_overview, store_id)
        try:
            assert started.wait(timeout=5)
            second = executor.submit(reporting.weekly_overview, store_id)
            with pytest.raises(reporting.WeeklyOverviewBusy):
                second.result(timeout=2)
        finally:
            release.set()
        result = first.result(timeout=5)

    assert len(calls) == 1
    assert reporting.weekly_overview(store_id) == result
    assert len(calls) == 1


def test_weekly_pending_response_and_coverage_reach_the_manager(client, manager_session, monkeypatch):
    cookie, _, store_id = manager_session
    reporting.queue_report("Manager", "closing", "Restocked the freezer.", store_id)
    monkeypatch.setattr(reporting, "call_openai", lambda *args: {"summary": "Restocked.", "wins": [], "risks": [], "follow_up": ""})
    with db_connection() as holder:
        holder.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (f"shiftly:weekly:{store_id}",))
        status, _, body = client("GET", "/api/weekly-overview", cookie=cookie)
        assert status == 202
        assert json.loads(body) == {"status": "pending", "retryAfter": 3}
    status, _, body = client("GET", "/api/weekly-overview", cookie=cookie)
    assert status == 200
    result = json.loads(body)
    assert result["includedReportCount"] == result["reportCount"] == 1
    assert result["truncated"] is False


def test_weekly_overview_rejects_anonymous_and_crew_access(client, manager_session):
    _, _, store_id = manager_session
    with db_connection() as connection:
        connection.execute("INSERT INTO crew_sessions (token_hash, store_id, expires_at) VALUES (%s, %s, NOW() + INTERVAL '1 hour')", (hashlib.sha256(b"test-crew").hexdigest(), store_id))
    assert client("GET", "/api/weekly-overview")[0] == 401
    assert client("GET", "/api/weekly-overview", cookie="shiftly_crew_session=test-crew")[0] == 401


@pytest.mark.parametrize("role", ["crew", "manager"])
def test_concurrent_logins_cannot_exceed_remaining_failure_budget(manager_session, monkeypatch, role):
    from backend.shiftly.identity.accounts import AccountsService
    from backend.shiftly.identity import IdentityError
    from database import db_connection
    handler=SimpleNamespace(client_address=('127.0.0.1',4173))
    budget='named-sign-in'
    for _ in range(9): security.record_login_failure(handler,budget)
    entered,release=Event(),Event()
    def slow_hash(*args):
        entered.set(); assert release.wait(timeout=5); return 'incorrect-hash'
    service=AccountsService(db_connection,admission=security.admission_control(),password_hasher=slow_hash)
    def login():
        try:
            service.login(None,'test-manager-crew' if role=='crew' else 'test-manager','incorrect-password',client_key='127.0.0.1')
        except IdentityError as error: return error.code
    with ThreadPoolExecutor(max_workers=12) as executor:
        last=executor.submit(login)
        try:
            assert entered.wait(timeout=5)
            rejected=[executor.submit(login) for _ in range(11)]
            assert [future.result(timeout=2) for future in rejected]==['limited']*11
        finally:release.set()
        assert last.result(timeout=5)=='unauthenticated'
    assert login()=='limited'
    assert not security.LOGIN_IN_FLIGHT
    assert len(security.LOGIN_FAILURES[security._login_key(handler,budget)])==10


def test_successful_login_releases_reservation_without_using_failure_budget(client, manager_session):
    handler = SimpleNamespace(client_address=("127.0.0.1", 4173))
    for _ in range(9):
        security.record_login_failure(handler, "named-sign-in")
    for _ in range(2):
        status, _, _ = client("POST", "/api/auth/login", payload={"username": "test-manager-crew", "password": "test-crew-password"})
        assert status == 200
    assert not security.LOGIN_IN_FLIGHT
    assert len(security.LOGIN_FAILURES[security._login_key(handler, "named-sign-in")]) == 9


def test_tests_refuse_application_database_when_test_url_is_absent():
    environment = {**os.environ, "DATABASE_URL": "postgresql://unused:unused@127.0.0.1:1/do_not_connect"}
    environment.pop("TEST_DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_baseline.py::test_db_connection_uses_database_url"],
        cwd=Path(__file__).resolve().parents[1], env=environment, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode != 0
    assert "Set TEST_DATABASE_URL to a disposable PostgreSQL database." in result.stdout
    assert "connection refused" not in result.stdout.casefold()


def test_startup_database_failure_has_clear_error_instead_of_name_error():
    environment = {**os.environ, "DATABASE_URL": "postgresql://unused:unused@127.0.0.1:1/do_not_connect?connect_timeout=1"}
    result = subprocess.run(
        [sys.executable, "server.py"], cwd=Path(__file__).resolve().parents[1],
        env=environment, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "Could not connect to Postgres." in result.stderr
    assert "NameError" not in result.stderr
