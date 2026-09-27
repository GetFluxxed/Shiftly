"""Roster metadata describes only delegation in the selected store's business."""
import pytest

from backend.shiftly.identity.accounts import AccountsService
from backend.shiftly.identity.primitives import hash_store_code
from backend.shiftly.identity.service import IdentityError
from database import db_connection


@pytest.fixture
def roster_scope(isolated_database):
    accounts=AccountsService(db_connection)
    users={}
    with db_connection() as connection:
        business=connection.execute("INSERT INTO businesses(name) VALUES('Roster business') RETURNING id").fetchone()[0]
        other=connection.execute("INSERT INTO businesses(name) VALUES('Private other business') RETURNING id").fetchone()[0]
        store=connection.execute("INSERT INTO stores(name,access_code_hash,business_id,accounts_enabled) VALUES('Roster store',%s,%s,true) RETURNING id",(hash_store_code('roster-store'),business)).fetchone()[0]
        foreign=connection.execute("INSERT INTO stores(name,access_code_hash,business_id,accounts_enabled) VALUES('Other store',%s,%s,true) RETURNING id",(hash_store_code('private-store'),other)).fetchone()[0]
        for name in ('viewer','owner','delegated','revoked','foreign_owner','ordinary','private'):
            users[name]=connection.execute(
                "INSERT INTO account_users(username,display_name,password_salt,password_hash) VALUES(%s,%s,'synthetic','unused') RETURNING id",
                (name,name),
            ).fetchone()[0]
            sid,bid=(foreign,other) if name=='private' else (store,business)
            connection.execute("INSERT INTO account_store_memberships(user_id,store_id,business_id,role,capabilities) VALUES(%s,%s,%s,%s,%s)",
                               (users[name],sid,bid,'manager' if name=='viewer' else 'crew',['memberships.manage'] if name=='viewer' else ['counts.submit']))
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role) VALUES(%s,%s,'owner'),(%s,%s,'owner')",
                           (users['owner'],business,users['foreign_owner'],other))
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role,state,capabilities) VALUES(%s,%s,'admin','active',ARRAY['catalog.manage']),(%s,%s,'admin','revoked',ARRAY['reports.view'])",
                           (users['delegated'],business,users['revoked'],business))
        token=accounts._issue_session(connection,users['viewer'],store).token
    return accounts,users,store,foreign,token


def test_roster_preserves_local_role_and_exposes_selected_business_authority(roster_scope):
    accounts,users,store,_,token=roster_scope
    result=accounts.roster(token)
    rows={row['userId']:row for row in result['members']}
    assert result['storeId']==store
    assert rows[users['owner']]=={
        'userId':users['owner'],'username':'owner','displayName':'owner','accountState':'active',
        'role':'crew','membershipState':'active','capabilities':['counts.submit'],
        'businessRole':'owner','businessState':'active','businessCapabilities':[], 'lastSignInAt':None,
    }
    delegated=rows[users['delegated']]
    assert delegated['role']=='crew' and delegated['businessRole']=='admin'
    assert delegated['businessState']=='active' and delegated['businessCapabilities']==['catalog.manage']


def test_roster_reports_revoked_delegation_without_treating_it_as_active(roster_scope):
    accounts,users,_,_,token=roster_scope
    revoked=next(row for row in accounts.roster(token)['members'] if row['userId']==users['revoked'])
    assert revoked['membershipState']=='active'
    assert revoked['businessRole']=='admin' and revoked['businessState']=='revoked'
    assert revoked['businessCapabilities']==['reports.view']


def test_roster_does_not_disclose_other_business_roles_or_unlisted_people(roster_scope):
    accounts,users,_,foreign,token=roster_scope
    rows={row['userId']:row for row in accounts.roster(token)['members']}
    for name in ('ordinary','foreign_owner'):
        row=rows[users[name]]
        assert row['businessRole'] is None and row['businessState'] is None
        assert row['businessCapabilities']==[]
    assert users['private'] not in rows
    with pytest.raises(IdentityError) as denied:
        accounts.roster(token,store_id=foreign)
    assert denied.value.code=='forbidden'


def test_recent_sign_ins_are_store_scoped_and_nulls_sort_last(roster_scope):
    accounts,users,store,foreign,token=roster_scope
    with db_connection() as connection:
        for name,action,hour,sid in [
            ('ordinary','session.login',3,store),('ordinary','session.login',1,store),
            ('revoked','session.login',3,store),('delegated','session.login',2,store),
            ('owner','account.activated',1,store),('foreign_owner','session.login',4,foreign),
            ('private','session.login',5,store),('viewer','session.switch_store',6,store),
        ]:
            connection.execute(
                "INSERT INTO account_audit(actor_user_id,subject_user_id,store_id,action,created_at) VALUES(%s,%s,%s,%s,%s)",
                (None if action=='account.activated' else users[name], users[name] if action=='account.activated' else None,
                 sid,action,f'2026-09-25 {hour:02d}:00:00+00'),
            )
    rows=accounts.roster(token)['members']
    assert [row['username'] for row in rows]==['ordinary','revoked','delegated','owner','foreign_owner','viewer']
    assert rows[0]['lastSignInAt']=='2026-09-25T03:00:00+00:00'
    assert rows[3]['lastSignInAt']=='2026-09-25T01:00:00+00:00'
    assert all(row['lastSignInAt'] is None for row in rows[4:])
    managed=accounts.management(token)['members']
    assert [(row['userId'],row['lastSignInAt']) for row in managed]==[(row['userId'],row['lastSignInAt']) for row in rows]


def test_session_refresh_and_rotation_do_not_fabricate_sign_in_dates(roster_scope):
    accounts,users,store,_,token=roster_scope
    with db_connection() as connection:
        accounts._issue_session(connection,users['ordinary'],store)
        connection.execute('UPDATE account_sessions SET last_seen_at=NOW()')
    assert all(member['lastSignInAt'] is None for member in accounts.roster(token)['members'])
