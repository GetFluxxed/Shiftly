import os
import subprocess
import sys
import time
from dataclasses import replace

import psycopg
import pytest
from psycopg_pool import PoolClosed, PoolTimeout

from backend.shiftly.reports import WeeklyOverviewBusy
from backend.shiftly.runtime.application import build_runtime
from backend.shiftly.runtime.database import DatabaseResources, connect_dedicated
from backend.shiftly.runtime.provider import make_provider
from config import Settings
from database import db_connection


ACCEPTED = {"status": "accepted", "summary": "Restocked.", "wins": [], "risks": [], "follow_up": "Review tomorrow."}


def test_pool_checkout_is_bounded_and_returns_capacity(runtime_settings):
    settings = replace(runtime_settings, db_pool_max_size=1, db_pool_timeout=0.15)
    with DatabaseResources(settings) as resources:
        with resources.connection() as first:
            start = time.monotonic()
            with pytest.raises(PoolTimeout):
                with resources.connection():
                    pytest.fail("exceeded pool maximum")
            assert time.monotonic() - start < 1
            assert first.execute("SELECT 1").fetchone() == (1,)
        with resources.connection() as second:
            assert second.execute("SELECT 1").fetchone() == (1,)
        assert resources.pool.get_stats()["pool_size"] == 1
    with pytest.raises(PoolClosed):
        with resources.connection():
            pass


def test_pool_rolls_back_and_resets_session_state(runtime_settings):
    settings = replace(runtime_settings, db_pool_max_size=1)
    with DatabaseResources(settings) as resources:
        with pytest.raises(RuntimeError):
            with resources.connection() as connection:
                connection.execute("INSERT INTO stores (name, access_code_hash) VALUES ('Rolled back', 'rollback')")
                raise RuntimeError("abort")
        with resources.connection() as connection:
            connection.execute("SELECT pg_advisory_lock(9412345)")
            connection.execute("SET application_name = 'should-not-leak'")
            connection.execute("CREATE TEMP TABLE should_not_leak (id int)")
            # Exercise resetting a caller-changed autocommit mode as well.
            connection.commit()
            connection.autocommit = True
        with resources.connection() as connection:
            assert not connection.autocommit
            assert connection.execute("SELECT count(*) FROM stores WHERE access_code_hash='rollback'").fetchone()[0] == 0
            assert connection.execute("SHOW application_name").fetchone()[0] != "should-not-leak"
            assert connection.execute("SELECT to_regclass('pg_temp.should_not_leak')").fetchone()[0] is None
            assert connection.execute("SELECT current_schema()").fetchone()[0].startswith("shiftly_test_")
        with connect_dedicated(settings) as observer:
            assert observer.execute("SELECT pg_try_advisory_lock(9412345)").fetchone()[0]


def test_query_and_lock_waits_are_bounded(runtime_settings):
    settings = replace(runtime_settings, db_statement_timeout_ms=150, db_lock_timeout_ms=75)
    with DatabaseResources(settings) as resources:
        with pytest.raises(psycopg.errors.QueryCanceled):
            with resources.connection() as connection:
                connection.execute("SELECT pg_sleep(2)")
        with connect_dedicated(settings) as holder:
            holder.execute("SELECT pg_advisory_xact_lock(23456789)")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                with resources.connection() as connection:
                    connection.execute("SELECT pg_advisory_xact_lock(23456789)")
        with resources.connection() as connection:
            assert connection.execute("SELECT 1").fetchone() == (1,)


def test_dedicated_capacity_and_close_release_locks(runtime_settings):
    settings = replace(runtime_settings, db_pool_timeout=0.1)
    with DatabaseResources(settings) as resources:
        with resources.weekly_connection() as first, resources.weekly_connection():
            first.execute("SELECT pg_advisory_lock(9812345)")
            with pytest.raises(PoolTimeout):
                with resources.weekly_connection():
                    pass
        assert first.closed
        with resources.weekly_connection() as connection:
            assert connection.execute("SELECT pg_try_advisory_lock(9812345)").fetchone()[0]
    assert connection.closed


class CancelWork(BaseException):
    pass


@pytest.mark.parametrize("failure", [RuntimeError, CancelWork, None])
def test_weekly_sessions_release_locks_after_all_provider_outcomes(runtime_settings, failure):
    calls = []
    def provider(report, prompt):
        calls.append(True)
        # No transaction may span this provider request.
        with db_connection() as observer:
            assert observer.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND state='idle in transaction' AND pid <> pg_backend_pid()").fetchone()[0] == 0
        if failure is not None:
            raise failure("stop")
        return ACCEPTED
    runtime = build_runtime(settings=runtime_settings, provider=provider)
    runtime.open()
    try:
        with runtime.resources.connection() as connection:
            store_id = connection.execute("INSERT INTO stores (name,access_code_hash) VALUES ('Weekly','weekly') RETURNING id").fetchone()[0]
        runtime.services.reports.queue_report("Crew", "closing", "Restocked the freezer.", store_id)
        if failure:
            with pytest.raises(failure):
                runtime.services.weekly.overview(store_id)
        else:
            assert runtime.services.weekly.overview(store_id)["summary"] == ACCEPTED["summary"]
        assert calls == [True]
        with db_connection() as observer:
            assert observer.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0))", (f"shiftly:weekly:{store_id}",)).fetchone()[0]
        # A fresh operation is not stuck behind leaked capacity or a stale lock.
        runtime.services.weekly.provider = lambda *args: ACCEPTED
        assert runtime.services.weekly.overview(store_id)["reportCount"] == 1
    finally:
        runtime.close()


def test_weekly_contention_returns_busy_without_provider(runtime_settings):
    runtime = build_runtime(settings=runtime_settings, provider=lambda *a: pytest.fail("busy store called provider"))
    runtime.open()
    try:
        with db_connection() as holder:
            holder.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))", ("shiftly:weekly:123",))
            with pytest.raises(WeeklyOverviewBusy):
                runtime.services.weekly.overview(123)
    finally:
        runtime.close()


@pytest.mark.parametrize("changes", [
    {"web_concurrency": 2}, {"db_pool_timeout": 0}, {"db_pool_timeout": float("nan")},
    {"db_pool_max_size": 0}, {"worker_mode": "both"}, {"db_statement_timeout_ms": -1},
])
def test_invalid_resource_settings_fail_before_io(runtime_settings, changes):
    with pytest.raises(ValueError):
        DatabaseResources(replace(runtime_settings, **changes))


def test_runtime_construction_is_side_effect_free_in_fresh_process():
    script = '''
import threading, psycopg, urllib.request
from config import Settings
from backend.shiftly.runtime.application import build_runtime

def forbidden(*args, **kwargs):
    raise AssertionError('unexpected I/O or thread startup')
threading.Thread.start = forbidden
psycopg.connect = forbidden
urllib.request.urlopen = forbidden
runtime = build_runtime(settings=Settings(database_url='postgresql://invalid.invalid/unused'))
assert runtime.resources.pool is None
'''
    result = subprocess.run([sys.executable, "-c", script], env={**os.environ, "OPENAI_API_KEY": "", "DATABASE_URL": ""}, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_provider_uses_explicit_credentials_and_model(runtime_settings, monkeypatch):
    import reporting
    calls = []
    monkeypatch.setattr(reporting, "call_openai", lambda *args, **kwargs: calls.append((args, kwargs)) or ACCEPTED)
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-key")
    provider = make_provider(replace(runtime_settings, openai_api_key="injected-key", openai_model="injected-model"))
    assert not calls
    assert provider({"notes": "example"}, "injected-prompt") == ACCEPTED
    assert calls[0][1] == {"api_key": "injected-key", "model": "injected-model"}


def test_pool_recovers_after_real_connection_loss(runtime_settings):
    with DatabaseResources(runtime_settings) as resources:
        with pytest.raises(psycopg.OperationalError):
            with resources.connection() as connection:
                pid = connection.execute("SELECT pg_backend_pid()").fetchone()[0]
                with db_connection() as observer:
                    assert observer.execute("SELECT pg_terminate_backend(%s)", (pid,)).fetchone()[0]
                connection.execute("SELECT 1")
        with resources.connection() as replacement:
            assert replacement.execute("SELECT 1").fetchone() == (1,)
            assert replacement.execute("SELECT pg_backend_pid()").fetchone()[0] != pid
