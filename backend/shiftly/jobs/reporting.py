"""Durable briefing jobs and their dependency-injected worker loop."""

import json
import logging
import time
import urllib.error
import uuid
from threading import Event, Lock

import psycopg

from backend.shiftly.runtime.provider import ProviderConfigurationError

MAX_JOB_ATTEMPTS = 3
JOB_LEASE_SECONDS = 300
JOB_RETRY_SECONDS = 30
WORKER_STALE_SECONDS = 60
WORKER_LOG = logging.getLogger("shiftly.worker")


class ClaimedJobId(int):
    """An int-compatible job ID carrying its claim's fencing token."""

    def __new__(cls, value, lease_token, attempt):
        result = super().__new__(cls, value)
        result.lease_token = lease_token
        result.attempt = attempt
        return result


class TerminalJobError(RuntimeError):
    """Work that cannot succeed by retrying its current inputs."""


def failure_kind(error):
    """Return a sanitized durable error code and whether the work may retry."""
    cause = error
    for _ in range(8):
        if isinstance(cause, (TerminalJobError, ProviderConfigurationError)):
            return "terminal_job_error", False
        if isinstance(cause, urllib.error.HTTPError):
            retry = cause.code in {408, 409, 425, 429} or cause.code >= 500
            return ("provider_unavailable" if retry else "provider_rejected"), retry
        if isinstance(cause, (psycopg.OperationalError, psycopg.InterfaceError)):
            return "database_unavailable", True
        if isinstance(cause, psycopg.Error):
            return "database_error", False
        if isinstance(cause, (urllib.error.URLError, TimeoutError, ConnectionError)):
            return "provider_unavailable", True
        if isinstance(cause, (ValueError, TypeError, KeyError)):
            return "invalid_result", True
        if cause.__cause__ is None:
            break
        cause = cause.__cause__
    return "processing_error", True


def worker_log(event, job_id=None, error=None, *, logger=WORKER_LOG):
    fields = {"event": event}
    if job_id is not None:
        fields.update(jobId=int(job_id), attempt=getattr(job_id, "attempt", None))
    if error is not None:
        fields["errorCode"], fields["retryable"] = failure_kind(error)
    logger.log(logging.WARNING if error else logging.INFO, json.dumps(fields))


class WorkerStatus:
    """Process-local observations; polling is deliberately separate from output."""

    def __init__(self, clock=time.monotonic, *, stale_seconds=WORKER_STALE_SECONDS):
        self.clock = clock
        self.stale_seconds = stale_seconds
        self.lock = Lock()
        self.running = False
        self.phase = "not_started"
        self.last_poll = None
        self.last_completion = None
        self.last_activity = None
        self.completed = 0
        self.errors = 0

    def update(self, phase, *, polled=False, completed=False, errors=0):
        with self.lock:
            now = self.clock()
            self.phase = phase
            self.running = phase != "stopped"
            self.last_activity = now
            if polled:
                self.last_poll = now
            if completed:
                self.last_completion = now
                self.completed += 1
            self.errors = errors

    def snapshot(self):
        with self.lock:
            now = self.clock()

            def age(value):
                return round(max(0, now - value), 3) if value is not None else None

            stale = self.last_activity is not None and now - self.last_activity >= self.stale_seconds
            healthy = self.running and self.last_poll is not None and not stale and self.phase in {"idle", "processing"}
            return {
                "status": "ok" if healthy else "degraded",
                "state": "stalled" if self.running and stale else self.phase,
                "running": self.running,
                "lastPollAgeSeconds": age(self.last_poll),
                "lastCompletionAgeSeconds": age(self.last_completion),
                "completedJobs": self.completed,
                "consecutiveErrors": self.errors,
            }


def claim_job(*, connect, max_attempts=MAX_JOB_ATTEMPTS,
              lease_seconds=JOB_LEASE_SECONDS, retry_seconds=JOB_RETRY_SECONDS):
    """Claim one due job; database timestamps and attempts survive restarts."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH exhausted AS (
                    SELECT id FROM briefing_jobs
                    WHERE status = 'processing' AND attempts >= %s
                      AND COALESCE(locked_at, created_at) <= NOW() - %s * INTERVAL '1 second'
                    ORDER BY created_at, id
                    FOR UPDATE SKIP LOCKED LIMIT 100
                ), finalized AS (
                    UPDATE briefing_jobs j
                    SET status = 'failed', last_error = 'attempts_exhausted',
                        finished_at = NOW(), locked_at = NULL
                    FROM exhausted WHERE j.id = exhausted.id
                    RETURNING j.id
                )
                INSERT INTO briefing_job_recovery (job_id, terminal)
                SELECT id, TRUE FROM finalized
                ON CONFLICT (job_id) DO UPDATE SET terminal = TRUE,
                    lease_token = NULL, next_attempt_at = NULL
                """,
                (max_attempts, lease_seconds),
            )
            cursor.execute(
                """
                SELECT j.id, j.report_id, j.attempts
                FROM briefing_jobs j
                LEFT JOIN briefing_job_recovery r ON r.job_id = j.id
                WHERE j.attempts < %s AND NOT COALESCE(r.terminal, FALSE)
                  AND (
                    j.status = 'pending'
                    OR (j.status = 'processing' AND COALESCE(j.locked_at, j.created_at)
                        <= NOW() - %s * INTERVAL '1 second')
                    OR (j.status = 'failed' AND COALESCE(r.next_attempt_at,
                        COALESCE(j.finished_at, j.created_at) +
                        %s * POWER(2, GREATEST(j.attempts - 1, 0)) * INTERVAL '1 second') <= NOW())
                  )
                ORDER BY j.created_at, j.id
                FOR UPDATE OF j SKIP LOCKED LIMIT 1
                """,
                (max_attempts, lease_seconds, retry_seconds),
            )
            job = cursor.fetchone()
            if job is None:
                return None
            job_id, report_id, attempts = job
            lease_token = uuid.uuid4()
            cursor.execute(
                """
                UPDATE briefing_jobs SET status = 'processing', locked_at = NOW(),
                    attempts = attempts + 1, finished_at = NULL, last_error = NULL
                WHERE id = %s
                """, (job_id,),
            )
            cursor.execute(
                """
                INSERT INTO briefing_job_recovery (job_id, lease_token)
                VALUES (%s, %s)
                ON CONFLICT (job_id) DO UPDATE SET lease_token = EXCLUDED.lease_token,
                    next_attempt_at = NULL, terminal = FALSE
                """, (job_id, lease_token),
            )
        connection.commit()
    return ClaimedJobId(job_id, lease_token, attempts + 1), report_id


def job_report(report_id, *, connect):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, employee, shift, notes FROM reports WHERE id = %s", (report_id,))
            row = cursor.fetchone()
    if not row:
        raise TerminalJobError("Queued report no longer exists.")
    return {"id": str(row[0]), "employee": row[1], "shift": row[2], "notes": row[3]}


def _owned_job(cursor, job_id, *, lease_seconds):
    token = getattr(job_id, "lease_token", None)
    if token is None:
        return None
    cursor.execute("SELECT report_id, attempts FROM briefing_jobs WHERE id = %s FOR UPDATE", (int(job_id),))
    row = cursor.fetchone()
    if row is None:
        return None
    cursor.execute(
        """
        SELECT 1 FROM briefing_jobs j JOIN briefing_job_recovery r ON r.job_id = j.id
        WHERE j.id = %s AND j.status = 'processing' AND r.lease_token = %s
          AND j.locked_at > clock_timestamp() - %s * INTERVAL '1 second'
          AND NOT r.terminal
        """, (int(job_id), token, lease_seconds),
    )
    return row if cursor.fetchone() else None


def _record_failure(cursor, job_id, attempt, code, retryable, *, max_attempts, retry_seconds):
    terminal = not retryable or attempt >= max_attempts
    cursor.execute(
        """
        UPDATE briefing_jobs SET status = 'failed', last_error = %s,
            finished_at = NOW(), locked_at = NULL WHERE id = %s
        """, (code, int(job_id)),
    )
    delay = retry_seconds * 2 ** (attempt - 1)
    cursor.execute(
        """
        UPDATE briefing_job_recovery SET lease_token = NULL, terminal = %s,
            next_attempt_at = CASE WHEN %s THEN NULL ELSE NOW() + %s * INTERVAL '1 second' END
        WHERE job_id = %s
        """, (terminal, terminal, delay, int(job_id)),
    )


def complete_job(job_id, report, briefing, *, connect, model,
                 lease_seconds=JOB_LEASE_SECONDS, max_attempts=MAX_JOB_ATTEMPTS,
                 retry_seconds=JOB_RETRY_SECONDS):
    """Commit a current claim once; stale, duplicate, and bare IDs return False."""
    with connect() as connection:
        with connection.cursor() as cursor:
            owned = _owned_job(cursor, job_id, lease_seconds=lease_seconds)
            if owned is None:
                return False
            report_id, attempt = owned
            if str(report_id) != str(report["id"]):
                raise TerminalJobError("Claim does not belong to this report.")
            if not isinstance(briefing, dict) or briefing.get("status") not in ("accepted", "rejected"):
                raise ValueError("Invalid briefing response.")
            if briefing["status"] == "rejected":
                _record_failure(
                    cursor, job_id, attempt, "Report rejected by briefing rules.", False,
                    max_attempts=max_attempts, retry_seconds=retry_seconds,
                )
            else:
                if (
                    any(not isinstance(briefing.get(key, ""), str) for key in ("summary", "follow_up"))
                    or any(
                        not isinstance(briefing.get(key, []), list)
                        or any(not isinstance(item, str) for item in briefing[key])
                        for key in ("wins", "risks") if key in briefing
                    )
                ):
                    raise ValueError("Invalid briefing response.")
                cursor.execute(
                    """
                    INSERT INTO briefings (report_id, source_notes, summary, wins, risks, follow_up, model)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (report_id) DO NOTHING
                    """,
                    (report_id, report["notes"], briefing.get("summary", ""), briefing.get("wins", []),
                     briefing.get("risks", []), briefing.get("follow_up", ""), model),
                )
                cursor.execute(
                    "UPDATE briefing_jobs SET status = 'completed', finished_at = NOW(), "
                    "last_error = NULL, locked_at = NULL WHERE id = %s", (int(job_id),),
                )
                cursor.execute(
                    "UPDATE briefing_job_recovery SET lease_token = NULL, next_attempt_at = NULL, "
                    "terminal = TRUE WHERE job_id = %s", (int(job_id),),
                )
        connection.commit()
    return True


def fail_job(job_id, error, *, connect, lease_seconds=JOB_LEASE_SECONDS,
             max_attempts=MAX_JOB_ATTEMPTS, retry_seconds=JOB_RETRY_SECONDS):
    code, retryable = failure_kind(error)
    with connect() as connection:
        with connection.cursor() as cursor:
            owned = _owned_job(cursor, job_id, lease_seconds=lease_seconds)
            if owned is None:
                return False
            _record_failure(
                cursor, job_id, owned[1], code, retryable,
                max_attempts=max_attempts, retry_seconds=retry_seconds,
            )
        connection.commit()
    return True


def worker_backoff(delay, stop_event):
    # Report submissions cannot wake an outage retry early. Shutdown can.
    stop_event.wait(delay)


def worker_loop(*, claim, load_report, provider, complete, fail, status, wake,
                stop_event=None, backoff=worker_backoff, poll_seconds=2,
                log=worker_log):
    stop_event = stop_event if stop_event is not None else Event()
    failures = 0
    status.update("starting")
    log("worker_started")
    try:
        while not stop_event.is_set():
            job_id = None
            try:
                job = claim()
                status.update("processing" if job else "idle", polled=True)
                if job:
                    job_id, report_id = job
                    log("job_claimed", job_id)
                    report = load_report(report_id)
                    briefing = provider(report)
                    committed = complete(job_id, report, briefing)
                    accepted = committed and briefing.get("status") == "accepted"
                    status.update("idle", completed=accepted)
                    event = "job_completed" if accepted else "job_rejected" if committed else "lease_lost"
                    log(event, job_id)
                    failures = 0
                    continue
                failures = 0
            except Exception as error:
                failures += 1
                log("job_failed" if job_id is not None else "claim_failed", job_id, error)
                if job_id is not None:
                    try:
                        recorded = fail(job_id, error)
                        log("failure_recorded" if recorded else "lease_lost", job_id)
                    except Exception as recording_error:
                        log("failure_recording_failed", job_id, recording_error)
                status.update("backoff", errors=failures)
                backoff(min(30, 2 ** min(failures, 5)), stop_event)
                continue
            wake.wait(poll_seconds)
            wake.clear()
    finally:
        status.update("stopped")
        log("worker_stopped")
