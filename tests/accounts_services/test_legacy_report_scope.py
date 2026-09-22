"""Legacy inboxes preserve historical content within currently permitted scopes."""

from types import SimpleNamespace
import uuid

import psycopg
import pytest

from backend.shiftly.identity.primitives import hash_store_code, hash_token
from backend.shiftly.identity.repository import IdentityRepository
from backend.shiftly.reports.repository import ReportsRepository
from backend.shiftly.runtime.migrate import migrate


@pytest.fixture
def legacy_inbox(empty_database):
    connect = lambda: psycopg.connect(empty_database)
    migrate(connect)
    with connect() as connection:
        active_business = connection.execute(
            "INSERT INTO businesses(name) VALUES('Active business') RETURNING id"
        ).fetchone()[0]
        disabled_business = connection.execute(
            "INSERT INTO businesses(name,active) VALUES('Disabled business',FALSE) RETURNING id"
        ).fetchone()[0]
        manager_id = connection.execute(
            """INSERT INTO manager_users(username,password_salt,password_hash)
               VALUES('Legacy manager','synthetic salt','synthetic hash') RETURNING id"""
        ).fetchone()[0]
        user_id = connection.execute(
            """INSERT INTO account_users(username,display_name,password_salt,password_hash,legacy_manager_id)
               VALUES('Legacy manager','Legacy manager','synthetic salt','synthetic hash',%s) RETURNING id""",
            (manager_id,),
        ).fetchone()[0]
        cases = {
            'selected': (active_business, True, True, 'active'),
            'other_allowed': (active_business, True, True, 'active'),
            'disabled_store': (active_business, False, True, 'active'),
            'disabled_business': (disabled_business, True, True, 'active'),
            'revoked_membership': (active_business, True, True, 'revoked'),
            'foreign': (active_business, True, False, 'active'),
            'unassigned_compatibility': (None, True, True, 'active'),
        }
        stores, reports = {}, {}
        for name, (business_id, active, assigned, membership_state) in cases.items():
            store_id = connection.execute(
                'INSERT INTO stores(name,access_code_hash,business_id,active) VALUES(%s,%s,%s,%s) RETURNING id',
                (name, hash_store_code(name), business_id, active),
            ).fetchone()[0]
            stores[name] = store_id
            if assigned:
                connection.execute(
                    'INSERT INTO store_memberships(manager_user_id,store_id) VALUES(%s,%s)',
                    (manager_id, store_id),
                )
                connection.execute(
                    """INSERT INTO account_store_memberships(user_id,store_id,business_id,role,state)
                       VALUES(%s,%s,%s,'manager',%s)""",
                    (user_id, store_id, business_id, membership_state),
                )
            report_id = uuid.uuid4()
            reports[name] = report_id
            connection.execute(
                """INSERT INTO reports(id,store_id,employee,shift,notes,report_hash)
                   VALUES(%s,%s,'Original historical name','closing',%s,%s)""",
                (report_id, store_id, f'Historical notes for {name}', hash_token(name)),
            )
            connection.execute('INSERT INTO briefing_jobs(report_id) VALUES(%s)', (report_id,))
        token = 'synthetic-legacy-session'
        connection.execute(
            """INSERT INTO manager_sessions(token_hash,manager_user_id,store_id,expires_at)
               VALUES(%s,%s,%s,NOW()+INTERVAL '1 hour')""",
            (hash_token(token), manager_id, stores['selected']),
        )
    return SimpleNamespace(connect=connect, repository=ReportsRepository(connect),
                           identity=IdentityRepository(connect), manager_id=manager_id,
                           user_id=user_id, token=token, stores=stores, reports=reports)


def test_legacy_inbox_excludes_disabled_and_revoked_scopes_beyond_selected_store(legacy_inbox):
    inbox = legacy_inbox
    assert inbox.identity.manager_id(inbox.token) == inbox.manager_id
    assert inbox.identity.selected_store(inbox.token, inbox.manager_id) == inbox.stores['selected']
    rows = inbox.repository.for_manager(inbox.manager_id)
    assert {row[0] for row in rows} == {
        inbox.reports['selected'], inbox.reports['other_allowed'], inbox.reports['unassigned_compatibility'],
    }
    assert all(row[1] == 'Original historical name' for row in rows)
    assert all(row[5] == 'pending' for row in rows)
    with inbox.connect() as connection:
        assert connection.execute('SELECT count(*) FROM reports').fetchone() == (7,)


@pytest.mark.parametrize('state', ['suspended', 'pending'])
def test_legacy_inbox_rechecks_named_account_state(legacy_inbox, state):
    inbox = legacy_inbox
    with inbox.connect() as connection:
        connection.execute('UPDATE account_users SET state=%s WHERE id=%s', (state, inbox.user_id))
    assert not inbox.identity.manager_id(inbox.token)
    assert inbox.repository.for_manager(inbox.manager_id) == []


def test_legacy_inbox_rechecks_original_manager_state(legacy_inbox):
    inbox = legacy_inbox
    with inbox.connect() as connection:
        connection.execute('UPDATE manager_users SET active=FALSE WHERE id=%s', (inbox.manager_id,))
    assert not inbox.identity.manager_id(inbox.token)
    assert inbox.repository.for_manager(inbox.manager_id) == []


def test_legacy_inbox_preserves_missing_named_membership_compatibility(legacy_inbox):
    inbox = legacy_inbox
    with inbox.connect() as connection:
        connection.execute(
            'DELETE FROM account_store_memberships WHERE user_id=%s AND store_id=%s',
            (inbox.user_id, inbox.stores['other_allowed']),
        )
    assert inbox.reports['other_allowed'] in {row[0] for row in inbox.repository.for_manager(inbox.manager_id)}


def test_legacy_inbox_preserves_unenrolled_manager_compatibility(legacy_inbox):
    inbox = legacy_inbox
    with inbox.connect() as connection:
        connection.execute('DELETE FROM account_store_memberships WHERE user_id=%s', (inbox.user_id,))
        connection.execute('DELETE FROM account_users WHERE id=%s', (inbox.user_id,))
    assert inbox.identity.manager_id(inbox.token) == inbox.manager_id
    assert {row[0] for row in inbox.repository.for_manager(inbox.manager_id)} == {
        inbox.reports['selected'], inbox.reports['other_allowed'],
        inbox.reports['revoked_membership'], inbox.reports['unassigned_compatibility'],
    }
