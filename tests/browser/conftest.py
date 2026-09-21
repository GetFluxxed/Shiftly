import hashlib
import http.client
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Thread

import pytest
from http.server import ThreadingHTTPServer

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


@pytest.fixture
def browser_app(isolated_database, monkeypatch):
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
