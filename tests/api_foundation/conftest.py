import os
from contextlib import contextmanager
from threading import Thread

import psycopg
import pytest
from fastapi.testclient import TestClient
from http.server import ThreadingHTTPServer

import server
from backend.shiftly.app import create_app
from config import Settings


def worker_status(status="degraded", state="not_started"):
    return {
        "status": status,
        "state": state,
        "running": status == "ok",
        "lastPollAgeSeconds": 0.25 if status == "ok" else None,
        "lastCompletionAgeSeconds": None,
        "completedJobs": 0,
        "consecutiveErrors": 0,
    }


@pytest.fixture
def app_settings():
    return Settings(
        database_url="postgresql://unused-for-injected-test",
        openai_api_key="test-key",
        secure_cookies=True,
    )


@pytest.fixture
def fastapi_client(app_settings):
    app = create_app(
        settings=app_settings,
        connection_factory=lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
        worker_status_provider=lambda: worker_status(),
    )
    with TestClient(app) as client:
        yield client
    assert app.state.lifecycle == "stopped"


@pytest.fixture
def database_client(isolated_database, monkeypatch):
    dsn = os.environ["DATABASE_URL"]
    settings = Settings(
        database_url=dsn,
        openai_api_key="test-key",
        secure_cookies=False,
    )
    app = create_app(
        settings=settings,
        connection_factory=lambda: psycopg.connect(dsn),
        worker_status_provider=lambda: worker_status(),
    )
    with TestClient(app) as client:
        yield client


@contextmanager
def legacy_http_server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.ShiftlyHandler)
    thread = Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
