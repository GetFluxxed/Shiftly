import hashlib

import pytest

from database import db_connection
from reporting import queue_report


@pytest.mark.parametrize("revocation", ["expired", "inactive_manager", "inactive_store", "membership"])
def test_revoked_manager_cannot_read_or_write_through_either_server(api, workspace, revocation):
    token_hash = hashlib.sha256(workspace["manager_cookie"].split("=", 1)[1].encode()).hexdigest()
    with db_connection() as connection:
        manager_id = connection.execute("SELECT manager_user_id FROM manager_sessions WHERE token_hash=%s", (token_hash,)).fetchone()[0]
        if revocation == "expired":
            connection.execute("UPDATE manager_sessions SET expires_at=NOW()-INTERVAL '1 second' WHERE token_hash=%s", (token_hash,))
        elif revocation == "inactive_manager":
            connection.execute("UPDATE manager_users SET active=false WHERE id=%s", (manager_id,))
        elif revocation == "inactive_store":
            connection.execute("UPDATE stores SET active=false WHERE id=%s", (workspace["store_id"],))
        else:
            connection.execute("DELETE FROM store_memberships WHERE manager_user_id=%s", (manager_id,))
    for path in ("/api/reports", "/api/managers", "/api/heads-up", "/api/weekly-overview"):
        assert api.request("GET", path, cookie=workspace["manager_cookie"]).status == 401
    for path in ("/api/reports", "/api/heads-up"):
        assert api.request("POST", path, payload={}, cookie=workspace["manager_cookie"]).status == 401
    assert api.request("GET", "/manager.html", cookie=workspace["manager_cookie"]).status == 302


def test_membership_inbox_and_selected_store_ignore_request_spoofing(api, workspace):
    with db_connection() as connection:
        second = connection.execute("INSERT INTO stores (name,access_code_hash) VALUES ('Second','second') RETURNING id").fetchone()[0]
        token_hash = hashlib.sha256(workspace["manager_cookie"].split("=", 1)[1].encode()).hexdigest()
        manager_id = connection.execute("SELECT manager_user_id FROM manager_sessions WHERE token_hash=%s", (token_hash,)).fetchone()[0]
        connection.execute("INSERT INTO store_memberships (manager_user_id,store_id) VALUES (%s,%s)", (manager_id, second))
        connection.execute("UPDATE manager_sessions SET store_id=%s WHERE token_hash=%s", (second, token_hash))
    queue_report("First Crew", "closing", "First store original notes.", workspace["store_id"])
    queue_report("Second Crew", "closing", "Second store original notes.", second)
    inbox = api.request("GET", "/api/reports", cookie=workspace["manager_cookie"])
    assert {item["employee"] for item in inbox.json()["reports"]} == {"First Crew", "Second Crew"}
    weekly = api.request("GET", f"/api/weekly-overview?storeId={workspace['store_id']}", cookie=workspace["manager_cookie"])
    assert weekly.status == 200 and weekly.json()["reportCount"] == 1
    posted = api.request("POST", "/api/heads-up", cookie=workspace["manager_cookie"],
                         payload={"message": "Selected store only", "storeId": workspace["store_id"]})
    assert posted.status == 200
    submitted = api.request("POST", "/api/reports", cookie=workspace["manager_cookie"], payload={
        "employee": "Scoped Crew", "shift": "opening", "notes": "Verified the receiving area and restocked cups.",
        "storeId": workspace["store_id"],
    })
    assert submitted.status == 202
    with db_connection() as connection:
        assert connection.execute("SELECT store_id FROM store_heads_up WHERE message='Selected store only'").fetchone() == (second,)
        assert connection.execute("SELECT store_id FROM reports WHERE employee='Scoped Crew'").fetchone() == (second,)


def test_add_manager_preserves_admin_guard_and_individual_session(api, workspace):
    fields = {"adminKey": "wrong", "storeCode": workspace["store_code"],
              "managerUsername": "second-manager", "managerPassword": "new-password-123",
              "confirmPassword": "new-password-123"}
    denied = api.request("POST", "/api/auth/add-manager", payload=fields)
    assert denied.status == 403
    fields["adminKey"] = "contract-admin-key"
    created = api.request("POST", "/api/auth/add-manager", payload=fields)
    assert created.status == 201
    assert created.json()["role"] == "manager"
    status = api.request("GET", "/api/auth/status", cookie=created.cookies()[0])
    assert status.json()["managerName"] == "second-manager"
    managers = api.request("GET", "/api/managers", cookie=workspace["manager_cookie"])
    assert {item["name"] for item in managers.json()["managers"]} == {"contract-manager", "second-manager"}
