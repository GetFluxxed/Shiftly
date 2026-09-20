#!/usr/bin/env python3
"""Shiftly API server with Postgres persistence and a background briefing worker."""

import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

from auth import is_manager, session_store_id
from config import load_settings
from database import db_connection
from reporting import (
    JOB_WAKE,
    QUALITY_PROMPT,
    SYSTEM_PROMPT,
    call_openai,
    database_reports,
    ensure_submission_allowed,
    fail_job,
    json_bytes,
    job_report,
    queue_report,
    validate_report,
    weekly_overview,
    worker_loop,
    claim_job,
    complete_job,
)
from routes import add_manager as routes_add_manager, login as routes_login, save_heads_up as routes_save_heads_up, signup as routes_signup, submit_report as routes_submit_report
from security import (
    clean,
    client_key,
    cookie_token,
    login_rate_limited,
    parse_json,
    password_hash,
    rate_limited,
    record_login_failure,
    record_signup_attempt as security_record_signup_attempt,
    session_token,
    signup_rate_limited as security_signup_rate_limited,
)
from store_service import heads_up, is_crew, manager_accounts, manager_username, store_for_code

ROOT = Path(__file__).parent
REQUESTS = {}
LOGIN_FAILURES = {}
SIGNUP_ATTEMPTS = {}
SESSION_TTL = 8 * 60 * 60
SETTINGS = load_settings()

signup_rate_limited = security_signup_rate_limited
record_signup_attempt = security_record_signup_attempt

HOST = SETTINGS.host
PORT = SETTINGS.port
MODEL = SETTINGS.openai_model
DB_URL = SETTINGS.database_url
REPORT_COOLDOWN_SECONDS = SETTINGS.report_cooldown_seconds
SECURE_COOKIES = SETTINGS.secure_cookies
ADMIN_SIGNUP_KEY = SETTINGS.admin_signup_key

REPORT_SIMILARITY_THRESHOLD = 0.75

try:
    import certifi
except ImportError:
    certifi = None


def initialize_database():
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
            for migration in sorted((ROOT / "migrations").glob("*.sql")):
                cursor.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (migration.name,))
                if cursor.fetchone():
                    continue
                cursor.execute(migration.read_text(encoding="utf-8"))
                cursor.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (migration.name,))
        connection.commit()




class ShiftlyHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        if SECURE_COOKIES:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        super().end_headers()

    def send_json(self, status, value):
        body = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            database_ok = False
            try:
                with db_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1")
                        database_ok = cursor.fetchone() == (1,)
            except (RuntimeError, psycopg.Error):
                database_ok = False
            openai_configured = bool(os.environ.get("OPENAI_API_KEY"))
            healthy = database_ok
            self.send_json(200 if healthy else 503, {
                "status": "ok" if healthy else "degraded",
                "openaiConfigured": openai_configured,
                "databaseConfigured": database_ok,
                "secureCookies": SECURE_COOKIES,
            })
            return
        if path == "/api/auth/status":
            manager_id = is_manager(self)
            crew_store_id = is_crew(self)
            self.send_json(200, {
                "authenticated": bool(manager_id or crew_store_id),
                "role": "manager" if manager_id else "crew" if crew_store_id else None,
                "managerName": manager_username(manager_id) if manager_id else None,
            })
            return
        if path == "/api/reports":
            manager_id = is_manager(self)
            if not manager_id:
                self.send_json(401, {"error": "Manager authentication required."})
                return
            try:
                self.send_json(200, {"reports": database_reports(manager_id)})
            except RuntimeError as error:
                self.send_json(503, {"error": str(error)})
            return
        if path == "/api/heads-up":
            manager_id = is_manager(self)
            store_id = session_store_id(self, manager_id) if manager_id else is_crew(self)
            if not store_id:
                self.send_json(401, {"error": "Sign-in required."})
                return
            self.send_json(200, heads_up(store_id))
            return
        if path == "/api/managers":
            manager_id = is_manager(self)
            store_id = session_store_id(self, manager_id)
            if not store_id:
                self.send_json(401, {"error": "Manager sign-in required."})
                return
            self.send_json(200, {"managers": manager_accounts(store_id)})
            return
        if path == "/api/weekly-overview":
            manager_id = is_manager(self)
            store_id = session_store_id(self, manager_id)
            if not store_id:
                self.send_json(401, {"error": "Manager sign-in required."})
                return
            try:
                self.send_json(200, weekly_overview(store_id))
            except (RuntimeError, ValueError, json.JSONDecodeError) as error:
                self.send_json(503, {"error": str(error)})
            return
        if path in {"/", "/index.html"}:
            file_path = ROOT / "index.html"
        elif path == "/crew.html":
            if not is_crew(self):
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
                return
            file_path = ROOT / "crew.html"
        elif path == "/manager.html":
            if not is_manager(self):
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
                return
            file_path = ROOT / "manager.html"
        else:
            public_files = {
                "/about.html": ROOT / "about.html",
                "/app.js": ROOT / "app.js",
                "/auth.js": ROOT / "auth.js",
                "/crew.html": ROOT / "crew.html",
                "/manager.js": ROOT / "manager.js",
                "/manager.html": ROOT / "manager.html",
                "/styles.css": ROOT / "styles.css",
            }
            file_path = public_files.get(path)
            if file_path is None:
                self.send_error(404)
                return
        if not file_path.is_file() or file_path.resolve().parent != ROOT.resolve():
            self.send_error(404)
            return
        content_type = "text/html" if file_path.suffix == ".html" else "text/css" if file_path.suffix == ".css" else "application/javascript"
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/auth/login":
            routes_login(self)
            return
        if path == "/api/auth/signup":
            routes_signup(self)
            return
        if path == "/api/auth/add-manager":
            routes_add_manager(self)
            return
        if path == "/api/auth/logout":
            manager_token = cookie_token(self, "shiftly_manager_session")
            crew_token = cookie_token(self, "shiftly_crew_session")
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    if manager_token:
                        cursor.execute("DELETE FROM manager_sessions WHERE token_hash = %s", (hashlib.sha256(manager_token.encode()).hexdigest(),))
                    if crew_token:
                        cursor.execute("DELETE FROM crew_sessions WHERE token_hash = %s", (hashlib.sha256(crew_token.encode()).hexdigest(),))
                connection.commit()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            secure = "; Secure" if SECURE_COOKIES else ""
            self.send_header("Set-Cookie", f"shiftly_manager_session=; Path=/; HttpOnly; SameSite=Strict{secure}; Max-Age=0")
            self.send_header("Set-Cookie", f"shiftly_crew_session=; Path=/; HttpOnly; SameSite=Strict{secure}; Max-Age=0")
            body = json_bytes({"authenticated": False})
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/heads-up":
            routes_save_heads_up(self)
            return
        routes_submit_report(self)

    def login(self):
        routes_login(self)

    def signup(self):
        routes_signup(self)

    def add_manager(self):
        routes_add_manager(self)

    def save_heads_up(self):
        routes_save_heads_up(self)

    def submit_report(self):
        routes_submit_report(self)

    def log_message(self, *_):
        return


if __name__ == "__main__":
    if not DB_URL:
        raise SystemExit("DATABASE_URL is missing. Add it to .env before starting Shiftly.")
    try:
        initialize_database()
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    except psycopg.OperationalError as error:
        raise SystemExit(
            "Could not connect to Postgres. Check DATABASE_URL, the database "
            "password, and that the configured port matches docker-compose.yml.\n"
            f"Connection detail: {error}"
        ) from error
    Thread(target=worker_loop, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), ShiftlyHandler)
    print(f"Shiftly is running at http://{HOST}:{PORT}/", flush=True)
    print("Leave this terminal open while using the app. Press Ctrl+C to stop.", flush=True)
    server.serve_forever()
