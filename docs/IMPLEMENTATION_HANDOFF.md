# Shiftly baseline handoff

## Repository and checkout

- Repository folder: Shift-Observer
- Current branch: main
- Current commit: b289865
- Verification method: git status and git rev-parse on the checkout, plus a file-level inspection of the server and migration files.

## Verified baseline summary

This checkout is a single-file Python web app in server.py backed by PostgreSQL and a background briefing worker thread. It is not yet split into modular services, and it does not currently include a test suite or GitHub Actions workflow.

### Observed runtime structure
- HTTP server: ThreadingHTTPServer
- Main app logic: server.py
- Auth/session management: manager_sessions, crew_sessions, store_memberships
- Report storage and AI briefing: reports, briefing_jobs, briefings
- Head’s Up: store_heads_up
- Migrations: migrations/*.sql
- Deployment config: render.yaml
- Local database config: docker-compose.yml and .env.example

### Startup flow
1. Copy .env.example to .env and populate secrets.
2. Start Postgres locally with docker compose up -d postgres.
3. Set DATABASE_URL to the local Postgres connection string.
4. Start the app with python3 server.py.
5. The server calls initialize_database() before serving traffic.

### Environment variables observed
- HOST
- PORT
- OPENAI_API_KEY
- OPENAI_MODEL
- DATABASE_URL
- REPORT_COOLDOWN_SECONDS
- SECURE_COOKIES
- ADMIN_SIGNUP_KEY
- POSTGRES_USER
- POSTGRES_PASSWORD
- POSTGRES_DB

### Routes observed
- GET /api/health
- GET /api/auth/status
- GET /api/reports
- GET /api/heads-up
- GET /api/managers
- GET /api/weekly-overview
- POST /api/auth/login
- POST /api/auth/signup
- POST /api/auth/add-manager
- POST /api/auth/logout
- POST /api/reports

### Key product behavior observed
- Crew sign-in uses a shared store code and crew password.
- Manager sign-in uses per-user credentials and store membership lookup.
- Reports are accepted only after a quality gate passes.
- Accepted reports are queued into briefing_jobs and processed by a background thread.
- Head’s Up is store-scoped and can be updated by a manager.
- Manager listings and weekly overview are scoped by the selected session store.

## Migration and database notes

Migrations present in this checkout:
- 001_initial_schema.sql
- 002_manager_sessions.sql
- 003_remove_image_submission.sql
- 004_multi_tenant_access.sql
- 005_crew_sessions.sql
- 006_manager_credentials.sql
- 007_allow_username_managers.sql
- 008_store_heads_up.sql
- 009_manager_last_sign_in.sql

The schema includes the core tables for reports, jobs, briefings, stores, managers, memberships, and store messaging.

## Gaps identified against the handoff brief

- No pytest suite exists in the repository checkout.
- No .github/workflows/ directory exists, so there is no CI configuration.
- The current app is a monolithic Python service, not yet organized into modules/services.
- The repo name and app branding differ: the folder is Shift-Observer while the README and app call it Shiftly.
- The product brief describes a phased architecture and expected tenant-aware evolution; the current checkout still has a single-server implementation and no explicit modular boundary yet.

## Current implementation risks to record before refactor

- Security and tenant behavior are tightly coupled inside server.py.
- Database access and AI orchestration are interleaved with HTTP handling.
- Startup depends on a single local Postgres configuration and a single background thread.
- There is no regression test safety net yet.
- There is no staging or backup/restore runbook in the repo.

## Recommended next work

1. Baseline documentation and repo notes (in progress)
2. Add disposable Postgres integration tests
3. Add GitHub Actions for code quality and test validation
4. Document staging/deploy/runbook and backup/restore process
5. Extract configuration loading and separate concerns in small, tested increments

This is a verified baseline, not a rewrite plan. The next work should preserve current behavior while adding guardrails and structure.
