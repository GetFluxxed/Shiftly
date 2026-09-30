"""Focused policy boundaries for dedicated Production accounts."""

import psycopg
import pytest

from backend.shiftly.identity.accounts import AccountsService
from backend.shiftly.identity.accounts_policy import (
    MANAGER_CAPABILITIES, PRODUCTION_CAPABILITIES, AccountActor, assert_grant, capabilities_for,
)
from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.identity.primitives import hash_store_code, password_hash
from backend.shiftly.runtime.migrate import migrate


def denied(call):
    with pytest.raises(IdentityError) as caught:
        call()
    assert caught.value.code == "forbidden"


def test_production_defaults_exclude_every_report_and_management_capability():
    effective = capabilities_for("production")
    assert effective == PRODUCTION_CAPABILITIES
    assert {"production.view", "production.submit", "inventory.view"} <= effective
    assert not ({"reports.submit", "reports.view", "reports.manage", "production.manage",
                 "recipes.manage", "forecasts.view", "memberships.manage"} & effective)
    for capability in ("reports.submit", "reports.view", "reports.manage"):
        denied(lambda capability=capability: capabilities_for("production", [capability]))


def test_manager_defaults_cover_production_but_keep_admin_role_assignment():
    assert {"production.view", "production.submit", "production.manage",
            "recipes.manage", "forecasts.view"} <= MANAGER_CAPABILITIES
    manager = AccountActor(1, "manager", "Manager", 10, 20, "manager",
                           MANAGER_CAPABILITIES | {"memberships.manage"}, None, 1)
    assert assert_grant(manager, "crew") == frozenset()
    denied(lambda: assert_grant(manager, "production"))
    denied(lambda: assert_grant(manager, "manager"))
    denied(lambda: assert_grant(manager, "admin"))


def test_production_promotion_revokes_old_session_and_remains_single_store(empty_database):
    connect = lambda: psycopg.connect(empty_database)
    migrate(connect)
    accounts = AccountsService(connect)
    salt = "production-test-salt"
    with connect() as connection:
        business = connection.execute("INSERT INTO businesses(name) VALUES('Production Test') RETURNING id").fetchone()[0]
        stores = [connection.execute(
            "INSERT INTO stores(name,access_code_hash,business_id,accounts_enabled) VALUES(%s,%s,%s,true) RETURNING id",
            (name, hash_store_code(code), business),
        ).fetchone()[0] for name, code in (("First", "first"), ("Second", "second"))]
        owner = connection.execute(
            "INSERT INTO account_users(username,display_name,password_salt,password_hash) VALUES('Owner','Owner',%s,%s) RETURNING id",
            (salt, password_hash("owner-password", salt)),
        ).fetchone()[0]
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role) VALUES(%s,%s,'owner')", (owner, business))
        connection.execute(
            "INSERT INTO account_store_memberships(user_id,store_id,business_id,role) VALUES(%s,%s,%s,'manager')",
            (owner, stores[0], business),
        )
    owner_token = accounts.login("first", "Owner", "owner-password", client_key="production-owner").token
    invitation = accounts.invite(owner_token, username="Production Person")
    activated = accounts.activate_invitation(invitation["token"], "production-password", client_key="production-activation")
    accounts.set_membership(owner_token, user_id=invitation["userId"], role="production")
    with pytest.raises(IdentityError) as revoked:
        accounts.resolve_actor(activated.token)
    assert revoked.value.code == "unauthenticated"
    session = accounts.login("first", "Production Person", "production-password", client_key="production-login")
    actor = accounts.resolve_actor(session.token)
    assert actor.role == "production" and actor.capabilities == PRODUCTION_CAPABILITIES
    denied(lambda: accounts.resolve_actor(session.token, capability="reports.submit"))
    denied(lambda: accounts.switch_store(session.token, stores[1]))
