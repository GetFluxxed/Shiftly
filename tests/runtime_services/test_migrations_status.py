import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import psycopg
import pytest

import reporting
from backend.shiftly.jobs.status import DatabaseWorkerStatus, PersistentWorkerStatus
from backend.shiftly.runtime.application import build_runtime
from backend.shiftly.runtime.database import DatabaseResources
from backend.shiftly.runtime.migrate import MIGRATIONS, migrate, schema_status
from config import Settings
from database import db_connection


def test_fresh_and_concurrent_migrations_are_serialized(empty_database):
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: migrate(db_connection), range(2)))
    assert sorted(len(result) for result in results) == [0, 13]
    assert schema_status(db_connection) == {"status": "ok", "schemaReady": True, "pendingMigrations": []}
    assert migrate(db_connection) == []


def test_migration_failure_is_atomic(empty_database, tmp_path):
    (tmp_path / "001_first.sql").write_text("CREATE TABLE temporary_upgrade (id int);")
    (tmp_path / "002_bad.sql").write_text("NOT VALID SQL;")
    with pytest.raises(psycopg.errors.SyntaxError):
        migrate(db_connection, directory=tmp_path)
    with db_connection() as connection:
        assert connection.execute("SELECT to_regclass('temporary_upgrade'), to_regclass('schema_migrations')").fetchone() == (None, None)


def test_migration_lock_wait_is_bounded(empty_database):
    with db_connection() as holder:
        holder.execute("SELECT pg_advisory_xact_lock(hashtext(current_database()), hashtext(current_schema() || ':shiftly-migrate'))")
        with pytest.raises(psycopg.errors.LockNotAvailable):
            migrate(db_connection, lock_timeout_ms=50)
    assert len(migrate(db_connection)) == 13


def test_runtime_migration_preserves_existing_reports(empty_database, tmp_path):
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name < "013_":
            (tmp_path / path.name).write_text(path.read_text())
    migrate(db_connection, directory=tmp_path)
    with db_connection() as connection:
        store = connection.execute("INSERT INTO stores (name,access_code_hash) VALUES ('Upgrade','upgrade') RETURNING id").fetchone()[0]
    report_id, _ = reporting.queue_report("Crew", "closing", "Original notes survive upgrade.", store)
    with db_connection() as connection:
        before = connection.execute("SELECT * FROM reports WHERE id=%s", (report_id,)).fetchone()
    assert migrate(db_connection) == ["013_runtime_operations.sql"]
    with db_connection() as connection:
        assert connection.execute("SELECT * FROM reports WHERE id=%s", (report_id,)).fetchone() == before
        assert connection.execute("SELECT status,attempts FROM briefing_jobs WHERE report_id=%s", (report_id,)).fetchone() == ("pending", 0)


def test_application_runtime_refuses_schema_without_migrating(empty_database):
    runtime = build_runtime(settings=Settings(database_url=empty_database), provider=lambda *a: None)
    with pytest.raises(RuntimeError, match="schema is not ready"):
        runtime.open()
    assert runtime.resources.pool.closed
    with db_connection() as connection:
        assert connection.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None


def test_migration_cli_reads_explicit_environment(empty_database, child_environment):
    result = subprocess.run([sys.executable, "-m", "backend.shiftly.runtime.migrate"], env=child_environment(empty_database), capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "applied 13 migration(s)" in result.stdout
    assert schema_status(db_connection)["schemaReady"]


def test_schema_health_does_not_expose_database_errors():
    def failed():
        raise psycopg.OperationalError("password and private notes")
    result = schema_status(failed)
    assert result["status"] == "degraded"
    assert "password" not in repr(result)


def test_worker_observations_distinguish_polling_completion_and_staleness(runtime_settings):
    reader = DatabaseWorkerStatus(db_connection, stale_seconds=60)
    assert reader()["state"] == "not_started"
    writer = PersistentWorkerStatus(db_connection)
    writer.update("idle", polled=True)
    status = reader()
    assert status["status"] == "ok" and status["completedJobs"] == 0
    assert status["lastCompletionAgeSeconds"] is None
    with db_connection() as connection:
        before = connection.execute("SELECT observed_at FROM runtime_worker_status").fetchone()[0]
    reader(); reader()
    with db_connection() as connection:
        assert connection.execute("SELECT observed_at FROM runtime_worker_status").fetchone()[0] == before
    writer.update("idle", completed=True)
    assert reader()["completedJobs"] == 1
    writer.update("backoff", errors=2)
    assert reader()["status"] == "degraded" and reader()["consecutiveErrors"] == 2
    writer.update("processing", polled=True)
    with db_connection() as connection:
        connection.execute("UPDATE runtime_worker_status SET observed_at=NOW()-INTERVAL '61 seconds'")
    assert reader()["state"] == "stalled"
    writer.update("stopped")
    assert not reader()["running"]


def test_old_worker_cannot_overwrite_new_instance(runtime_settings):
    old = PersistentWorkerStatus(db_connection)
    old.update("idle", polled=True)
    new = PersistentWorkerStatus(db_connection)
    new.update("idle", polled=True)
    old.update("stopped", completed=True, errors=10)
    status = DatabaseWorkerStatus(db_connection)()
    assert status["state"] == "idle" and status["completedJobs"] == 0 and status["consecutiveErrors"] == 0


def test_worker_queue_age_excludes_terminal_work(runtime_settings):
    with db_connection() as connection:
        store = connection.execute("INSERT INTO stores (name,access_code_hash) VALUES ('Queue','queue') RETURNING id").fetchone()[0]
    reporting.queue_report("Crew", "closing", "Restocked the freezer.", store)
    reader = DatabaseWorkerStatus(db_connection)
    assert reader()["queueDepth"] == 1
    assert reader()["oldestQueuedAgeSeconds"] >= 0
    job, _ = reporting.claim_job()
    reporting.fail_job(job, reporting.TerminalJobError("rejected"))
    assert reader()["queueDepth"] == 0
    assert reader()["oldestQueuedAgeSeconds"] is None


def test_worker_publication_failure_is_sanitized_and_reader_degrades(caplog):
    def failed():
        raise psycopg.OperationalError("password=secret private report notes")
    writer = PersistentWorkerStatus(failed)
    writer.update("idle", polled=True)
    assert not writer.registered
    status = DatabaseWorkerStatus(failed)()
    assert status["state"] == "unavailable" and status["status"] == "degraded"
    assert "secret" not in caplog.text and "private report" not in caplog.text


def test_lost_ownership_cannot_publish_even_if_first_registration_failed(runtime_settings):
    def lost():
        raise psycopg.OperationalError("ownership lost")
    old = PersistentWorkerStatus(db_connection, ownership_check=lost)
    newer = PersistentWorkerStatus(db_connection)
    newer.update("idle", polled=True)
    old.update("starting")
    with db_connection() as connection:
        assert connection.execute("SELECT instance_id FROM runtime_worker_status").fetchone()[0] == newer.instance_id


def test_concurrent_migration_commands_share_database_lock(empty_database, child_environment):
    command = [sys.executable, "-m", "backend.shiftly.runtime.migrate"]
    environment = child_environment(empty_database, DB_LOCK_TIMEOUT_MS="2000")
    first = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    second = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        results = [(process, process.communicate(timeout=10)) for process in (first, second)]
        assert all(process.returncode == 0 for process, _ in results), results
        assert sorted(output[0].strip() for _, output in results) == [
            "Migrations ready; applied 0 migration(s).", "Migrations ready; applied 13 migration(s).",
        ]
    finally:
        for process in (first, second):
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=3)


def test_legacy_migration_wrapper_uses_configured_lock_budget(empty_database, monkeypatch):
    import server
    monkeypatch.setattr(server, "SETTINGS", replace(server.SETTINGS, db_lock_timeout_ms=50))
    with db_connection() as holder:
        holder.execute("SELECT pg_advisory_xact_lock(hashtext(current_database()), hashtext(current_schema() || ':shiftly-migrate'))")
        with pytest.raises(psycopg.errors.LockNotAvailable):
            server.initialize_database()
    assert len(server.initialize_database()) == 13
