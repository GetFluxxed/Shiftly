"""Real separate-process worker tests; provider/network boundaries are fail closed."""

import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

import reporting
from backend.shiftly.jobs.status import DatabaseWorkerStatus
from database import db_connection

ACCEPTED = {"status": "accepted", "summary": "Freezer restocked.", "wins": ["Restocked"], "risks": [], "follow_up": "None."}


def wait_for(predicate, *, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.04)
    pytest.fail("Timed out waiting for disposable worker state")


@pytest.fixture
def workers(tmp_path, child_environment):
    processes = []
    def start(dsn, mode="accepted", **overrides):
        script = '''
import time, urllib.request
from config import load_settings
from backend.shiftly.jobs.worker import run_worker

def forbidden(*args, **kwargs):
    raise AssertionError("External AI/network is forbidden in this worker test")
urllib.request.urlopen = forbidden

def provider(report, prompt=None):
    if MODE == "blocked":
        time.sleep(60)
    return {"status":"accepted", "summary":"Freezer restocked.", "wins":["Restocked"], "risks":[], "follow_up":"None."}
run_worker(load_settings(load_env=False), provider=provider, install_signals=True)
'''.replace("MODE", repr(mode))
        output = tmp_path / f"worker-{len(processes)}.log"
        handle = output.open("w+")
        process = subprocess.Popen([sys.executable, "-c", script], env=child_environment(dsn, **overrides), stdout=handle, stderr=subprocess.STDOUT, text=True)
        processes.append((process, handle))
        return process, output
    yield start
    for process, handle in processes:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        handle.close()


@pytest.fixture
def queued(runtime_settings):
    with db_connection() as connection:
        store = connection.execute("INSERT INTO stores (name,access_code_hash) VALUES ('Process test','process') RETURNING id").fetchone()[0]
    report_id, _ = reporting.queue_report("Crew", "closing", "Original freezer notes.", store)
    return report_id


def job_row(report_id):
    with db_connection() as connection:
        return connection.execute("SELECT status,attempts FROM briefing_jobs WHERE report_id=%s", (report_id,)).fetchone()


def test_worker_completes_without_web_wake_and_stops_gracefully(runtime_settings, queued, workers):
    process, output = workers(runtime_settings.database_url, OPENAI_MODEL="injected-worker-model")
    wait_for(lambda: job_row(queued) == ("completed", 1))
    wait_for(lambda: DatabaseWorkerStatus(db_connection)()["completedJobs"] == 1)
    status = DatabaseWorkerStatus(db_connection)()
    assert status["status"] == "ok" and status["completedJobs"] == 1
    with db_connection() as connection:
        assert connection.execute("SELECT source_notes,model FROM briefings WHERE report_id=%s", (queued,)).fetchone() == ("Original freezer notes.", "injected-worker-model")
    process.terminate()
    assert process.wait(timeout=4) == 0, output.read_text()
    assert DatabaseWorkerStatus(db_connection)()["state"] == "stopped"


def test_crash_restart_reclaims_expired_lease_and_fences_old_result(runtime_settings, queued, workers):
    first, _ = workers(runtime_settings.database_url, mode="blocked")
    wait_for(lambda: job_row(queued) == ("processing", 1))
    with db_connection() as connection:
        row = connection.execute("SELECT j.id,r.lease_token,j.attempts FROM briefing_jobs j JOIN briefing_job_recovery r ON r.job_id=j.id WHERE j.report_id=%s", (queued,)).fetchone()
    stale_id = reporting.ClaimedJobId(*row)
    first.kill()
    first.wait(timeout=3)
    with db_connection() as connection:
        connection.execute("UPDATE briefing_jobs SET locked_at=NOW()-INTERVAL '301 seconds' WHERE report_id=%s", (queued,))
    second, output = workers(runtime_settings.database_url)
    wait_for(lambda: job_row(queued) == ("completed", 2))
    assert not reporting.complete_job(stale_id, reporting.job_report(queued), ACCEPTED)
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM briefings WHERE report_id=%s", (queued,)).fetchone() == (1,)
        assert connection.execute("SELECT notes FROM reports WHERE id=%s", (queued,)).fetchone() == ("Original freezer notes.",)
    second.terminate()
    assert second.wait(timeout=4) == 0, output.read_text()


def test_only_one_separate_worker_holds_ownership(runtime_settings, workers):
    first, _ = workers(runtime_settings.database_url)
    wait_for(lambda: DatabaseWorkerStatus(db_connection)()["state"] == "idle")
    second, output = workers(runtime_settings.database_url)
    assert second.wait(timeout=5) != 0
    assert "already running" in output.read_text()
    assert first.poll() is None
    assert DatabaseWorkerStatus(db_connection)()["status"] == "ok"


def test_shutdown_budget_does_not_wait_for_blocked_provider(runtime_settings, queued, workers):
    process, output = workers(runtime_settings.database_url, mode="blocked", SHUTDOWN_TIMEOUT="0.2")
    wait_for(lambda: job_row(queued) == ("processing", 1))
    started = time.monotonic()
    process.terminate()
    assert process.wait(timeout=3) != 0
    assert time.monotonic() - started < 3
    assert "shutdown deadline exceeded" in output.read_text()
    assert job_row(queued) == ("processing", 1)


def test_lost_ownership_session_exits_for_supervisor_restart(runtime_settings, workers):
    process, output = workers(runtime_settings.database_url)
    wait_for(lambda: DatabaseWorkerStatus(db_connection)()["state"] == "idle")
    with db_connection() as connection:
        old_instance = connection.execute("SELECT instance_id FROM runtime_worker_status").fetchone()[0]
        pid = connection.execute("""SELECT pid FROM pg_locks WHERE locktype='advisory'
            AND classid=hashtext(current_database())::oid
            AND objid=hashtext(current_schema() || ':shiftly-briefing-worker')::oid
            AND granted AND pid <> pg_backend_pid()""").fetchone()[0]
        assert connection.execute("SELECT pg_terminate_backend(%s)", (pid,)).fetchone()[0]
    assert process.wait(timeout=5) != 0
    assert "ownership was lost" in output.read_text()
    replacement, _ = workers(runtime_settings.database_url)
    def new_instance_is_idle():
        with db_connection() as connection:
            return connection.execute("SELECT instance_id <> %s AND state='idle' FROM runtime_worker_status", (old_instance,)).fetchone()[0]
    wait_for(new_instance_is_idle)
    assert replacement.poll() is None


def test_worker_cli_requires_preexisting_schema(empty_database, child_environment):
    process = subprocess.run([sys.executable, "-m", "backend.shiftly.jobs.worker"], env=child_environment(empty_database), capture_output=True, text=True, timeout=8)
    assert process.returncode != 0
    assert "schema readiness" in process.stderr
    assert "Traceback" not in process.stderr
    with db_connection() as connection:
        assert connection.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None


def test_legacy_external_mode_serves_without_starting_worker(runtime_settings, queued, child_environment):
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    environment = child_environment(runtime_settings.database_url, HOST="127.0.0.1", PORT=str(port))
    process = subprocess.Popen([sys.executable, "server.py"], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    def health():
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            connection.request("GET", "/api/health/worker")
            response = connection.getresponse()
            body = json.loads(response.read())
            return (response.status, body)
        except OSError:
            return None
        finally:
            connection.close()
    try:
        status, body = wait_for(health)
        assert status == 503 and body["state"] == "not_started"
        assert job_row(queued) == ("pending", 0)
        with db_connection() as connection:
            assert connection.execute("SELECT count(*) FROM runtime_worker_status").fetchone() == (0,)
    finally:
        process.terminate()
        process.communicate(timeout=4)
