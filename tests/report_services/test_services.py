"""Domain workflows exercised directly, without an HTTP server or database."""

import hashlib
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import BoundedSemaphore

import pytest

from backend.shiftly.reports import (
    ReportRejected, ReportSubmission, ReportsService,
    WeeklyOverviewBusy, WeeklyOverviewService, prepare_report,
)
from backend.shiftly.reports.weekly import weekly_source


STAMP = datetime(2026, 9, 21, tzinfo=timezone.utc)
FIELDS = {"employee": "Nina", "shift": "closing", "notes": "Restocked the freezer."}
SUMMARY = {"summary": "Restock complete.", "wins": ["Stock checked."], "risks": [], "follow_up": "Review tomorrow."}


class MemoryReports:
    def __init__(self):
        self.previous = {}
        self.enqueued = []
        self.reads = []

    def latest_for_employee(self, store_id, employee):
        self.reads.append((store_id, employee))
        return self.previous.get((store_id, employee))

    def enqueue(self, *args):
        self.enqueued.append(args)
        return uuid.UUID(int=len(self.enqueued)), STAMP


def reports_service(repository, *, now=STAMP.timestamp(), wake=lambda: None, cooldown=60, similarity=0.75):
    return ReportsService(
        repository, cooldown_seconds=cooldown, similarity_threshold=similarity,
        clock=lambda: now, wake=wake,
    )


def test_submission_normalizes_then_checks_policy_quality_and_trusted_store():
    events = []
    repository = MemoryReports()
    service = reports_service(repository, wake=lambda: events.append("wake"))
    def policy(store_id, employee, notes):
        events.append(("policy", store_id, employee, notes))
        service.ensure_submission_allowed(store_id, employee, notes)
    def quality(report):
        events.append(("quality", report.copy()))
        return {"status": "accepted"}
    submission = ReportSubmission(ensure_allowed=policy, quality_gate=quality, enqueue=service.queue_report)
    fields = {"employee": "  NiNa \n", "shift": " closing  ", "notes": " Restocked\n the   freezer. ", "store_id": "forged", "manager_id": "forged"}
    saved = submission.submit("trusted-store", fields)
    assert saved == (uuid.UUID(int=1), STAMP)
    assert events == [
        ("policy", "trusted-store", "NiNa", "Restocked the freezer."),
        ("quality", {"employee": "NiNa", "shift": "closing", "notes": "Restocked the freezer."}),
        "wake",
    ]
    assert repository.enqueued == [("NiNa", "closing", "Restocked the freezer.", "trusted-store", hashlib.sha256(b"nina|closing|restocked the freezer.").hexdigest())]
    assert fields["employee"] == "  NiNa \n"  # No mutation of the caller's payload.


@pytest.mark.parametrize("fields,message", [
    ({}, "Enter your name and meaningful shift notes."),
    ({**FIELDS, "employee": " \n", "shift": "invalid"}, "Enter your name and meaningful shift notes."),
    ({**FIELDS, "notes": " \n"}, "Enter your name and meaningful shift notes."),
    ({**FIELDS, "shift": "late"}, "Choose a valid shift."),
])
def test_validation_failure_precedes_every_dependency(fields, message):
    def unexpected(*args):
        pytest.fail("Invalid inputs must not reach policy, AI or persistence.")
    submission = ReportSubmission(ensure_allowed=unexpected, quality_gate=unexpected, enqueue=unexpected)
    with pytest.raises(ValueError, match=message.replace(".", r"\.")):
        submission.submit("trusted-store", fields)


def test_input_limits_are_applied_before_provider_work():
    prepared = prepare_report({**FIELDS, "employee": "N" * 81, "notes": "x" * 2001})
    assert prepared == {"employee": "N" * 80, "shift": "closing", "notes": "x" * 2000}


@pytest.mark.parametrize("reason,expected", [("Add store details.", "Add store details."), ("", "Please add meaningful shift details and try again.")])
def test_quality_rejection_preserves_reason_and_never_enqueues(reason, expected):
    repository = MemoryReports()
    wakes = []
    service = reports_service(repository, wake=lambda: wakes.append(True))
    submission = ReportSubmission(
        ensure_allowed=service.ensure_submission_allowed,
        quality_gate=lambda report: {"status": "rejected", "reason": reason},
        enqueue=service.queue_report,
    )
    with pytest.raises(ReportRejected) as rejected:
        submission.submit("alpha", FIELDS)
    assert rejected.value.reason == expected
    assert repository.enqueued == wakes == []


def test_provider_exception_propagates_without_a_write_or_wakeup():
    repository = MemoryReports()
    service = reports_service(repository, wake=lambda: pytest.fail("No wake on failure"))
    failure = RuntimeError("provider unavailable")
    def provider(report):
        raise failure
    submission = ReportSubmission(ensure_allowed=service.ensure_submission_allowed, quality_gate=provider, enqueue=service.queue_report)
    with pytest.raises(RuntimeError) as raised:
        submission.submit("alpha", FIELDS)
    assert raised.value is failure
    assert repository.enqueued == []


def test_clock_cooldown_boundary_and_similarity_normalization_are_injected():
    repository = MemoryReports()
    repository.previous[("alpha", "Nina")] = ("  RESTOCKED\nTHE FREEZER. ", STAMP)
    recent = reports_service(repository, now=STAMP.timestamp() + 10, cooldown=60)
    with pytest.raises(ValueError, match="Please wait 50 seconds"):
        recent.ensure_submission_allowed("alpha", "Nina", "An unrelated shift update.")
    ready = reports_service(repository, now=STAMP.timestamp() + 60, similarity=1.0)
    with pytest.raises(ValueError, match="too similar"):
        ready.ensure_submission_allowed("alpha", "Nina", "restocked the freezer.")
    ready.ensure_submission_allowed("alpha", "Nina", "The oven requires servicing.")
    recent.ensure_submission_allowed("beta", "Nina", "restocked the freezer.")
    assert repository.reads[-1] == ("beta", "Nina")


def test_policy_failure_prevents_quality_and_queue_calls():
    repository = MemoryReports()
    repository.previous[("alpha", "Nina")] = (FIELDS["notes"], STAMP)
    service = reports_service(repository)
    def unexpected(*args):
        pytest.fail("Policy failures must precede provider and queue calls.")
    submission = ReportSubmission(ensure_allowed=service.ensure_submission_allowed, quality_gate=unexpected, enqueue=unexpected)
    with pytest.raises(ValueError, match="Please wait 60 seconds"):
        submission.submit("alpha", FIELDS)


def test_persistence_failure_does_not_signal_the_worker():
    class FailedRepository:
        def enqueue(self, *args):
            raise RuntimeError("transaction rolled back")
    service = reports_service(FailedRepository(), wake=lambda: pytest.fail("Must not wake after rollback"))
    with pytest.raises(RuntimeError, match="rolled back"):
        service.queue_report("Nina", "closing", "Original notes", "alpha")


class MemoryWeekly:
    def __init__(self, rows):
        self.rows = rows
        self.cache = {}
        self.opened = []
        self.active = 0
        self.saved = []

    @contextmanager
    def weekly_session(self, store_id):
        self.opened.append(store_id)
        self.active += 1
        repository = self
        class Session:
            def source_rows(self, limit):
                rows = repository.rows.get(store_id, [])
                return [(*row, len(rows)) for row in rows[:limit]]

            def cached_result(self, fingerprint):
                return repository.cache.get((store_id, fingerprint))

            def save_result(self, fingerprint, report_count, result):
                repository.saved.append((store_id, report_count, result))
                repository.cache[(store_id, fingerprint)] = tuple(result[key] for key in ("summary", "wins", "risks", "follow_up"))
        try:
            yield Session()
        finally:
            self.active -= 1


def weekly_service(repository, provider, *, capacity=None, model="test-model", prompt="test-weekly", max_reports=2, max_input_chars=200):
    return WeeklyOverviewService(
        repository, provider=provider, capacity=capacity if capacity is not None else BoundedSemaphore(1),
        model=model, prompt=prompt, max_reports=max_reports, max_input_chars=max_input_chars,
    )


def source_rows():
    return [
        ("Crème", "closing", "Restocked café.", STAMP, uuid.UUID(int=1)),
        ("Nina", "opening", "Cleaned.", datetime(2026, 9, 20, tzinfo=timezone.utc), uuid.UUID(int=2)),
        ("Hidden", "midday", "Below the report limit.", STAMP, uuid.UUID(int=3)),
    ]


def test_pre_extraction_cache_fingerprint_and_coverage_are_preserved():
    # Captured by executing only the pure baseline _weekly_source/json_bytes
    # definitions at 2e0e2ec with these explicit settings/rows (before extraction).
    expected_fingerprint = "18fb5081037995f25d638d8ed2c5b0dec972a0b12a46c6c21db51839b0a647db"
    expected_notes = "Employee: Crème\nShift: closing\nDate: 2026-09-21\nNotes: Restocked café.\n\nEmployee: Nina\nShift: opening\nDate: 2026-09-20\nNotes: Cleaned."
    assert weekly_source(source_rows()[:2], 3, model="test-model", prompt="test-weekly", max_reports=2, max_input_chars=200) == (expected_fingerprint, expected_notes, 2)
    repository = MemoryWeekly({"alpha": source_rows()})
    repository.cache[("alpha", expected_fingerprint)] = tuple(SUMMARY[key] for key in ("summary", "wins", "risks", "follow_up"))
    service = weekly_service(repository, lambda *args: pytest.fail("The old valid cache must avoid generation"))
    assert service.overview("alpha") == {**SUMMARY, "reportCount": 3, "includedReportCount": 2, "truncated": True}
    assert repository.saved == [] and repository.active == 0


def test_weekly_caps_complete_reports_and_passes_explicit_prompt():
    repository = MemoryWeekly({"alpha": source_rows()})
    calls = []
    def provider(report, prompt):
        calls.append((report, prompt))
        return SUMMARY
    service = weekly_service(repository, provider, max_input_chars=80)
    result = service.overview("alpha")
    assert result["reportCount"] == 3 and result["includedReportCount"] == 1 and result["truncated"]
    assert calls == [({"employee": "store team", "shift": "weekly overview", "notes": "Employee: Crème\nShift: closing\nDate: 2026-09-21\nNotes: Restocked café."}, "test-weekly")]
    assert service.overview("alpha") == result
    assert len(calls) == 1


def test_oversized_first_source_is_not_sent_or_cached():
    repository = MemoryWeekly({"alpha": source_rows()})
    service = weekly_service(repository, lambda *args: pytest.fail("No partial source may be generated"), max_input_chars=10)
    with pytest.raises(RuntimeError, match="too large"):
        service.overview("alpha")
    assert repository.saved == [] and repository.active == 0


def test_empty_weekly_source_has_no_provider_or_cache_writes():
    repository = MemoryWeekly({})
    result = weekly_service(repository, lambda *args: pytest.fail("Empty source must avoid AI")).overview("alpha")
    assert result == {"summary": "No shift reports have been submitted in the last seven days.", "reportCount": 0, "includedReportCount": 0, "truncated": False}
    assert repository.saved == []


@pytest.mark.parametrize("error", [RuntimeError("provider unavailable"), ValueError("invalid JSON")])
def test_weekly_failure_releases_the_session_and_shared_capacity(error):
    repository = MemoryWeekly({"alpha": source_rows()})
    capacity = BoundedSemaphore(1)
    def failed(*args):
        raise error
    first = weekly_service(repository, failed, capacity=capacity)
    with pytest.raises(type(error)) as raised:
        first.overview("alpha")
    assert raised.value is error and repository.active == 0 and repository.saved == []
    second = weekly_service(repository, lambda *args: SUMMARY, capacity=capacity)
    assert second.overview("alpha")["summary"] == SUMMARY["summary"]


def test_exhausted_capacity_never_opens_a_repository_session():
    repository = MemoryWeekly({"alpha": source_rows()})
    capacity = BoundedSemaphore(1)
    capacity.acquire()
    service = weekly_service(repository, lambda *args: SUMMARY, capacity=capacity)
    try:
        with pytest.raises(WeeklyOverviewBusy):
            service.overview("alpha")
        assert repository.opened == []
    finally:
        capacity.release()


@pytest.mark.parametrize("changed", [{"model": "new-model"}, {"prompt": "new-prompt"}, {"max_reports": 3}, {"max_input_chars": 300}])
def test_weekly_configuration_changes_invalidate_cache(changed):
    repository = MemoryWeekly({"alpha": source_rows()})
    calls = []
    def provider(*args):
        calls.append(True)
        return SUMMARY
    weekly_service(repository, provider).overview("alpha")
    weekly_service(repository, provider, **changed).overview("alpha")
    assert len(calls) == 2


def test_services_import_and_construct_without_legacy_modules_or_io():
    # A fresh process avoids pytest's pre-imported legacy fixtures masking a
    # backwards dependency. No runtime modules or threads are needed here.
    result = subprocess.run([sys.executable, "-c", '''
import builtins, sys, threading
original_import = builtins.__import__
blocked = {"server", "routes", "reporting", "config", "database", "auth", "security", "store_service", "fastapi", "psycopg"}
def checked_import(name, *args, **kwargs):
    if name.split(".")[0] in blocked:
        raise AssertionError("Forbidden runtime dependency: " + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = checked_import
def no_io(*args, **kwargs):
    raise AssertionError("Construction must not use runtime resources")
threading.Thread.start = no_io
from backend.shiftly.reports import ReportsRepository, ReportsService, ReportSubmission, WeeklyOverviewService
repository = ReportsRepository(no_io)
service = ReportsService(repository, cooldown_seconds=60, similarity_threshold=.75, clock=no_io, wake=no_io)
ReportSubmission(ensure_allowed=service.ensure_submission_allowed, quality_gate=no_io, enqueue=service.queue_report)
WeeklyOverviewService(repository, provider=no_io, capacity=None, model="test", prompt="test", max_reports=2, max_input_chars=200)
assert not blocked.intersection(sys.modules)
print("isolated")
'''], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "isolated"
