from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import routes
import security
from reporting import WEEKLY_MAX_INPUT_CHARS, _weekly_source
from security import login_rate_limited, record_login_failure


def test_login_failures_share_case_and_role_budget():
    handler = SimpleNamespace(client_address=("127.0.0.1", 4173))
    for _ in range(10):
        record_login_failure(handler, "Store-Code", "auto")

    assert login_rate_limited(handler, "store-code", "crew")


def test_weekly_source_caps_model_input():
    rows = [
        ("Crew", "closing", "x" * 2000, datetime.now(timezone.utc), str(index))
        for index in range(50)
    ]

    _, notes, included = _weekly_source(rows, len(rows))

    assert len(notes) <= WEEKLY_MAX_INPUT_CHARS
    assert 0 < included < len(rows)
    assert notes.count("Employee:") == included
    assert notes.endswith("x" * 2000)


def test_expired_failures_free_budget_but_active_checks_still_count(monkeypatch):
    now = [1000]
    monkeypatch.setattr(security.time, "time", lambda: now[0])
    handler = SimpleNamespace(client_address=("127.0.0.1", 4173))
    for _ in range(9):
        record_login_failure(handler, "store")
    assert security.reserve_login_attempt(handler, "store")
    assert not security.reserve_login_attempt(handler, "store")
    now[0] += 901
    for _ in range(9):
        assert security.reserve_login_attempt(handler, "store")
    assert not security.reserve_login_attempt(handler, "store")
    for _ in range(10):
        security.finish_login_attempt(handler, "store", failed=False)
    assert not security.LOGIN_IN_FLIGHT


def test_login_exception_releases_reservation(monkeypatch):
    handler = SimpleNamespace(client_address=("127.0.0.1", 4173))
    def unavailable(*args):
        raise RuntimeError("Database unavailable")
    monkeypatch.setattr(routes, "store_for_code", unavailable)
    with pytest.raises(RuntimeError, match="Database unavailable"):
        routes.login(handler, "store", "crew", "password")
    assert not security.LOGIN_IN_FLIGHT
    assert len(security.LOGIN_FAILURES[security._login_key(handler, "store")]) == 1
