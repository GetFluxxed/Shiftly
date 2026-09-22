"""Synthetic named-account authentication/policy and durable-session contracts."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import psycopg
import pytest

from backend.shiftly.identity.accounts_core import AccountCore, ensure_manager_account, policy_lock
from backend.shiftly.identity.accounts_policy import (
    ALL_CAPABILITIES, CREW_CAPABILITIES, MANAGER_CAPABILITIES, assert_grant, capabilities_for,
)
from backend.shiftly.identity.primitives import hash_store_code, hash_token, password_hash
from backend.shiftly.identity.service import IdentityError
from database import db_connection


def user(connection, username, password="same-password", *, legacy_id=None):
    return connection.execute(
        """INSERT INTO account_users (username,display_name,password_salt,password_hash,legacy_manager_id)
           VALUES (%s,%s,'test-salt',%s,%s) RETURNING id""",
        (username, username, password_hash(password, "test-salt"), legacy_id),
    ).fetchone()[0]


def store(connection, code, business):
    return connection.execute(
        """INSERT INTO stores (name,access_code_hash,business_id,accounts_enabled)
           VALUES (%s,%s,%s,true) RETURNING id""", (code, hash_store_code(code), business),
    ).fetchone()[0]


def membership(connection, uid, sid, bid, role="crew", grants=()):
    connection.execute(
        """INSERT INTO account_store_memberships (user_id,store_id,business_id,role,capabilities)
           VALUES (%s,%s,%s,%s,%s)""", (uid, sid, bid, role, list(grants)),
    )


@pytest.fixture
def foundation(isolated_database):
    core = AccountCore(db_connection)
    with db_connection() as connection:
        business = connection.execute("INSERT INTO businesses(name) VALUES ('Synthetic') RETURNING id").fetchone()[0]
        other_business = connection.execute("INSERT INTO businesses(name) VALUES ('Other') RETURNING id").fetchone()[0]
        first, second, third = store(connection, "first", business), store(connection, "second", business), store(connection, "third", other_business)
        owner = user(connection, "Owner")
        manager = user(connection, "Manager")
        crew = user(connection, "Crew")
        admin = user(connection, "Admin")
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role) VALUES (%s,%s,'owner')", (owner,business))
        membership(connection, manager, first, business, "manager")
        membership(connection, crew, first, business, grants=("inventory.view", "counts.submit"))
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role,capabilities) VALUES (%s,%s,'admin',%s)", (admin,business,list(ALL_CAPABILITIES)))
        membership(connection, admin, first, business, "admin", ("inventory.view", "reports.view"))
    return core, {"owner":owner,"manager":manager,"crew":crew,"admin":admin,"business":business,"other_business":other_business,"first":first,"second":second,"third":third}


def signed(core, name="owner", code="first"):
    return core.login(code, name, "same-password", client_key="synthetic")


def test_named_credentials_identify_equal_password_users(foundation):
    core, ids = foundation
    manager, crew = signed(core, "manager"), signed(core, "crew")
    assert core.resolve_actor(manager.token).user_id == ids["manager"]
    assert core.resolve_actor(crew.token).user_id == ids["crew"]
    assert manager.role == crew.role == "account"
    assert manager.response["role"] == "manager" and crew.response["role"] == "crew"
    assert manager.token not in repr(manager)
    with db_connection() as connection:
        hashes = connection.execute("SELECT token_hash FROM account_sessions").fetchall()
    assert (hash_token(manager.token),) in hashes
    assert manager.token not in str(hashes)


def test_named_username_normalization_and_collision(foundation):
    core, ids = foundation
    assert core.resolve_actor(signed(core, "  ＣＲＥＷ ").token).user_id == ids["crew"]
    with pytest.raises(psycopg.errors.UniqueViolation), db_connection() as connection:
        user(connection, "Ｃｒｅｗ")
    with db_connection() as connection:
        uid = user(connection, "Two   Names")
        membership(connection, uid, ids["first"], ids["business"])
    assert core.resolve_actor(signed(core, " two names ").token).user_id == uid


@pytest.mark.parametrize("name,password,code", [("nobody","same-password","first"),("crew","wrong","first"),("crew","same-password","third"),("crew","same-password","nonexistent")])
def test_named_login_denies_wrong_identity_and_scope(foundation, name, password, code):
    core, _ = foundation
    with pytest.raises(IdentityError) as error:
        core.login(code,name,password,client_key="bad")
    assert error.value.code == "unauthenticated"
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM account_sessions").fetchone()[0] == 0


@pytest.mark.parametrize("name,allowed,denied", [
    ("owner", "catalog.manage", None),
    ("manager", "stock.adjust", "catalog.manage"),
    ("crew", "counts.submit", "counts.approve"),
    ("admin", "inventory.view", "memberships.manage"),
])
def test_effective_role_capability_matrix(foundation, name, allowed, denied):
    core, _ = foundation
    token = signed(core,name).token
    assert allowed in core.resolve_actor(token,capability=allowed).capabilities
    if denied:
        with pytest.raises(IdentityError) as error:
            core.resolve_actor(token,capability=denied)
        assert error.value.code == "forbidden"


def test_manager_shared_catalog_requires_distinct_business_delegation(foundation):
    core, ids = foundation
    token = signed(core,"manager").token
    assert "catalog.manage" not in core.resolve_actor(token).capabilities
    with db_connection() as connection:
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role,capabilities) VALUES (%s,%s,'admin',ARRAY['catalog.manage'])", (ids["manager"],ids["business"]))
    actor = core.resolve_actor(token)
    assert actor.role == "manager" and "catalog.manage" in actor.capabilities
    assert "memberships.manage" not in actor.capabilities


def test_owner_has_business_stores_and_admin_only_delegated_store(foundation):
    core, ids = foundation
    owner = signed(core).token
    admin = signed(core,"admin").token
    assert [s["storeId"] for s in core.authorized_stores(owner)] == [ids["first"],ids["second"]]
    assert [s["storeId"] for s in core.authorized_stores(admin)] == [ids["first"]]
    assert core.resolve_actor(owner,store_id=ids["second"]).store_id == ids["second"]
    with pytest.raises(IdentityError):
        core.resolve_actor(owner,store_id=ids["third"])
    with pytest.raises(IdentityError):
        core.resolve_actor(admin,store_id=ids["second"])
    assert core.resolve_actor(owner).store_id == ids["first"]


def test_store_switch_rotates_token_and_preserves_authority(foundation):
    core, ids = foundation
    initial = signed(core)
    switched = core.switch_store(initial.token,ids["second"])
    assert switched.token != initial.token
    assert core.resolve_actor(switched.token).store_id == ids["second"]
    with pytest.raises(IdentityError):
        core.resolve_actor(initial.token)
    with pytest.raises(IdentityError):
        core.switch_store(switched.token,ids["third"])
    assert core.resolve_actor(switched.token).store_id == ids["second"]


@pytest.mark.parametrize("sql,field", [
    ("UPDATE account_users SET state='suspended' WHERE id=%s","crew"),
    ("UPDATE account_users SET credential_version=credential_version+1 WHERE id=%s","crew"),
    ("UPDATE account_store_memberships SET state='revoked' WHERE user_id=%s","crew"),
    ("UPDATE stores SET active=false WHERE id=%s","first"),
    ("UPDATE businesses SET active=false WHERE id=%s","business"),
])
def test_current_policy_revokes_existing_session(foundation, sql, field):
    core, ids = foundation
    token = signed(core,"crew").token
    with db_connection() as connection:
        connection.execute(sql,(ids[field],))
    with pytest.raises(IdentityError):
        core.resolve_actor(token)


def test_logout_and_logout_all_are_durable(foundation):
    core, _ = foundation
    first, second = signed(core), signed(core)
    core.logout(first.token)
    core.logout(first.token)
    with pytest.raises(IdentityError):
        core.resolve_actor(first.token)
    assert core.resolve_actor(second.token)
    third = signed(core)
    core.logout_all(second.token)
    for token in (second.token,third.token):
        with pytest.raises(IdentityError):
            core.resolve_actor(token)


def test_unmapped_legacy_manager_is_named_but_reporting_only(isolated_database):
    core = AccountCore(db_connection)
    with db_connection() as connection:
        sid = connection.execute("INSERT INTO stores(name,access_code_hash) VALUES ('legacy',%s) RETURNING id", (hash_store_code("legacy"),)).fetchone()[0]
        mid = connection.execute("INSERT INTO manager_users(username,password_salt,password_hash) VALUES ('Legacy','preserved',%s) RETURNING id", (password_hash("same-password","preserved"),)).fetchone()[0]
        connection.execute("INSERT INTO store_memberships(manager_user_id,store_id) VALUES (%s,%s)",(mid,sid))
        uid = ensure_manager_account(connection,mid)
        assert ensure_manager_account(connection,mid) == uid
    actor = core.resolve_actor(signed(core,"legacy","legacy").token)
    assert actor.legacy_manager_id == mid and actor.user_id == uid
    assert actor.capabilities == {"reports.submit","reports.view","reports.manage"}
    with db_connection() as connection:
        connection.execute("UPDATE account_store_memberships SET state='revoked' WHERE user_id=%s",(uid,))
        ensure_manager_account(connection,mid)
    with pytest.raises(IdentityError):
        signed(core,"legacy","legacy")


def test_manager_mapping_never_merges_people(isolated_database):
    with db_connection() as connection:
        uid = user(connection,"Existing")
        mid = connection.execute("INSERT INTO manager_users(username,password_salt,password_hash) VALUES ('existing','salt','hash') RETURNING id").fetchone()[0]
        with pytest.raises(IdentityError) as error:
            ensure_manager_account(connection,mid)
        assert error.value.code == "conflict"
        assert connection.execute("SELECT legacy_manager_id FROM account_users WHERE id=%s",(uid,)).fetchone()[0] is None


def test_authorization_and_audit_share_write_transaction(foundation):
    core, ids = foundation
    token = signed(core).token
    with pytest.raises(RuntimeError), db_connection() as connection:
        actor = core.require(token,"memberships.manage",connection=connection)
        core._audit(connection,actor,"synthetic.write",store_id=ids["first"])
        connection.execute("UPDATE stores SET name='should roll back' WHERE id=%s",(ids["first"],))
        raise RuntimeError("injected failure")
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM account_audit WHERE action='synthetic.write'").fetchone()[0] == 0
        assert connection.execute("SELECT name FROM stores WHERE id=%s",(ids["first"],)).fetchone()[0] == "first"


def test_policy_lock_serializes_revocation_and_privileged_write(foundation):
    core, ids = foundation
    token = signed(core,"manager").token
    waiting = Event()
    def attempted_write():
        with db_connection() as connection:
            waiting.set()
            try:
                core.require(token,"stock.adjust",connection=connection)
            except IdentityError:
                return "denied"
            core._audit(connection,ids["manager"],"should.not.write")
            return "wrote"
    with ThreadPoolExecutor(max_workers=1) as executor:
        with db_connection() as connection:
            policy_lock(connection)
            connection.execute("UPDATE account_store_memberships SET state='revoked' WHERE user_id=%s",(ids["manager"],))
            future = executor.submit(attempted_write)
            assert waiting.wait(3)
            assert not future.done()
        assert future.result(timeout=5) == "denied"
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM account_audit WHERE action='should.not.write'").fetchone()[0] == 0


def test_construction_and_policy_are_framework_free_without_io():
    def forbidden():
        raise AssertionError("Unexpected connection")
    core = AccountCore(forbidden)
    assert core.session_ttl == 28800
    assert capabilities_for("crew") == {"reports.submit"}
    assert capabilities_for("crew", ["counts.submit"]) == {"reports.submit", "counts.submit"}
    assert capabilities_for("manager") == MANAGER_CAPABILITIES
    with pytest.raises(IdentityError):
        capabilities_for("crew",["counts.approve"])


def test_crew_receives_only_explicit_operational_grants(foundation):
    core, _ = foundation
    actor = core.resolve_actor(signed(core,"crew").token)
    assert actor.capabilities == {"reports.submit", "inventory.view", "counts.submit"}
    assert not {"receipts.draft", "catalog.propose", "counts.approve"} & actor.capabilities


def test_audit_defaults_to_verified_actor_scope(foundation):
    core, ids = foundation
    actor = core.resolve_actor(signed(core).token)
    with db_connection() as connection:
        core._audit(connection,actor,"scope.test")
        row = connection.execute("SELECT actor_user_id,store_id,business_id FROM account_audit WHERE action='scope.test'").fetchone()
    assert row == (ids["owner"],ids["first"],ids["business"])


def test_mapped_store_rejects_null_membership_scope_at_commit(foundation):
    _, ids = foundation
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db_connection() as connection:
        uid = user(connection, "bad-null-scope")
        membership(connection,uid,ids["first"],None)


def test_mapping_can_update_store_and_memberships_in_one_transaction(isolated_database):
    with db_connection() as connection:
        uid = user(connection,"mapping-user")
        business = connection.execute("INSERT INTO businesses(name) VALUES ('Mapped') RETURNING id").fetchone()[0]
        sid = connection.execute("INSERT INTO stores(name,access_code_hash) VALUES ('Unmapped','mapping-hash') RETURNING id").fetchone()[0]
        membership(connection,uid,sid,None)
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db_connection() as connection:
        connection.execute("UPDATE stores SET business_id=%s WHERE id=%s",(business,sid))
    with db_connection() as connection:
        connection.execute("UPDATE stores SET business_id=%s WHERE id=%s",(business,sid))
        connection.execute("UPDATE account_store_memberships SET business_id=%s WHERE store_id=%s",(business,sid))
    with db_connection() as connection:
        assert connection.execute("SELECT business_id FROM account_store_memberships WHERE user_id=%s",(uid,)).fetchone()[0] == business


def test_invitation_scope_cannot_bypass_composite_fk_with_null(foundation):
    import uuid
    _, ids = foundation
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db_connection() as connection:
        connection.execute(
            """INSERT INTO account_invitations (id,token_hash,user_id,store_id,business_id,role,created_by,expires_at)
               VALUES (%s,%s,%s,%s,NULL,'crew',%s,NOW()+INTERVAL '1 day')""",
            (uuid.uuid4(),hash_token('synthetic-bad-invite'),ids['crew'],ids['first'],ids['owner']),
        )
