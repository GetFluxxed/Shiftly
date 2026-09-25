import hashlib

from database import db_connection


def test_malformed_login_and_invalid_role_are_rejected(api):
    malformed = api.request("POST", "/api/auth/login", raw=b"{")
    assert malformed.status == 400
    assert malformed.json()["error"] == "Invalid login request."

    invalid_role = api.request(
        "POST",
        "/api/auth/login",
        payload={"storeCode": "missing", "role": "owner", "password": "password"},
    )
    assert invalid_role.status == 400
    assert invalid_role.json()["error"] == "Username must be text."


def test_login_status_and_logout_preserve_cookie_contract(api, workspace):
    login = api.request(
        "POST",
        "/api/auth/login",
        payload={
            "username": workspace["manager_username"],
            "password": workspace["manager_password"],
        },
    )
    assert login.status == 200
    assert login.json()["role"] == "manager"
    manager_cookie = login.cookies()[0]

    status = api.request("GET", "/api/auth/status", cookie=manager_cookie)
    assert status.status == 200
    assert status.json()["authenticated"] is True
    assert status.json()["role"] == "manager"

    logout = api.request("POST", "/api/auth/logout", cookie=manager_cookie)
    assert logout.status == 200
    assert {cookie.split("=", 1)[0] for cookie in logout.cookies()} == {
        "shiftly_account_session",
        "shiftly_manager_session",
        "shiftly_crew_session",
    }
    assert api.request("GET", "/api/auth/status", cookie=manager_cookie).json()["authenticated"] is False


def test_expired_manager_session_is_denied(api, workspace):
    token = workspace["manager_cookie"].split("=", 1)[1]
    with db_connection() as connection:
        connection.execute(
            "UPDATE account_sessions SET expires_at = NOW() - INTERVAL '1 second' WHERE token_hash = %s",
            (hashlib.sha256(token.encode()).hexdigest(),),
        )

    response = api.request("GET", "/api/reports", cookie=workspace["manager_cookie"])
    assert response.status == 401


def test_cross_store_reports_are_not_visible(api, workspace):
    from tests.account_fixtures import seed_workspace
    other=seed_workspace(store_code='other-store',manager_name='other-manager')
    crew_login = api.request(
        "POST",
        "/api/auth/login",
        payload={"username": other["crew_username"], "password": other["crew_password"]},
    )
    assert crew_login.status == 200
    report = api.request(
        "POST",
        "/api/reports",
        cookie=crew_login.cookies()[0],
        payload={"employee": "Other Store", "shift": "closing", "notes": "A separate store update."},
    )
    assert report.status == 202

    manager_reports = api.request("GET", "/api/reports", cookie=workspace["manager_cookie"])
    assert manager_reports.status == 200
    assert all(item["employee"] != "Other Store" for item in manager_reports.json()["reports"])
