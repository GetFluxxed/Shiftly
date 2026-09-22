# Shiftly architecture: current baseline and target

Updated: 2026-09-21. Delivery authority: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Current runtime

Merged baseline `e01e84e` includes framework-independent identity, store and
report services under `backend/shiftly/`, a FastAPI application factory and
compatibility routes, bounded database resources, coordinated migrations and a
separate durable worker. Legacy adapters delegate to these boundaries; route
discovery of `server.py` globals has been removed. The supported new topology is
one API process plus one separately supervised worker.

PostgreSQL stores accounts, sessions, memberships, reports, briefing jobs,
briefings, Head's Up, and the weekly cache. The existing client is HTML/CSS/JS.
Contract and Chromium browser tests run on both transports. The focused
verification follow-up closes request-error and recovery coverage gaps; see
[verification evidence](workstreams/focused-verification.md). Production still
uses the legacy entry point in `render.yaml`. Inventory, media storage, sales
ingestion and the installable client remain planned.

## Target application

One Shiftly application will expose a FastAPI backend and an installable mobile
web client. A separately supervised worker processes durable jobs. PostgreSQL
remains the transaction authority; private object storage holds inventory images.

The manager app has Operations and Inventory spaces. Both use the same account
and selected-store context. A later native client uses the versioned API rather
than reimplementing stock calculations or permissions.

FastAPI routers will group module endpoints, with shared authorization and
resource dependencies. This follows its supported [router/dependency structure](https://fastapi.tiangolo.com/tutorial/bigger-applications/).

Proposed organization, to be introduced incrementally:

```text
backend/shiftly/
  app.py                  application factory and router registration
  core/                   settings, database resources, errors, logging
  identity/               accounts, sessions, memberships, permissions
  stores/                 store configuration and selected-store context
  reports/                existing report and briefing workflows
  inventory/
    catalog/              items, conversions, weights and pars
    locations/            areas, shelves, bins and assignments
    ledger/               movements, balances, transfers and reversals
    counts/               sessions, observations, weighing and approval
  media/                  private uploads, evidence and retention
  vision/                 count proposals, provider adapters and evaluation
  sales/                  ingestion, recipes and usage mappings
  forecasting/            shortage estimates and explanations
  receiving/              invoices, scans and receipt posting
  jobs/                   durable queue, handlers and worker entry point
web/
  app-shell/              routing, navigation, installation and sync status
  operations/             existing manager workflows
  inventory/              tracker, shelves, count review and receiving
  shared/                 authenticated API client and reusable controls
```

Identity, stores, reports, jobs, runtime and the API/core boundaries are implemented.
Inventory, media, vision, sales, forecasting, receiving and the new client tree
remain targets. Choose client
build tooling in the app-shell work package; preserve existing pages while
introducing feature modules and a consistent API client.

## Boundary rules

- HTTP adapters parse requests, authorize, and translate responses. Business
  services own workflows; repositories own SQL.
- Domain services do not import HTTP handlers or `server.py`. Inject settings,
  the authenticated actor/store context, database resources, clock, and provider
  interfaces where required.
- Inventory owns stock posting. Vision, receiving, and forecasting cannot write
  balances directly; they submit reviewed observations or approved movement
  commands through inventory services.
- The ledger records one atomic posting and updates its balance projection in
  the same transaction. Jobs can run more than once; commands remain idempotent.
- Keep existing psycopg/SQL and migrations initially. A new web framework does
  not require a simultaneous ORM or database rewrite.
- Do not call blocking database/AI work directly inside an async event loop.
  Use bounded synchronous execution initially or deliberately adopt compatible
  async clients; image processing belongs in durable workers.
- Store-level authorization applies to nested IDs, media, jobs, count approval,
  invoice lines, exports, and all retry/sync paths.

## FastAPI transition

1. Extract services and capture the current behavior in contract tests.
2. Introduce the app factory and routers alongside the current server for
   development/staging. The old `BaseHTTPRequestHandler` is not an ASGI app;
   port its adapters rather than pretending it can be mounted unchanged.
3. Keep current `/api/...` routes and static entry pages during migration.
   Explicitly map validation/status/cookie differences. New modules use
   `/api/v1/...`; document compatibility and deprecation separately.
4. Use FastAPI [lifespan](https://fastapi.tiangolo.com/advanced/events/) to open
   and close application resources. Run a coordinated migration command before
   web and worker startup, with compatible additive migrations.
5. Move durable work into an independently started, supervised process using
   the existing PostgreSQL queue as the initial foundation. Image analysis,
   imports, and stock-affecting work are not request-lifetime background tasks.
   FastAPI's [background-task guidance](https://fastapi.tiangolo.com/tutorial/background-tasks/)
   distinguishes lightweight in-process tasks from heavier work.
6. Preserve data, sessions, and route contracts through staging verification,
   cutover, and a rehearsed rollback. Retire the old transport only after parity.

## Runtime and failure behavior

Use liveness for process availability, readiness for required dependencies and
schema compatibility, and separate worker heartbeat/queue-age indicators. A
healthy database alone does not prove jobs are being processed.

Workers need bounded attempts, delayed retry, lease recovery, dead-letter/manual
retry controls, and exception handling that survives failure to record another
failure. Save sanitized diagnostics and correlation IDs without credentials or
unnecessary report/photo content. Preserve original notes during AI outages.

The current login budget and weekly concurrency cap are process-local. Before
adding web replicas, introduce coordinated admission and shared limits. Keep
database pool sizes and worker concurrency within a documented deployment budget.
Migration locking and queue ownership must work across processes.

## Client and media behavior

The confirmed first app is an installable mobile web app. Add an app manifest,
same-origin HTTPS delivery, an asset-only service-worker cache policy, explicit
draft/sync states, and refresh/version handling. Keep final inventory posting
online; saved drafts recheck authorization and versions on reconnect.

Use phone capture with an upload fallback. Private image storage, validation,
limited retention, evidence links, and provider isolation belong to the media
and vision modules. Camera permission policy changes are scoped to capture
surfaces. Native app packaging, device credentials, and push integrations are
later work using the same backend.

## Data ownership

Current store IDs remain the authorization boundary. Decide whether a future
organization groups multiple stores before introducing shared catalogs; do not
invent an organization migration as a prerequisite for a single-store pilot.
Inventory IDs and relationships remain store-scoped either way.

See [INVENTORY.md](INVENTORY.md) for measurement rules, count reconciliation,
movement history, forecasts, and receiving. See [DATABASE.md](DATABASE.md) for
implemented schema versus proposed additions.
