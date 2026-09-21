import os
import subprocess
import sys

from fastapi.testclient import TestClient

from backend.shiftly.app import create_app


def test_package_import_has_no_startup_side_effects():
    environment = {**os.environ, "DATABASE_URL": "postgresql://invalid.invalid/never-connect"}
    result = subprocess.run(
        [sys.executable, "-c", "import backend.shiftly.app; print('imported')"],
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "imported"


def test_factory_does_not_connect_or_start_provider(app_settings):
    calls = []
    app = create_app(
        settings=app_settings,
        connection_factory=lambda: calls.append("connection"),
        worker_status_provider=lambda: calls.append("worker"),
    )

    assert calls == []
    assert not hasattr(app.state, "lifecycle")


def test_factory_instances_keep_injected_state_isolated(app_settings):
    first = create_app(
        settings=app_settings,
        connection_factory=lambda: (_ for _ in ()).throw(RuntimeError("unavailable")),
        worker_status_provider=lambda: {
            "status": "ok",
            "state": "idle",
            "running": True,
            "lastPollAgeSeconds": 0.1,
            "lastCompletionAgeSeconds": None,
            "completedJobs": 2,
            "consecutiveErrors": 0,
        },
    )
    second_settings = app_settings.__class__(
        database_url=app_settings.database_url,
        openai_api_key="",
        secure_cookies=False,
    )
    second = create_app(
        settings=second_settings,
        connection_factory=lambda: (_ for _ in ()).throw(RuntimeError("unavailable")),
        worker_status_provider=lambda: {
            "status": "degraded",
            "state": "stalled",
            "running": True,
            "lastPollAgeSeconds": 61,
            "lastCompletionAgeSeconds": None,
            "completedJobs": 2,
            "consecutiveErrors": 1,
        },
    )

    with TestClient(first) as first_client, TestClient(second) as second_client:
        first_health = first_client.get("/api/health")
        second_health = second_client.get("/api/health")

    assert first_health.status_code == 503
    assert first_health.json()["secureCookies"] is True
    assert first_health.json()["worker"]["status"] == "ok"
    assert second_health.json()["secureCookies"] is False
    assert second_health.json()["worker"]["state"] == "stalled"
