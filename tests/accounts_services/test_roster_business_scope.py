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
        'businessRole':'owner','businessState':'active','businessCapabilities':[],
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
