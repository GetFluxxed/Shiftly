"""Cache safety, resource bounds, and accurate weekly-summary coverage."""

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event

import pytest

import reporting
import server
from database import db_connection


def summary(text="Restock complete."):
    return {"summary": text, "wins": ["Freezer restocked."], "risks": [], "follow_up": "Check stock tomorrow."}


def add_report(connection, store_id, notes="Restocked the freezer.", age=0):
    report_id = uuid.uuid4()
    connection.execute(
        "INSERT INTO reports (id, store_id, employee, shift, notes, report_hash, created_at) "
        "VALUES (%s, %s, 'Crew', 'closing', %s, %s, %s)",
        (report_id, store_id, notes, hashlib.sha256(str(report_id).encode()).hexdigest(),
         datetime.now(timezone.utc) - timedelta(seconds=age)),
    )


@pytest.fixture
def stores(isolated_database):
    with db_connection() as connection:
        return [connection.execute(
            "INSERT INTO stores (name, access_code_hash) VALUES (%s, %s) RETURNING id",
            (name, hashlib.sha256(name.encode()).hexdigest()),
        ).fetchone()[0] for name in ("alpha", "beta", "gamma")]


def test_generation_capacity_rejects_without_opening_another_connection(stores, monkeypatch):
    with db_connection() as connection:
        for store in stores:
            add_report(connection, store)
    pids = []
    def connect():
        connection = db_connection()
        pids.append(connection.info.backend_pid)
        return connection
    ready = Barrier(3)
    release = Event()
    def slow_provider(*args):
        ready.wait(timeout=5)
        assert release.wait(timeout=5)
        return summary()
    monkeypatch.setattr(reporting, "db_connection", connect)
    monkeypatch.setattr(reporting, "call_openai", slow_provider)
    with ThreadPoolExecutor(max_workers=3) as executor:
        active = [executor.submit(reporting.weekly_overview, store) for store in stores[:2]]
        try:
            ready.wait(timeout=5)
            overflow = executor.submit(reporting.weekly_overview, stores[2])
            with pytest.raises(reporting.WeeklyOverviewBusy):
                overflow.result(timeout=2)
            assert len(pids) == 2
            with db_connection() as connection:
                states = connection.execute("SELECT state, wait_event_type FROM pg_stat_activity WHERE pid = ANY(%s)", (pids,)).fetchall()
            assert states == [("idle", "Client"), ("idle", "Client")]
        finally:
            release.set()
        for future in active:
            assert future.result(timeout=5)["summary"] == summary()["summary"]
    monkeypatch.setattr(reporting, "call_openai", lambda *args: summary())
    assert reporting.weekly_overview(stores[2])["reportCount"] == 1


def test_another_process_holding_store_lock_gets_a_prompt_busy_response(stores, monkeypatch):
    with db_connection() as connection:
        add_report(connection, stores[0])
    monkeypatch.setattr(reporting, "call_openai", lambda *args: summary())
    with db_connection() as holder:
        holder.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (f"shiftly:weekly:{stores[0]}",))
        with ThreadPoolExecutor(max_workers=1) as executor:
            blocked = executor.submit(reporting.weekly_overview, stores[0])
            try:
                with pytest.raises(reporting.WeeklyOverviewBusy):
                    blocked.result(timeout=2)
                assert reporting.weekly_overview(stores[1])["reportCount"] == 0
            finally:
                holder.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (f"shiftly:weekly:{stores[0]}",))
    assert reporting.weekly_overview(stores[0])["reportCount"] == 1


@pytest.mark.parametrize("invalid", [
    None, [], {}, {"summary": ""}, {"summary": "   "},
    {**summary(), "summary": None}, {**summary(), "summary": 123},
    {**summary(), "wins": "not a list"}, {**summary(), "risks": [None]},
    {**summary(), "follow_up": None},
])
def test_invalid_provider_output_is_not_cached_and_can_recover(stores, monkeypatch, invalid):
    with db_connection() as connection:
        add_report(connection, stores[0])
    monkeypatch.setattr(reporting, "call_openai", lambda *args: invalid)
    with pytest.raises(RuntimeError, match="invalid response"):
        reporting.weekly_overview(stores[0])
    with db_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM weekly_overview_cache").fetchone() == (0,)
    monkeypatch.setattr(reporting, "call_openai", lambda *args: summary("Recovered"))
    assert reporting.weekly_overview(stores[0])["summary"] == "Recovered"


def test_provider_failure_releases_lock_and_capacity(stores, monkeypatch):
    with db_connection() as connection:
        add_report(connection, stores[0])
    def unavailable(*args):
        raise RuntimeError("Provider unavailable")
    monkeypatch.setattr(reporting, "call_openai", unavailable)
    for _ in range(3):
        with pytest.raises(RuntimeError, match="Provider unavailable"):
            reporting.weekly_overview(stores[0])
    monkeypatch.setattr(reporting, "call_openai", lambda *args: summary())
    assert reporting.weekly_overview(stores[0])["reportCount"] == 1


def test_invalid_existing_cache_entry_is_replaced(stores, monkeypatch):
    with db_connection() as connection:
        add_report(connection, stores[0])
    monkeypatch.setattr(reporting, "call_openai", lambda *args: summary())
    reporting.weekly_overview(stores[0])
    with db_connection() as connection:
        connection.execute("UPDATE weekly_overview_cache SET summary = '' WHERE store_id = %s", (stores[0],))
    monkeypatch.setattr(reporting, "call_openai", lambda *args: summary("Repaired"))
    assert reporting.weekly_overview(stores[0])["summary"] == "Repaired"
    with db_connection() as connection:
        assert connection.execute("SELECT summary FROM weekly_overview_cache WHERE store_id = %s", (stores[0],)).fetchone() == ("Repaired",)


@pytest.mark.parametrize(("count", "length", "included"), [(12, 2000, 9), (55, 30, 50), (2, 30, 2)])
def test_coverage_counts_complete_reports_on_cache_miss_and_hit(stores, monkeypatch, count, length, included):
    with db_connection() as connection:
        for index in range(count):
            add_report(connection, stores[0], (f"Report {index}: " + "x" * length)[:length], age=index + 1)
    calls = []
    def capture(report, prompt):
        calls.append(report["notes"])
        return summary()
    monkeypatch.setattr(reporting, "call_openai", capture)
    first = reporting.weekly_overview(stores[0])
    second = reporting.weekly_overview(stores[0])
    assert first == second
    assert first["reportCount"] == count
    assert first["includedReportCount"] == included
    assert first["truncated"] is (included < count)
    assert len(calls) == 1 and len(calls[0]) <= reporting.WEEKLY_MAX_INPUT_CHARS
    assert calls[0].count("Employee:") == included
    assert f"Report {included - 1}:" in calls[0]
    if included < count:
        assert f"Report {included}:" not in calls[0]


def test_cache_is_store_scoped_and_invalidates_on_new_and_expired_reports(stores, monkeypatch):
    with db_connection() as connection:
        for store, text in zip(stores, ("Alpha private notes", "Beta private notes", "Gamma private notes")):
            add_report(connection, store, text)
    calls = []
    def capture(report, prompt):
        calls.append(report["notes"])
        return summary(report["notes"])
    monkeypatch.setattr(reporting, "call_openai", capture)
    for store, text in zip(stores, ("Alpha private notes", "Beta private notes", "Gamma private notes")):
        result = reporting.weekly_overview(store)
        assert text in result["summary"]
        assert reporting.weekly_overview(store) == result
    assert len(calls) == 3
    with db_connection() as connection:
        add_report(connection, stores[0], "New report")
    assert reporting.weekly_overview(stores[0])["reportCount"] == 2
    assert len(calls) == 4
    with db_connection() as connection:
        connection.execute("UPDATE reports SET created_at = NOW() - INTERVAL '8 days' WHERE store_id = %s", (stores[0],))
    result = reporting.weekly_overview(stores[0])
    assert result["reportCount"] == result["includedReportCount"] == 0
    assert result["truncated"] is False
    assert len(calls) == 4


def test_migration_011_upgrades_without_changing_existing_reports(empty_database):
    with db_connection() as connection:
        connection.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
        for migration in sorted((server.ROOT / "migrations").glob("*.sql")):
            if migration.name >= "011_":
                continue
            connection.execute(migration.read_text())
            connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (migration.name,))
        store = connection.execute("INSERT INTO stores (name, access_code_hash) VALUES ('Historical store', %s) RETURNING id", ("a" * 64,)).fetchone()[0]
        add_report(connection, store)
        before = connection.execute("SELECT * FROM reports").fetchall()
    server.initialize_database()
    server.initialize_database()
    with db_connection() as connection:
        assert connection.execute("SELECT * FROM reports").fetchall() == before
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = '011_weekly_overview_cache.sql'").fetchone() == (1,)
