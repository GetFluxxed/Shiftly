import hashlib
import http.client
import json
import socket
import time
from dataclasses import dataclass
from threading import Thread

import pytest
import uvicorn
from http.server import ThreadingHTTPServer

import reporting
import server
from database import db_connection
from backend.shiftly.app import create_app
from config import Settings


@dataclass
class ApiResponse:
    status: int
    headers: list[tuple[str, str]]
    body: bytes

    def json(self):
        return json.loads(self.body)

    def cookies(self):
        return [
            value.split(";", 1)[0]
            for name, value in self.headers
            if name.lower() == "set-cookie"
        ]


class ApiClient:
    def __init__(self, base_url):
        self.host, self.port = base_url.removeprefix("http://").split(":")

    def request(self, method, path, *, payload=None, raw=None, cookie=None):
        body = raw if raw is not None else (
            json.dumps(payload).encode("utf-8") if payload is not None else None
        )
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        connection = http.client.HTTPConnection(self.host, int(self.port), timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return ApiResponse(response.status, response.getheaders(), response.read())
        finally:
            connection.close()


@pytest.fixture(params=["legacy", "fastapi"])
def app_server(isolated_database, monkeypatch, request):
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "contract-admin-key")
    monkeypatch.setattr(server, "SECURE_COOKIES", False)
    if request.param == "fastapi":
        app = create_app(
            settings=Settings(database_url=isolated_database,
                              admin_signup_key="contract-admin-key", secure_cookies=False),
            connection_factory=db_connection,
            # Late binding lets the same provider-failure tests exercise both servers.
            provider=lambda report, prompt=None: reporting.call_openai(report, prompt),
        )
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            runner = uvicorn.Server(uvicorn.Config(app, log_level="error"))
            thread = Thread(target=runner.run, kwargs={"sockets": [listener]}, daemon=True)
            thread.start()
            try:
                deadline = time.monotonic() + 5
                while not runner.started and thread.is_alive() and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert runner.started, "FastAPI contract server did not start"
                yield f"http://127.0.0.1:{port}"
            finally:
                runner.should_exit = True
                thread.join(timeout=5)
                assert not thread.is_alive(), "FastAPI contract server did not stop"
        return
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


@pytest.fixture(autouse=True)
def deterministic_ai(monkeypatch):
    def fake_openai(report, system_prompt=None):
        if report["shift"] == "weekly overview":
            return {
                "summary": "The team completed the reported shift work.",
                "wins": ["The store remained operational."],
                "risks": [],
                "follow_up": "Review the next handoff.",
            }
        return {
            "status": "accepted",
            "reason": "",
            "summary": "Report accepted.",
            "wins": ["Shift notes were received."],
            "risks": [],
            "follow_up": "Review the next handoff.",
        }

    monkeypatch.setattr(reporting, "call_openai", fake_openai)
    monkeypatch.setattr(server, "call_openai", fake_openai)
    monkeypatch.setattr(server, "validate_report", lambda report: {"status": "accepted"})


def create_workspace(api, *, store_code, manager_name):
    from tests.account_fixtures import seed_workspace
    return seed_workspace(store_code=store_code,manager_name=manager_name)


@pytest.fixture
def api(app_server):
    return ApiClient(app_server)


@pytest.fixture
def workspace(api):
    return create_workspace(api, store_code="contract-store", manager_name="contract-manager")
