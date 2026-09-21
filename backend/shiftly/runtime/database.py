"""Explicit bounded pools plus closing sessions for advisory-lock workflows."""

from contextlib import contextmanager
from threading import BoundedSemaphore, Lock

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import ConnectionPool, PoolClosed, PoolTimeout

from .settings import validate_runtime_settings


def connection_kwargs(settings):
    validate_runtime_settings(settings)
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    # Keep caller-supplied search_path (including disposable schema isolation).
    options = conninfo_to_dict(settings.database_url).get("options", "")
    options += (f" -c statement_timeout={settings.db_statement_timeout_ms}"
                f" -c lock_timeout={settings.db_lock_timeout_ms}"
                f" -c idle_in_transaction_session_timeout={settings.db_idle_transaction_timeout_ms}")
    return {"connect_timeout": settings.db_connect_timeout, "options": options.strip(),
            "prepare_threshold": None}


def connect_dedicated(settings):
    return psycopg.connect(settings.database_url, **connection_kwargs(settings))


def _reset(connection):
    # All session state, including advisory locks, must be cleared before reuse.
    connection.autocommit = True
    try:
        connection.execute("DISCARD ALL")
    finally:
        connection.autocommit = False


class DatabaseResources:
    """Construct freely; open/close explicitly in lifespan (off the event loop).

    At most db_pool_max_size regular connections plus two dedicated weekly
    sessions. Each acquisition has a timeout. No threads exist before open().
    """

    def __init__(self, settings):
        validate_runtime_settings(settings)
        self.settings = settings
        self.pool = None
        self._weekly_slots = BoundedSemaphore(2)
        self._lock = Lock()
        self._dedicated = set()
        self._closed = False

    def open(self):
        if self._closed:
            raise PoolClosed("Database resources are closed.")
        if self.pool is not None:
            return self
        self.pool = ConnectionPool(
            self.settings.database_url, kwargs=connection_kwargs(self.settings),
            min_size=1, max_size=self.settings.db_pool_max_size, open=False,
            timeout=self.settings.db_pool_timeout, max_waiting=32,
            reset=_reset, num_workers=1,
            reconnect_timeout=self.settings.db_connect_timeout,
        )
        try:
            self.pool.open(wait=True, timeout=self.settings.db_pool_timeout)
        except BaseException:
            self.close()
            raise
        return self

    @contextmanager
    def connection(self):
        if self.pool is None or self._closed:
            raise PoolClosed("Database resources are not open.")
        with self.pool.connection(timeout=self.settings.db_pool_timeout) as connection:
            yield connection

    @contextmanager
    def weekly_connection(self):
        if self.pool is None or self._closed:
            raise PoolClosed("Database resources are not open.")
        if not self._weekly_slots.acquire(timeout=self.settings.db_pool_timeout):
            raise PoolTimeout("Dedicated connection capacity is exhausted.")
        connection = None
        try:
            connection = connect_dedicated(self.settings)
            with self._lock:
                if self._closed:
                    raise PoolClosed("Database resources are closed.")
                self._dedicated.add(connection)
            with connection:
                yield connection
        finally:
            if connection is not None:
                connection.close()
                with self._lock:
                    self._dedicated.discard(connection)
            self._weekly_slots.release()

    def close(self):
        with self._lock:
            self._closed = True
            connections = list(self._dedicated)
        for connection in connections:
            connection.close()
        if self.pool is not None:
            self.pool.close(timeout=self.settings.shutdown_timeout)

    def __enter__(self):
        return self.open()

    def __exit__(self, *_):
        self.close()
