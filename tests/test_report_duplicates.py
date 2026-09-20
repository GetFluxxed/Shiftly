"""Migration, transaction, and concurrency checks against disposable PostgreSQL."""

import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import psycopg
from psycopg import sql
import pytest

import reporting
import server
from database import db_connection


def add_store(connection, name):
    return connection.execute(
        "INSERT INTO stores (name, access_code_hash) VALUES (%s, %s) RETURNING id",
        (name, hashlib.sha256(name.encode()).hexdigest()),
    ).fetchone()[0]


def enqueue(store_id):
    return reporting.queue_report("Nina", "closing", "Restocked the freezer.", store_id)


@pytest.fixture
def stores(isolated_database):
    with db_connection() as connection:
        return [add_store(connection, name) for name in ("alpha", "beta")]


def assert_report_and_job_counts(count):
    with db_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM reports").fetchone() == (count,)
        assert connection.execute("SELECT COUNT(*) FROM briefing_jobs").fetchone() == (count,)


def test_identical_reports_in_different_stores_are_independent(stores):
    first, _ = enqueue(stores[0])
    second, _ = enqueue(stores[1])
    assert first != second
    assert_report_and_job_counts(2)
    with pytest.raises(ValueError, match="matches a previous submission"):
        enqueue(stores[0])
    assert_report_and_job_counts(2)


@pytest.mark.parametrize("same_store", [True, False])
def test_simultaneous_identical_submissions_are_scoped_and_atomic(stores, same_store):
    start = Barrier(2)
    def submit(store_id):
        start.wait(timeout=5)
        try:
            enqueue(store_id)
            return "saved"
        except ValueError as error:
            assert "matches a previous submission" in str(error)
            return "duplicate"
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, [stores[0], stores[0] if same_store else stores[1]]))
    assert sorted(outcomes) == (["duplicate", "saved"] if same_store else ["saved", "saved"])
    assert_report_and_job_counts(1 if same_store else 2)


def test_job_failure_rolls_back_report_and_does_not_wake_worker(stores):
    with db_connection() as connection:
        connection.execute("ALTER TABLE briefing_jobs ADD CONSTRAINT reject_test_jobs CHECK (false)")
    with pytest.raises(psycopg.errors.CheckViolation):
        enqueue(stores[0])
    assert_report_and_job_counts(0)
    assert not reporting.JOB_WAKE.is_set()


def test_upgrade_preserves_existing_reports_briefings_jobs_and_legacy_rows(empty_database):
    old_report = uuid.uuid4()
    legacy_report = uuid.uuid4()
    report_hash = hashlib.sha256(b"nina|closing|restocked the freezer.").hexdigest()
    with db_connection() as connection:
        connection.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
        for migration in sorted((server.ROOT / "migrations").glob("*.sql")):
            if migration.name >= "010_":
                continue
            connection.execute(migration.read_text())
            connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (migration.name,))
        alpha, beta = [add_store(connection, name) for name in ("alpha", "beta")]
        connection.execute(
            "INSERT INTO reports (id, store_id, employee, shift, notes, report_hash) VALUES (%s, %s, %s, %s, %s, %s)",
            (old_report, alpha, "Nina", "closing", "Restocked the freezer.", report_hash),
        )
        connection.execute("INSERT INTO briefing_jobs (report_id, status, attempts) VALUES (%s, 'completed', 1)", (old_report,))
        connection.execute(
            "INSERT INTO briefings (report_id, source_notes, summary, follow_up, model) VALUES (%s, %s, %s, %s, %s)",
            (old_report, "Restocked the freezer.", "Restock complete.", "None.", "test-model"),
        )
        connection.execute(
            "INSERT INTO reports (id, employee, shift, notes, report_hash) VALUES (%s, 'Legacy', 'other', 'Historical notes', %s)",
            (legacy_report, "a" * 64),
        )
        before_reports = connection.execute("SELECT * FROM reports ORDER BY id").fetchall()
        before_jobs = connection.execute("SELECT * FROM briefing_jobs ORDER BY id").fetchall()
        before_briefings = connection.execute("SELECT * FROM briefings ORDER BY id").fetchall()
    server.initialize_database()
    server.initialize_database()
    with db_connection() as connection:
        assert connection.execute("SELECT * FROM reports ORDER BY id").fetchall() == before_reports
        assert connection.execute("SELECT * FROM briefing_jobs ORDER BY id").fetchall() == before_jobs
        assert connection.execute("SELECT * FROM briefings ORDER BY id").fetchall() == before_briefings
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = '010_store_scoped_report_hash.sql'").fetchone() == (1,)
    enqueue(beta)
    with pytest.raises(ValueError, match="matches a previous submission"):
        enqueue(alpha)
    with pytest.raises(psycopg.errors.UniqueViolation):
        with db_connection() as connection:
            connection.execute(
                "INSERT INTO reports (id, employee, shift, report_hash) VALUES (%s, 'Legacy duplicate', 'other', %s)",
                (uuid.uuid4(), "a" * 64),
            )


def test_database_fixture_preserves_existing_application_schema(request):
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.fail("Set TEST_DATABASE_URL to a disposable PostgreSQL database.")
    schema = "fixture_sentinel_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        admin.execute(sql.SQL("CREATE TABLE {}.reports (notes TEXT)").format(sql.Identifier(schema)))
        admin.execute(sql.SQL("INSERT INTO {}.reports VALUES ('Preserve this record')").format(sql.Identifier(schema)))
    def check_and_cleanup():
        with psycopg.connect(dsn, autocommit=True) as admin:
            try:
                assert admin.execute(sql.SQL("SELECT notes FROM {}.reports").format(sql.Identifier(schema))).fetchall() == [("Preserve this record",)]
            finally:
                admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
    request.addfinalizer(check_and_cleanup)
    request.getfixturevalue("isolated_database")
    with db_connection() as connection:
        current_schema = connection.execute("SELECT current_schema()").fetchone()[0]
        assert current_schema.startswith("shiftly_test_")
        assert current_schema != schema
        assert connection.execute("SELECT COUNT(*) FROM reports").fetchone() == (0,)
