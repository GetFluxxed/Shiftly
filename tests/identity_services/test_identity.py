"""Direct identity/store behavior, without a live HTTP application."""

import hashlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import psycopg
import pytest

from backend.shiftly.identity import AdmissionControl, IdentityError
from backend.shiftly.runtime import build_services
from database import db_connection


def fields(code="first-store", name="first-manager"):
    return {"storeName": "First Store", "storeCode": code, "crewPassword": "crew-secret-123",
            "managerUsername": name, "managerPassword": "manager-secret-123",
            "confirmPassword": "manager-secret-123", "adminKey": "test-admin"}


@pytest.fixture
def services(isolated_database):
    def provider(*args):
        raise AssertionError("Identity work must not invoke AI")
    return build_services(settings=SimpleNamespace(admin_signup_key="test-admin",
                          report_cooldown_seconds=60, openai_model="test-model"),
                          connection_factory=db_connection, provider=provider)


def test_signup_login_and_store_workflows(services):
    identity = services.identity
    signup = identity.signup(fields())
    assert signup.role == "manager" and signup.ttl == 28800
    assert signup.token not in repr(signup)
    manager_id = identity.manager_id(signup.token)
    store_id = identity.selected_store(signup.token, manager_id)
    assert identity.crew_store("", signup.token) == store_id
    for role in ("auto", "manager"):
        result = identity.login("FIRST-STORE", role, "manager-secret-123", client_key="local")
        assert result.response == signup.response
        assert identity.manager_id(result.token) == manager_id
    crew = identity.login("first-store", "crew", "crew-secret-123", client_key="local")
    assert identity.crew_store(crew.token) == store_id
    assert not identity.manager_id(crew.token)
    assert services.stores.save_heads_up(store_id, "  Fresh\nstock  ")["message"] == "Fresh stock"
    assert services.stores.manager_accounts(store_id)[0]["name"] == "first-manager"
    identity.logout(signup.token, crew.token)
    assert not identity.manager_id(signup.token)
    assert not identity.crew_store(crew.token)


@pytest.mark.parametrize("change", [
    "UPDATE manager_users SET active = false WHERE id = %s",
    "DELETE FROM store_memberships WHERE manager_user_id = %s",
    "UPDATE manager_sessions SET expires_at = NOW() - INTERVAL '1 second' WHERE manager_user_id = %s",
])
def test_manager_session_loses_authority_on_revocation(services, change):
    session = services.identity.signup(fields())
    manager_id = services.identity.manager_id(session.token)
    with db_connection() as connection:
        connection.execute(change, (manager_id,))
    assert not services.identity.manager_id(session.token)
    assert not services.identity.selected_store(session.token, manager_id)
    assert not services.identity.crew_store("", session.token)


def test_inactive_store_blocks_both_roles(services):
    manager = services.identity.signup(fields())
    crew = services.identity.login("first-store", "crew", "crew-secret-123", client_key="peer")
    with db_connection() as connection:
        connection.execute("UPDATE stores SET active = false")
    assert not services.identity.manager_id(manager.token)
    assert not services.identity.crew_store(crew.token)
    with pytest.raises(IdentityError) as error:
        services.identity.login("first-store", "manager", "manager-secret-123", client_key="peer")
    assert error.value.code == "unauthenticated"


def test_selected_store_is_bound_to_token_and_membership(services):
    first = services.identity.signup(fields())
    second = services.identity.signup(fields("second-store", "second-manager"))
    first_id = services.identity.manager_id(first.token)
    second_id = services.identity.manager_id(second.token)
    first_store = services.identity.selected_store(first.token, first_id)
    second_store = services.identity.selected_store(second.token, second_id)
    assert not services.identity.selected_store(first.token, second_id)
    with db_connection() as connection:
        connection.execute("INSERT INTO store_memberships (manager_user_id, store_id) VALUES (%s,%s)", (first_id, second_store))
        connection.execute("UPDATE manager_sessions SET store_id = NULL WHERE manager_user_id = %s", (first_id,))
    assert services.identity.selected_store(first.token, first_id) == first_store
    with db_connection() as connection:
        row = connection.execute("SELECT store_id FROM manager_sessions WHERE token_hash = %s",
                                 (hashlib.sha256(first.token.encode()).hexdigest(),)).fetchone()
    assert row == (first_store,)


def test_crew_token_cannot_cross_store_or_survive_expiry(services):
    services.identity.signup(fields())
    services.identity.signup(fields("second-store", "second-manager"))
    crew = services.identity.login("first-store", "crew", "crew-secret-123", client_key="peer")
    first_id = services.stores.store_for_code("first-store")[0]
    assert services.identity.crew_store(crew.token) == first_id
    with db_connection() as connection:
        connection.execute("UPDATE crew_sessions SET expires_at = NOW() - INTERVAL '1 second'")
    assert not services.identity.crew_store(crew.token)


def test_add_manager_uses_existing_store_and_admin_guard(services):
    first = services.identity.signup(fields())
    second = services.identity.add_manager(fields(name="second-manager"))
    assert services.identity.selected_store(first.token, services.identity.manager_id(first.token)) == services.identity.selected_store(second.token, services.identity.manager_id(second.token))
    with pytest.raises(IdentityError) as error:
        services.identity.add_manager({**fields(name="third-manager"), "adminKey": "wrong"})
    assert error.value.code == "forbidden"
    assert len(services.stores.manager_accounts(services.stores.store_for_code("first-store")[0])) == 2


@pytest.mark.parametrize("action", ["signup", "add_manager"])
def test_session_failure_rolls_back_account_and_membership(services, monkeypatch, action):
    if action == "add_manager":
        services.identity.signup(fields())
    def broken(*args):
        raise RuntimeError("session unavailable")
    monkeypatch.setattr(services.identity.repository, "_session", broken)
    with pytest.raises(RuntimeError, match="session unavailable"):
        getattr(services.identity, action)(fields(name="new-manager"))
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM manager_users WHERE username='new-manager'").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM stores").fetchone()[0] == (action == "add_manager")
        assert connection.execute("SELECT count(*) FROM store_memberships").fetchone()[0] == (action == "add_manager")


def test_duplicate_workspace_does_not_leave_partial_records(services):
    services.identity.signup(fields())
    with pytest.raises(IdentityError) as error:
        services.identity.signup(fields("other-store"))
    assert error.value.code == "conflict"
    assert services.stores.store_for_code("other-store") is None


def test_missing_and_forged_manager_id_cannot_select_store(services):
    result = services.identity.signup(fields())
    actual = services.identity.manager_id(result.token)
    assert not services.identity.selected_store("", actual)
    assert not services.identity.selected_store("forged", actual)
    assert not services.identity.selected_store(result.token, actual + 100)


def test_admission_and_validation_order_without_database():
    calls = []
    settings = SimpleNamespace(admin_signup_key="", report_cooldown_seconds=60, openai_model="test")
    services = build_services(settings=settings, connection_factory=lambda: calls.append("db"), provider=lambda *a: calls.append("ai"))
    with pytest.raises(IdentityError) as error:
        services.identity.admit_account_creation("peer")
    assert error.value.code == "unavailable"
    assert not services.admission.signups
    with pytest.raises(IdentityError) as error:
        services.identity.login_payload({"storeCode": []}, client_key="peer")
    assert str(error.value) == "Invalid store code."
    with pytest.raises(IdentityError) as error:
        services.identity.login("store", "owner", "secret", client_key="peer")
    assert error.value.code == "invalid"
    assert not calls and not services.admission.in_flight


def test_login_exception_returns_reserved_capacity(services, monkeypatch):
    def fail(code):
        raise psycopg.OperationalError("unavailable")
    monkeypatch.setattr(services.identity, "store_lookup", fail)
    with pytest.raises(psycopg.OperationalError):
        services.identity.login("store", "crew", "secret", client_key="peer")
    assert not services.admission.in_flight
    assert len(services.admission.failures[services.admission.login_key("peer", "store")]) == 1


def test_concurrent_admission_reserves_exact_budget_and_recovers():
    now = [1000]
    admission = AdmissionControl(clock=lambda: now[0])
    with ThreadPoolExecutor(max_workers=20) as executor:
        accepted = list(executor.map(lambda _: admission.reserve_login("peer", "STORE"), range(30)))
    assert sum(accepted) == 10
    for _ in range(10):
        admission.finish_login("peer", "store", failed=True)
    assert admission.login_limited("peer", "Store")
    now[0] += 901
    assert admission.reserve_login("peer", "store")
    admission.finish_login("peer", "store", failed=False)
    assert not admission.in_flight
    with ThreadPoolExecutor(max_workers=20) as executor:
        assert sum(executor.map(lambda _: admission.admit_signup("peer"), range(30))) == 5


def test_report_and_store_services_share_injected_boundaries(services):
    manager = services.identity.signup(fields())
    manager_id = services.identity.manager_id(manager.token)
    store_id = services.identity.selected_store(manager.token, manager_id)
    services.submission.quality_gate = lambda report: {"status": "accepted"}
    # Payload authority is ignored by the existing report service.
    services.submission.submit(store_id, {"storeId": store_id+99, "employee": "Crew", "shift": "closing", "notes": "Restocked the refrigerator and cleaned the floors."})
    assert len(services.reports.list_for_manager(manager_id)) == 1
    assert services.reports.list_for_manager(manager_id + 999) == []


def test_import_and_construction_do_not_load_http_or_legacy_runtime():
    script = '''
import builtins
from types import SimpleNamespace
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'server', 'routes', 'reporting', 'fastapi', 'auth', 'security', 'store_service', 'config', 'database'}:
        raise AssertionError(name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from backend.shiftly.runtime import build_services
def forbidden(*a, **kw):
    raise AssertionError('construction performed I/O')
settings = SimpleNamespace(admin_signup_key='key', report_cooldown_seconds=60, openai_model='test')
services = build_services(settings=settings, connection_factory=forbidden, provider=forbidden)
assert services.identity and services.stores and services.submission
'''
    completed = subprocess.run([sys.executable, "-c", script], env={**os.environ, "DATABASE_URL": "", "OPENAI_API_KEY": ""}, capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
