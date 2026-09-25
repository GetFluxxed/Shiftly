"""Explicit individual identities for release HTTP tests; no public bootstrap."""
from backend.shiftly.identity.accounts import AccountsService
from backend.shiftly.identity.primitives import hash_store_code, password_hash
from database import db_connection


def seed_workspace(*, store_code, manager_name, manager_password='manager-password-123', crew_password='crew-password-123', store_name=None):
    salt='release-test-salt'
    with db_connection() as c:
        business=c.execute('INSERT INTO businesses(name) VALUES(%s) RETURNING id',(store_name or manager_name,)).fetchone()[0]
        sid=c.execute('INSERT INTO stores(name,access_code_hash,business_id,accounts_enabled,shared_crew_enabled) VALUES(%s,%s,%s,true,false) RETURNING id',
                      (store_name or f'{manager_name} Store',hash_store_code(store_code),business)).fetchone()[0]
        ids=[]
        for username,role,password in [(manager_name,'manager',manager_password),(manager_name+'-crew','crew',crew_password)]:
            uid=c.execute('INSERT INTO account_users(username,display_name,password_salt,password_hash) VALUES(%s,%s,%s,%s) RETURNING id',
                          (username,username,salt,password_hash(password,salt))).fetchone()[0]
            c.execute('INSERT INTO account_store_memberships(user_id,store_id,business_id,role) VALUES(%s,%s,%s,%s)',(uid,sid,business,role))
            ids.append(uid)
    session=AccountsService(db_connection).login(None,manager_name,manager_password,client_key='fixture')
    return dict(store_id=sid,store_code=store_code,manager_name=manager_name,manager_username=manager_name,
                crew_username=manager_name+'-crew',manager_password=manager_password,crew_password=crew_password,
                user_id=ids[0],crew_user_id=ids[1],manager_cookie='shiftly_account_session='+session.token)
