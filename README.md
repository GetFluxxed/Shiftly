# Shiftly

Shiftly is a store-scoped shift reporting application. Crew members submit notes
from a phone or browser; managers review the original notes, AI-generated
briefings, a Weekly Overview, and a shared Head's Up message.

## Project status

Status checked against `origin/main` at
[`818a03c`](https://github.com/GetFluxxed/Shiftly/commit/818a03cb1bcff67c6c36a3ddbbd73a1028894dff)
on September 21, 2026. The worker recovery, contract/browser testing, report-service
extraction, and FastAPI foundation branches are merged. The
[combined CI run passed](https://github.com/GetFluxxed/Shiftly/actions/runs/35659723156).
This describes repository integration, not a verified production deployment.

| Area | Current state |
| --- | --- |
| Crew and manager workflows | Implemented in the existing HTML/CSS/JavaScript application and Python server |
| Worker recovery | Durable jobs, bounded retries, expired-lease recovery, stale-result protection, and diagnostics implemented |
| Report services | Submission rules, report persistence/listing, and weekly generation/cache extracted into injectable services and repositories |
| FastAPI | App factory, configuration/dependency injection, security middleware, and two health endpoints implemented for development |
| Application migration | In progress; authentication, report/weekly/Head's Up HTTP adapters, and static pages still use the existing server |
| Automated checks | Disposable PostgreSQL, mocked AI, service/regression/contract tests, Chromium browser flows, and pinned CI dependencies |
| Inventory and installable app | Planned; no inventory workspace, camera counting, stock ledger, or installable app shell yet |

These changes complete foundation slices, not all F0–F3 exit gates. Full FastAPI
compatibility, worker separation, staging/restore/rollback evidence, and required
merge-check enforcement remain to be completed or verified.

## What works today

### Crew

- Sign in with the store's shared crew access.
- Enter a name, shift, and notes, then submit a report.
- Read the current store Head's Up and its update time.
- Receive validation or submission feedback without access to manager briefings
  or the manager report inbox.

Crew names are self-reported metadata, not verified individual identities.

### Managers

- Review reports from stores covered by their memberships.
- Read original notes alongside generated briefings and processing status.
- Request a cached, AI-assisted Weekly Overview for the session's selected store.
- Publish or replace that store's current Head's Up.

Manager accounts are individual, but the current sign-in flow identifies them
using store code and password. Explicit username-based sign-in and the stronger
identity/permission model needed for inventory approvals remain planned work.

An authorized administrator can create a workspace with a store, shared crew
password, and first manager account. Admin-key-protected creation of additional
manager accounts also exists. Empty databases do not require seeded store data.

## Current architecture and reliability

The configured application entry point is still `python server.py`, including in
[render.yaml](render.yaml). It serves the browser application and existing API
through `ThreadingHTTPServer`, applies migrations at startup, and starts a
briefing worker thread in the same process.

- **Application adapters:** `server.py`, `routes.py`, `auth.py`, `security.py`, and
  `store_service.py` retain HTTP/session responsibilities. Some account routes
  still depend on server globals.
- **Report services:** [backend/shiftly/reports/](backend/shiftly/reports/) contains
  framework-independent workflows and PostgreSQL repositories. Existing callers
  reach them through compatibility wrappers; adapters still own authorization.
- **FastAPI foundation:** [backend/shiftly/app.py](backend/shiftly/app.py) provides
  an injectable app factory. Importing or creating the app does not run
  migrations, connect to the database, call AI, or start a worker.
- **Storage:** PostgreSQL migrations 001–012 cover stores, memberships, accounts,
  sessions, reports, briefings/jobs, Head's Up, weekly caching, and job recovery.

Submission validation, duplicate checks, cooldowns, and an AI quality gate run
before acceptance. Accepted original notes and their briefing job are committed
together, before background briefing generation. The original notes remain
available if that later generation fails.

Transient briefing failures have bounded retries. Expired job leases can be
reclaimed, and a stale worker cannot overwrite a newer claim's result. Worker
errors use sanitized diagnostics, and failures while recording another failure
no longer terminate processing. A provider call can repeat after a crash; job
recovery does not promise exactly-once external AI execution.

Both transports expose:

- `GET /api/health`: database-based 200/503 status plus worker diagnostics.
- `GET /api/health/worker`: 200 only when the observed worker is healthy;
  otherwise 503.

The development FastAPI app does not start a worker, so its default worker health
is degraded. Worker diagnostics are process-local; a separate worker deployment,
cross-process monitoring, coordinated migrations, database pools/timeouts, and
shared limits are still future work. Database health alone does not prove that
briefing jobs are progressing.

## Local development

Use Python 3.12 (the CI target), PostgreSQL 16, and a checkout containing the
merged foundations above. Run commands from the repository root.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
cp .env.example .env
```

Edit `.env` with a local `DATABASE_URL`, matching PostgreSQL credentials, an
`ADMIN_SIGNUP_KEY`, and an `OPENAI_API_KEY` for interactive AI functionality.
For local HTTP development set `HOST=127.0.0.1` and `SECURE_COOKIES=false`; HTTPS
deployments should use secure cookies. Keep `.env` private.

The included Compose configuration supplies a development database on port
55432 with persistent local storage:

```sh
docker compose up -d postgres
python server.py
```

Open [http://127.0.0.1:4173](http://127.0.0.1:4173). Use **Create a workspace** with
the configured admin key to create the first store and manager. Normal report
submission invokes AI; automated tests replace it with deterministic mocks.

To run the separate FastAPI health foundation:

```sh
python -m uvicorn backend.shiftly.app:create_app --factory --host 127.0.0.1 --port 4174
```

This is a development entry point. Crew/manager pages and business endpoints
have not been ported to it.

## Testing

Install Chromium after the development dependencies:

```sh
python -m playwright install chromium
```

Set `TEST_DATABASE_URL` to a **disposable PostgreSQL database**, then run:

```sh
DATABASE_URL='' OPENAI_API_KEY='' python -m pytest -q \
  --browser chromium --tracing=retain-on-failure --screenshot=only-on-failure
python -m pip check
```

Database tests create isolated temporary schemas and remove them after use;
fixtures refuse to fall back to the application's database. AI calls are mocked,
and unexpected provider requests fail tests. Coverage includes worker recovery,
report services, store boundaries, authentication contracts, weekly behavior,
FastAPI health, and real Chromium flows against the existing server. Browser
viewport emulation is not physical iPhone/Android validation or FastAPI browser
parity.

[CI](.github/workflows/ci.yml) runs Python 3.12 with disposable PostgreSQL 16,
installs locked dependencies, checks Python compilation and dependency
consistency, runs the suite, and retains browser failure artifacts.

## Next three integration steps

1. **Finish the service boundaries.** Extract account/session/store workflows
   still tied to HTTP handlers and server globals. Preserve authorization,
   cookies, and store scope; reconcile the planning status and outstanding
   foundation checks against the merged baseline.
2. **Complete FastAPI compatibility.** Connect those services and the extracted
   report services to the existing API contracts, then serve the current pages.
   Run the same contract and browser flows against both transports, including
   error codes, cookies, headers, and cross-store access checks.
3. **Prepare and verify the runtime cutover.** Separate and supervise the durable
   worker, coordinate migrations, add bounded database resources and shared
   monitoring/limits, and rehearse staging migration, backup restoration, and
   rollback before switching the configured application entry point.

## Planned modules after the foundation

The first app release will be an **installable mobile web app**, with native
iPhone/Android clients considered later. Inventory will be a separate workspace
reached from the manager window, using authorized store context.

- **Catalog and shelves:** items, pack/unit conversions, explicit locations,
  shelf assignments, and editable store pars.
- **Running inventory:** movement history, manual receipts/counts, corrections,
  and a digital tracker with source and freshness information.
- **Partial inventory:** item-specific full weights and container tare profiles;
  measured open stock combined with unopened stock without double counting.
- **Phone camera counts:** private photo capture/upload and suggested quantities
  that require review before changing inventory. Photos do not establish the
  remaining weight of open containers.
- **Shortage insights:** below-par indicators first, then explainable estimates
  using validated sales/usage mappings and current inventory.
- **Stretch receiving:** scan barcodes/SKUs to reconcile invoice lines and post
  confirmed receipts through the same inventory records.

Manual inventory and weighing establish the trusted workflow before camera
automation. Inventory work follows the service, compatibility, and operational
gates; it is not part of the current FastAPI health foundation.

## Project documents

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md) — delivery sequence and exit gates.
- [Work packages](docs/TASKS.md) — dependencies and completion criteria.
- [Architecture](docs/ARCHITECTURE.md) — target modules and boundaries.
- [Inventory specification](docs/INVENTORY.md) — stock, weighing, camera, and receiving rules.
- [Worker recovery handoff](docs/workstreams/codex-foundation.md).
- [Contract/browser/CI handoff](docs/workstreams/copilot-foundation.md).
- [Report-service handoff](docs/workstreams/codex-f1-report-services.md).
- [FastAPI foundation handoff](docs/workstreams/copilot-f1-api-foundation.md).

The central plan, backlog, and architecture baseline sections still describe
the pre-foundation snapshot. Use this README's dated status, the merged code,
and the handoffs for current implementation evidence; retain the plan's exit
gates for deciding what is ready to ship.
