"""Compatibility facade for legacy root reporting imports."""

import time
from threading import BoundedSemaphore, Event

from backend.shiftly.reports import ReportsRepository, ReportsService, WeeklyOverviewBusy, WeeklyOverviewService
from backend.shiftly.reports.service import normalized_notes as _normalized_notes
from backend.shiftly.reports.weekly import validated_weekly_result, weekly_cache_result, weekly_source
from backend.shiftly.jobs import reporting as _briefing_jobs
from backend.shiftly.runtime.prompts import SYSTEM_PROMPT, QUALITY_PROMPT, WEEKLY_PROMPT
from backend.shiftly.runtime.provider import (
    ProviderConfigurationError as _ProviderConfigurationError,
    call_openai as _runtime_call_openai,
    json_bytes as _runtime_json_bytes,
)
from config import load_settings
from database import db_connection

SETTINGS = load_settings()
MODEL = SETTINGS.openai_model
REPORT_COOLDOWN_SECONDS = SETTINGS.report_cooldown_seconds
JOB_WAKE = Event()
MAX_JOB_ATTEMPTS = _briefing_jobs.MAX_JOB_ATTEMPTS
JOB_LEASE_SECONDS = _briefing_jobs.JOB_LEASE_SECONDS
JOB_RETRY_SECONDS = _briefing_jobs.JOB_RETRY_SECONDS
WORKER_STALE_SECONDS = _briefing_jobs.WORKER_STALE_SECONDS
WORKER_LOG = _briefing_jobs.WORKER_LOG


WORKER_STATUS = _briefing_jobs.WorkerStatus()


def worker_status():
    return WORKER_STATUS.snapshot()


REPORT_SIMILARITY_THRESHOLD = 0.75
WEEKLY_MAX_REPORTS = 50
WEEKLY_MAX_INPUT_CHARS = 20_000
WEEKLY_GENERATION_SLOTS = BoundedSemaphore(2)


def _reports_service():
    # Compose per call so legacy callers/tests can replace these dependencies.
    # Creating a service opens no connection and creates no worker resources.
    return ReportsService(
        ReportsRepository(db_connection), cooldown_seconds=REPORT_COOLDOWN_SECONDS,
        similarity_threshold=REPORT_SIMILARITY_THRESHOLD, clock=time.time, wake=JOB_WAKE.set,
    )


def queue_report(employee, shift, notes, store_id, *, actor_token=None, accounts=None, legacy_credentials=None):
    return _reports_service().queue_report(employee, shift, notes, store_id,
                                         actor_token=actor_token, accounts=accounts, legacy_credentials=legacy_credentials)


def normalized_notes(notes):
    return _normalized_notes(notes)


def ensure_submission_allowed(store_id, employee, notes):
    return _reports_service().ensure_submission_allowed(store_id, employee, notes)


def database_reports(manager_id):
    return _reports_service().list_for_manager(manager_id)


def account_reports(token, accounts):
    return _reports_service().list_for_actor(token, accounts)


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


# Package implementations back the legacy root API. Resolve facade defaults at
# call time so supported monkeypatch/test contracts continue to work.
ClaimedJobId = _briefing_jobs.ClaimedJobId
TerminalJobError = _briefing_jobs.TerminalJobError
WorkerStatus = _briefing_jobs.WorkerStatus


def json_bytes(value):
    return _runtime_json_bytes(value)


def _failure_kind(error):
    return _briefing_jobs.failure_kind(error)


def _worker_log(event, job_id=None, error=None):
    return _briefing_jobs.worker_log(event, job_id, error, logger=WORKER_LOG)


def claim_job(*, connect=None):
    return _briefing_jobs.claim_job(
        connect=db_connection if connect is None else connect,
        max_attempts=MAX_JOB_ATTEMPTS, lease_seconds=JOB_LEASE_SECONDS,
        retry_seconds=JOB_RETRY_SECONDS,
    )


def job_report(report_id, *, connect=None):
    return _briefing_jobs.job_report(
        report_id, connect=db_connection if connect is None else connect,
    )


def complete_job(job_id, report, briefing, *, connect=None, model=None):
    return _briefing_jobs.complete_job(
        job_id, report, briefing,
        connect=db_connection if connect is None else connect,
        model=MODEL if model is None else model,
        lease_seconds=JOB_LEASE_SECONDS, max_attempts=MAX_JOB_ATTEMPTS,
        retry_seconds=JOB_RETRY_SECONDS,
    )


def fail_job(job_id, error, *, connect=None):
    return _briefing_jobs.fail_job(
        job_id, error, connect=db_connection if connect is None else connect,
        lease_seconds=JOB_LEASE_SECONDS, max_attempts=MAX_JOB_ATTEMPTS,
        retry_seconds=JOB_RETRY_SECONDS,
    )


def _worker_backoff(delay, stop_event):
    return _briefing_jobs.worker_backoff(delay, stop_event)


def worker_loop(*, stop_event=None, claim=None, load_report=None, provider=None,
                complete=None, fail=None, status=None, wake=None, backoff=None,
                poll_seconds=2):
    return _briefing_jobs.worker_loop(
        stop_event=stop_event,
        claim=claim if claim is not None else claim_job,
        load_report=load_report if load_report is not None else job_report,
        provider=provider if provider is not None else call_openai,
        complete=complete if complete is not None else complete_job,
        fail=fail if fail is not None else fail_job,
        status=status if status is not None else WORKER_STATUS,
        wake=wake if wake is not None else JOB_WAKE,
        backoff=backoff if backoff is not None else _worker_backoff,
        poll_seconds=poll_seconds,
        log=_worker_log,
    )


def call_openai(report, system_prompt=SYSTEM_PROMPT, *, api_key=None, model=None):
    try:
        return _runtime_call_openai(
            report, system_prompt, api_key=api_key,
            model=MODEL if model is None else model,
        )
    except _ProviderConfigurationError as error:
        raise TerminalJobError(str(error)) from error
