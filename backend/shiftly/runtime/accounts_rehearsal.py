"""Real upgrade/archive-restore rehearsal using explicitly disposable PostgreSQL.

Run with ACCOUNTS_REHEARSAL_DATABASE_URL and
ACCOUNTS_REHEARSAL_RESTORE_DATABASE_URL. Optional
ACCOUNTS_REHEARSAL_SOURCE_CONTAINER / ACCOUNTS_REHEARSAL_RESTORE_CONTAINER select
PostgreSQL client tools inside explicit local containers. Native pg_dump and
pg_restore are used otherwise. No application .env, HTTP server, worker, AI or
production configuration is loaded.

--create-databases creates absent disposable databases and drops only databases
created by this invocation, even on failure. Without it, both databases must
already exist and be empty; they are retained for inspection.
"""
import argparse
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from backend.shiftly.identity.accounts import AccountsService
from backend.shiftly.identity.primitives import hash_store_code, hash_token, password_hash
from backend.shiftly.identity.repository import IdentityRepository
from backend.shiftly.identity.service import IdentityError, IdentityService
from backend.shiftly.reports.repository import ReportsRepository
from backend.shiftly.reports.service import ReportsService
from backend.shiftly.stores.repository import StoresRepository
from backend.shiftly.stores.service import StoresService
from .accounts_admin import bootstrap_mapping
from .migrate import MIGRATIONS, migrate, schema_status
from scripts.rehearse_release import backup_restore, snapshot


PASSWORD = "synthetic-accounts-password"
NEW_PASSWORD = "synthetic-accounts-new-password"
CREW_PASSWORD = "synthetic-shared-crew-password"


def _check(condition, message):
    if not condition:
        raise RuntimeError(message)


def _validate_targets(source_dsn, restore_dsn):
    targets = []
    for dsn in (source_dsn, restore_dsn):
        values = conninfo_to_dict(dsn)
        name = values.get("dbname", "")
        if not re.fullmatch(r"shiftly_accounts_(?:rehearsal|restore)(?:_[a-zA-Z0-9_]+)?", name):
            raise RuntimeError("Use an explicitly named shiftly_accounts_rehearsal/restore disposable database.")
        if values.get("host") not in {"127.0.0.1", "localhost", "::1"} or values.get("options"):
            raise RuntimeError("Accounts rehearsal requires an explicit local host and no search-path overrides.")
        targets.append((name, values.get("port", "5432")))
    # Refuse the same name even through host aliases or different port mappings.
    _check(targets[0][0] != targets[1][0], "Source and restore database names must differ.")
    return targets


def _create_database(dsn):
    name = conninfo_to_dict(dsn)["dbname"]
    with psycopg.connect(make_conninfo(dsn, dbname="postgres"), autocommit=True) as connection:
        _check(not connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone(),
               "Refusing to replace an existing rehearsal database.")
        connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))


def _drop_created_database(dsn):
    name = conninfo_to_dict(dsn)["dbname"]
    with psycopg.connect(make_conninfo(dsn, dbname="postgres"), autocommit=True) as connection:
        connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def _assert_empty(dsn):
    with psycopg.connect(dsn) as connection:
        tables = connection.execute(
            "SELECT 1 FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') LIMIT 1"
        ).fetchone()
        _check(not tables, "Both rehearsal databases must be fresh and empty.")
        version = int(connection.execute("SHOW server_version_num").fetchone()[0])
        _check(160000 <= version < 170000, "This rehearsal targets PostgreSQL 16.")


def _snapshot(dsn):
    result = snapshot(dsn)
    with psycopg.connect(dsn) as connection:
        result["checks"] = connection.execute(
            """SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid)
               FROM pg_constraint WHERE contype='c' AND connamespace='public'::regnamespace
               ORDER BY 1,2"""
        ).fetchall()
        result["triggers"] = connection.execute(
            """SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t
               JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY 1,2"""
        ).fetchall()
        result["functions"] = connection.execute(
            """SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p
               JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
               ORDER BY p.proname,p.oid::regprocedure::text"""
        ).fetchall()
    return result


def _legacy_rows(dsn, columns=None):
    with psycopg.connect(dsn) as connection:
        if columns is None:
            columns = {}
            for table, column in connection.execute(
                """SELECT table_name,column_name FROM information_schema.columns
                   WHERE table_schema='public' AND table_name<>'schema_migrations'
                   ORDER BY table_name,ordinal_position"""
            ).fetchall():
                columns.setdefault(table, []).append(column)
        rows = {}
        for table, names in columns.items():
            query = sql.SQL("SELECT row_to_json(original)::text FROM (SELECT {} FROM {}) original ORDER BY 1").format(
                sql.SQL(",").join(map(sql.Identifier, names)), sql.Identifier(table),
            )
            rows[table] = connection.execute(query).fetchall()
    return columns, rows


def _seed_013(dsn):
    connect = lambda: psycopg.connect(dsn)
    with tempfile.TemporaryDirectory(prefix="shiftly-account-migrations-") as directory:
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name < "014_":
                shutil.copyfile(path, Path(directory) / path.name)
        _check(len(migrate(connect, directory=Path(directory))) == 13, "Expected fresh migrations 001–013.")
    report_id = uuid.uuid4()
    old_manager_token, old_crew_token = "synthetic-before-upgrade-manager", "synthetic-before-upgrade-crew"
    with connect() as connection:
        stores = []
        for code in ("account-rehearsal-a", "account-rehearsal-b"):
            digest = hash_store_code(code)
            stores.append(connection.execute(
                "INSERT INTO stores(name,access_code_hash,crew_password_hash) VALUES(%s,%s,%s) RETURNING id",
                (code,digest,password_hash(CREW_PASSWORD,f"shiftly-crew:{digest}")),
            ).fetchone()[0])
        manager_id = connection.execute(
            "INSERT INTO manager_users(username,password_salt,password_hash) VALUES('rehearsal-owner','legacy-salt',%s) RETURNING id",
            (password_hash(PASSWORD,"legacy-salt"),),
        ).fetchone()[0]
        for store_id in stores:
            connection.execute("INSERT INTO store_memberships(manager_user_id,store_id) VALUES(%s,%s)",(manager_id,store_id))
        connection.execute(
            "INSERT INTO manager_sessions(token_hash,manager_user_id,store_id,expires_at) VALUES(%s,%s,%s,NOW()+INTERVAL '1 day')",
            (hash_token(old_manager_token),manager_id,stores[0]),
        )
        connection.execute(
            "INSERT INTO crew_sessions(token_hash,store_id,expires_at) VALUES(%s,%s,NOW()+INTERVAL '1 day')",
            (hash_token(old_crew_token),stores[0]),
        )
        connection.execute(
            """INSERT INTO reports(id,store_id,employee,shift,notes,report_hash)
               VALUES(%s,%s,'Historical typed name','closing','Original legacy report text remains unchanged.',%s)""",
            (report_id,stores[0],hash_token("historical-report")),
        )
        connection.execute("INSERT INTO briefing_jobs(report_id,status,attempts) VALUES(%s,'completed',1)",(report_id,))
        connection.execute(
            """INSERT INTO briefings(report_id,source_notes,summary,follow_up,model)
               VALUES(%s,'Original legacy report text remains unchanged.','Synthetic summary.','Review.','synthetic')""",(report_id,),
        )
    return {"manager_id":manager_id,"stores":stores,"historical_report":report_id,
            "old_manager_token":old_manager_token,"old_crew_token":old_crew_token}


def _services(dsn):
    connect = lambda: psycopg.connect(dsn)
    accounts = AccountsService(connect)
    identity = IdentityService(IdentityRepository(connect),StoresService(StoresRepository(connect)),accounts=accounts)
    reports = ReportsService(ReportsRepository(connect),cooldown_seconds=0,similarity_threshold=0.9,
                             clock=time.time,wake=lambda:None)
    return connect,accounts,identity,reports


def _denied(operation, description):
    try:
        operation()
    except IdentityError:
        return
    raise RuntimeError(f"Expected denial: {description}.")


def _exercise_accounts(dsn, facts):
    connect,accounts,identity,reports = _services(dsn)
    with connect() as connection:
        owner_id=connection.execute("SELECT id FROM account_users WHERE username='rehearsal-owner'").fetchone()[0]
    _denied(lambda:accounts.login('account-rehearsal-a','rehearsal-owner',PASSWORD,client_key='unmapped'), 'ambiguous manager assignments before explicit ownership mapping')
    manifest = {"reason":"Synthetic account recovery rehearsal only.",
                "businesses":[{"id":901,"name":"Synthetic rehearsal business","owner_user_ids":[owner_id]}],
                "stores":[{"store_id":sid,"business_id":901,"accounts_enabled":True} for sid in facts["stores"]]}
    _check(bootstrap_mapping(connect,manifest)["mode"] == "dry-run", "Mapping dry-run failed.")
    with connect() as connection:
        _check(connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 0, "Dry-run changed ownership.")
    bootstrap_mapping(connect,manifest,apply=True)
    owner_session = accounts.login("account-rehearsal-a","rehearsal-owner",PASSWORD,client_key="synthetic-owner")
    facts.update(owner_id=owner_id,old_owner_named_token=owner_session.token)
    invite = accounts.invite(owner_session.token,username="rehearsal-crew",reason="Synthetic enrollment.")
    crew_session = accounts.activate_invitation(invite["token"],PASSWORD,client_key="synthetic-activation")
    crew_id = accounts.resolve_actor(crew_session.token).user_id
    _denied(lambda:accounts.set_membership(owner_session.token,user_id=crew_id,role="crew",store_id=facts["stores"][1]),"multiple staff stores")
    named_report, _ = reports.queue_report("Typed name is preserved","opening","Named crew report before recovery.",
                                         facts["stores"][0],actor_token=crew_session.token,accounts=accounts)
    with connect() as connection:
        _check(connection.execute("SELECT actor_user_id,employee FROM reports WHERE id=%s",(named_report,)).fetchone() ==
               (crew_id,"Typed name is preserved"), "Named report actor or original text was not persisted.")
    reset = accounts.issue_password_reset(user_id=crew_id,reason="Synthetic verified operator recovery.")
    accounts.reset_password(reset["token"],NEW_PASSWORD,client_key="synthetic-recovery")
    _denied(lambda:accounts.resolve_actor(crew_session.token),"pre-reset crew session")
    _denied(lambda:accounts.reset_password(reset["token"],PASSWORD,client_key="synthetic-recovery"),"reset replay")
    _denied(lambda:accounts.login("account-rehearsal-a","rehearsal-crew",PASSWORD,client_key="synthetic-old-password"),"old password")
    crew_a = accounts.login("account-rehearsal-a","rehearsal-crew",NEW_PASSWORD,client_key="synthetic-crew")
    accounts.set_membership(owner_session.token,user_id=crew_id,role="crew",active=False,reason="Synthetic local access removal.")
    _denied(lambda:accounts.resolve_actor(crew_a.token),"revoked local membership")
    accounts.set_membership(owner_session.token,user_id=crew_id,role="crew",store_id=facts["stores"][1])
    crew_b = accounts.login("account-rehearsal-b","rehearsal-crew",NEW_PASSWORD,client_key="synthetic-crew")
    _check(accounts.resolve_actor(crew_b.token).store_id == facts["stores"][1], "Local revocation removed another store's access.")
    pending = accounts.invite(owner_session.token,username="restore-activation",reason="Synthetic pending restore activation.")
    suspended = accounts.invite(owner_session.token,username="suspended-crew",reason="Synthetic suspension fixture.")
    suspended_session = accounts.activate_invitation(suspended["token"],PASSWORD,client_key="synthetic-activation")
    suspended_id = accounts.resolve_actor(suspended_session.token).user_id
    accounts.suspend_user(owner_session.token,user_id=suspended_id,reason="Synthetic account suspension.")
    accounts.cutover_store(owner_session.token,reason="Synthetic shared-crew cutover.")
    _check(identity.repository.crew_store(facts["old_crew_token"]) is None, "Shared legacy session survived cutover.")
    owner_reset = accounts.issue_password_reset(user_id=owner_id,reason="Synthetic legacy credential synchronization.")
    accounts.reset_password(owner_reset["token"],NEW_PASSWORD,client_key="synthetic-owner-recovery")
    _check(identity.manager_id(facts["old_manager_token"]) is None, "Legacy manager session survived credential reset.")
    _denied(lambda:identity.login("account-rehearsal-a","manager",PASSWORD,client_key="synthetic-old-legacy"),"legacy old password")
    owner_current = accounts.login("account-rehearsal-a","rehearsal-owner",NEW_PASSWORD,client_key="synthetic-owner")
    facts.update(crew_id=crew_id,named_report=named_report,crew_old_token=crew_session.token,
                 crew_revoked_token=crew_a.token,crew_live_token=crew_b.token,reset_token=reset["token"],
                 owner_live_token=owner_current.token,pending_invite=pending["token"],
                 suspended_token=suspended_session.token)
    return facts


def _verify_restored(dsn, facts):
    connect,accounts,identity,reports = _services(dsn)
    for field in ("old_owner_named_token","crew_old_token","crew_revoked_token","suspended_token"):
        _denied(lambda:accounts.resolve_actor(facts[field]),f"restored {field}")
    _check(accounts.resolve_actor(facts["owner_live_token"]).user_id == facts["owner_id"], "Live owner session did not survive restore.")
    _check(accounts.resolve_actor(facts["crew_live_token"]).store_id == facts["stores"][1], "Live scoped crew session did not survive restore.")
    _check(identity.manager_id(facts["old_manager_token"]) is None, "Restore resurrected old manager session.")
    _check(identity.repository.crew_store(facts["old_crew_token"]) is None, "Restore resurrected shared crew session.")
    _denied(lambda:accounts.reset_password(facts["reset_token"],PASSWORD,client_key="restore-replay"),"restored reset replay")
    _denied(lambda:accounts.login("account-rehearsal-a","rehearsal-crew",NEW_PASSWORD,client_key="restore-local"),"restored revoked local membership")
    _denied(lambda:accounts.login("account-rehearsal-a","suspended-crew",PASSWORD,client_key="restore-suspended"),"restored suspended account")
    _denied(lambda:identity.login("account-rehearsal-a","crew",CREW_PASSWORD,client_key="restore-shared"),"restored shared crew cutover")
    _denied(lambda:identity.login("account-rehearsal-a","manager",PASSWORD,client_key="restore-old-password"),"restored legacy old password")
    owner = accounts.login("account-rehearsal-a","rehearsal-owner",NEW_PASSWORD,client_key="restore-owner")
    legacy = identity.login("account-rehearsal-a","manager",NEW_PASSWORD,client_key="restore-legacy")
    _check(identity.manager_id(legacy.token) == facts["manager_id"], "Restored synchronized legacy credentials failed.")
    visible = reports.list_for_actor(owner.token,accounts)
    visible_ids = {row["id"] for row in visible}
    _check({str(facts["historical_report"]),str(facts["named_report"])} <= visible_ids, "Restored authorized report reads lost history.")
    with connect() as connection:
        _check(connection.execute("SELECT notes,actor_user_id FROM reports WHERE id=%s",(facts["historical_report"],)).fetchone() ==
               ("Original legacy report text remains unchanged.",None), "Historical name was inferred as account identity.")
    activated = accounts.activate_invitation(facts["pending_invite"],PASSWORD,client_key="restore-activation")
    _denied(lambda:accounts.activate_invitation(facts["pending_invite"],PASSWORD,client_key="restore-activation"),"restored activation replay")
    restored_actor = accounts.resolve_actor(activated.token)
    report_id,_ = reports.queue_report("Post-restore name","closing","Named report after a real archive restore.",
                                       facts["stores"][0],actor_token=activated.token,accounts=accounts)
    with connect() as connection:
        _check(connection.execute("SELECT actor_user_id FROM reports WHERE id=%s",(report_id,)).fetchone()[0] == restored_actor.user_id,
               "Restored named report persistence failed.")
    try:
        with connect() as connection:
            connection.execute("UPDATE account_store_memberships SET business_id=NULL WHERE user_id=%s AND store_id=%s",(restored_actor.user_id,facts["stores"][0]))
    except psycopg.errors.ForeignKeyViolation:
        pass
    else:
        raise RuntimeError("Restored deferred scope constraint did not enforce business/store mapping.")


def rehearse(source_dsn, restore_dsn, *, source_container=None, restore_container=None, create_databases=False):
    _validate_targets(source_dsn,restore_dsn)
    created=[]
    start=time.monotonic()
    try:
        if create_databases:
            for dsn in (source_dsn,restore_dsn):
                _create_database(dsn)
                created.append(dsn)
        _assert_empty(source_dsn)
        _assert_empty(restore_dsn)
        facts=_seed_013(source_dsn)
        columns,historical_rows=_legacy_rows(source_dsn)
        before_upgrade=_snapshot(source_dsn)
        connect=lambda:psycopg.connect(source_dsn)
        applied=migrate(connect)
        _check("014_accounts_access.sql" in applied,"Accounts migration was not applied.")
        _check(_legacy_rows(source_dsn,columns)[1]==historical_rows,"Accounts upgrade changed historical values.")
        after_upgrade=_snapshot(source_dsn)
        _check(all(after_upgrade["sequences"][key]==value for key,value in before_upgrade["sequences"].items()),
               "Accounts upgrade changed legacy sequence state.")
        _check(migrate(connect)==[],"Repeated migration was not idempotent.")
        _check(schema_status(connect)["schemaReady"],"Upgraded schema is not ready.")
        facts=_exercise_accounts(source_dsn,facts)
        before_restore=_snapshot(source_dsn)
        required={"account_users","businesses","business_memberships","account_store_memberships","account_sessions",
                  "account_audit","account_invitations","account_password_resets","reports"}
        _check(required<=set(before_restore["rows"]),"Account backup snapshot omitted durable tables.")
        archive_bytes=backup_restore(source_dsn,restore_dsn,source_container=source_container,restore_container=restore_container)
        _check(_snapshot(restore_dsn)==before_restore,"Archive restore changed rows, sequences or database constraints/functions.")
        _verify_restored(restore_dsn,facts)
        result={"result":"passed","elapsedSeconds":round(time.monotonic()-start,2),"archiveBytes":archive_bytes,
                "tablesCompared":len(before_restore["rows"]),"sequencesCompared":len(before_restore["sequences"]),
                "foreignKeysCompared":len(before_restore["foreign_keys"]),"checksCompared":len(before_restore["checks"]),
                "triggersCompared":len(before_restore["triggers"]),"functionsCompared":len(before_restore["functions"]),
                "checks":["001–013 upgrade preserves every historical column and sequence",
                          "explicit owner mapping dry-run and controlled synthetic activation",
                          "named report actor and original report text",
                          "password reset synchronizes legacy credentials and revokes sessions",
                          "store-only membership revocation preserves other-store access",
                          "suspension and shared-crew cutover remain effective",
                          "real pg_dump/pg_restore of every durable table, sequence, FK, check, trigger and function",
                          "restored login, report reads/writes, invitation/reset replay denial and scope constraints"],
                "cleanup":"created disposable databases removed" if create_databases else "precreated disposable databases retained"}
    finally:
        for dsn in reversed(created):
            _drop_created_database(dsn)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-databases",action="store_true",help="Create absent disposable targets; drop only those created by this run afterward.")
    args=parser.parse_args(argv)
    try:
        source=os.environ["ACCOUNTS_REHEARSAL_DATABASE_URL"]
        target=os.environ["ACCOUNTS_REHEARSAL_RESTORE_DATABASE_URL"]
        result=rehearse(source,target,source_container=os.environ.get("ACCOUNTS_REHEARSAL_SOURCE_CONTAINER"),
                        restore_container=os.environ.get("ACCOUNTS_REHEARSAL_RESTORE_CONTAINER"),create_databases=args.create_databases)
    except (KeyError,ValueError,RuntimeError,IdentityError,psycopg.Error):
        # SQL/tool exceptions can contain connection strings or credential values.
        raise SystemExit("Accounts rehearsal failed. Verify explicit disposable target settings, migration readiness and PostgreSQL client tools; no production configuration was loaded.") from None
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=="__main__":
    main()
