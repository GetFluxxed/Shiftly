import os
from dataclasses import replace

import pytest

from config import Settings


@pytest.fixture
def runtime_settings(isolated_database):
    return Settings(database_url=isolated_database, admin_signup_key="test-admin",
                    openai_api_key="", db_pool_timeout=0.5, db_connect_timeout=2,
                    db_lock_timeout_ms=150, db_statement_timeout_ms=2000,
                    shutdown_timeout=0.5, worker_mode="external")


@pytest.fixture
def child_environment():
    def build(dsn, **overrides):
        return {**os.environ, "DATABASE_URL": dsn, "TEST_DATABASE_URL": dsn,
                "OPENAI_API_KEY": "", "ADMIN_SIGNUP_KEY": "test-admin",
                "WEB_CONCURRENCY": "1", "SHIFTLY_WORKER_MODE": "external",
                "DB_POOL_TIMEOUT": "1", "DB_CONNECT_TIMEOUT": "2",
                "DB_LOCK_TIMEOUT_MS": "300", "DB_STATEMENT_TIMEOUT_MS": "2000",
                "SHUTDOWN_TIMEOUT": "0.3", "SECURE_COOKIES": "false",
                **overrides}
    return build
