"""Independent security boundary checks for named and compatibility credentials."""
from dataclasses import replace
from contextlib import contextmanager
import http.client
from http.server import ThreadingHTTPServer
import json
from threading import Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import psycopg

from backend.shiftly.identity.accounts_policy import AccountActor
from backend.shiftly.identity.principal import resolve_principal
from backend.shiftly.identity.service import IdentityError
from backend.shiftly.identity.accounts import AccountsService
from backend.shiftly.identity.accounts_core import policy_lock
from backend.shiftly.identity.primitives import hash_store_code, hash_token, password_hash
from backend.shiftly.identity.repository import IdentityRepository
from database import db_connection
import server


@pytest.fixture
def identity_boundary():
    actor = AccountActor(10, "verified-manager", "Manager", 11, 12, "manager",
                         frozenset({"reports.submit", "reports.view"}), 13, 1)
    return SimpleNamespace(
        accounts=SimpleNamespace(resolve_actor=Mock(return_value=actor)),
        repository=SimpleNamespace(manager_id=Mock(return_value=13), selected_store=Mock(return_value=11),
                                   crew_store=Mock(return_value=11)),
    )


def test_named_session_is_the_only_authenticated_person(identity_boundary):
    result = resolve_principal(identity_boundary, account_token="named")
    assert result.named and result.actor.user_id == 10 and result.store_id == 11
    assert result.can_manage is True
    identity_boundary.repository.manager_id.assert_not_called()
    identity_boundary.repository.crew_store.assert_not_called()


def test_same_person_and_same_store_compatibility_pair_is_allowed(identity_boundary):
    result = resolve_principal(identity_boundary, account_token="named", manager_token="legacy")
    assert result.named and result.actor.user_id == 10 and result.store_id == 11


@pytest.mark.parametrize("manager_id,store_id", [(None, None), (999, 11), (13, 999), (13, None)])
def test_named_cookie_cannot_borrow_another_manager_or_store(identity_boundary, manager_id, store_id):
    identity_boundary.repository.manager_id.return_value = manager_id
    identity_boundary.repository.selected_store.return_value = store_id
    with pytest.raises(IdentityError) as error:
        resolve_principal(identity_boundary, account_token="named", manager_token="legacy")
    assert error.value.code == "unauthenticated"


@pytest.mark.parametrize("cookies", [
    {"account_token": "named", "crew_token": "shared"},
    {"account_token": "named", "manager_token": "legacy", "crew_token": "shared"},
    {"manager_token": "legacy", "crew_token": "shared"},
])
def test_shared_crew_never_proves_equivalence_to_named_or_manager_identity(identity_boundary, cookies):
    with pytest.raises(IdentityError) as error:
        resolve_principal(identity_boundary, **cookies)
    assert error.value.code == "unauthenticated"


@pytest.mark.parametrize("other_cookies", [{}, {"manager_token": "valid"}, {"crew_token": "valid"}])
def test_expired_or_revoked_named_session_never_falls_back(identity_boundary, other_cookies):
    identity_boundary.accounts.resolve_actor.side_effect = IdentityError("unauthenticated", "Expired")
    with pytest.raises(IdentityError) as error:
        resolve_principal(identity_boundary, account_token="expired", **other_cookies)
    assert error.value.code == "unauthenticated"
    identity_boundary.repository.manager_id.assert_not_called()
    identity_boundary.repository.crew_store.assert_not_called()


def test_legacy_manager_link_does_not_inflate_named_crew_permission(identity_boundary):
    identity_boundary.accounts.resolve_actor.return_value = replace(
        identity_boundary.accounts.resolve_actor.return_value, role="crew", capabilities=frozenset({"reports.submit"}),
    )
    result = resolve_principal(identity_boundary, account_token="named", manager_token="legacy")
    assert result.manager_id == 13 and result.named and not result.can_manage


def test_shared_crew_principal_never_acquires_a_person_id(identity_boundary):
    result = resolve_principal(identity_boundary, crew_token="shared")
    assert result.store_id == 11 and not result.named and result.manager_id is None
    assert not result.can_manage


@pytest.mark.parametrize("expired_kind", ["crew", "manager"])
def test_one_valid_legacy_session_survives_an_expired_other_cookie(identity_boundary, expired_kind):
    if expired_kind == "crew":
        identity_boundary.repository.crew_store.return_value = None
    else:
        identity_boundary.repository.manager_id.return_value = None
        identity_boundary.repository.selected_store.return_value = None
    result = resolve_principal(identity_boundary, manager_token="legacy", crew_token="shared")
    assert result.store_id == 11 and not result.named
    assert result.can_manage is (expired_kind == "crew")


@pytest.mark.parametrize("kind", ["manager", "crew"])
def test_invalid_compatibility_session_is_rejected(identity_boundary, kind):
    identity_boundary.repository.manager_id.return_value = None
    identity_boundary.repository.selected_store.return_value = None
    identity_boundary.repository.crew_store.return_value = None
    with pytest.raises(IdentityError) as error:
        resolve_principal(identity_boundary, **{f"{kind}_token": "bad"})
    assert error.value.code == "unauthenticated"


def test_missing_credentials_do_not_create_a_principal(identity_boundary):
    assert resolve_principal(identity_boundary) is None


@pytest.mark.parametrize('token', ['', False, 0])
def test_present_invalid_named_cookie_never_falls_back(identity_boundary, token):
    with pytest.raises(IdentityError) as error:
        resolve_principal(identity_boundary, account_token=token, manager_token='valid')
    assert error.value.code == 'unauthenticated'
    identity_boundary.repository.manager_id.assert_not_called()


@pytest.fixture
def legacy_account_http(isolated_database, monkeypatch):
    """Use the actual legacy transport with synthetic, explicitly mapped identities."""
    monkeypatch.setattr(server, "ADMIN_SIGNUP_KEY", "test-operator-key")
    monkeypatch.setattr(server, "SECURE_COOKIES", False)
    monkeypatch.setattr(server, "validate_report", lambda report: {"status": "accepted"})
    password = "synthetic-password-123"
    salt, digest = "synthetic-salt", password_hash(password, "synthetic-salt")
    users, stores = {}, []
    with db_connection() as connection:
        for index in (1, 2):
            business = connection.execute("INSERT INTO businesses(name) VALUES (%s) RETURNING id", (f"Business {index}",)).fetchone()[0]
            code = f"boundary-{index}"
            store = connection.execute(
                """INSERT INTO stores(name,access_code_hash,crew_password_hash,business_id,accounts_enabled)
                   VALUES (%s,%s,%s,%s,TRUE) RETURNING id""",
                (f"Store {index}", hash_store_code(code), password_hash(password, f"shiftly-crew:{hash_store_code(code)}"), business),
            ).fetchone()[0]
            stores.append((store, business))
        for name, role, scope, linked in (
            ("owner", "manager", 0, True), ("crew", "crew", 0, False),
            ("manager", "manager", 0, False), ("other", "manager", 1, True),
        ):
            store, business = stores[scope]
            manager_id = None
            if linked:
                manager_id = connection.execute(
                    "INSERT INTO manager_users(username,password_salt,password_hash) VALUES (%s,%s,%s) RETURNING id",
                    (f"boundary-{name}", salt, digest),
                ).fetchone()[0]
                connection.execute("INSERT INTO store_memberships(manager_user_id,store_id) VALUES (%s,%s)", (manager_id, store))
                connection.execute(
                    """INSERT INTO manager_sessions(token_hash,manager_user_id,store_id,expires_at)
                       VALUES (%s,%s,%s,NOW()+INTERVAL '1 hour')""", (hash_token(f"legacy-{name}"), manager_id, store),
                )
            user = connection.execute(
                """INSERT INTO account_users(username,display_name,password_salt,password_hash,legacy_manager_id)
                   VALUES (%s,%s,%s,%s,%s) RETURNING id""", (f"boundary-{name}", f"Verified {name}", salt, digest, manager_id),
            ).fetchone()[0]
            users[name] = user
            connection.execute(
                "INSERT INTO account_store_memberships(user_id,store_id,business_id,role) VALUES (%s,%s,%s,%s)",
                (user, store, business, role),
            )
        connection.execute(
            "INSERT INTO business_memberships(user_id,business_id,role) VALUES (%s,%s,'owner')", (users["owner"], stores[0][1]),
        )
        connection.execute(
            "INSERT INTO crew_sessions(token_hash,store_id,expires_at) VALUES (%s,%s,NOW()+INTERVAL '1 hour')",
            (hash_token("shared-crew"), stores[0][0]),
        )
    accounts = AccountsService(db_connection)
    cookies = {
        name: "shiftly_account_session=" + accounts.login(
            f"boundary-{2 if name == 'other' else 1}", f"boundary-{name}", password, client_key=f"setup-{name}",
        ).token for name in users
    }
    cookies.update(legacy="shiftly_manager_session=legacy-owner", other_legacy="shiftly_manager_session=legacy-other", shared="shiftly_crew_session=shared-crew")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.ShiftlyHandler)
    thread = Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()

    def request(method, path, *, cookie=None, payload=None, headers=None):
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        if cookie:
            request_headers["Cookie"] = cookie
        body = json.dumps(payload).encode() if payload is not None else None
        connection = http.client.HTTPConnection(*httpd.server_address, timeout=5)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            data, response_headers = response.read(), response.getheaders()
            return SimpleNamespace(status=response.status, body=data, headers=response_headers,
                                   json=lambda: json.loads(data),
                                   cookies=[v.split(";", 1)[0] for k, v in response_headers if k.lower() == "set-cookie"])
        finally:
            connection.close()

    try:
        yield SimpleNamespace(request=request, accounts=accounts, users=users, stores=stores, cookies=cookies, password=password)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_legacy_transport_named_login_uses_verified_identity_and_safe_cookies(legacy_account_http):
    api = legacy_account_http
    login = api.request("POST", "/api/accounts/login", payload={
        "storeCode": "boundary-1", "username": "boundary-crew", "password": api.password,
        "role": "owner", "userId": api.users["owner"], "storeId": api.stores[1][0],
    })
    assert login.status == 200, login.body
    assert login.json()["actor"]["userId"] == api.users["crew"]
    assert login.json()["actor"]["role"] == "crew"
    assert login.json()["actor"]["storeId"] == api.stores[0][0]
    cookie_headers = [value for name, value in login.headers if name.lower() == "set-cookie"]
    assert len(cookie_headers) == 3
    assert all("HttpOnly" in value and "SameSite=Strict" in value for value in cookie_headers)
    assert {value for value in login.cookies if value.endswith("=")} == {
        "shiftly_manager_session=", "shiftly_crew_session=",
    }
    status = api.request("GET", "/api/accounts/status", cookie=login.cookies[0])
    assert status.status == 200 and status.json()["authenticated"] is True
    assert status.json()["actor"]["provenance"] == "named"


def test_legacy_cookie_cannot_open_new_account_surfaces(legacy_account_http):
    api = legacy_account_http
    status = api.request("GET", "/api/accounts/status", cookie=api.cookies["legacy"])
    assert status.status == 200 and status.json() == {"authenticated": False, "reauthenticationRequired": True}
    assert api.request("GET", "/api/accounts/team", cookie=api.cookies["legacy"]).status == 401
    assert api.request("POST", "/api/accounts/invitations", cookie=api.cookies["legacy"], payload={
        "username": "unauthorized-invite", "role": "crew",
    }).status == 401


def test_named_authentication_does_not_depend_on_reporting_permissions(legacy_account_http):
    api = legacy_account_http
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO business_memberships(user_id,business_id,role,capabilities) VALUES (%s,%s,'admin',ARRAY['inventory.view'])",
            (api.users['manager'], api.stores[0][1]),
        )
        connection.execute(
            "UPDATE account_store_memberships SET role='admin',capabilities=ARRAY['inventory.view'] WHERE user_id=%s",
            (api.users['manager'],),
        )
    status = api.request('GET', '/api/auth/status', cookie=api.cookies['manager'])
    assert status.status == 200 and status.json()['authenticated'] is True
    assert status.json()['actor']['role'] == 'admin'
    assert status.json()['actor']['capabilities'] == ['inventory.view']
    assert api.request('GET', '/api/reports', cookie=api.cookies['manager']).status == 401


def test_account_database_failure_returns_sanitized_error(legacy_account_http, monkeypatch):
    def unavailable(*args, **kwargs):
        raise psycopg.OperationalError('internal database connection details must stay private')

    monkeypatch.setattr(AccountsService, 'login_payload', unavailable)
    response = legacy_account_http.request('POST', '/api/accounts/login', payload={
        'storeCode': 'boundary-1', 'username': 'boundary-crew', 'password': 'synthetic-password-123',
    })
    assert response.status == 503
    assert response.json() == {'error': 'Account service is temporarily unavailable.'}


def test_legacy_logout_waits_for_in_progress_authorized_writes(legacy_account_http):
    @contextmanager
    def short_wait_connection():
        with db_connection() as connection:
            connection.execute("SET LOCAL lock_timeout = '100ms'")
            yield connection

    repository = IdentityRepository(short_wait_connection)
    with db_connection() as writing:
        policy_lock(writing)
        with pytest.raises(psycopg.errors.LockNotAvailable):
            repository.logout('legacy-owner', 'shared-crew')
        assert writing.execute("SELECT count(*) FROM manager_sessions WHERE token_hash=%s", (hash_token('legacy-owner'),)).fetchone()[0] == 1
        assert writing.execute("SELECT count(*) FROM crew_sessions WHERE token_hash=%s", (hash_token('shared-crew'),)).fetchone()[0] == 1
    repository.logout('legacy-owner', 'shared-crew')
    assert legacy_account_http.request('GET', '/api/auth/status', cookie=legacy_account_http.cookies['legacy']).json()['authenticated'] is False
    assert legacy_account_http.request('GET', '/api/auth/status', cookie=legacy_account_http.cookies['shared']).json()['authenticated'] is False


def test_expired_legacy_crew_cookie_does_not_block_valid_manager_compatibility(legacy_account_http):
    api = legacy_account_http
    with db_connection() as connection:
        connection.execute("UPDATE crew_sessions SET expires_at=NOW()-INTERVAL '1 second'")
    cookie = api.cookies["legacy"] + "; " + api.cookies["shared"]
    status = api.request("GET", "/api/auth/status", cookie=cookie)
    assert status.status == 200 and status.json()["authenticated"] is True
    assert status.json()["role"] == "manager"
    assert api.request("GET", "/api/reports", cookie=cookie).status == 200
    assert api.request("GET", "/api/accounts/status", cookie=cookie).json() == {
        "authenticated": False, "reauthenticationRequired": True,
    }


def test_revoked_selected_store_cannot_be_rescued_by_another_authorized_store(legacy_account_http):
    api = legacy_account_http
    user = api.users["crew"]
    target_store, target_business = api.stores[1]
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO account_store_memberships(user_id,store_id,business_id,role) VALUES (%s,%s,%s,'manager')",
            (user, target_store, target_business),
        )
        # Leave the token row intact: current membership policy itself must deny
        # it, even if session cleanup did not happen before this request.
        connection.execute(
            "UPDATE account_store_memberships SET state='revoked' WHERE user_id=%s AND store_id=%s", (user, api.stores[0][0]),
        )
    with pytest.raises(IdentityError):
        api.accounts.resolve_actor(api.cookies["crew"].split("=", 1)[1], store_id=target_store)
    assert api.request("POST", "/api/accounts/switch-store", cookie=api.cookies["crew"], payload={"storeId": target_store}).status == 403


def test_named_report_actor_and_new_manager_without_legacy_identity(legacy_account_http):
    api = legacy_account_http
    report = api.request("POST", "/api/reports", cookie=api.cookies["crew"], payload={
        "employee": "Historical display text", "shift": "closing", "notes": "The closing team restocked shelves and recorded all freezer temperatures.",
        "actorUserId": api.users["owner"], "userId": api.users["owner"], "storeId": api.stores[1][0], "role": "owner",
    })
    assert report.status == 202, report.body
    with db_connection() as connection:
        assert connection.execute("SELECT employee,actor_user_id,store_id FROM reports").fetchone() == (
            "Historical display text", api.users["crew"], api.stores[0][0],
        )
        assert connection.execute("SELECT legacy_manager_id FROM account_users WHERE id=%s", (api.users["manager"],)).fetchone()[0] is None
    listed = api.request("GET", "/api/reports", cookie=api.cookies["manager"])
    assert listed.status == 200, listed.body
    assert len(listed.json()["reports"]) == 1
    assert api.request("GET", "/api/reports", cookie=api.cookies["other"]).json()["reports"] == []
    assert api.request("GET", "/api/reports", cookie=api.cookies["crew"]).status == 401
    heads_up = api.request("POST", "/api/heads-up", cookie=api.cookies["manager"], payload={"message": "Verified manager update"})
    assert heads_up.status == 200, heads_up.body


@pytest.mark.parametrize("conflict", ["different_person", "shared_crew", "expired_named", "legacy_pair",
                                      "empty_named", "malformed_named", "duplicate_named"])
def test_conflicting_credentials_are_denied_across_legacy_transport(legacy_account_http, conflict):
    api = legacy_account_http
    cookie = {
        "different_person": api.cookies["owner"] + "; " + api.cookies["other_legacy"],
        "shared_crew": api.cookies["owner"] + "; " + api.cookies["shared"],
        "expired_named": "shiftly_account_session=expired; " + api.cookies["legacy"],
        "legacy_pair": api.cookies["legacy"] + "; " + api.cookies["shared"],
        "empty_named": "shiftly_account_session=; " + api.cookies['legacy'],
        "malformed_named": "shiftly_account_session; " + api.cookies['legacy'],
        "duplicate_named": api.cookies['owner'] + "; shiftly_account_session=; " + api.cookies['legacy'],
    }[conflict]
    assert api.request("GET", "/api/auth/status", cookie=cookie).json()["authenticated"] is False
    for path in ("/api/accounts/status", "/api/accounts/team", "/api/reports"):
        response = api.request("GET", path, cookie=cookie)
        assert response.status == 401, (path, response.status, response.body)
    for path in ("/manager.html", "/crew.html", "/accounts.html", "/inventory.html"):
        assert api.request("GET", path, cookie=cookie).status == 302, path
    denied = api.request("POST", "/api/reports", cookie=cookie, payload={
        "employee": "Crew", "shift": "closing", "notes": "A report must not be written using conflicting credentials.",
    })
    assert denied.status == 401
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM reports").fetchone()[0] == 0


def test_cutover_blocks_existing_and_new_shared_crew_sessions(legacy_account_http):
    api = legacy_account_http
    assert api.request("GET", "/api/auth/status", cookie=api.cookies["shared"]).json()["authenticated"] is True
    result = api.request("POST", "/api/accounts/cutover", cookie=api.cookies["owner"], payload={"reason": "Verified enrollment complete"})
    assert result.status == 200 and result.json()["sharedCrewEnabled"] is False
    assert api.request("GET", "/api/auth/status", cookie=api.cookies["shared"]).json()["authenticated"] is False
    assert api.request("POST", "/api/auth/login", payload={
        "storeCode": "boundary-1", "password": api.password, "role": "crew",
    }).status == 401
    assert api.request("GET", "/api/accounts/status", cookie=api.cookies["crew"]).json()["authenticated"] is True


def test_enabled_store_rejects_legacy_manager_creation_even_with_operator_key(legacy_account_http):
    api = legacy_account_http
    response = api.request("POST", "/api/auth/add-manager", cookie=api.cookies["owner"], payload={
        "adminKey": "test-operator-key", "storeCode": "boundary-1", "managerUsername": "bypass-manager",
        "managerPassword": "bypass-password-123", "confirmPassword": "bypass-password-123",
    })
    assert response.status == 403, response.body
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM manager_users WHERE username='bypass-manager'").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM account_users WHERE username='bypass-manager'").fetchone()[0] == 0


def test_named_account_mutation_rejects_cross_origin_before_writing(legacy_account_http):
    api = legacy_account_http
    response = api.request("POST", "/api/accounts/invitations", cookie=api.cookies["owner"], payload={
        "username": "cross-origin-person", "role": "crew",
    }, headers={"Origin": "https://attacker.invalid", "Sec-Fetch-Site": "cross-site"})
    assert response.status == 403
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM account_users WHERE username='cross-origin-person'").fetchone()[0] == 0


@pytest.mark.parametrize("legacy_role", ["manager", "auto"])
def test_password_change_between_legacy_verification_and_session_issue_fails_closed(legacy_account_http, monkeypatch, legacy_role):
    api = legacy_account_http
    original = IdentityRepository.issue_session
    replacements = []

    def change_after_verification(repository, *args, **kwargs):
        replacements.append(api.accounts.change_password(
            api.cookies["owner"].split("=", 1)[1], current_password=api.password,
            new_password="rotated-password-456",
        ))
        return original(repository, *args, **kwargs)

    monkeypatch.setattr(IdentityRepository, "issue_session", change_after_verification)
    result = api.request("POST", "/api/auth/login", payload={
        "storeCode": "boundary-1", "password": api.password, "role": legacy_role,
    })
    assert len(replacements) == 1 and replacements[0]["changed"] is True
    assert result.status == 401, result.body
    assert result.cookies == []
    with db_connection() as connection:
        assert connection.execute(
            """SELECT count(*) FROM manager_sessions WHERE manager_user_id=(
               SELECT legacy_manager_id FROM account_users WHERE id=%s)""", (api.users["owner"],),
        ).fetchone()[0] == 0
    monkeypatch.setattr(IdentityRepository, "issue_session", original)
    old_named = api.request("POST", "/api/accounts/login", payload={
        "storeCode": "boundary-1", "username": "boundary-owner", "password": api.password,
    })
    assert old_named.status == 401
    new_named = api.request("POST", "/api/accounts/login", payload={
        "storeCode": "boundary-1", "username": "boundary-owner", "password": "rotated-password-456",
    })
    assert new_named.status == 200, new_named.body


@pytest.mark.parametrize("credential_kind", ["shared", "legacy", "crew"])
def test_revocation_during_report_quality_check_prevents_enqueue(legacy_account_http, monkeypatch, credential_kind):
    api = legacy_account_http
    checked = []

    def revoke_while_checking(report):
        checked.append(report)
        if credential_kind == "shared":
            api.accounts.cutover_store(api.cookies["owner"].split("=", 1)[1], reason="Enrollment completed during request")
        elif credential_kind == "crew":
            api.accounts.set_membership(api.cookies["owner"].split("=", 1)[1], user_id=api.users["crew"],
                                        role="crew", active=False, reason="Membership revoked during request")
        else:
            # Simulate a policy writer removing the legacy compatibility edge
            # after initial HTTP authentication, before the enqueue transaction.
            with db_connection() as connection:
                policy_lock(connection)
                connection.execute(
                    """DELETE FROM store_memberships WHERE store_id=%s AND manager_user_id=(
                       SELECT legacy_manager_id FROM account_users WHERE id=%s)""", (api.stores[0][0], api.users["owner"]),
                )
        return {"status": "accepted"}

    monkeypatch.setattr(server, "validate_report", revoke_while_checking)
    result = api.request("POST", "/api/reports", cookie=api.cookies[credential_kind], payload={
        "employee": "Crew", "shift": "closing", "notes": "The cooler shelves were stocked and the shift completed its safety checks.",
    })
    assert len(checked) == 1
    assert result.status == 401, result.body
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM briefing_jobs").fetchone()[0] == 0
