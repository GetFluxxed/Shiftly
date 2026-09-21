# GitHub Copilot F1 API foundation handoff

## Assignment identity

- Branch: `codex/f1-api-foundation`
- Worktree: `/Users/getfluxxed/projects/Shiftly-codex-f1-api-foundation`
- Base commit: `2e0e2ec6205bd874bfa1c318120786c70061f916`
- Scope: development-only FastAPI factory and health compatibility routes

The production entry point remains `server.py`. No report, authentication,
signup, manager, Head's Up, weekly, static-page, migration, inventory, camera,
or worker startup code was added to the FastAPI app.

## Factory and routes

`backend.shiftly.app.create_app` has this keyword-injectable signature:

```python
create_app(
    *,
    settings: Settings | None = None,
    connection_factory: ConnectionFactory | None = None,
    worker_status_provider: WorkerStatusProvider | None = None,
) -> FastAPI
```

- `Settings` is the existing root `config.Settings` model.
- The default database factory uses the injected settings URL and does not
  mutate environment variables.
- The default worker provider lazily imports the existing `reporting.worker_status`
  only when a health request needs it.
- App creation and package import do not connect to PostgreSQL, run migrations,
  call AI, launch threads, or bind a listener.
- An explicit FastAPI lifespan records startup/shutdown state and leaves
  resource ownership available for later app-owned resources.
- Blocking health database probes use synchronous route functions, so they run
  in FastAPI's worker thread rather than the async event loop.

Implemented:

- `GET /api/health`
  - Preserves legacy DB-based 200/503 semantics and stable fields.
  - Adds the existing worker status object.
- `GET /api/health/worker`
  - Uses the injected provider.
  - Returns 200 only for `status == "ok"`; otherwise 503.
  - Provider failures return a degraded, unstarted-safe status.

The middleware preserves current security headers, conditional HSTS, JSON
`Cache-Control: no-store`, and JSON content behavior for API responses. FastAPI
documentation/OpenAPI routes and all non-health routes are intentionally
unported; this branch does not claim whole-application compatibility.

## Changed files

Only the assigned allowlist was changed:

- `backend/__init__.py`
- `backend/shiftly/__init__.py`
- `backend/shiftly/app.py`
- `backend/shiftly/core/`
- `backend/shiftly/api/`
- `requirements.txt`
- `requirements-dev.txt`
- `requirements.lock`
- `requirements-dev.lock`
- `.github/workflows/ci.yml`
- `tests/api_foundation/`
- `scripts/run_api_dev.py`
- this handoff document

Codex-owned `backend/shiftly/reports/` (if later added), `reporting.py`,
`routes.py`, `server.py`, migrations, existing tests and fixtures, UI assets,
and deployment files were not edited.

## Dependency strategy

Runtime additions:

- FastAPI `0.141.1`
- Uvicorn standard extras `0.53.0`

Development additions:

- HTTPX `0.28.1` for the FastAPI test client
- Existing Playwright/Pytest pins were preserved
- Lock files pin the resolved direct and transitive test/runtime packages

The legacy server remains the production runtime. `scripts/run_api_dev.py`
provides an explicit local-only launch:

```sh
python3 scripts/run_api_dev.py
```

It binds `127.0.0.1:4174` and does not change production startup.

## Validation evidence

Environment:

- Python 3.14.7 local runtime
- Python 3.12 remains the CI target
- PostgreSQL `postgres:16-alpine`
- Disposable database bound to `127.0.0.1:55434`
- No production database or paid AI request

Commands:

```sh
python3 -m pip install -r requirements-dev.lock
python3 -m pip check
python3 -m compileall -q backend scripts tests
TEST_DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55434/shiftly_test \
DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55434/shiftly_test \
OPENAI_API_KEY=test-key ADMIN_SIGNUP_KEY=test-admin-key \
python3 -m pytest -q tests/api_foundation
```

Foundation-only result:

```text
10 passed in 0.15s
```

Combined result, including existing tests, Round 1 contract/browser tests and
the new API foundation tests:

```text
135 passed in 22.61s
No broken requirements found.
```

The disposable PostgreSQL container was stopped after validation. Browser tests
continued to target the legacy `server.py`; no browser parity claim is made for
FastAPI in this slice.

## Gaps and coordinator requests

- Full endpoint parity, authentication identity extraction, browser cutover,
  static-page serving, reports adapters, and worker separation remain future
  work.
- The current FastAPI app is development-only and is not a production
  transport switch.
- Codex report-service extraction must be integrated independently; this branch
  does not depend on unpublished interfaces.
- After the coordinator confirms Codex integration, merge updated
  `origin/main` into this branch without rewriting published history and rerun
  the combined suite plus browser checks.
- Repository branch-protection/status-check settings were not changed. The
  coordinator should verify required CI checks and review enforcement.
