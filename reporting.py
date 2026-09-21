import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.request
import uuid
from threading import BoundedSemaphore, Event, Lock

import psycopg

from backend.shiftly.reports import ReportsRepository, ReportsService, WeeklyOverviewBusy, WeeklyOverviewService
from backend.shiftly.reports.service import normalized_notes as _normalized_notes
from backend.shiftly.reports.weekly import validated_weekly_result, weekly_cache_result, weekly_source
from backend.shiftly.runtime.prompts import SYSTEM_PROMPT, QUALITY_PROMPT, WEEKLY_PROMPT
from config import load_settings
from database import db_connection

SETTINGS = load_settings()
MODEL = SETTINGS.openai_model
REPORT_COOLDOWN_SECONDS = SETTINGS.report_cooldown_seconds
JOB_WAKE = Event()
MAX_JOB_ATTEMPTS = 3
JOB_LEASE_SECONDS = 300
JOB_RETRY_SECONDS = 30
WORKER_STALE_SECONDS = 60
WORKER_LOG = logging.getLogger("shiftly.worker")


class ClaimedJobId(int):
    """An int-compatible ID carrying the lease acquired by claim_job.

    Pass this ID unchanged to complete_job/fail_job. Two-value claim unpacking
    and existing SQL/JSON uses remain compatible; a bare ID cannot mutate work.
    """

    def __new__(cls, value, lease_token, attempt):
        result = super().__new__(cls, value)
        result.lease_token = lease_token
        result.attempt = attempt
        return result


class TerminalJobError(RuntimeError):
    """Work that cannot succeed by retrying its current inputs."""


def _failure_kind(error):
    # Inspect types/codes, never provider text, SQL detail, notes or credentials.
    cause = error
    for _ in range(8):
        if isinstance(cause, TerminalJobError):
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


def _worker_log(event, job_id=None, error=None):
    fields = {"event": event}
    if job_id is not None:
        fields.update(jobId=int(job_id), attempt=getattr(job_id, "attempt", None))
    if error is not None:
        fields["errorCode"], fields["retryable"] = _failure_kind(error)
    WORKER_LOG.log(logging.WARNING if error else logging.INFO, json.dumps(fields))


class WorkerStatus:
    """Process-local observations; polling is deliberately separate from output."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
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
            stale = self.last_activity is not None and now - self.last_activity >= WORKER_STALE_SECONDS
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


WORKER_STATUS = WorkerStatus()


def worker_status():
    return WORKER_STATUS.snapshot()






REPORT_SIMILARITY_THRESHOLD = 0.75
WEEKLY_MAX_REPORTS = 50
WEEKLY_MAX_INPUT_CHARS = 20_000
WEEKLY_GENERATION_SLOTS = BoundedSemaphore(2)



try:
    import certifi
except ImportError:
    certifi = None


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _reports_service():
    # Compose per call so legacy callers/tests can replace these dependencies.
    # Creating a service opens no connection and creates no worker resources.
    return ReportsService(
        ReportsRepository(db_connection), cooldown_seconds=REPORT_COOLDOWN_SECONDS,
        similarity_threshold=REPORT_SIMILARITY_THRESHOLD, clock=time.time, wake=JOB_WAKE.set,
    )


def queue_report(employee, shift, notes, store_id):
    return _reports_service().queue_report(employee, shift, notes, store_id)


def claim_job():
    """Claim one due job; database timestamps and attempts survive restarts."""
    with db_connection() as connection:
        with connection.cursor() as cursor:
            # Final crashed attempts must become terminal, not live forever as
            # processing. Bound cleanup and skip rows another worker owns.
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
                (MAX_JOB_ATTEMPTS, JOB_LEASE_SECONDS),
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
                (MAX_JOB_ATTEMPTS, JOB_LEASE_SECONDS, JOB_RETRY_SECONDS),
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


def job_report(report_id):
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, employee, shift, notes FROM reports WHERE id = %s", (report_id,))
            row = cursor.fetchone()
    if not row:
        raise TerminalJobError("Queued report no longer exists.")
    return {"id": str(row[0]), "employee": row[1], "shift": row[2], "notes": row[3]}


def _owned_job(cursor, job_id):
    token = getattr(job_id, "lease_token", None)
    if token is None:
        return None
    # Always lock the parent first, then read the current token in a fresh
    # statement. A waiter must not validate a token from a pre-lock snapshot.
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
        """, (int(job_id), token, JOB_LEASE_SECONDS),
    )
    return row if cursor.fetchone() else None


def _record_failure(cursor, job_id, attempt, code, retryable):
    terminal = not retryable or attempt >= MAX_JOB_ATTEMPTS
    cursor.execute(
        """
        UPDATE briefing_jobs SET status = 'failed', last_error = %s,
            finished_at = NOW(), locked_at = NULL WHERE id = %s
        """, (code, int(job_id)),
    )
    delay = JOB_RETRY_SECONDS * 2 ** (attempt - 1)
    cursor.execute(
        """
        UPDATE briefing_job_recovery SET lease_token = NULL, terminal = %s,
            next_attempt_at = CASE WHEN %s THEN NULL ELSE NOW() + %s * INTERVAL '1 second' END
        WHERE job_id = %s
        """, (terminal, terminal, delay, int(job_id)),
    )


def complete_job(job_id, report, briefing):
    """Commit a current claim once; stale/duplicate/bare IDs return False."""
    with db_connection() as connection:
        with connection.cursor() as cursor:
            owned = _owned_job(cursor, job_id)
            if owned is None:
                return False
            report_id, attempt = owned
            if str(report_id) != str(report["id"]):
                raise TerminalJobError("Claim does not belong to this report.")
            if not isinstance(briefing, dict) or briefing.get("status") not in ("accepted", "rejected"):
                raise ValueError("Invalid briefing response.")
            if briefing["status"] == "rejected":
                _record_failure(cursor, job_id, attempt, "Report rejected by briefing rules.", False)
            else:
                if (any(not isinstance(briefing.get(key, ""), str) for key in ("summary", "follow_up"))
                    or any(not isinstance(briefing.get(key, []), list)
                           or any(not isinstance(item, str) for item in briefing[key])
                           for key in ("wins", "risks") if key in briefing)):
                    raise ValueError("Invalid briefing response.")
                cursor.execute(
                    """
                    INSERT INTO briefings (report_id, source_notes, summary, wins, risks, follow_up, model)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (report_id) DO NOTHING
                    """,
                    (report_id, report["notes"], briefing.get("summary", ""), briefing.get("wins", []), briefing.get("risks", []), briefing.get("follow_up", ""), MODEL),
                )
                cursor.execute("UPDATE briefing_jobs SET status = 'completed', finished_at = NOW(), last_error = NULL, locked_at = NULL WHERE id = %s", (int(job_id),))
                cursor.execute("UPDATE briefing_job_recovery SET lease_token = NULL, next_attempt_at = NULL, terminal = TRUE WHERE job_id = %s", (int(job_id),))
        connection.commit()
    return True


def fail_job(job_id, error):
    code, retryable = _failure_kind(error)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            owned = _owned_job(cursor, job_id)
            if owned is None:
                return False
            _record_failure(cursor, job_id, owned[1], code, retryable)
        connection.commit()
    return True


def _worker_backoff(delay, stop_event):
    # Report submissions cannot wake an outage retry early. Shutdown can.
    stop_event.wait(delay)


def worker_loop(*, stop_event=None):
    stop_event = stop_event if stop_event is not None else Event()
    failures = 0
    WORKER_STATUS.update("starting")
    _worker_log("worker_started")
    try:
        while not stop_event.is_set():
            job_id = None
            try:
                job = claim_job()
                WORKER_STATUS.update("processing" if job else "idle", polled=True)
                if job:
                    job_id, report_id = job
                    _worker_log("job_claimed", job_id)
                    report = job_report(report_id)
                    briefing = call_openai(report)
                    committed = complete_job(job_id, report, briefing)
                    accepted = committed and briefing.get("status") == "accepted"
                    WORKER_STATUS.update("idle", completed=accepted)
                    event = "job_completed" if accepted else "job_rejected" if committed else "lease_lost"
                    _worker_log(event, job_id)
                    failures = 0
                    continue
                failures = 0
            except Exception as error:
                failures += 1
                _worker_log("job_failed" if job_id is not None else "claim_failed", job_id, error)
                if job_id is not None:
                    try:
                        recorded = fail_job(job_id, error)
                        _worker_log("failure_recorded" if recorded else "lease_lost", job_id)
                    except Exception as recording_error:
                        # Leave the durable lease intact for recovery after expiry.
                        _worker_log("failure_recording_failed", job_id, recording_error)
                WORKER_STATUS.update("backoff", errors=failures)
                _worker_backoff(min(30, 2 ** min(failures, 5)), stop_event)
                continue
            JOB_WAKE.wait(2)
            JOB_WAKE.clear()
    finally:
        WORKER_STATUS.update("stopped")
        _worker_log("worker_stopped")


def call_openai(report, system_prompt=SYSTEM_PROMPT):
    if not os.environ.get("OPENAI_API_KEY"):
        raise TerminalJobError("OPENAI_API_KEY is not configured on the server.")
    content = [{"type": "input_text", "text": f"Employee: {report['employee']}\nShift: {report['shift']}\nNotes: {report['notes']}"}]
    request = {
        "model": MODEL,
        "input": [{"role": "system", "content": [{"type": "input_text", "text": system_prompt}]}, {"role": "user", "content": content}],
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": 500,
    }
    http_request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json_bytes(request),
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where()) if certifi else ssl.create_default_context()
        with urllib.request.urlopen(http_request, timeout=30, context=ssl_context) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"OpenAI request failed ({error.code}).") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach OpenAI: {error.reason}") from error
    output = payload.get("output", [])
    text = "".join(item.get("text", "") for item in output if item.get("type") == "message" for item in item.get("content", []) if item.get("type") == "output_text")
    if not text:
        raise RuntimeError("OpenAI returned no briefing.")
    return json.loads(text)


def normalized_notes(notes):
    return _normalized_notes(notes)


def ensure_submission_allowed(store_id, employee, notes):
    return _reports_service().ensure_submission_allowed(store_id, employee, notes)


def database_reports(manager_id):
    return _reports_service().list_for_manager(manager_id)


def _weekly_source(rows, report_count):
    return weekly_source(
        rows, report_count, model=MODEL, prompt=WEEKLY_PROMPT,
        max_reports=WEEKLY_MAX_REPORTS, max_input_chars=WEEKLY_MAX_INPUT_CHARS,
    )


def _weekly_cache_result(row):
    return weekly_cache_result(row)


def _validated_weekly_result(result):
    return validated_weekly_result(result)


def _weekly_service():
    # Share the existing process capacity gate; do not allocate one per request.
    return WeeklyOverviewService(
        ReportsRepository(db_connection), provider=call_openai, capacity=WEEKLY_GENERATION_SLOTS,
        model=MODEL, prompt=WEEKLY_PROMPT, max_reports=WEEKLY_MAX_REPORTS,
        max_input_chars=WEEKLY_MAX_INPUT_CHARS,
    )


def weekly_overview(store_id):
    return _weekly_service().overview(store_id)


def _weekly_overview(store_id):
    # Retain the former internal entry point (its caller already owns capacity).
    return _weekly_service()._generate(store_id)


def validate_report(report):
    return call_openai(report, QUALITY_PROMPT)
