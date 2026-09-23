"""Native bearer transport preserves account authority and browser contracts."""
from types import SimpleNamespace

import pytest

from backend.shiftly.identity.primitives import hash_store_code, hash_token, password_hash
from database import db_connection


@pytest.fixture
def mobile(transport_clients):
    client, _ = transport_clients
    accounts = client.app.state.context.services.accounts
    password, salt = "synthetic-mobile-password", "mobile-salt"
    stores, users = [], {}
    with db_connection() as connection:
        business = connection.execute("INSERT INTO businesses(name) VALUES('Mobile business') RETURNING id").fetchone()[0]
        for code in ("mobile-first", "mobile-second", "mobile-unrelated"):
            stores.append(connection.execute(
                "INSERT INTO stores(name,access_code_hash,business_id,accounts_enabled) VALUES(%s,%s,%s,true) RETURNING id",
                (code, hash_store_code(code), business if code != "mobile-unrelated" else None),
            ).fetchone()[0])
        for username, role, capabilities in (("owner", "manager", []), ("crew", "crew", ["inventory.view"]),
                                              ("viewer", "admin", ["inventory.view"])):
            users[username] = connection.execute(
                "INSERT INTO account_users(username,display_name,password_salt,password_hash) VALUES(%s,%s,%s,%s) RETURNING id",
                (username, f"Mobile {username}", salt, password_hash(password, salt)),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO account_store_memberships(user_id,store_id,business_id,role,capabilities) VALUES(%s,%s,%s,%s,%s)",
                (users[username], stores[0], business, role, capabilities),
            )
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role) VALUES(%s,%s,'owner')",
                           (users["owner"], business))
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role,capabilities) VALUES(%s,%s,'admin',ARRAY['inventory.view'])",
                           (users["viewer"], business))

    def send(method, path, *, token=None, headers=None, **kwargs):
        client.cookies.clear()
        sent = list(headers or [])
        if token is not None:
            sent.append(("Authorization", f"Bearer {token}"))
        return client.request(method, path, headers=sent, **kwargs)

    def login(username="owner"):
        response = send("POST", "/api/mobile/accounts/login", json={
            "storeCode": "mobile-first", "username": username, "password": password,
        })
        assert response.status_code == 200, response.text
        return response.json()["sessionToken"]

    return SimpleNamespace(client=client, send=send, login=login, accounts=accounts,
                           users=users, stores=stores, password=password)


def test_native_login_opaque_session_and_web_cookie_contract(mobile):
    m = mobile
    body = {"storeCode": "mobile-first", "username": "crew", "password": m.password,
            "role": "owner", "userId": m.users["owner"], "storeId": m.stores[2]}
    login = m.send("POST", "/api/mobile/accounts/login", json=body)
    data = login.json()
    assert login.status_code == 200
    assert data["actor"]["userId"] == m.users["crew"]
    assert data["actor"]["storeId"] == m.stores[0]
    assert data["actor"]["role"] == "crew" and data["expiresIn"] == 28800
    assert "set-cookie" not in login.headers and login.headers["cache-control"] == "no-store"
    token = data["sessionToken"]
    with db_connection() as connection:
        row = connection.execute("SELECT token_hash,expires_at>NOW() FROM account_sessions WHERE user_id=%s",
                                 (m.users["crew"],)).fetchone()
        assert row == (hash_token(token), True) and row[0] != token
    status = m.send("GET", "/api/mobile/accounts/status", token=token)
    assert status.json()["actor"] == data["actor"]
    assert status.json()["stores"][0]["storeId"] == m.stores[0]
    assert "sessionToken" not in status.json()
    assert m.send("GET", "/api/accounts/status", token=token).json()["authenticated"] is False
    assert m.send("GET", "/api/reports", token=token).status_code == 401
    web = m.send("POST", "/api/accounts/login", json=body)
    assert "sessionToken" not in web.json() and "expiresIn" not in web.json()
    cookies = web.headers.get_list("set-cookie")
    assert len(cookies) == 3
    assert all("HttpOnly" in value and "SameSite=strict" in value for value in cookies)


@pytest.mark.parametrize("headers", [
    [("Authorization", "")], [("Authorization", "Basic abc")], [("Authorization", "Bearer")],
    [("Authorization", "Bearer abc def")], [("Authorization", "Bearer abc, Bearer def")],
    [("Authorization", "Bearer abc"), ("Authorization", "Bearer def")],
    [("Cookie", "shiftly_account_session=")], [("Cookie", "shiftly_manager_session")],
    [("Cookie", "shiftly_account_session = invalid")],
    [("Cookie", "irrelevant=1"), ("Cookie", "shiftly_crew_session=legacy")],
])
def test_native_rejects_malformed_or_browser_credentials_without_fallback(mobile, headers):
    m = mobile
    for path in ("/api/mobile/accounts/status", "/api/mobile/accounts/team", "/api/mobile/reports", "/api/mobile/heads-up"):
        response = m.send("GET", path, headers=headers)
        assert response.status_code == 401, (path, response.text)
        assert response.headers["cache-control"] == "no-store"
    login = m.send("POST", "/api/mobile/accounts/login", headers=headers,
                   json={"storeCode": "mobile-first", "username": "owner", "password": m.password})
    assert login.status_code == 401 and "sessionToken" not in login.json()


def test_native_valid_bearer_cannot_mix_with_auth_cookies(mobile):
    token = mobile.login()
    for cookie in ("shiftly_account_session=", f"shiftly_account_session={token}",
                   "shiftly_manager_session=expired", "shiftly_crew_session=expired"):
        assert mobile.send("GET", "/api/mobile/accounts/status", token=token,
                           headers=[("Cookie", cookie)]).status_code == 401
    assert mobile.send("GET", "/api/mobile/accounts/status", token=token,
                       headers=[("Cookie", "theme=dark")]).status_code == 200


@pytest.mark.parametrize("expected,status", [(None, 400), (True, 400), ("1", 400), (-1, 400), (999999, 409)])
def test_native_protected_writes_require_matching_selected_store(mobile, expected, status):
    m = mobile
    token = m.login()
    fields = {"storeId": m.stores[1]}
    if expected is not None:
        fields["expectedStoreId"] = expected
    switched = m.send("POST", "/api/mobile/accounts/switch-store", token=token, json=fields)
    assert switched.status_code == status
    assert m.send("GET", "/api/mobile/accounts/status", token=token).json()["actor"]["storeId"] == m.stores[0]
    report = m.send("POST", "/api/mobile/reports", token=token,
                    json={**fields, "employee": "Scoped employee", "shift": "opening", "notes": "Completed the opening checklist."})
    assert report.status_code == status
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM reports").fetchone()[0] == 0


def test_native_store_switch_rotates_revokes_and_denies_unrelated_scope(mobile):
    m = mobile
    token = m.login()
    unrelated = m.send("POST", "/api/mobile/accounts/switch-store", token=token,
                       json={"storeId": m.stores[2], "expectedStoreId": m.stores[0]})
    assert unrelated.status_code == 403
    switched = m.send("POST", "/api/mobile/accounts/switch-store", token=token,
                      json={"storeId": m.stores[1], "expectedStoreId": m.stores[0]})
    assert switched.status_code == 200 and "set-cookie" not in switched.headers
    fresh = switched.json()["sessionToken"]
    assert fresh != token and switched.json()["actor"]["storeId"] == m.stores[1]
    assert m.send("GET", "/api/mobile/accounts/status", token=token).status_code == 401
    stale_draft = m.send("POST", "/api/mobile/reports", token=fresh, json={
        "expectedStoreId": m.stores[0], "employee": "Old draft", "shift": "opening", "notes": "Old store checklist completed.",
    })
    assert stale_draft.status_code == 409


@pytest.mark.parametrize("operation", ["logout", "logout-all", "password"])
def test_native_lifecycle_revocation_is_shared_with_browser_sessions(mobile, operation):
    m = mobile
    token, second = m.login(), m.login()
    fields = {"expectedStoreId": m.stores[0], "currentPassword": m.password, "newPassword": "changed-mobile-password"}
    response = m.send("POST", f"/api/mobile/accounts/{operation}", token=token, json=fields)
    assert response.status_code == 200 and "set-cookie" not in response.headers
    assert m.send("GET", "/api/mobile/accounts/status", token=token).status_code == 401
    assert m.send("GET", "/api/accounts/status", headers=[("Cookie", f"shiftly_account_session={token}")]).status_code == 401
    assert m.send("GET", "/api/mobile/accounts/status", token=second).status_code == (200 if operation == "logout" else 401)
    assert m.send("POST", "/api/mobile/accounts/logout", token=token).status_code == 200
    assert m.send("POST", "/api/mobile/accounts/logout").json() == {"authenticated": False}


def test_native_activation_team_grants_and_suspension_use_existing_services(mobile):
    m = mobile
    owner, crew = m.login(), m.login("crew")
    assert m.send("GET", "/api/mobile/accounts/team", token=owner).status_code == 200
    assert m.send("GET", "/api/mobile/accounts/team", token=crew).status_code == 403
    invite = m.send("POST", "/api/mobile/accounts/invitations", token=owner, json={
        "expectedStoreId": m.stores[0], "username": "new-mobile", "displayName": "New Mobile", "role": "crew",
        "capabilities": ["inventory.view"], "reason": "Native activation test.",
    })
    assert invite.status_code == 200
    payload = {"token": invite.json()["token"], "password": m.password}
    activated = m.send("POST", "/api/mobile/accounts/activate", json=payload)
    assert activated.status_code == 200 and "set-cookie" not in activated.headers
    assert activated.json()["actor"]["userId"] == invite.json()["userId"]
    assert m.send("POST", "/api/mobile/accounts/activate", json=payload).status_code == 400
    suspended = m.send("POST", "/api/mobile/accounts/suspend", token=owner, json={
        "expectedStoreId": m.stores[0], "userId": invite.json()["userId"], "reason": "Native suspension test.",
    })
    assert suspended.status_code == 200
    assert m.send("GET", "/api/mobile/accounts/status", token=activated.json()["sessionToken"]).status_code == 401


def test_native_reports_record_actor_and_label_only_authorized_stores(mobile):
    m = mobile
    crew, owner = m.login("crew"), m.login()
    payload = {"expectedStoreId": m.stores[0], "employee": "Typed historical name", "shift": "opening",
               "notes": "Completed the opening checklist and replenished the coolers.",
               "storeId": m.stores[2], "actorUserId": m.users["owner"]}
    assert m.send("POST", "/api/mobile/reports", token=crew, json=payload).status_code == 202
    with db_connection() as connection:
        assert connection.execute("SELECT store_id,actor_user_id FROM reports").fetchone() == (m.stores[0], m.users["crew"])
    second = m.send("POST", "/api/mobile/accounts/switch-store", token=owner,
                    json={"expectedStoreId": m.stores[0], "storeId": m.stores[1]}).json()["sessionToken"]
    assert m.send("POST", "/api/mobile/reports", token=second,
                  json={**payload, "expectedStoreId": m.stores[1], "employee": "Second store", "notes": "Checked the delivery and filled the display."}).status_code == 202
    m.client.app.state.context.services.reports.queue_report(
        "Unrelated person", "opening", "A report that must stay outside this account's scope.", m.stores[2])
    rows = m.send("GET", "/api/mobile/reports", token=second).json()["reports"]
    assert {row["storeId"] for row in rows} == set(m.stores[:2])
    assert {row["storeName"] for row in rows} == {"mobile-first", "mobile-second"}
    browser = m.send("GET", "/api/reports", headers=[("Cookie", f"shiftly_account_session={second}")])
    assert browser.status_code == 200 and all("storeId" not in row for row in browser.json()["reports"])
    assert m.send("GET", "/api/mobile/reports", token=crew).status_code == 403
    assert m.send("GET", "/api/mobile/heads-up", token=crew).json() == {"message": "", "updatedAt": None}
    viewer = m.login("viewer")
    assert m.send("GET", "/api/mobile/heads-up", token=viewer).status_code == 403
    assert m.send("POST", "/api/mobile/reports", token=viewer, json=payload).status_code == 403


def test_native_expired_session_and_withdrawn_membership_deny_access(mobile):
    m = mobile
    token = m.login("crew")
    with db_connection() as connection:
        connection.execute("UPDATE account_sessions SET expires_at=NOW()-INTERVAL '1 second' WHERE token_hash=%s",
                           (hash_token(token),))
    assert m.send("GET", "/api/mobile/accounts/status", token=token).status_code == 401
    token = m.login("crew")
    with db_connection() as connection:
        connection.execute("UPDATE account_store_memberships SET state='revoked' WHERE user_id=%s", (m.users["crew"],))
    assert m.send("GET", "/api/mobile/accounts/status", token=token).status_code == 403
    assert m.send("GET", "/api/mobile/heads-up", token=token).status_code == 403
    response = m.send("POST", "/api/mobile/reports", token=token, json={
        "expectedStoreId": m.stores[0], "employee": "Withdrawn crew", "shift": "opening", "notes": "This write must be denied.",
    })
    assert response.status_code == 403
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM reports").fetchone()[0] == 0


def test_native_report_rechecks_revocation_after_quality_gate(mobile, monkeypatch):
    m = mobile
    token = m.login("crew")
    def revoke_while_checking(report):
        m.accounts.logout(token)
        return {"status": "accepted"}
    monkeypatch.setattr(m.client.app.state.context.services.submission, "quality_gate", revoke_while_checking)
    response = m.send("POST", "/api/mobile/reports", token=token, json={
        "expectedStoreId": m.stores[0], "employee": "Revoked crew", "shift": "closing",
        "notes": "Finished the closing checklist and secured the doors.",
    })
    assert response.status_code == 401
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM reports").fetchone()[0] == 0


def test_native_requests_keep_origin_body_and_secret_boundaries(mobile):
    m = mobile
    login = {"storeCode": "mobile-first", "username": "owner", "password": m.password}
    for headers in ([("Origin", "https://foreign.example")], [("Sec-Fetch-Site", "cross-site")]):
        assert m.send("POST", "/api/mobile/accounts/login", headers=headers, json=login).status_code == 403
    for body in (b"[]", b"{invalid", b"\xff", b"x" * 20001):
        response = m.send("POST", "/api/mobile/accounts/login", content=body)
        assert response.status_code == 400 and "sessionToken" not in response.text
    assert m.send("GET", "/api/mobile/accounts/status").json() == {"authenticated": False, "reauthenticationRequired": False}
    assert m.send("GET", "/api/mobile/reports", params={"sessionToken": m.login()}).status_code == 401


def test_native_management_choices_are_server_scoped_and_roster_contract_unchanged(mobile):
    m = mobile
    owner = m.login()
    data = m.send('GET', '/api/mobile/accounts/management', token=owner).json()
    assert data['storeId'] == m.stores[0] and data['isOwner'] is True
    assert [role['role'] for role in data['roles']] == ['crew', 'manager', 'admin']
    assert 'catalog.manage' in data['businessCapabilities']
    assert {person['userId'] for person in data['directory']} == set(m.users.values())
    assert next(person for person in data['directory'] if person['userId'] == m.users['owner'])['canTransfer'] is False
    assert next(person for person in data['members'] if person['userId'] == m.users['owner'])['canEdit'] is False
    assert 'canEdit' not in m.send('GET', '/api/mobile/accounts/team', token=owner).json()['members'][0]
    for username in ('crew', 'viewer'):
        assert m.send('GET', '/api/mobile/accounts/management', token=m.login(username)).status_code == 403
    assert m.send('GET', '/api/mobile/accounts/management', headers=[('Cookie', f'shiftly_account_session={owner}')]).status_code == 401
    m.accounts.set_membership(owner, user_id=m.users['crew'], role='manager', capabilities=['memberships.manage'])
    manager = m.login('crew')
    data = m.send('GET', '/api/mobile/accounts/management', token=manager).json()
    assert data['isOwner'] is False and data['directory'] == [] and data['businessCapabilities'] == []
    assert data['sharedCrewEnabled'] is None
    assert [role['role'] for role in data['roles']] == ['crew']
    assert 'catalog.manage' not in data['roles'][0]['optional']
    assert all(not member['canEdit'] for member in data['members'])
    assert m.send('POST', '/api/mobile/accounts/business-memberships', token=manager, json={
        'expectedStoreId': m.stores[0], 'userId': m.users['viewer'], 'role': 'owner',
    }).status_code == 403


def test_native_owner_directory_excludes_other_business_and_withholds_global_actions(mobile):
    m = mobile
    with db_connection() as connection:
        foreign = connection.execute("INSERT INTO businesses(name) VALUES('Foreign business') RETURNING id").fetchone()[0]
        connection.execute('UPDATE stores SET business_id=%s WHERE id=%s', (foreign, m.stores[2]))
        outsider = connection.execute("INSERT INTO account_users(username,display_name,password_salt,password_hash) VALUES('outsider','Outside','salt','hash') RETURNING id").fetchone()[0]
        connection.execute("INSERT INTO account_store_memberships(user_id,store_id,business_id,role) VALUES(%s,%s,%s,'crew')", (outsider, m.stores[2], foreign))
        # Revoked foreign history still prevents local owners from controlling a global account.
        connection.execute("INSERT INTO account_store_memberships(user_id,store_id,business_id,role,state) VALUES(%s,%s,%s,'crew','revoked')", (m.users['crew'], m.stores[2], foreign))
    owner = m.login()
    data = m.send('GET', '/api/mobile/accounts/management', token=owner).json()
    assert outsider not in {person['userId'] for person in data['directory']}
    assert next(person for person in data['directory'] if person['userId'] == m.users['crew'])['canSuspend'] is False
    assert m.send('POST', '/api/mobile/accounts/suspend', token=owner, json={
        'expectedStoreId': m.stores[0], 'userId': m.users['crew'], 'suspended': True,
    }).status_code == 403
    # Owners without a selected-store membership must still appear in the business directory.
    with db_connection() as connection:
        connection.execute('DELETE FROM account_store_memberships WHERE user_id=%s', (m.users['owner'],))
    data = m.send('GET', '/api/mobile/accounts/management', token=owner).json()
    assert m.users['owner'] in {person['userId'] for person in data['directory']}
    assert m.users['owner'] not in {person['userId'] for person in data['members']}


def test_native_invite_reissue_activate_and_membership_management_journey(mobile):
    m = mobile
    owner = m.login()
    def post(operation, **fields):
        response = m.send('POST', '/api/mobile/accounts/' + operation, token=owner,
                          json={'expectedStoreId': m.stores[0], **fields})
        assert response.status_code == 200, response.text
        return response.json()
    first = post('invitations', username='new.person', displayName='New Person', role='crew', capabilities=['inventory.view'])
    roster = m.send('GET', '/api/mobile/accounts/management', token=owner).json()
    assert next(person for person in roster['members'] if person['userId'] == first['userId'])['canReissue'] is True
    replacement = post('invitations/reissue', userId=first['userId'])
    assert m.send('POST', '/api/mobile/accounts/activate', json={'token': first['token'], 'password': m.password}).status_code == 400
    activated = m.send('POST', '/api/mobile/accounts/activate', json={'token': replacement['token'], 'password': m.password})
    assert activated.status_code == 200
    crew_token = activated.json()['sessionToken']
    post('memberships', userId=first['userId'], role='crew', capabilities=['inventory.view'], active=False)
    assert m.send('GET', '/api/mobile/accounts/status', token=crew_token).status_code == 401
    post('memberships', userId=first['userId'], role='manager', capabilities=[], active=True)
    login = m.send('POST', '/api/mobile/accounts/login', json={'storeCode': 'mobile-first', 'username': 'new.person', 'password': m.password})
    assert login.json()['actor']['role'] == 'manager'
    # Assign this existing active identity to another authorized store without changing its password.
    switched = m.send('POST', '/api/mobile/accounts/switch-store', token=owner, json={'expectedStoreId': m.stores[0], 'storeId': m.stores[1]})
    owner = switched.json()['sessionToken']
    assigned = m.send('POST', '/api/mobile/accounts/memberships', token=owner, json={
        'expectedStoreId': m.stores[1], 'userId': first['userId'], 'role': 'crew', 'capabilities': [],
    })
    assert assigned.status_code == 200
    assert m.send('POST', '/api/mobile/accounts/login', json={'storeCode': 'mobile-second', 'username': 'new.person', 'password': m.password}).status_code == 200


def test_native_owner_delegation_suspension_cutover_and_transfer_journey(mobile):
    m = mobile
    owner = m.login()
    def post(operation, **fields):
        response = m.send('POST', '/api/mobile/accounts/' + operation, token=owner,
                          json={'expectedStoreId': m.stores[0], **fields})
        assert response.status_code == 200, response.text
        return response.json()
    crew = m.login('crew')
    post('business-memberships', userId=m.users['crew'], role='admin', capabilities=['reports.submit', 'inventory.view'])
    assert m.send('GET', '/api/mobile/accounts/status', token=crew).status_code == 401
    post('memberships', userId=m.users['crew'], role='admin', capabilities=['reports.submit', 'inventory.view'])
    crew = m.login('crew')
    assert m.send('GET', '/api/mobile/accounts/status', token=crew).json()['actor']['role'] == 'admin'
    post('suspend', userId=m.users['crew'], suspended=True)
    assert m.send('GET', '/api/mobile/accounts/status', token=crew).status_code == 401
    post('suspend', userId=m.users['crew'], suspended=False)
    assert m.send('GET', '/api/mobile/accounts/status', token=m.login('crew')).status_code == 200
    post('business-memberships', userId=m.users['crew'], role='admin', capabilities=[], active=False)
    post('memberships', userId=m.users['crew'], role='crew', capabilities=[])
    post('cutover', storeId=m.stores[0])
    assert m.send('GET', '/api/mobile/accounts/management', token=owner).json()['sharedCrewEnabled'] is False
    post('transfer-ownership', userId=m.users['crew'])
    assert m.send('GET', '/api/mobile/accounts/status', token=owner).status_code == 401
    new_owner = m.login('crew')
    assert m.send('GET', '/api/mobile/accounts/status', token=new_owner).json()['actor']['role'] == 'owner'
    assert m.send('GET', '/api/mobile/accounts/management', token=new_owner).json()['isOwner'] is True


def test_native_error_codes_distinguish_domain_conflicts_from_stale_context(mobile):
    m = mobile
    token = m.login()
    fields = {"username": "crew", "expectedStoreId": m.stores[0]}
    duplicate = m.send("POST", "/api/mobile/accounts/invitations", token=token, json=fields)
    assert duplicate.status_code == 409
    assert duplicate.json()["errorCode"] == "duplicate_identifier"
    assert "already exists" in duplicate.json()["error"]
    assert m.send("GET", "/api/mobile/accounts/status", token=token).json()["authenticated"]
    stale = m.send("POST", "/api/mobile/accounts/invitations", token=token,
                   json={**fields, "expectedStoreId": m.stores[1]})
    assert stale.status_code == 409
    assert stale.json()["errorCode"] == "store_context_changed"
    # Browser response bodies remain compatible, including service exception aliases.
    web = m.send("POST", "/api/accounts/invitations", headers=[("Cookie", f"shiftly_account_session={token}")], json=fields)
    assert web.status_code == 409 and web.json() == {"error": duplicate.json()["error"]}


def test_native_permission_denial_and_revoked_context_have_distinct_codes(mobile):
    m = mobile
    token = m.login("crew")
    denied = m.send("GET", "/api/mobile/reports", token=token)
    assert denied.status_code == 403 and denied.json()["errorCode"] == "permission_denied"
    with db_connection() as connection:
        connection.execute("UPDATE account_store_memberships SET state='revoked' WHERE user_id=%s", (m.users['crew'],))
    revoked = m.send("GET", "/api/mobile/reports", token=token)
    assert revoked.status_code == 403 and revoked.json()["errorCode"] == "access_changed"
    with db_connection() as connection:
        connection.execute("UPDATE account_sessions SET revoked_at=NOW() WHERE token_hash=%s", (hash_token(token),))
    ended = m.send("GET", "/api/mobile/accounts/status", token=token)
    assert ended.status_code == 401 and ended.json()["errorCode"] == "session_invalid"
