#!/usr/bin/env python3
"""Rehearse the local API/worker release with disposable PostgreSQL resources."""

import argparse
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import time
import tempfile
import uuid
import urllib.request
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def provider(report, prompt=None):
    if os.environ.get("REHEARSAL_PROVIDER_DELAY"):
        time.sleep(float(os.environ["REHEARSAL_PROVIDER_DELAY"]))
    if report["shift"] == "weekly overview":
        return {
            "summary": "Rehearsal weekly summary.",
            "wins": ["The deterministic rehearsal provider responded."],
            "risks": [],
            "follow_up": "Review the rehearsal handoff.",
        }
    return {
        "status": "accepted",
        "reason": "",
        "summary": "Rehearsal report accepted.",
        "wins": ["The deterministic rehearsal provider responded."],
        "risks": [],
        "follow_up": "Review the rehearsal handoff.",
    }


def run_child(mode):
    os.environ["OPENAI_API_KEY"] = ""
    def forbidden(*args, **kwargs):
        raise AssertionError("External provider calls are forbidden in release rehearsals.")
    urllib.request.urlopen = forbidden
    from config import load_settings

    settings = load_settings(load_env=False)
    if mode == "worker":
        from backend.shiftly.jobs.worker import run_worker

        run_worker(settings, provider=provider, install_signals=True)
        return 0
    if mode == "api":
        import uvicorn

        from backend.shiftly.app import create_app

        uvicorn.run(
            create_app(settings=settings, provider=provider),
            host=settings.host,
            port=settings.port,
            log_level="error",
        )
        return 0
    if mode == "legacy":
        import runpy

        runpy.run_path(str(ROOT / "server.py"), run_name="__main__")
        return 0
    raise ValueError(f"Unknown child mode: {mode}")


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_http(base_url, path="/api/health", timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = request(base_url, "GET", path)
            if response[0] in {200, 503}:
                return
        except OSError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {base_url}{path}.")


def request(base_url, method, path, payload=None, cookie=None):
    parsed = urlparse(base_url)
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    connection = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        try:
            payload = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = data
        cookies = [
            value.split(";", 1)[0]
            for name, value in response.getheaders()
            if name.lower() == "set-cookie"
        ]
        return response.status, payload, cookies
    finally:
        connection.close()


def run_command(command, env):
    subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=60)


def migrate(env):
    run_command([sys.executable, "-m", "backend.shiftly.runtime.migrate"], env)


def start_process(mode, env, port=None):
    child_env = dict(env)
    child_env["HOST"] = "127.0.0.1"
    if port is not None:
        child_env["PORT"] = str(port)
    return subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), mode],
        cwd=ROOT,
        env=child_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_process(process):
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _postgres_tool(tool, dsn, container):
    if container:
        docker = shutil.which("docker")
        if docker is None:
            raise RuntimeError("Docker is required for container-based backup/restore.")
        # An explicitly selected disposable DB container runs the client against
        # its own PostgreSQL instance, independent of its published host port.
        local_dsn = make_conninfo(dsn, host="127.0.0.1", port="5432")
        return [docker, "exec", "-i", container, tool, "--dbname", local_dsn]
    executable = shutil.which(tool)
    if executable is None:
        raise RuntimeError(
            f"{tool} is required for a real PostgreSQL backup/restore. "
            "Install PostgreSQL client tools or set REHEARSAL_SOURCE_CONTAINER "
            "and REHEARSAL_RESTORE_CONTAINER to the disposable database containers."
        )
    return [executable, "--dbname", dsn]


def backup_restore(source_dsn, restore_dsn, *, source_container=None, restore_container=None):
    """Restore a real archive, including schema, relationships and sequences.

    Targets must be disposable. The restore replaces the rehearsal's already
    migrated target schema. Missing PostgreSQL tools are a failed prerequisite,
    never a reason to substitute a partial application-row copy.
    """
    source = conninfo_to_dict(source_dsn)
    target = conninfo_to_dict(restore_dsn)
    source_identity = (
        source_container or source.get("host", ""),
        "5432" if source_container else source.get("port", "5432"),
        source.get("dbname", ""),
    )
    target_identity = (
        restore_container or target.get("host", ""),
        "5432" if restore_container else target.get("port", "5432"),
        target.get("dbname", ""),
    )
    if source_identity == target_identity:
        raise RuntimeError("Backup source and restore target must be separate disposable databases.")
    dump_command = _postgres_tool("pg_dump", source_dsn, source_container)
    restore_command = _postgres_tool("pg_restore", restore_dsn, restore_container)
    with tempfile.TemporaryFile() as archive:
        stage = "backup"
        try:
            subprocess.run(
                [*dump_command, "--format=custom", "--no-owner", "--no-privileges"],
                stdout=archive, stderr=subprocess.PIPE, check=True, timeout=60,
            )
            archive_size = archive.tell()
            archive.seek(0)
            stage = "restore"
            subprocess.run(
                [*restore_command, "--clean", "--if-exists", "--no-owner",
                 "--no-privileges", "--exit-on-error", "--single-transaction"],
                stdin=archive, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                check=True, timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            # Tool errors can include connection strings or employee data.
            raise RuntimeError(f"PostgreSQL {stage} failed; rehearsal did not pass.") from None
    return archive_size


def wait_until(predicate, description, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise RuntimeError(f"Timed out: {description}.")


def snapshot(dsn):
    """All durable rows and sequence positions; worker heartbeat is transient."""
    with psycopg.connect(dsn) as connection:
        tables = connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'runtime_worker_status' ORDER BY tablename").fetchall()
        rows = {}
        for (table,) in tables:
            rows[table] = connection.execute(sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text").format(sql.Identifier(table))).fetchall()
        sequences = connection.execute("SELECT sequencename FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename").fetchall()
        sequence_state = {name: connection.execute(sql.SQL("SELECT last_value,is_called FROM {}").format(sql.Identifier(name))).fetchone() for (name,) in sequences}
        constraints = connection.execute("SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE contype='f' AND connamespace='public'::regnamespace ORDER BY conname").fetchall()
    return {"rows": rows, "sequences": sequence_state, "foreign_keys": constraints}


def seed_upgrade_baseline(dsn):
    """Rehearse the pre-runtime (001–012) schema with retained business data."""
    from backend.shiftly.runtime.migrate import MIGRATIONS, migrate as apply_migrations
    with tempfile.TemporaryDirectory() as directory:
        baseline = Path(directory)
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name < "013_":
                shutil.copyfile(path, baseline / path.name)
        applied = apply_migrations(lambda: psycopg.connect(dsn), directory=baseline)
        if len(applied) != 12:
            raise RuntimeError("Upgrade rehearsal requires a fresh disposable source database.")
    report_id = uuid.uuid4()
    with psycopg.connect(dsn) as connection:
        store = connection.execute("INSERT INTO stores (name,access_code_hash) VALUES ('Upgrade baseline','upgrade-baseline') RETURNING id").fetchone()[0]
        connection.execute("INSERT INTO reports (id,store_id,employee,shift,notes,report_hash) VALUES (%s,%s,'Baseline Crew','closing','Original baseline notes.','baseline-report')", (report_id, store))
        connection.execute("INSERT INTO briefing_jobs (report_id,status,attempts) VALUES (%s,'completed',1)", (report_id,))
        connection.execute("INSERT INTO briefings (report_id,source_notes,summary,follow_up,model) VALUES (%s,'Original baseline notes.','Baseline summary.','None.','test')", (report_id,))
    return snapshot(dsn)


def verify_upgrade(before, dsn):
    """Preserve every historical value while allowing explicitly additive schema.

    New columns/tables/sequences/FKs are checked by their feature migration tests;
    they cannot mask deleted rows, changed old fields or modified old constraints.
    Restore verification below still compares the entire post-upgrade snapshot.
    """
    after = snapshot(dsn)
    for table, rows in before["rows"].items():
        if table == "schema_migrations":
            continue
        current = after["rows"].get(table)
        if current is None or len(current) != len(rows):
            raise RuntimeError(f"Upgrade changed existing {table} rows.")
        if rows:
            originals = [json.loads(row[0]) for row in rows]
            fields = set(originals[0])
            projected = []
            for row in current:
                value = json.loads(row[0])
                if not fields <= value.keys():
                    raise RuntimeError(f"Upgrade removed existing {table} fields.")
                projected.append({field: value[field] for field in fields})
            canonical = lambda values: sorted(json.dumps(value, sort_keys=True) for value in values)
            if canonical(originals) != canonical(projected):
                raise RuntimeError(f"Upgrade changed existing {table} rows.")
    if any(after["sequences"].get(name) != state for name, state in before["sequences"].items()):
        raise RuntimeError("Upgrade changed existing sequence state.")
    if not set(before["foreign_keys"]) <= set(after["foreign_keys"]):
        raise RuntimeError("Upgrade changed existing foreign keys.")


def verify_reports(base_url, cookie):
    status, payload, _ = request(base_url, "GET", "/api/reports", cookie=cookie)
    expected = {"Rehearsal Crew": "Rehearsal report.", "Recovery Crew": "Recovery report."}
    if status != 200:
        raise RuntimeError("Report read failed during rollback/restore verification.")
    for item in payload.get("reports", []):
        if item["employee"] in expected:
            if item["status"] != "completed" or item["notes"] != expected.pop(item["employee"]):
                raise RuntimeError("Original report or completed briefing was not preserved.")
    if expected:
        raise RuntimeError("Rollback/restore lost a rehearsal report.")


def verify_database_outage(dsn, base_url, worker):
    """Refuse connections to this disposable database and terminate its sessions."""
    database = conninfo_to_dict(dsn)["dbname"]
    admin_dsn = make_conninfo(dsn, dbname="postgres")
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        try:
            admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(database)))
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s", (database,))
            status, health, _ = request(base_url, "GET", "/api/health")
            if status != 503 or health["databaseConfigured"] or health["worker"]["state"] != "unavailable":
                raise RuntimeError("Health did not report the database outage.")
            if worker.wait(timeout=15) == 0:
                raise RuntimeError("Worker did not signal lost database ownership to its supervisor.")
        finally:
            admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(database)))
    wait_until(lambda: request(base_url, "GET", "/api/health")[0] == 200,
               "API reconnects after database outage")


def seed_release_owner(dsn):
    """Controlled synthetic bootstrap; public account creation stays disabled."""
    from backend.shiftly.identity.primitives import hash_store_code, password_hash
    with psycopg.connect(dsn) as connection:
        business=connection.execute("INSERT INTO businesses(name) VALUES('Release rehearsal') RETURNING id").fetchone()[0]
        connection.execute("INSERT INTO stores(name,access_code_hash,business_id,accounts_enabled,shared_crew_enabled) VALUES('Rehearsal Store',%s,%s,true,false)",
                           (hash_store_code('rehearsal-store'),business))
        user=connection.execute("INSERT INTO account_users(username,display_name,password_salt,password_hash) VALUES('rehearsal-manager','Rehearsal Owner','rehearsal-salt',%s) RETURNING id",
                                (password_hash('manager-password-123','rehearsal-salt'),)).fetchone()[0]
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role) VALUES(%s,%s,'owner')",(user,business))


def rehearse():
    source_dsn = os.environ["REHEARSAL_DATABASE_URL"]
    restore_dsn = os.environ["REHEARSAL_RESTORE_DATABASE_URL"]
    env = dict(os.environ)
    env.update({
        "DATABASE_URL": source_dsn,
        "OPENAI_API_KEY": "",
        "ADMIN_SIGNUP_KEY": "rehearsal-admin-key",
        "SECURE_COOKIES": "false",
        "SHIFTLY_WORKER_MODE": "external",
        "WEB_CONCURRENCY": "1",
        "DB_POOL_TIMEOUT": "0.5",
        "DB_CONNECT_TIMEOUT": "2",
        "SHUTDOWN_TIMEOUT": "0.5",
    })
    env.pop("REHEARSAL_PROVIDER_DELAY", None)
    restore_env = dict(env)
    restore_env["DATABASE_URL"] = restore_dsn

    before_upgrade = seed_upgrade_baseline(source_dsn)
    migrate(env)
    verify_upgrade(before_upgrade, source_dsn)
    migrate(env)
    migrate(restore_env)
    concurrent = [
        subprocess.Popen([sys.executable, "-m", "backend.shiftly.runtime.migrate"], cwd=ROOT, env=env)
        for _ in range(2)
    ]
    try:
        statuses = [process.wait(timeout=30) for process in concurrent]
        if any(status != 0 for status in statuses):
            raise RuntimeError("Concurrent migration rehearsal failed.")
    finally:
        for process in concurrent:
            stop_process(process)

    seed_release_owner(source_dsn)
    api_port = free_port()
    api_env = dict(env)
    api_env["PORT"] = str(api_port)
    api = start_process("api", api_env, api_port)
    worker = None
    base_url = f"http://127.0.0.1:{api_port}"
    try:
        wait_for_http(base_url)
        status, health, _ = request(base_url, "GET", "/api/health/worker")
        if status != 503 or health["state"] != "not_started":
            raise RuntimeError("API must report the absent separate worker.")
        worker = start_process("worker", env)
        status, _, cookies = request(base_url,'POST','/api/accounts/login',
                                     {'username':'rehearsal-manager','password':'manager-password-123'})
        if status != 200:
            raise RuntimeError('Owner login rehearsal failed.')
        manager_cookie=next(cookie for cookie in cookies if cookie.startswith('shiftly_account_session='))
        status, invitation, _=request(base_url,'POST','/api/accounts/invitations',
                                      {'username':'rehearsal-crew'},manager_cookie)
        if status != 200:
            raise RuntimeError('Individual invitation rehearsal failed.')
        status, _, activation_cookies=request(base_url,'POST','/api/accounts/activate',
                                              {'token':invitation['token'],'password':'crew-password-123'})
        if status != 200:
            raise RuntimeError('Individual activation rehearsal failed.')
        request(base_url,'POST','/api/auth/logout',cookie=activation_cookies[0])
        request(base_url, "POST", "/api/auth/logout", cookie=manager_cookie)
        status, _, cookies = request(
            base_url,
            "POST",
            "/api/auth/login",
            {"username": "rehearsal-crew", "password": "crew-password-123"},
        )
        if status != 200:
            raise RuntimeError("Crew login rehearsal failed.")
        crew_cookie = next(cookie for cookie in cookies if cookie.startswith("shiftly_account_session="))
        status, _, _ = request(
            base_url,
            "POST",
            "/api/reports",
            {"employee": "Rehearsal Crew", "shift": "closing", "notes": "Rehearsal report."},
            crew_cookie,
        )
        if status != 202:
            raise RuntimeError("Report submission rehearsal failed.")
        request(base_url, "POST", "/api/auth/logout", cookie=crew_cookie)
        status, _, cookies = request(
            base_url,
            "POST",
            "/api/auth/login",
            {"username": "rehearsal-manager", "password": "manager-password-123"},
        )
        manager_cookie = next(cookie for cookie in cookies if cookie.startswith("shiftly_account_session="))
        deadline = time.monotonic() + 30
        reports = []
        while time.monotonic() < deadline:
            _, payload, _ = request(base_url, "GET", "/api/reports", cookie=manager_cookie)
            reports = payload.get("reports", [])
            if reports and reports[0]["status"] == "completed":
                break
            time.sleep(0.5)
        if not reports or reports[0]["status"] != "completed":
            raise RuntimeError("Worker did not complete the rehearsal report.")

        stop_process(worker)
        request(base_url, "POST", "/api/auth/logout", cookie=manager_cookie)
        _, _, cookies = request(
            base_url,
            "POST",
            "/api/auth/login",
            {"username": "rehearsal-crew", "password": "crew-password-123"},
        )
        crew_cookie = next(cookie for cookie in cookies if cookie.startswith("shiftly_account_session="))
        status, _, _ = request(
            base_url,
            "POST",
            "/api/reports",
            {"employee": "Recovery Crew", "shift": "closing", "notes": "Recovery report."},
            crew_cookie,
        )
        if status != 202:
            raise RuntimeError("Recovery report submission rehearsal failed.")
        request(base_url, "POST", "/api/auth/logout", cookie=crew_cookie)
        with psycopg.connect(source_dsn) as connection:
            recovery_id = connection.execute(
                "SELECT id FROM reports WHERE employee = 'Recovery Crew' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()[0]
        worker = start_process("worker", {**env, "REHEARSAL_PROVIDER_DELAY": "30"})
        def claimed():
            with psycopg.connect(source_dsn) as connection:
                return connection.execute("SELECT status,attempts FROM briefing_jobs WHERE report_id=%s", (recovery_id,)).fetchone() == ("processing", 1)
        wait_until(claimed, "delayed worker claims the recovery report")
        worker.kill()
        worker.wait(timeout=5)
        with psycopg.connect(source_dsn) as connection:
            if connection.execute("SELECT count(*) FROM briefings WHERE report_id=%s", (recovery_id,)).fetchone()[0] != 0:
                raise RuntimeError("Recovery report completed before the worker was killed.")
            # Advance only lease/heartbeat time; the actual claim and crash are real.
            connection.execute(
                """
                UPDATE briefing_jobs
                SET locked_at = NOW() - INTERVAL '10 minutes'
                WHERE report_id = %s
                """,
                (recovery_id,),
            )
            connection.execute("UPDATE runtime_worker_status SET observed_at=NOW()-INTERVAL '61 seconds'")
        status, health, _ = request(base_url, "GET", "/api/health/worker")
        if status != 503 or health["state"] != "stalled" or health["queueDepth"] != 1:
            raise RuntimeError("API failed to expose the crashed worker and pending queue.")
        worker = start_process("worker", env)
        _, _, cookies = request(
            base_url,
            "POST",
            "/api/auth/login",
            {"username": "rehearsal-manager", "password": "manager-password-123"},
        )
        manager_cookie = next(cookie for cookie in cookies if cookie.startswith("shiftly_account_session="))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            _, payload, _ = request(base_url, "GET", "/api/reports", cookie=manager_cookie)
            if any(
                item["employee"] == "Recovery Crew" and item["status"] == "completed"
                for item in payload.get("reports", [])
            ):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Worker did not recover the stale rehearsal job.")
        with psycopg.connect(source_dsn) as connection:
            briefing_count = connection.execute(
                "SELECT COUNT(*) FROM briefings WHERE report_id = %s", (recovery_id,)
            ).fetchone()[0]
        if briefing_count != 1:
            raise RuntimeError("Recovery created an unexpected number of briefings.")
        with psycopg.connect(source_dsn) as connection:
            if connection.execute("SELECT attempts FROM briefing_jobs WHERE report_id=%s", (recovery_id,)).fetchone() != (2,):
                raise RuntimeError("Recovery did not use a second fenced attempt.")
        verify_database_outage(source_dsn, base_url, worker)
        worker = start_process("worker", env)
        wait_until(lambda: request(base_url, "GET", "/api/health/worker")[0] == 200,
                   "worker recovers after database outage")
        verify_reports(base_url, manager_cookie)

        legacy_env = dict(env)
        legacy_port = free_port()
        legacy_env["PORT"] = str(legacy_port)
        legacy = start_process("legacy", legacy_env, legacy_port)
        try:
            legacy_url = f"http://127.0.0.1:{legacy_port}"
            wait_for_http(legacy_url)
            verify_reports(legacy_url, manager_cookie)
        finally:
            stop_process(legacy)

        # Stop activity before comparing a consistent archive, including sessions.
        stop_process(worker)
        stop_process(api)
        before_restore = snapshot(source_dsn)
        archive_bytes = backup_restore(
            source_dsn, restore_dsn,
            source_container=os.environ.get("REHEARSAL_SOURCE_CONTAINER"),
            restore_container=os.environ.get("REHEARSAL_RESTORE_CONTAINER"),
        )
        if snapshot(restore_dsn) != before_restore:
            raise RuntimeError("Restored rows, sequences or foreign keys do not match the backup source.")
        restored_port = free_port()
        restored_api = start_process("api", restore_env, restored_port)
        try:
            restored_url = f"http://127.0.0.1:{restored_port}"
            wait_for_http(restored_url)
            verify_reports(restored_url, manager_cookie)
            status, _, cookies = request(restored_url, "POST", "/api/auth/login", {
                "username": "rehearsal-manager", "password": "manager-password-123",
            })
            if status != 200:
                raise RuntimeError("Manager could not sign in to the restored database.")
            verify_reports(restored_url, cookies[0])
        finally:
            stop_process(restored_api)
        print(json.dumps({"result": "passed", "checks": [
            "fresh migration", "001-012 upgrade preserving data", "repeat/concurrent migration",
            "API and independent worker", "SIGKILL and fenced lease recovery", "worker health",
            "database outage and reconnect", "legacy rollback with original sessions/reports",
            "archive restore: all rows, sequences and foreign keys", "restored API login and reports",
        ], "archiveBytes": archive_bytes, "tablesCompared": len(before_restore["rows"]),
            "sequencesCompared": len(before_restore["sequences"]),
            "foreignKeysCompared": len(before_restore["foreign_keys"])}))
    finally:
        if worker is not None:
            stop_process(worker)
        stop_process(api)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", choices=("api", "worker", "legacy"))
    args = parser.parse_args()
    if args.mode:
        raise SystemExit(run_child(args.mode))
    rehearse()


if __name__ == "__main__":
    main()
