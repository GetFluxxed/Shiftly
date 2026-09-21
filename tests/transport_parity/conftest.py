import os
from threading import Thread

import psycopg
import pytest
from fastapi.testclient import TestClient
from http.server import ThreadingHTTPServer

import server
from backend.shiftly.app import create_app
from config import Settings


@pytest.fixture
def transport_clients(isolated_database, monkeypatch):
    dsn = os.environ["DATABASE_URL"]
    worker = {
        "status": "degraded",
        "state": "not_started",
        "running": False,
        "lastPollAgeSeconds": None,
        "lastCompletionAgeSeconds": None,
        "completedJobs": 0,
        "consecutiveErrors": 0,
    }
    settings = Settings(database_url=dsn, openai_api_key="test-key", secure_cookies=False)
    fastapi_app = create_app(
        settings=settings,
        connection_factory=lambda: psycopg.connect(dsn),
        worker_status_provider=lambda: worker,
    )
    fastapi_client = TestClient(fastapi_app)

    monkeypatch.setattr(server, "SECURE_COOKIES", False)
    monkeypatch.setattr(server, "worker_status", lambda: worker)
    legacy_httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.ShiftlyHandler)
    legacy_thread = Thread(
        target=legacy_httpd.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    legacy_thread.start()
    try:
        yield fastapi_client, legacy_httpd
    finally:
        fastapi_client.close()
        legacy_httpd.shutdown()
        legacy_httpd.server_close()
        legacy_thread.join(timeout=5)
