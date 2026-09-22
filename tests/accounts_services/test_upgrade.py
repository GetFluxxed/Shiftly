"""Exercise the real 013-to-014 upgrade against historical account/report data."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import uuid

import psycopg
import pytest

from backend.shiftly.runtime.migrate import MIGRATIONS, migrate, schema_status
from database import db_connection


@pytest.fixture
def historical_database(empty_database, tmp_path):
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name < "014_":
            (tmp_path / path.name).write_text(path.read_text())
    applied = migrate(db_connection, directory=tmp_path)
    assert len(applied) == 13
    with db_connection() as connection:
        first = connection.execute(
            "INSERT INTO stores(name,access_code_hash,crew_password_hash) VALUES ('First','first','crew-one') RETURNING id",
        ).fetchone()[0]
        second = connection.execute(
            "INSERT INTO stores(name,access_code_hash,crew_password_hash) VALUES ('Second','second','crew-two') RETURNING id",
        ).fetchone()[0]
        manager = connection.execute(
            """INSERT INTO manager_users(username,password_salt,password_hash)
               VALUES ('Original Manager','preserved-salt','preserved-pbkdf2') RETURNING id""",
        ).fetchone()[0]
        inactive = connection.execute(
            """INSERT INTO manager_users(username,password_salt,password_hash,active)
               VALUES ('Inactive Manager','inactive-salt','inactive-pbkdf2',FALSE) RETURNING id""",
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO store_memberships(manager_user_id,store_id) VALUES (%s,%s),(%s,%s),(%s,%s)",
            (manager, first, manager, second, inactive, first),
        )
        connection.execute(
            """INSERT INTO manager_sessions(token_hash,manager_user_id,store_id,expires_at)
               VALUES (%s,%s,%s,NOW()+INTERVAL '1 hour')""",
            (hashlib.sha256(b"historical-manager-cookie").hexdigest(), manager, first),
        )
        connection.execute(
            """INSERT INTO crew_sessions(token_hash,store_id,expires_at)
               VALUES (%s,%s,NOW()+INTERVAL '1 hour')""",
            (hashlib.sha256(b"historical-crew-cookie").hexdigest(), first),
        )
        report_id = uuid.uuid4()
        # The typed name deliberately equals a manager name: migration must not
        # reinterpret this unverified attribution as that manager's identity.
        connection.execute(
            """INSERT INTO reports(id,employee,shift,notes,report_hash,store_id)
               VALUES (%s,'Original Manager','closing','Original historical notes',%s,%s)""",
            (report_id, "f" * 64, first),
        )
        connection.execute("INSERT INTO briefing_jobs(report_id) VALUES (%s)", (report_id,))
        connection.execute(
            """INSERT INTO briefings(report_id,source_notes,summary,follow_up,model)
               VALUES (%s,'Original historical notes','Original summary','Original follow up','historical-model')""",
            (report_id,),
        )
    return {"store_ids": [first, second], "manager_id": manager, "inactive_id": inactive}


def _historical_snapshot():
    with db_connection() as connection:
        result = {}
        for table, order in (
            ("stores", "id"), ("manager_users", "id"), ("store_memberships", "manager_user_id,store_id"),
            ("manager_sessions", "token_hash"), ("crew_sessions", "token_hash"), ("reports", "id"),
            ("briefing_jobs", "id"), ("briefings", "id"),
        ):
            # These are fixed test-owned table names, not external SQL input.
            result[table] = connection.execute(
                f"SELECT to_jsonb(t) - 'business_id' - 'accounts_enabled' - 'shared_crew_enabled' - 'actor_user_id' FROM {table} t ORDER BY {order}",
            ).fetchall()
        return result


def test_upgrade_preserves_history_and_links_only_verified_legacy_managers(historical_database):
    before = _historical_snapshot()
    assert migrate(db_connection) == ["014_accounts_access.sql"]
    assert _historical_snapshot() == before
    with db_connection() as connection:
        assert connection.execute(
            """SELECT count(*) FROM account_users u JOIN manager_users m ON m.id=u.legacy_manager_id
               WHERE u.password_salt=m.password_salt AND u.password_hash=m.password_hash
                 AND u.created_at=m.created_at AND u.username=m.username""",
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT state FROM account_users WHERE legacy_manager_id=%s", (historical_database["inactive_id"],),
        ).fetchone()[0] == "suspended"
        assert connection.execute("SELECT count(*) FROM account_users").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM business_memberships").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM reports WHERE actor_user_id IS NOT NULL").fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM stores WHERE business_id IS NULL AND NOT accounts_enabled AND shared_crew_enabled",
        ).fetchone()[0] == 2
        assert connection.execute(
            """SELECT count(*) FROM account_store_memberships m JOIN account_users u ON u.id=m.user_id
               JOIN store_memberships old ON old.manager_user_id=u.legacy_manager_id AND old.store_id=m.store_id
               WHERE m.role='manager' AND m.business_id IS NULL AND m.state='active'""",
        ).fetchone()[0] == 3
    assert schema_status(db_connection)["schemaReady"] is True
    assert migrate(db_connection) == []
    assert _historical_snapshot() == before


def test_concurrent_013_upgrades_apply_accounts_once(historical_database):
    before = _historical_snapshot()
    with ThreadPoolExecutor(max_workers=2) as executor:
        applied = list(executor.map(lambda _: migrate(db_connection), range(2)))
    assert sorted(applied) == [[], ["014_accounts_access.sql"]]
    assert _historical_snapshot() == before
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM account_users").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM account_store_memberships").fetchone()[0] == 3


@pytest.mark.parametrize("collision_name", [" original   manager ", "Ｏｒｉｇｉｎａｌ　Ｍａｎａｇｅｒ"])
def test_normalization_collision_rolls_back_entire_upgrade(historical_database, collision_name):
    with db_connection() as connection:
        connection.execute(
            """INSERT INTO manager_users(username,password_salt,password_hash)
               VALUES (%s,'collision-salt','collision-hash')""", (collision_name,),
        )
    before = _historical_snapshot()
    with pytest.raises(psycopg.errors.UniqueViolation):
        migrate(db_connection)
    assert _historical_snapshot() == before
    with db_connection() as connection:
        assert connection.execute("SELECT to_regclass('account_users'),to_regclass('businesses')").fetchone() == (None, None)
        assert connection.execute("SELECT count(*) FROM schema_migrations WHERE version LIKE '014_%'").fetchone()[0] == 0
        assert connection.execute(
            """SELECT count(*) FROM information_schema.columns WHERE table_schema=current_schema()
               AND ((table_name='stores' AND column_name IN ('business_id','accounts_enabled','shared_crew_enabled'))
                 OR (table_name='reports' AND column_name='actor_user_id'))""",
        ).fetchone()[0] == 0
        assert connection.execute("SELECT to_regprocedure('account_username_key(text)')").fetchone()[0] is None
    assert schema_status(db_connection)["pendingMigrations"] == ["014_accounts_access.sql"]


@pytest.fixture
def constrained_accounts(isolated_database):
    with db_connection() as connection:
        business = connection.execute("INSERT INTO businesses(name) VALUES ('First') RETURNING id").fetchone()[0]
        other = connection.execute("INSERT INTO businesses(name) VALUES ('Other') RETURNING id").fetchone()[0]
        store = connection.execute(
            "INSERT INTO stores(name,access_code_hash,business_id) VALUES ('Store','store',%s) RETURNING id", (business,),
        ).fetchone()[0]
        user = connection.execute(
            """INSERT INTO account_users(username,display_name,password_salt,password_hash)
               VALUES ('Verified Person','Person','salt','hash') RETURNING id""",
        ).fetchone()[0]
    return user, store, business, other


def test_membership_cannot_reference_a_different_business(constrained_accounts):
    user, store, _, other = constrained_accounts
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db_connection() as connection:
        connection.execute(
            "INSERT INTO account_store_memberships(user_id,store_id,business_id,role) VALUES (%s,%s,%s,'crew')",
            (user, store, other),
        )


@pytest.mark.parametrize("role,forbidden_capability", [
    ("crew", "counts.approve"), ("crew", "receipts.post"), ("crew", "stock.adjust"),
    ("crew", "memberships.manage"), ("crew", "catalog.manage"), ("manager", "catalog.manage"),
])
def test_database_rejects_dangerous_role_grants(constrained_accounts, role, forbidden_capability):
    user, store, business, _ = constrained_accounts
    with pytest.raises(psycopg.errors.CheckViolation), db_connection() as connection:
        connection.execute(
            """INSERT INTO account_store_memberships(user_id,store_id,business_id,role,capabilities)
               VALUES (%s,%s,%s,%s,%s)""", (user, store, business, role, [forbidden_capability]),
        )


def test_database_rejects_invalid_session_generation(constrained_accounts):
    user, store, _, _ = constrained_accounts
    with pytest.raises(psycopg.errors.CheckViolation), db_connection() as connection:
        connection.execute(
            """INSERT INTO account_sessions(token_hash,user_id,store_id,credential_version,expires_at)
               VALUES (%s,%s,%s,0,NOW()+INTERVAL '1 hour')""", ("1" * 64, user, store),
        )


def test_database_unique_username_prevents_bypassing_service_normalization(constrained_accounts):
    with pytest.raises(psycopg.errors.UniqueViolation), db_connection() as connection:
        connection.execute(
            """INSERT INTO account_users(username,display_name,password_salt,password_hash)
               VALUES ('  verified    PERSON ','Another person','salt','hash')""",
        )
