# Shiftly

Shiftly is a store-scoped shift reporting application. Crew members submit notes
from a phone or browser; managers review the original notes, AI-generated
briefings, a Weekly Overview, and a shared Head's Up message.

## Project status

Native phone and tablet development is now the first client priority. The
[React Native/Expo application](apps/mobile/README.md) provides individual
sign-in, store selection, account controls, crew reporting and a manager inbox
through the existing FastAPI services. The browser workspace remains available
as account administration and remaining workflows move to native screens.
See the [native roadmap](docs/NATIVE_APP_ROADMAP.md) and
[foundation handoff](docs/workstreams/react-native-foundation.md).

Accounts & Access integration status, September 22, 2026. This branch builds on
verified base `9a31a930ebf6fa305e8919d1ff398177666b3577` and published account
backend `261637a2da7aaaa942acdcd2ac5764bece610b32`. The combined local suite passed
588 tests, plus real release and account recovery rehearsals. See the
[integration handoff](docs/workstreams/copilot-accounts-permissions.md) for exact
revisions and evidence. This is integration-review readiness, not production cutover.

| Area | Current state |
| --- | --- |
| Crew and manager workflows | Implemented in the existing HTML/CSS/JavaScript application and Python server |
| Worker recovery | Durable jobs, bounded retries, expired-lease recovery, stale-result protection, and diagnostics implemented |
| Report services | Submission rules, report persistence/listing, and weekly generation/cache extracted into injectable services and repositories |
| FastAPI | Shared services, authentication/reporting/account adapters, protected pages and security middleware |
| Accounts & Access | Named crew/manager identities, scoped owner/admin/manager/crew policy, invitations, recovery, team and owner workflows |
| Automated checks | Disposable PostgreSQL, mocked AI, service/regression/contract tests, Chromium browser flows, and pinned CI dependencies |
| Native app | React Native/Expo phone and tablet foundation; native API, secure sign-in and daily reporting; real-device release checks pending |
| Inventory | Alphabetized company catalog with editable full-container sizes, add/edit/archive/restore, store shelves and product assignments in the native app; quantities and camera capture remain planned |

Both transports and independent worker/recovery flows are verified locally.
Hosted staging, actual ownership mapping and production promotion remain separate.

Current inventory work starts with the [foundation and shared company catalog](docs/workstreams/inventory-foundation-and-shared-catalog.md): reuse products/SKUs
across store-specific shelves. The prerequisite cleanup and first catalog/shelf slice are implemented with
additive migrations 015–016. Open **Inventory → Company catalog** to add products,
then **Inventory → Shelves** to create a shelf and assign them.

## What works today

### Crew

- Sign in with an individual username and password, or shared crew access during enrollment.
- Enter a name, shift, and notes, then submit a report.
- Read the current store Head's Up and its update time.
- Receive validation or submission feedback without access to manager briefings
  or the manager report inbox.

Typed employee names remain historical display metadata. New named submissions
also persist the server-verified individual actor.

### Managers

- Review reports from stores covered by their memberships.
- Read original notes alongside generated briefings and processing status.
- Request a cached, AI-assisted Weekly Overview for the session's selected store.
- Publish or replace that store's current Head's Up.

Named sign-in explicitly selects store, username and password. Existing
password-only reporting access remains available during enrollment, but grants
no account or inventory powers. Role and capability checks come from the server.

An authorized administrator can create a workspace with a store, shared crew
password, and first manager account. Admin-key-protected creation of additional
manager accounts is restricted to unassigned compatibility stores. Mapped stores
use named account administration. Empty databases do not require seeded data;
real business/owner mapping is an explicit, dry-run-first operator procedure.

### Accounts & Access

- Choose authorized stores, change passwords and sign out across devices.
- Invite and activate individual accounts without requiring employee email.
- Manage permitted store membership and delegated business authority.
- Transfer ownership, suspend authorized accounts and deliberately end shared login.
- Redeem independently issued recovery codes without exposing global password
  reset powers to local managers.
- Clear stale private information and drafts when another tab changes access.

## Current architecture and reliability

The configured application entry point is still `python server.py`, including in
[render.yaml](render.yaml). It serves the browser application and existing API
through `ThreadingHTTPServer`, applies migrations at startup, and starts a
briefing worker thread in the same process.

- **Application adapters:** `server.py`, `routes.py`, `auth.py`, `security.py`, and
  `store_service.py` translate HTTP to shared account/store/report services.
- **Report services:** [backend/shiftly/reports/](backend/shiftly/reports/) contains
  framework-independent workflows and PostgreSQL repositories. Existing callers
  reach them through compatibility wrappers. Named writes recheck policy in their
  transaction and serialize against revocation.
- **FastAPI foundation:** [backend/shiftly/app.py](backend/shiftly/app.py) provides
  an injectable app factory. Importing or creating the app does not run
  migrations, connect to the database, call AI, or start a worker.
- **Storage:** PostgreSQL migrations 001–014 cover reporting, worker/runtime
  recovery, named accounts, business/store memberships, sessions and audit.

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

The FastAPI app does not start a worker; the independent runtime supports bounded
database resources, coordinated migrations and database-backed worker health.
The supported runtime is one API process and a separate worker. Admission limits
remain process-local, so API replication needs shared limits. Database health
alone does not prove briefing jobs are progressing.

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

To run the development FastAPI adapter:

```sh
python -m uvicorn backend.shiftly.app:create_app --factory --host 127.0.0.1 --port 4174
```

This serves the integrated pages and APIs. Follow the runtime/deployment runbook
for coordinated migrations and a separate worker; production startup is unchanged.

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
account lifecycle, principal conflicts and real Chromium flows through both
servers. Browser viewport emulation is not physical iPhone/Android validation.

[CI](.github/workflows/ci.yml) runs Python 3.12 with disposable PostgreSQL 16,
installs locked dependencies, checks Python compilation and dependency
consistency, runs the suite and both recovery rehearsals, and retains evidence.

## Next three integration steps

1. **Review the Accounts & Access changes.** Use the backend and integration
   handoffs and green combined checks before merging the feature branches.
2. **Begin catalog/inventory development.** Reuse the verified actor and capability
   contract for SKU, location and manual inventory workflows, with additive migrations.
3. **Prepare hosted enrollment and runtime cutover.** Verify real ownership mapping,
   staging recovery, independent worker supervision and rollback before production
   activation. Local or CI rehearsal does not replace hosted operational evidence.

[Round 3](docs/parallel/ROUND_03.md) assigns these steps to
[Codex](docs/prompts/CODEX_INTEGRATION_RUNTIME.md) and
[GitHub Copilot](docs/prompts/COPILOT_FASTAPI_INTEGRATION.md), with exclusive file
ownership and published service checkpoints. Its Gate D defines when reviewed,
tested integration is ready for new-feature development; Gate P adds the hosted
staging and operational evidence required before production release. The initial
runtime target is one API process and one separate worker; shared cross-replica
limits are required before adding API replicas.

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
gates; operational stock and camera features are not part of Accounts & Access.

## Project documents

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md) — delivery sequence and exit gates.
- [Work packages](docs/TASKS.md) — dependencies and completion criteria.
- [Architecture](docs/ARCHITECTURE.md) — target modules and boundaries.
- [Inventory specification](docs/INVENTORY.md) — stock, weighing, camera, and receiving rules.
- [Worker recovery handoff](docs/workstreams/codex-foundation.md).
- [Contract/browser/CI handoff](docs/workstreams/copilot-foundation.md).
- [Report-service handoff](docs/workstreams/codex-f1-report-services.md).
- [FastAPI foundation handoff](docs/workstreams/copilot-f1-api-foundation.md).
- [Accounts backend contract](docs/workstreams/codex-accounts-permissions.md).
- [Accounts integration and verification](docs/workstreams/copilot-accounts-permissions.md).

The central plan, backlog, and architecture baseline sections still describe
the pre-foundation snapshot. Use this README's dated status, the merged code,
and the handoffs for current implementation evidence; retain the plan's exit
gates for deciding what is ready to ship.
