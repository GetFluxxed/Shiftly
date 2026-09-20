"""Disposable PostgreSQL schemas and fail-closed AI stubs for every test."""

import os
import urllib.request
import uuid
from threading import Event

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

import reporting
import security
import server


@pytest.fixture(autouse=True)
def isolated_process_state(monkeypatch):
    for name in ("REQUESTS", "LOGIN_FAILURES", "SIGNUP_ATTEMPTS"):
        monkeypatch.setattr(security, name, {})
    wake = Event()
    monkeypatch.setattr(reporting, "JOB_WAKE", wake)
    monkeypatch.setattr(server, "JOB_WAKE", wake)

    def no_external_ai(*args, **kwargs):
        raise AssertionError("Tests must supply a deterministic AI response.")

    monkeypatch.setattr(reporting, "call_openai", no_external_ai)
    monkeypatch.setattr(server, "call_openai", no_external_ai)
    monkeypatch.setattr(urllib.request, "urlopen", no_external_ai)


@pytest.fixture
def empty_database(monkeypatch):
    """Never fall back to the application's DATABASE_URL or public schema."""
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.fail("Set TEST_DATABASE_URL to a disposable PostgreSQL database.")
    schema = "shiftly_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            test_dsn = make_conninfo(dsn, options=f"-csearch_path={schema}")
            monkeypatch.setenv("DATABASE_URL", test_dsn)
            monkeypatch.setattr(server, "DB_URL", test_dsn)
            yield test_dsn
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def isolated_database(empty_database):
    server.initialize_database()
    return empty_database
