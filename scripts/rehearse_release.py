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
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlparse

import psycopg
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
    os.environ.setdefault("OPENAI_API_KEY", "")
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
    subprocess.run(command, cwd=ROOT, env=env, check=True)


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
    })
    restore_env = dict(env)
    restore_env["DATABASE_URL"] = restore_dsn

    migrate(env)
    migrate(env)
    migrate(restore_env)
    concurrent = [
        subprocess.Popen([sys.executable, "-m", "backend.shiftly.runtime.migrate"], cwd=ROOT, env=env)
        for _ in range(2)
    ]
    if any(process.wait(timeout=30) != 0 for process in concurrent):
        raise RuntimeError("Concurrent migration rehearsal failed.")

    api_port = free_port()
    api_env = dict(env)
    api_env["PORT"] = str(api_port)
    api = start_process("api", api_env, api_port)
    worker = start_process("worker", env)
    base_url = f"http://127.0.0.1:{api_port}"
    try:
        wait_for_http(base_url)
        status, signup, cookies = request(
            base_url,
            "POST",
            "/api/auth/signup",
            {
                "adminKey": "rehearsal-admin-key",
                "storeName": "Rehearsal Store",
                "storeCode": "rehearsal-store",
                "crewPassword": "crew-password-123",
                "managerUsername": "rehearsal-manager",
                "managerPassword": "manager-password-123",
                "confirmPassword": "manager-password-123",
            },
        )
        if status != 201:
            raise RuntimeError(f"Signup rehearsal failed with status {status}.")
        manager_cookie = next(cookie for cookie in cookies if cookie.startswith("shiftly_manager_session="))
        request(base_url, "POST", "/api/auth/logout", cookie=manager_cookie)
        status, _, cookies = request(
            base_url,
            "POST",
            "/api/auth/login",
            {"storeCode": "rehearsal-store", "role": "crew", "password": "crew-password-123"},
        )
        if status != 200:
            raise RuntimeError("Crew login rehearsal failed.")
        crew_cookie = next(cookie for cookie in cookies if cookie.startswith("shiftly_crew_session="))
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
            {"storeCode": "rehearsal-store", "password": "manager-password-123"},
        )
        manager_cookie = next(cookie for cookie in cookies if cookie.startswith("shiftly_manager_session="))
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

        request(base_url, "POST", "/api/auth/logout", cookie=manager_cookie)
        _, _, cookies = request(
            base_url,
            "POST",
            "/api/auth/login",
            {"storeCode": "rehearsal-store", "role": "crew", "password": "crew-password-123"},
        )
        crew_cookie = next(cookie for cookie in cookies if cookie.startswith("shiftly_crew_session="))
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
        stop_process(worker)
        with psycopg.connect(source_dsn) as connection:
            connection.execute(
                "DELETE FROM briefings WHERE report_id = %s", (recovery_id,)
            )
            connection.execute(
                """
                UPDATE briefing_jobs
                SET status = 'processing', locked_at = NOW() - INTERVAL '10 minutes', attempts = 1
                WHERE report_id = %s
                """,
                (recovery_id,),
            )
        worker = start_process("worker", env)
        _, _, cookies = request(
            base_url,
            "POST",
            "/api/auth/login",
            {"storeCode": "rehearsal-store", "password": "manager-password-123"},
        )
        manager_cookie = next(cookie for cookie in cookies if cookie.startswith("shiftly_manager_session="))
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

        legacy_env = dict(env)
        legacy_port = free_port()
        legacy_env["PORT"] = str(legacy_port)
        legacy = start_process("legacy", legacy_env, legacy_port)
        try:
            wait_for_http(f"http://127.0.0.1:{legacy_port}")
        finally:
            stop_process(legacy)

        backup_restore(
            source_dsn, restore_dsn,
            source_container=os.environ.get("REHEARSAL_SOURCE_CONTAINER"),
            restore_container=os.environ.get("REHEARSAL_RESTORE_CONTAINER"),
        )
        with psycopg.connect(restore_dsn) as restored:
            if restored.execute("SELECT COUNT(*) FROM reports").fetchone()[0] < 1:
                raise RuntimeError("Restored database did not contain the rehearsal report.")
        print("Release rehearsal passed: migration, API, worker, report completion, backup and restore.")
    finally:
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
