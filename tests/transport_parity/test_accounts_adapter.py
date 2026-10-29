from backend.shiftly.identity.primitives import hash_store_code, password_hash
from database import db_connection


def seed_named_manager():
    with db_connection() as connection:
        business = connection.execute(
            "INSERT INTO businesses(name) VALUES ('Named Business') RETURNING id"
        ).fetchone()[0]
        store = connection.execute(
            """
            INSERT INTO stores(name, access_code_hash, business_id, accounts_enabled, shared_crew_enabled)
            VALUES ('Named Store', %s, %s, true, false) RETURNING id
            """,
            (hash_store_code("named-store"), business),
        ).fetchone()[0]
        user = connection.execute(
            """
            INSERT INTO account_users(username, display_name, password_salt, password_hash)
            VALUES ('named-manager', 'Named Manager', 'test-salt', %s) RETURNING id
            """,
            (password_hash("named-password", "test-salt"),),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO account_store_memberships(user_id, store_id, business_id, role, capabilities)
            VALUES (%s, %s, %s, 'manager', %s)
            """,
            (user, store, business, ["reports.submit", "reports.view", "reports.manage", "inventory.view"]),
        )


def test_named_login_status_and_permission_aware_pages(transport_clients):
    fastapi_client, _ = transport_clients
    seed_named_manager()
    login = fastapi_client.post(
        "/api/accounts/login",
        json={"storeCode": "named-store", "username": "named-manager", "password": "named-password"},
    )
    assert login.status_code == 200
    actor = login.json()["actor"]
    assert actor["username"] == "named-manager"
    assert "inventory.view" in actor["capabilities"]
    assert "shiftly_account_session" in login.headers.get("set-cookie", "")

    status = fastapi_client.get("/api/accounts/status")
    assert status.status_code == 200
    assert status.json()["actor"]["displayName"] == "Named Manager"
    assert fastapi_client.get("/inventory.html", follow_redirects=False).status_code == 200
    assert fastapi_client.get("/accounts.html", follow_redirects=False).status_code == 200


def test_named_logout_all_clears_named_and_legacy_cookies(transport_clients):
    fastapi_client, _ = transport_clients
    seed_named_manager()
    assert fastapi_client.post(
        "/api/accounts/login",
        json={"storeCode": "named-store", "username": "named-manager", "password": "named-password"},
    ).status_code == 200
    logout = fastapi_client.post("/api/accounts/logout-all", json={})
    assert logout.status_code == 200
    cookies = logout.headers.get_list("set-cookie")
    assert any("shiftly_account_session=" in cookie and "Max-Age=0" in cookie for cookie in cookies)
    assert fastapi_client.get("/api/accounts/status").json()["authenticated"] is False
