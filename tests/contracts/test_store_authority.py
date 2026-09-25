import hashlib

import pytest

from database import db_connection
from reporting import queue_report


@pytest.mark.parametrize("revocation", ["expired", "inactive_manager", "inactive_store", "membership"])
def test_revoked_manager_cannot_read_or_write_through_either_server(api, workspace, revocation):
    token_hash = hashlib.sha256(workspace["manager_cookie"].split("=", 1)[1].encode()).hexdigest()
    with db_connection() as connection:
        manager_id = connection.execute("SELECT user_id FROM account_sessions WHERE token_hash=%s", (token_hash,)).fetchone()[0]
        if revocation == "expired":
            connection.execute("UPDATE account_sessions SET expires_at=NOW()-INTERVAL '1 second' WHERE token_hash=%s", (token_hash,))
        elif revocation == "inactive_manager":
            connection.execute("UPDATE account_users SET state='suspended' WHERE id=%s", (manager_id,))
        elif revocation == "inactive_store":
            connection.execute("UPDATE stores SET active=false WHERE id=%s", (workspace["store_id"],))
        else:
            connection.execute("DELETE FROM account_store_memberships WHERE user_id=%s", (manager_id,))
    for path in ("/api/reports", "/api/managers", "/api/heads-up", "/api/weekly-overview"):
        assert api.request("GET", path, cookie=workspace["manager_cookie"]).status == 401
    for path in ("/api/reports", "/api/heads-up"):
        assert api.request("POST", path, payload={}, cookie=workspace["manager_cookie"]).status == 401
    assert api.request("GET", "/manager.html", cookie=workspace["manager_cookie"]).status == 302


def test_store_inbox_and_writes_ignore_request_spoofing(api, workspace):
    from tests.account_fixtures import seed_workspace
    other=seed_workspace(store_code='second',manager_name='Second')
    second=other['store_id']; first=workspace['store_id']
    queue_report('First Crew','closing','First store original notes.',first)
    queue_report('Second Crew','closing','Second store original notes.',second)
    inbox=api.request('GET',f'/api/reports?storeId={second}',cookie=workspace['manager_cookie'])
    assert {item['employee'] for item in inbox.json()['reports']}=={'First Crew'}
    assert api.request('POST','/api/accounts/switch-store',cookie=workspace['manager_cookie'],payload={'storeId':second}).status==403
    assert api.request('POST','/api/heads-up',cookie=workspace['manager_cookie'],payload={'message':'Only my store','storeId':second}).status==200
    with db_connection() as c:
        assert c.execute("SELECT store_id FROM store_heads_up WHERE message='Only my store'").fetchone()==(first,)


def test_public_account_creation_is_closed_even_with_old_admin_key(api, workspace):
    for path in ('/api/auth/signup','/api/auth/add-manager'):
        for key in ('wrong','contract-admin-key'):
            response=api.request('POST',path,payload={'adminKey':key,'storeCode':workspace['store_code'],'managerUsername':'bypass','managerPassword':'new-password-123','confirmPassword':'new-password-123'})
            assert response.status==403 and not response.cookies()
    with db_connection() as c:
        assert not c.execute("SELECT 1 FROM account_users WHERE username='bypass'").fetchone()
