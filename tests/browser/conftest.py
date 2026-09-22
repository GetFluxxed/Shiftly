import hashlib
import http.client
import json
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Thread

import psycopg
import pytest
from http.server import ThreadingHTTPServer
import uvicorn

from backend.shiftly.app import create_app
from config import Settings

import reporting
import server
from database import db_connection


@dataclass
class BrowserResponse:
    status: int
    headers: list[tuple[str, str]]
    body: bytes

    def json(self):
        return json.loads(self.body)

    def cookie(self, name):
        prefix = f"{name}="
        for header_name, value in self.headers:
            if header_name.lower() == "set-cookie" and value.startswith(prefix):
                return value.split(";", 1)[0]
        return ""


class BrowserApi:
    def __init__(self, base_url):
        self.host, self.port = base_url.removeprefix("http://").split(":")

    def request(self, method, path, *, payload=None, cookie=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        connection = http.client.HTTPConnection(self.host, int(self.port), timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return BrowserResponse(response.status, response.getheaders(), response.read())
        finally:
            connection.close()


@pytest.fixture(params=["legacy", "fastapi"], ids=["legacy", "fastapi"])
def browser_app(isolated_database, monkeypatch, request):
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "browser-admin-key")

    def fake_openai(report, system_prompt=None):
        if report["shift"] == "weekly overview":
            return {
                "summary": "The weekly team summary is ready.",
                "wins": ["The team completed the reported work."],
                "risks": [],
                "follow_up": "Review the next handoff.",
            }
        return {
            "status": "accepted",
            "reason": "",
            "summary": "Report accepted.",
            "wins": ["The report was received."],
            "risks": [],
            "follow_up": "Review the next handoff.",
        }

    monkeypatch.setattr(reporting, "call_openai", fake_openai)
    monkeypatch.setattr(server, "call_openai", fake_openai)
    monkeypatch.setattr(server, "validate_report", lambda report: {"status": "accepted"})

    if request.param == "legacy":
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.ShiftlyHandler)
        thread = Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            yield base_url
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
        return

    def provider(report, system_prompt=None):
        if report["shift"] == "weekly overview":
            return {
                "summary": "The weekly team summary is ready.",
                "wins": ["The team completed the reported work."],
                "risks": [],
                "follow_up": "Review the next handoff.",
            }
        return {
            "status": "accepted",
            "reason": "",
            "summary": "Report accepted.",
            "wins": ["The report was received."],
            "risks": [],
            "follow_up": "Review the next handoff.",
        }

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(
        settings=Settings(
            database_url=os.environ["DATABASE_URL"],
            admin_signup_key="browser-admin-key",
            openai_api_key="test-key",
            secure_cookies=False,
        ),
        connection_factory=lambda: psycopg.connect(os.environ["DATABASE_URL"]),
        worker_status_provider=lambda: {"status": "degraded", "state": "not_started"},
        provider=provider,
    )
    uvicorn_server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if uvicorn_server.started:
            break
        import time
        time.sleep(0.1)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        uvicorn_server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def browser_workspace(browser_app):
    api = BrowserApi(browser_app)
    signup = api.request(
        "POST",
        "/api/auth/signup",
        payload={
            "adminKey": "browser-admin-key",
            "storeName": "Browser Store",
            "storeCode": "browser-store",
            "crewPassword": "crew-password-123",
            "managerUsername": "browser-manager",
            "managerPassword": "manager-password-123",
            "confirmPassword": "manager-password-123",
        },
    )
    assert signup.status == 201, signup.body
    with db_connection() as connection:
        store_id = connection.execute(
            "SELECT id FROM stores WHERE access_code_hash = %s",
            (hashlib.sha256(b"browser-store").hexdigest(),),
        ).fetchone()[0]
    return {
        "base_url": browser_app,
        "store_id": store_id,
        "store_code": "browser-store",
        "crew_password": "crew-password-123",
        "manager_password": "manager-password-123",
    }


@pytest.fixture
def seed_report():
    def add(store_id, employee, notes, *, age_seconds=0):
        report_id = uuid.uuid4()
        created_at = datetime.now(timezone.utc)
        if age_seconds:
            from datetime import timedelta
            created_at -= timedelta(seconds=age_seconds)
        with db_connection() as connection:
            connection.execute(
                """
                INSERT INTO reports
                    (id, store_id, employee, shift, notes, report_hash, created_at)
                VALUES (%s, %s, %s, 'closing', %s, %s, %s)
                """,
                (
                    report_id,
                    store_id,
                    employee,
                    notes,
                    hashlib.sha256(str(report_id).encode()).hexdigest(),
                    created_at,
                ),
            )
            connection.execute("INSERT INTO briefing_jobs (report_id) VALUES (%s)", (report_id,))
        return report_id

    return add


@pytest.fixture
def complete_jobs():
    def complete_all():
        while True:
            job = reporting.claim_job()
            if not job:
                return
            job_id, report_id = job
            report = reporting.job_report(report_id)
            reporting.complete_job(job_id, report, reporting.call_openai(report))

    return complete_all


@pytest.fixture
def named_workspace(browser_app):
    """Synthetic business and people; both HTTP transports use identical policy."""
    from backend.shiftly.identity.accounts import AccountsService
    from backend.shiftly.identity.primitives import hash_store_code, password_hash

    password = 'named-password-123'
    salt = 'browser-named-salt'
    digest = password_hash(password, salt)
    stores, users = [], {}
    with db_connection() as connection:
        business = connection.execute("INSERT INTO businesses(name) VALUES ('Browser Accounts Business') RETURNING id").fetchone()[0]
        for name, code in [('Market Street', 'market-store'), ('Harbor', 'harbor-store')]:
            store = connection.execute(
                """INSERT INTO stores(name,access_code_hash,crew_password_hash,business_id,accounts_enabled)
                   VALUES (%s,%s,%s,%s,TRUE) RETURNING id""",
                (name, hash_store_code(code), password_hash('shared-password-123', f'shiftly-crew:{hash_store_code(code)}'), business),
            ).fetchone()[0]
            stores.append({'id': store, 'name': name, 'code': code, 'business': business})
        for key, role, grants in [
            ('owner', 'manager', []), ('manager', 'manager', ['memberships.manage']),
            ('crew', 'crew', []), ('viewer', 'crew', ['inventory.view']),
            ('admin', 'admin', ['inventory.view']),
        ]:
            user = connection.execute(
                """INSERT INTO account_users(username,display_name,password_salt,password_hash)
                   VALUES (%s,%s,%s,%s) RETURNING id""",
                (f'account-{key}', f'Account {key.title()}', salt, digest),
            ).fetchone()[0]
            users[key] = user
            connection.execute(
                """INSERT INTO account_store_memberships(user_id,store_id,business_id,role,capabilities)
                   VALUES (%s,%s,%s,%s,%s)""", (user, stores[0]['id'], business, role, grants),
            )
            if key in {'owner', 'admin'}:
                connection.execute(
                    "INSERT INTO business_memberships(user_id,business_id,role,capabilities) VALUES (%s,%s,%s,%s)",
                    (user, business, key, grants),
                )
    return {'base_url': browser_app, 'stores': stores, 'users': users,
            'password': password, 'accounts': AccountsService(db_connection)}
