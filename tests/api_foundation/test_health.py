import json
from contextlib import contextmanager
from threading import Thread
from urllib.parse import urlparse
from http.client import HTTPConnection

import pytest
from http.server import ThreadingHTTPServer
from fastapi.testclient import TestClient

import server


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


def test_healthy_database_matches_legacy_stable_health_contract(database_client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(server, "SECURE_COOKIES", False)
    monkeypatch.setattr(server, "worker_status", lambda: worker_status())

    with legacy_http_server() as base_url:
        parsed = urlparse(base_url)
        connection = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        connection.request("GET", "/api/health")
        legacy_response = connection.getresponse()
        legacy_payload = json.loads(legacy_response.read())
        connection.close()

    fastapi_response = database_client.get("/api/health")
    assert fastapi_response.status_code == legacy_response.status
    assert {
        "status",
        "openaiConfigured",
        "databaseConfigured",
        "secureCookies",
    } <= fastapi_response.json().keys()
    for field in ("status", "openaiConfigured", "databaseConfigured", "secureCookies"):
        assert fastapi_response.json()[field] == legacy_payload[field]
    assert fastapi_response.json()["worker"]["status"] == "degraded"


def test_unavailable_database_is_degraded_with_legacy_status_code(fastapi_client):
    response = fastapi_client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["databaseConfigured"] is False
    assert response.json()["worker"]["state"] == "not_started"


@pytest.mark.parametrize(
    ("status", "state", "expected_code"),
    [
        ("degraded", "not_started", 503),
        ("degraded", "stalled", 503),
        ("degraded", "backoff", 503),
        ("ok", "idle", 200),
    ],
)
def test_worker_health_uses_injected_status(fastapi_client, status, state, expected_code):
    from backend.shiftly.app import create_app
    from config import Settings

    app = create_app(
        settings=Settings(secure_cookies=False),
        connection_factory=lambda: (_ for _ in ()).throw(RuntimeError("not used")),
        worker_status_provider=lambda: worker_status(status, state),
    )
    with TestClient(app) as client:
        response = client.get("/api/health/worker")

    assert response.status_code == expected_code
    assert response.json()["state"] == state


def test_worker_provider_failure_is_degraded(fastapi_client):
    from backend.shiftly.app import create_app
    from config import Settings

    app = create_app(
        settings=Settings(secure_cookies=False),
        connection_factory=lambda: (_ for _ in ()).throw(RuntimeError("not used")),
        worker_status_provider=lambda: (_ for _ in ()).throw(RuntimeError("worker unavailable")),
    )
    with TestClient(app) as client:
        response = client.get("/api/health/worker")

    assert response.status_code == 503
    assert response.json()["state"] == "unavailable"


def test_health_routes_include_security_and_cache_headers(fastapi_client):
    response = fastapi_client.get("/api/health")

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
