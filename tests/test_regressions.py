"""HTTP and test-safety regressions found during the origin review."""

import hashlib
import http.client
import json
import os
import subprocess
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import psycopg
import pytest

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
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "test-admin-key")
    status, headers, _ = client("POST", "/api/auth/signup", payload={
        "storeName": "Test Store", "storeCode": "test-store",
        "crewPassword": "test-crew-password", "managerUsername": "test-manager",
        "managerPassword": "test-manager-password", "confirmPassword": "test-manager-password",
        "adminKey": "test-admin-key",
    })
    assert status == 201
    cookie = headers["Set-Cookie"].split(";")[0]
    with db_connection() as connection:
        manager_id, store_id = connection.execute("SELECT manager_user_id, store_id FROM manager_sessions").fetchone()
    return cookie, manager_id, store_id


@pytest.mark.parametrize("raw", ["{", "", "[]", '"text"', "null", "x" * 10001, b"\xff", '{"storeCode":{}}'])
def test_malformed_login_returns_400(client, raw):
    status, _, body = client("POST", "/api/auth/login", raw=raw)
    assert (status, json.loads(body)) == (400, {"error": "Invalid login request."})


@pytest.mark.parametrize("length", ["invalid", "-1", "10001"])
def test_invalid_login_length_returns_400(client, length):
    status, _, body = client("POST", "/api/auth/login", raw="{}", headers={"Content-Length": length})
    assert (status, json.loads(body)) == (400, {"error": "Invalid login request."})


def test_invalid_login_role_is_rejected_before_store_lookup(client, monkeypatch):
    import routes
    def unexpected_lookup(*args):
        pytest.fail("Invalid roles must be rejected before querying stores.")
    monkeypatch.setattr(routes, "store_for_code", unexpected_lookup)
    status, _, body = client("POST", "/api/auth/login", payload={"storeCode": "missing", "role": "owner", "password": "password"})
    assert (status, json.loads(body)) == (400, {"error": "Invalid sign-in role."})


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
def test_manager_can_open_employee_page_and_submit_to_selected_store(client, manager_session, monkeypatch, stale_crew_cookie):
    cookie, manager_id, original_store = manager_session
    with db_connection() as connection:
        selected_store = connection.execute(
            "INSERT INTO stores (name, access_code_hash) VALUES (%s, %s) RETURNING id",
            ("Selected store", hashlib.sha256(b"second-store").hexdigest()),
        ).fetchone()[0]
        connection.execute("INSERT INTO store_memberships (manager_user_id, store_id) VALUES (%s, %s)", (manager_id, selected_store))
        connection.execute("UPDATE manager_sessions SET store_id = %s WHERE manager_user_id = %s", (selected_store, manager_id))
        if stale_crew_cookie:
            connection.execute(
                "INSERT INTO crew_sessions (token_hash, store_id, expires_at) VALUES (%s, %s, NOW() - INTERVAL '1 second')",
                (hashlib.sha256(b"expired-crew").hexdigest(), original_store),
            )
            cookie += "; shiftly_crew_session=expired-crew"
    monkeypatch.setattr(server, "validate_report", lambda report: {"status": "accepted"})
    assert client("GET", "/crew.html", cookie=cookie)[0] == 200
    status, _, body = client("POST", "/api/reports", cookie=cookie, payload={
        "employee": "Test Manager", "shift": "closing", "notes": "Restocked the freezer.", "storeId": original_store,
    })
    assert status == 202
    assert json.loads(body)["status"] == "pending"
    with db_connection() as connection:
        assert connection.execute("SELECT store_id FROM reports").fetchall() == [(selected_store,)]


@pytest.mark.parametrize("revocation", ["expired", "inactive_manager", "inactive_store", "missing_membership"])
def test_invalid_manager_cannot_use_employee_access(client, manager_session, revocation):
    cookie, manager_id, store_id = manager_session
    statements = {
        "expired": ("UPDATE manager_sessions SET expires_at = NOW() - INTERVAL '1 second' WHERE manager_user_id = %s", manager_id),
        "inactive_manager": ("UPDATE manager_users SET active = false WHERE id = %s", manager_id),
        "inactive_store": ("UPDATE stores SET active = false WHERE id = %s", store_id),
        "missing_membership": ("DELETE FROM store_memberships WHERE manager_user_id = %s", manager_id),
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
