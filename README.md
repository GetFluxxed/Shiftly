# Shiftly

Shiftly is a store-scoped operations application for shift reports, inventory,
production, and manager review. The primary phone/tablet client is React Native
with Expo; FastAPI exposes the supported mobile API and PostgreSQL is the system
of record. The browser application remains a compatibility surface for existing
reporting and selected administration and production workflows.

## Status and evidence

This document describes the source tree as of 2026-10-25. `604683d` is the clean
adoption baseline supplied for this review. "Implemented" below means present in
this checkout. Local or CI verification is evidence only for the revision on
which it ran. Hosted deployment, production data mapping, physical-device behavior,
signed builds, and app-store publication are not verified by this documentation
review.

Implemented in the current source:

- individual invitation-based accounts, opaque revocable sessions, business/store
  memberships, and owner/admin/manager/production/crew policy;
- native sign-in, reporting, Heads Up, team and owner administration;
- an owner-operated [Time Tracking demo](docs/workstreams/time-tracking-demo.md)
  with named crew, clock-in/out history, independent 3:30 / 5:30 timers, and compact
  rosters with member detail modals for larger teams;
- a business catalog, store shelves, package definitions, barcode lookup/capture,
  stock balances and movement history;
- reviewed whole-store counts with draft, review, and posting transitions;
- revisioned recipes with Ingredients/Variegato sections and recipe-only lines,
  confirmed production deductions with a 1% ingredient allowance,
  reversal rules, and store-scoped production forecasts;
- durable briefing jobs and a separate worker runtime; and
- manager/owner invoice drafts, reviewed photo extraction and incoming stock previews;
- additive PostgreSQL migrations `001` through `029`.

Mobile count observations now have a durable offline queue with a restricted
prepared-count workspace; device acceptance remains pending. Review and stock
posting stay online. Invoice photo reading and reviewed incoming previews are
implemented; receipt posting, shelf-photo counting and offline stock posting remain
planned. See [invoice previews](docs/workstreams/invoice-receiving-preview.md).
Camera barcode scanning is implemented and does not save an image. The temporary
Saved scans inbox keeps up to 100 catalog drafts on the device for explicit online
review; it never creates stock. Its restricted offline workspace requires online
preparation and catalog-management permission. See the
[October 31 iPhone pilot](docs/workstreams/iphone-pilot-2026-10-31.md) for its
retirement criteria and signed-build/device/hosting gates. Forecasts are
store-scoped decision support; they do not bypass reviewed stock operations.

Shared crew credentials, password-only manager access, and public signup are
retired product flows. Existing compatibility data and browser adapters remain
only where needed for migration and supported browser behavior. All new staff
activation starts with an invitation and baseline crew authority. An authorized
owner or administrator may later assign another permitted role. Crew, production,
and manager accounts have one active store; owners and appropriately delegated
administrators may switch within their authorized business scope. Production
accounts do not receive Reports or Store navigation.

## Repository map

| Path | Responsibility |
| --- | --- |
| `backend/shiftly/api/` | FastAPI transport adapters and compatibility routes |
| `backend/shiftly/identity/` | accounts, sessions, invitations, membership policy |
| `backend/shiftly/reports/` | report submission, persistence, briefings, weekly overview |
| `backend/shiftly/inventory/` | catalog, packages, shelves, balances, movements, counts |
| `backend/shiftly/production/` | recipes and production transactions |
| `backend/shiftly/forecasts/` | store forecast validation, storage, provider boundary |
| `backend/shiftly/jobs/` | durable job status and worker entry point |
| `backend/shiftly/runtime/` | composition, database resources, migrations, provider setup |
| `apps/mobile/` | Expo/React Native phone and tablet client |
| `migrations/` | immutable, ordered PostgreSQL migrations |
| `tests/` | service, API, migration, recovery, and browser checks |

See [Architecture](docs/ARCHITECTURE.md), [Database](docs/DATABASE.md),
[Security](docs/SECURITY.md), and the [implementation plan](docs/IMPLEMENTATION_PLAN.md)
for boundaries and delivery state. The repository adopts the external
[ENGINEERING.md](ENGINEERING.md) policy through [engineering adoption](docs/workstreams/engineering-adoption.md);
that workstream records the project-specific baseline and exceptions without
duplicating the policy.

## Local development

Use Python 3.12.15, PostgreSQL 16, Node.js 22.13+ or 24.3+, and the package manager
version declared by `apps/mobile/package.json`. Run backend commands from the
repository root.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
docker compose up -d postgres
export DATABASE_URL='postgresql://shiftly:change-me@127.0.0.1:55432/shiftly'
python -m backend.shiftly.runtime.migrate
```

The migration and worker commands do not load `.env`. The API retains a
compatibility `.env` loader, but use explicit configuration consistently: export
`DATABASE_URL`, provider settings, `HOST=127.0.0.1`, and `SECURE_COOKIES=false` in
each process environment
(or use the documented secret manager). The URL above matches the Compose
defaults; change it when you change those credentials. Never put secrets in the
mobile environment or commit `.env`. For an isolated empty local database and guarded
first-owner setup, follow [Create a fresh local demo](apps/mobile/README.md#create-a-fresh-local-demo).

Start the supported FastAPI and worker topology in separate terminals:

```sh
SHIFTLY_WORKER_MODE=external python -m uvicorn backend.shiftly.app:create_app \
  --factory --host 127.0.0.1 --port 4174 --workers 1
SHIFTLY_WORKER_MODE=external python -m backend.shiftly.jobs.worker
```

FastAPI startup checks the applied schema; it does not apply migrations. The
single API process limit is intentional until admission controls are shared
across replicas. `python server.py` is the legacy browser runtime and does not
serve `/api/mobile`.

For the native client, follow [apps/mobile/README.md](apps/mobile/README.md). Its
local API origin belongs in ignored `apps/mobile/.env.local`. Use a private LAN
address for a physical device; `127.0.0.1` on a phone means the phone itself.

## Verification and operations

Backend tests require an explicit `TEST_DATABASE_URL` for disposable PostgreSQL.
They refuse to fall back to the application database. The authoritative commands,
CI coverage, recovery rehearsals, and evidence rules are in
[docs/TESTING.md](docs/TESTING.md). Deployment, rollback, backup, and hosted
verification procedures are in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Common native checks are:

```sh
pnpm --dir apps/mobile check
pnpm --dir apps/mobile export:native
```

An export proves JavaScript/assets can be bundled; it does not compile or sign a
native binary and does not prove camera, secure storage, lifecycle, accessibility,
or network behavior on a real device.

## Delivery documents

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md) — implemented, active, and
  planned product phases.
- [Native roadmap](docs/NATIVE_APP_ROADMAP.md) — native behavior and device gates.
- [Inventory rules](docs/INVENTORY.md) — quantity, stock, weighing, and evidence
  invariants.
- [Individual account release contract](docs/workstreams/individual-accounts-release-2026-09-24.md).
- [Catalog and shelf contract](docs/workstreams/inventory-foundation-and-shared-catalog.md).
- [Inventory count contract](docs/workstreams/inventory-counts.md).
- [Production and assisted inventory contract](docs/workstreams/production-and-assisted-inventory.md).

Older integration handoffs and parallel-round documents are historical evidence.
Their branch names, test totals, shared-login transition language, or planned
feature lists do not override this source tree or the current contracts above.
