"""Worker recovery checks; all databases are disposable and AI is mocked."""

import http.client
import json
import logging
import os
import subprocess
import sys
import urllib.error
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from threading import Barrier, Event, Thread

import psycopg
import pytest

import reporting
import server
from database import db_connection


class StopWorker(BaseException):
    """End a deterministic loop without being mistaken for a job failure."""


def test_nested_failure_does_not_terminate_worker(monkeypatch):
    claims = []
    waits = []

    def claim():
        claims.append(True)
        if len(claims) == 2:
            raise StopWorker()
        return 1, uuid.uuid4()

    def unavailable(*args):
        raise psycopg.OperationalError("private report notes and credentials")

    class Wake:
        def wait(self, timeout):
            waits.append(timeout)

        def clear(self):
            pass

    monkeypatch.setattr(reporting, "claim_job", claim)
    monkeypatch.setattr(reporting, "job_report", lambda report_id: {})
    monkeypatch.setattr(reporting, "call_openai", unavailable)
    monkeypatch.setattr(reporting, "fail_job", unavailable)
    monkeypatch.setattr(reporting, "JOB_WAKE", Wake())
    monkeypatch.setattr(reporting, "_worker_backoff", lambda delay, stop: waits.append(delay), raising=False)
    with pytest.raises(StopWorker):
        reporting.worker_loop()
    assert len(claims) == 2
    assert waits and all(delay >= 2 for delay in waits)


ACCEPTED = {"status": "accepted", "summary": "Freezer restocked.", "wins": ["Restocked"], "risks": [], "follow_up": "None."}


@pytest.fixture(autouse=True)
def worker_state(monkeypatch):
    state = reporting.WorkerStatus()
    monkeypatch.setattr(reporting, "WORKER_STATUS", state)
    return state


@pytest.fixture
def queued(isolated_database):
    with db_connection() as connection:
        store = connection.execute(
            "INSERT INTO stores (name, access_code_hash) VALUES ('Recovery test', %s) RETURNING id",
            (uuid.uuid4().hex,),
        ).fetchone()[0]
    report_id, _ = reporting.queue_report("Nina", "closing", "Restocked the freezer.", store)
    return report_id


def job_state():
    with db_connection() as connection:
        return connection.execute("SELECT status, attempts, last_error FROM briefing_jobs").fetchone()


def expire_claim():
    with db_connection() as connection:
        connection.execute("UPDATE briefing_jobs SET locked_at = NOW() - INTERVAL '301 seconds'")


def retry_now():
    with db_connection() as connection:
        connection.execute("UPDATE briefing_job_recovery SET next_attempt_at = NOW() - INTERVAL '1 second'")


def retry_state():
    with db_connection() as connection:
        return connection.execute(
            "SELECT terminal, EXTRACT(EPOCH FROM next_attempt_at - NOW()) FROM briefing_job_recovery"
        ).fetchone()


def stop_when_idle(monkeypatch):
    class Wake:
        def wait(self, timeout):
            raise StopWorker()
    monkeypatch.setattr(reporting, "JOB_WAKE", Wake())


def test_loop_recovers_after_provider_and_failure_persistence_outages(queued, monkeypatch, worker_state, caplog):
    caplog.set_level(logging.INFO, logger="shiftly.worker")
    provider_calls = []
    waits = []
    fail = reporting.fail_job

    def provider(report):
        provider_calls.append(report)
        if len(provider_calls) == 1:
            raise urllib.error.URLError("private report and api-key")
        return ACCEPTED

    def recording_failure(job_id, error):
        raise psycopg.OperationalError("database credentials")

    def backoff(delay, stop):
        waits.append(delay)
        assert job_state()[:2] == ("processing", 1)
        assert worker_state.snapshot()["status"] == "degraded"
        expire_claim()
        monkeypatch.setattr(reporting, "fail_job", fail)

    monkeypatch.setattr(reporting, "call_openai", provider)
    monkeypatch.setattr(reporting, "fail_job", recording_failure)
    monkeypatch.setattr(reporting, "_worker_backoff", backoff)
    stop_when_idle(monkeypatch)
    with pytest.raises(StopWorker):
        reporting.worker_loop()
    assert waits == [2]
    assert len(provider_calls) == 2
    assert job_state() == ("completed", 2, None)
    status = worker_state.snapshot()
    assert status["completedJobs"] == 1
    assert status["lastCompletionAgeSeconds"] is not None
    assert status["state"] == "stopped"
    records = [json.loads(record.message) for record in caplog.records if record.name == "shiftly.worker"]
    assert any(row["event"] == "failure_recording_failed" for row in records)
    assert any(row["event"] == "job_completed" and row["attempt"] == 2 for row in records)
    assert all("Restocked" not in record.message and "credentials" not in record.message and "api-key" not in record.message for record in caplog.records)


def test_claim_outage_backoff_is_bounded_and_cannot_be_woken_by_submissions(monkeypatch, worker_state):
    calls = []
    waits = []

    def claim():
        calls.append(True)
        if len(calls) <= 8:
            raise psycopg.OperationalError("connection unavailable")
        return None

    class Stop:
        def is_set(self):
            return False

        def wait(self, delay):
            waits.append(delay)
            assert worker_state.snapshot()["consecutiveErrors"] == len(waits)
            assert worker_state.snapshot()["status"] == "degraded"

    monkeypatch.setattr(reporting, "claim_job", claim)
    stop_when_idle(monkeypatch)
    with pytest.raises(StopWorker):
        reporting.worker_loop(stop_event=Stop())
    assert waits == [2, 4, 8, 16, 30, 30, 30, 30]
    assert len(calls) == 9
    assert worker_state.snapshot()["lastPollAgeSeconds"] is not None
    assert worker_state.snapshot()["completedJobs"] == 0


@pytest.mark.parametrize("error,code,retryable", [
    (psycopg.OperationalError("secret DSN"), "database_unavailable", True),
    (psycopg.errors.SerializationFailure("secret SQL"), "database_unavailable", True),
    (psycopg.errors.CheckViolation("raw report notes"), "database_error", False),
    (urllib.error.URLError("private URL"), "provider_unavailable", True),
    (urllib.error.HTTPError("private URL", 429, "secret", None, None), "provider_unavailable", True),
    (urllib.error.HTTPError("private URL", 503, "secret", None, None), "provider_unavailable", True),
    (urllib.error.HTTPError("private URL", 401, "secret", None, None), "provider_rejected", False),
    (urllib.error.HTTPError("private URL", 400, "secret", None, None), "provider_rejected", False),
    (reporting.TerminalJobError("private configuration"), "terminal_job_error", False),
    (ValueError("private result"), "invalid_result", True),
])
def test_failure_classification_and_sanitized_durable_delay(queued, error, code, retryable):
    job_id, _ = reporting.claim_job()
    assert reporting.fail_job(job_id, error)
    assert job_state() == ("failed", 1, code)
    terminal, seconds = retry_state()
    assert terminal is not retryable
    assert 28 <= seconds <= 30 if retryable else seconds is None
    assert reporting.claim_job() is None
    retry_now()
    assert (reporting.claim_job() is not None) is retryable


def test_wrapped_http_failure_retains_retry_classification(queued):
    job_id, _ = reporting.claim_job()
    error = RuntimeError("wrapped error with notes")
    error.__cause__ = urllib.error.HTTPError("secret URL", 403, "secret", None, None)
    assert reporting.fail_job(job_id, error)
    assert job_state() == ("failed", 1, "provider_rejected")
    assert reporting.claim_job() is None


def test_retry_delays_increase_and_attempts_stop_at_three(queued):
    for attempt, expected_delay in [(1, 30), (2, 60), (3, None)]:
        job_id, _ = reporting.claim_job()
        assert job_id.attempt == attempt
        assert reporting.fail_job(job_id, TimeoutError("private timeout"))
        terminal, delay = retry_state()
        if expected_delay is None:
            assert terminal and delay is None
        else:
            assert not terminal and expected_delay - 2 <= delay <= expected_delay
        assert reporting.claim_job() is None
        retry_now()
    assert reporting.claim_job() is None
    assert job_state() == ("failed", 3, "provider_unavailable")


def fresh_process_claim():
    result = subprocess.run(
        [sys.executable, "-c", "import json, reporting; job = reporting.claim_job(); print(json.dumps(None if job is None else job[0].attempt))"],
        env={**os.environ, "OPENAI_API_KEY": ""}, capture_output=True, text=True, check=True, timeout=15,
    )
    return json.loads(result.stdout)


def test_retry_schedule_survives_a_fresh_process(queued):
    job_id, _ = reporting.claim_job()
    reporting.fail_job(job_id, TimeoutError())
    assert fresh_process_claim() is None
    retry_now()
    assert fresh_process_claim() == 2
    assert job_state()[:2] == ("processing", 2)
    assert reporting.claim_job() is None


def test_expired_lease_recovery_fences_old_and_duplicate_completion(queued):
    old_id, report_id = reporting.claim_job()
    report = reporting.job_report(report_id)
    assert reporting.claim_job() is None
    expire_claim()
    new_id, _ = reporting.claim_job()
    assert old_id == new_id and old_id.lease_token != new_id.lease_token
    assert new_id.attempt == 2
    assert not reporting.complete_job(old_id, report, ACCEPTED)
    assert not reporting.fail_job(old_id, TimeoutError())
    assert not reporting.complete_job(int(new_id), report, ACCEPTED)
    assert reporting.complete_job(new_id, report, ACCEPTED)
    assert not reporting.complete_job(new_id, report, {**ACCEPTED, "summary": "Duplicate"})
    assert not reporting.fail_job(new_id, TimeoutError())
    assert job_state() == ("completed", 2, None)
    with db_connection() as connection:
        assert connection.execute("SELECT source_notes, summary FROM briefings").fetchall() == [(report["notes"], ACCEPTED["summary"])]


def test_expired_lease_cannot_write_even_before_reclaim(queued):
    job_id, report_id = reporting.claim_job()
    expire_claim()
    assert not reporting.complete_job(job_id, reporting.job_report(report_id), ACCEPTED)
    assert not reporting.fail_job(job_id, TimeoutError())
    assert job_state()[:2] == ("processing", 1)


def test_crashes_on_every_attempt_eventually_become_terminal(queued):
    for attempt in range(1, 4):
        job_id, _ = reporting.claim_job()
        assert job_id.attempt == attempt
        expire_claim()
    assert fresh_process_claim() is None
    assert reporting.claim_job() is None
    assert job_state() == ("failed", 3, "attempts_exhausted")
    assert retry_state() == (True, None)


def test_concurrent_claimers_only_one_owns_the_job(queued):
    barrier = Barrier(2)
    def claim():
        barrier.wait(timeout=5)
        return reporting.claim_job()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert job_state()[:2] == ("processing", 1)


def test_concurrent_duplicate_completions_commit_once(queued):
    job_id, report_id = reporting.claim_job()
    report = reporting.job_report(report_id)
    barrier = Barrier(2)
    def complete():
        barrier.wait(timeout=5)
        return reporting.complete_job(job_id, report, ACCEPTED)
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: complete(), range(2))) == [False, True]
    with db_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM briefings").fetchone() == (1,)
    assert job_state() == ("completed", 1, None)


def test_rejection_is_terminal_and_reason_is_not_copied_into_diagnostics(queued):
    job_id, report_id = reporting.claim_job()
    assert reporting.complete_job(job_id, reporting.job_report(report_id), {"status": "rejected", "reason": "Raw notes and secret"})
    assert job_state() == ("failed", 1, "Report rejected by briefing rules.")
    assert retry_state() == (True, None)
    assert reporting.claim_job() is None
    with db_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM briefings").fetchone() == (0,)


@pytest.mark.parametrize("result", [None, [], {"status": []}, {"status": "unknown"}, {**ACCEPTED, "wins": "bad"}, {**ACCEPTED, "summary": 123}])
def test_invalid_provider_result_cannot_partially_complete(queued, result):
    job_id, report_id = reporting.claim_job()
    with pytest.raises(ValueError):
        reporting.complete_job(job_id, reporting.job_report(report_id), result)
    assert job_state()[:2] == ("processing", 1)
    with db_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM briefings").fetchone() == (0,)


def test_completion_failure_rolls_back_and_wrong_report_is_rejected(queued):
    job_id, report_id = reporting.claim_job()
    report = reporting.job_report(report_id)
    with pytest.raises(reporting.TerminalJobError):
        reporting.complete_job(job_id, {**report, "id": str(uuid.uuid4())}, ACCEPTED)
    with db_connection() as connection:
        connection.execute("ALTER TABLE briefings ADD CONSTRAINT reject_test_briefing CHECK (FALSE)")
    with pytest.raises(psycopg.errors.CheckViolation):
        reporting.complete_job(job_id, report, ACCEPTED)
    assert job_state()[:2] == ("processing", 1)


def test_lost_commit_acknowledgment_cannot_reopen_completed_job(queued, monkeypatch, worker_state):
    complete = reporting.complete_job
    def lost_ack(*args):
        assert complete(*args)
        raise psycopg.OperationalError("lost response after commit")
    monkeypatch.setattr(reporting, "complete_job", lost_ack)
    monkeypatch.setattr(reporting, "call_openai", lambda report: ACCEPTED)
    monkeypatch.setattr(reporting, "_worker_backoff", lambda *args: None)
    stop_when_idle(monkeypatch)
    with pytest.raises(StopWorker):
        reporting.worker_loop()
    assert job_state() == ("completed", 1, None)
    assert worker_state.snapshot()["completedJobs"] == 0  # Do not claim an unobserved commit.
    with db_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM briefings").fetchone() == (1,)


def test_worker_status_separates_polling_completion_failure_and_stalling():
    now = [10.0]
    state = reporting.WorkerStatus(clock=lambda: now[0])
    assert state.snapshot()["state"] == "not_started"
    assert state.snapshot()["status"] == "degraded"
    state.update("starting")
    assert state.snapshot()["status"] == "degraded"
    state.update("idle", polled=True)
    assert state.snapshot()["status"] == "ok"
    assert state.snapshot()["completedJobs"] == 0
    assert state.snapshot()["lastCompletionAgeSeconds"] is None
    state.update("processing", polled=True)
    now[0] += 61
    assert state.snapshot()["state"] == "stalled"
    assert state.snapshot()["status"] == "degraded"
    state.update("backoff", errors=1)
    assert state.snapshot()["status"] == "degraded"
    assert state.snapshot()["lastPollAgeSeconds"] == 61
    state.update("idle", polled=True, completed=True)
    assert state.snapshot()["completedJobs"] == 1
    assert state.snapshot()["status"] == "ok"
    state.update("stopped")
    assert not state.snapshot()["running"]
    assert state.snapshot()["status"] == "degraded"
    state.update("starting")
    assert state.snapshot()["status"] == "degraded"


def test_idle_worker_shuts_down_when_signalled(monkeypatch, worker_state):
    polled = Event()
    stop = Event()
    def claim():
        polled.set()
        return None
    monkeypatch.setattr(reporting, "claim_job", claim)
    worker = Thread(target=reporting.worker_loop, kwargs={"stop_event": stop}, daemon=True)
    worker.start()
    try:
        assert polled.wait(2)
    finally:
        stop.set()
        reporting.JOB_WAKE.set()
        worker.join(2)
    assert not worker.is_alive()
    assert worker_state.snapshot()["state"] == "stopped"


def test_worker_health_is_additive_and_does_not_mask_a_stopped_worker(isolated_database, worker_state):
    http_server = ThreadingHTTPServer(("127.0.0.1", 0), server.ShiftlyHandler)
    thread = Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    def get(path):
        connection = http.client.HTTPConnection(*http_server.server_address, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()
    try:
        status, body = get("/api/health")
        assert status == 200 and body["status"] == "ok" and body["databaseConfigured"]
        assert {"openaiConfigured", "databaseConfigured", "secureCookies"} <= body.keys()
        assert body["worker"]["status"] == "degraded"
        assert get("/api/health/worker")[0] == 503
        worker_state.update("idle", polled=True)
        assert get("/api/health/worker")[0] == 200
        worker_state.update("backoff", errors=1)
        assert get("/api/health/worker")[0] == 503
        assert get("/api/health")[0] == 200
    finally:
        http_server.shutdown()
        thread.join(2)
        http_server.server_close()


def test_migration_upgrade_preserves_legacy_jobs_and_repeated_startup(empty_database):
    with db_connection() as connection:
        connection.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
        for migration in sorted((server.ROOT / "migrations").glob("*.sql")):
            if migration.name >= "012_":
                continue
            connection.execute(migration.read_text())
            connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (migration.name,))
        for index, (status, attempts, age) in enumerate([("pending", 0, 0), ("failed", 1, 0), ("failed", 1, 3600), ("processing", 1, 3600), ("processing", 3, 3600), ("completed", 1, 3600)]):
            report_id = uuid.uuid4()
            connection.execute("INSERT INTO reports (id, employee, shift, notes, report_hash) VALUES (%s, 'Legacy', 'closing', 'Saved notes', %s)", (report_id, str(index) * 64))
            connection.execute("INSERT INTO briefing_jobs (report_id, status, attempts, locked_at, finished_at) VALUES (%s, %s, %s, NOW() - %s * INTERVAL '1 second', NOW() - %s * INTERVAL '1 second')", (report_id, status, attempts, age, age))
        before = connection.execute("SELECT * FROM briefing_jobs ORDER BY id").fetchall()
    server.initialize_database()
    server.initialize_database()
    with db_connection() as connection:
        assert connection.execute("SELECT * FROM briefing_jobs ORDER BY id").fetchall() == before
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = '012_briefing_job_recovery.sql'").fetchone() == (1,)
    claims = [reporting.claim_job() for _ in range(3)]
    assert [job[0].attempt for job in claims] == [1, 2, 2]
    assert reporting.claim_job() is None
    with db_connection() as connection:
        states = connection.execute("SELECT status, attempts FROM briefing_jobs ORDER BY id").fetchall()
        assert states == [("processing", 1), ("failed", 1), ("processing", 2), ("processing", 2), ("failed", 3), ("completed", 1)]


def test_new_process_reclaims_expired_work_and_fences_the_prior_process(queued):
    job_id, report_id = reporting.claim_job()
    expire_claim()
    assert fresh_process_claim() == 2
    assert not reporting.complete_job(job_id, reporting.job_report(report_id), ACCEPTED)
    assert not reporting.fail_job(job_id, TimeoutError())
    assert job_state()[:2] == ("processing", 2)


def test_loop_persists_retry_then_completes_when_due(queued, monkeypatch, worker_state):
    provider_calls = []
    waits = []
    def provider(report):
        provider_calls.append(report)
        if len(provider_calls) == 1:
            raise TimeoutError("private notes")
        return ACCEPTED
    def backoff(delay, stop):
        waits.append(delay)
        assert job_state() == ("failed", 1, "provider_unavailable")
        assert reporting.claim_job() is None
        assert worker_state.snapshot()["completedJobs"] == 0
        retry_now()
    monkeypatch.setattr(reporting, "call_openai", provider)
    monkeypatch.setattr(reporting, "_worker_backoff", backoff)
    stop_when_idle(monkeypatch)
    with pytest.raises(StopWorker):
        reporting.worker_loop()
    assert waits == [2]
    assert len(provider_calls) == 2
    assert job_state() == ("completed", 2, None)
    assert worker_state.snapshot()["completedJobs"] == 1


def test_rejected_job_is_not_reported_as_a_completed_briefing(queued, monkeypatch, worker_state):
    monkeypatch.setattr(reporting, "call_openai", lambda report: {"status": "rejected", "reason": "private notes"})
    stop_when_idle(monkeypatch)
    with pytest.raises(StopWorker):
        reporting.worker_loop()
    assert job_state()[:2] == ("failed", 1)
    assert worker_state.snapshot()["completedJobs"] == 0
    assert worker_state.snapshot()["lastCompletionAgeSeconds"] is None
