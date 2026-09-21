"""Direct service/repository integration against disposable PostgreSQL."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BoundedSemaphore

import psycopg
import pytest

import reporting
from backend.shiftly.reports import ReportSubmission, ReportsRepository, ReportsService, WeeklyOverviewService
from database import db_connection


@pytest.fixture
def context(isolated_database):
    with db_connection() as connection:
        stores = [connection.execute(
            "INSERT INTO stores (name, access_code_hash) VALUES (%s, %s) RETURNING id",
            (name, hashlib.sha256(name.encode()).hexdigest()),
        ).fetchone()[0] for name in ("alpha", "beta", "gamma")]
        managers = [connection.execute(
            "INSERT INTO manager_users (username, password_salt, password_hash) VALUES (%s, 'test-salt', 'test-hash') RETURNING id",
            (name,),
        ).fetchone()[0] for name in ("multi-store", "other-manager")]
        for manager, store in ((managers[0], stores[0]), (managers[0], stores[1]), (managers[1], stores[2])):
            connection.execute("INSERT INTO store_memberships (manager_user_id, store_id, role) VALUES (%s, %s, 'manager')", (manager, store))
    repository = ReportsRepository(db_connection)
    service = ReportsService(repository, cooldown_seconds=60, similarity_threshold=.75, clock=lambda: 0, wake=lambda: None)
    return stores, managers, repository, service


def counts():
    with db_connection() as connection:
        return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("reports", "briefing_jobs"))


def test_commit_is_visible_before_wakeup_and_duplicate_does_not_wake(context):
    stores, _, _, service = context
    wakes = []
    service.wake = lambda: wakes.append(counts())
    saved = service.queue_report("Nina", "closing", "Restocked the freezer.", stores[0])
    assert wakes == [(1, 1)]
    with pytest.raises(ValueError, match="matches a previous submission"):
        service.queue_report("NINA", "closing", "RESTOCKED THE FREEZER.", stores[0])
    assert wakes == [(1, 1)]
    other = service.queue_report("Nina", "closing", "Restocked the freezer.", stores[1])
    assert other[0] != saved[0]
    assert wakes[-1] == (2, 2)


def test_queue_rolls_back_report_if_job_insertion_fails(context):
    stores, _, _, service = context
    service.wake = lambda: pytest.fail("A rolled back enqueue must not wake the worker")
    with db_connection() as connection:
        connection.execute("ALTER TABLE briefing_jobs ADD CONSTRAINT reject_service_test_job CHECK (FALSE)")
    with pytest.raises(psycopg.errors.CheckViolation):
        service.queue_report("Nina", "closing", "Original notes", stores[0])
    assert counts() == (0, 0)


def test_concurrent_duplicate_service_submissions_commit_only_once(context):
    stores, _, _, service = context
    ready = Barrier(2)
    def submit():
        ready.wait(timeout=5)
        try:
            service.queue_report("Nina", "closing", "Original notes", stores[0])
            return "saved"
        except ValueError as error:
            assert "matches a previous submission" in str(error)
            return "duplicate"
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: submit(), range(2))) == ["duplicate", "saved"]
    assert counts() == (1, 1)


def test_policy_lookup_uses_store_and_case_insensitive_employee(context):
    stores, _, repository, service = context
    _, created_at = service.queue_report("Nina", "closing", "Alpha notes", stores[0])
    assert repository.latest_for_employee(stores[0], "NINA") == ("Alpha notes", created_at)
    assert repository.latest_for_employee(stores[1], "Nina") is None
    assert repository.latest_for_employee(stores[0], "Somebody else") is None
    service.clock = lambda: created_at.timestamp() + 30
    with pytest.raises(ValueError, match="Please wait 30 seconds"):
        service.ensure_submission_allowed(stores[0], "NINA", "New details")
    service.ensure_submission_allowed(stores[1], "Nina", "New details")


def test_manager_inbox_keeps_membership_scope_and_existing_worker_result(context):
    stores, managers, _, service = context
    notes = ["Alpha private notes", "Beta private notes", "Gamma private notes"]
    saved = [service.queue_report("Nina", "closing", text, store)[0] for store, text in zip(stores, notes)]
    job_id, report_id = reporting.claim_job()
    assert report_id == saved[0]
    assert job_id.lease_token is not None
    assert reporting.complete_job(job_id, reporting.job_report(report_id), {
        "status": "accepted", "summary": "Alpha briefing", "wins": [], "risks": [], "follow_up": "Review stock",
    })
    inbox = service.list_for_manager(managers[0])
    assert {report["notes"] for report in inbox} == set(notes[:2])
    completed = next(report for report in inbox if report["id"] == str(saved[0]))
    assert completed["status"] == "completed" and completed["error"] is None
    assert completed["briefing"] == {"summary": "Alpha briefing", "wins": [], "risks": [], "follow_up": "Review stock"}
    pending = next(report for report in inbox if report["id"] == str(saved[1]))
    assert pending["briefing"] is None and pending["status"] == "pending"
    assert [report["notes"] for report in service.list_for_manager(managers[1])] == notes[2:]
    assert service.list_for_manager(max(managers) + 1) == []


def test_submission_ignores_payload_store_and_queues_only_in_authorized_store(context):
    stores, _, _, service = context
    provider_calls = []
    def quality(report):
        provider_calls.append(report.copy())
        return {"status": "accepted"}
    submission = ReportSubmission(ensure_allowed=service.ensure_submission_allowed, quality_gate=quality, enqueue=service.queue_report)
    submission.submit(stores[0], {"employee": "Nina", "shift": "closing", "notes": "  Original\n notes  ", "store_id": str(stores[1])})
    with db_connection() as connection:
        assert connection.execute("SELECT store_id, notes FROM reports").fetchall() == [(stores[0], "Original notes")]
    assert provider_calls == [{"employee": "Nina", "shift": "closing", "notes": "Original notes"}]
    assert counts() == (1, 1)


def test_weekly_service_keeps_selected_store_cache_and_provider_outside_transaction(context):
    stores, _, _, reports = context
    for store, text in zip(stores, ("Alpha notes", "Beta notes", "Gamma notes")):
        reports.queue_report("Nina", "closing", text, store)
    connections = []
    def connect():
        connection = db_connection()
        connections.append(connection)
        return connection
    calls = []
    def provider(report, prompt):
        assert connections[-1].info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        calls.append((report, prompt))
        return {"summary": report["notes"], "wins": [], "risks": [], "follow_up": "Review"}
    weekly = WeeklyOverviewService(
        ReportsRepository(connect), provider=provider, capacity=BoundedSemaphore(2),
        model="test-model", prompt="explicit-prompt", max_reports=50, max_input_chars=20_000,
    )
    alpha = weekly.overview(stores[0])
    assert "Alpha notes" in alpha["summary"] and "Beta notes" not in alpha["summary"]
    assert weekly.overview(stores[0]) == alpha and len(calls) == 1
    beta = weekly.overview(stores[1])
    assert "Beta notes" in beta["summary"] and "Alpha notes" not in beta["summary"]
    assert len(calls) == 2 and all(prompt == "explicit-prompt" for _, prompt in calls)
    assert all(connection.closed for connection in connections)
    with db_connection() as connection:
        assert {row[0] for row in connection.execute("SELECT store_id FROM weekly_overview_cache").fetchall()} == set(stores[:2])


def test_weekly_query_excludes_expired_sources_and_cache_invalidates(context):
    stores, _, repository, service = context
    first, _ = service.queue_report("Nina", "closing", "Old notes", stores[0])
    with db_connection() as connection:
        connection.execute("UPDATE reports SET created_at = NOW() - INTERVAL '8 days' WHERE id = %s", (first,))
    second, _ = service.queue_report("Nina", "closing", "Recent notes", stores[0])
    calls = []
    def provider(report, prompt):
        calls.append(report["notes"])
        return {"summary": "Summary", "wins": [], "risks": [], "follow_up": "Review"}
    weekly = WeeklyOverviewService(repository, provider=provider, capacity=BoundedSemaphore(1), model="test", prompt="test", max_reports=50, max_input_chars=20_000)
    assert weekly.overview(stores[0])["reportCount"] == 1
    assert "Recent notes" in calls[0] and "Old notes" not in calls[0]
    with db_connection() as connection:
        connection.execute("UPDATE reports SET notes = 'Corrected recent notes' WHERE id = %s", (second,))
    weekly.overview(stores[0])
    assert len(calls) == 2 and "Corrected recent notes" in calls[1]
