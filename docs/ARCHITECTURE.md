# Shiftly architecture

Reviewed against source revision `df53f98` on 2026-10-21. This is the current
source boundary. Delivery order lives in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md),
operational topology in [DEPLOYMENT.md](DEPLOYMENT.md), and accepted legacy
deviations in the [implementation plan](IMPLEMENTATION_PLAN.md#accepted-legacy-deviations).

## Runtime and clients

FastAPI is the supported API for the Expo/React Native client and also serves
compatibility browser pages and routes. PostgreSQL is the transaction authority.
A separately supervised worker processes durable briefings and production forecasts. The supported
initial topology is one API process and one worker; admission controls remain
process-local, so API replicas require a shared limit design first.

`backend/shiftly/app.py` builds the FastAPI application without applying
migrations. Its lifespan opens bounded resources and checks schema readiness.
`backend/shiftly/runtime/` composes services, database resources, settings, and
provider adapters. `python server.py` remains a legacy browser runtime and does
not expose `/api/mobile`. In its default `embedded` mode it applies migrations at
startup and runs only the briefing worker in-process. Forecast jobs need the
separate worker (`python -m backend.shiftly.jobs.worker`), which processes both
briefings and forecasts. With `SHIFTLY_WORKER_MODE=external` the legacy server
only checks the schema and reads shared worker health. Never run both worker modes
against one queue.

The native application lives in `apps/mobile`. Browser HTML/CSS/JavaScript at
the repository root is a compatibility surface, not a second product authority.
Both clients use the same server policy and domain services.

## Implemented domain boundaries

```text
backend/shiftly/
  api/          HTTP parsing, credentials, authorization entry, response mapping
  core/         transport-neutral settings, errors, request and security helpers
  identity/     users, sessions, invitations, memberships and capabilities
  stores/       store lookup and selected-store behavior
  reports/      reports, briefings and weekly overview workflows/repositories
  inventory/    catalog, packages, shelves, quantities, movements and counts
  production/   recipes, production posting and reversal
  forecasts/    store forecast workflow, persistence and provider boundary
  jobs/         durable job ownership, status and worker entry point
  runtime/      composition, migrations, database resources and provider setup
apps/mobile/
  app/          Expo Router entry and navigation
  src/          API/session code, feature screens, state and shared UI
```

The reporting boundary preserves old imports through a facade:
root `reporting.py` is a compatibility facade; the real OpenAI transport and
factory belong to `backend/shiftly/runtime/provider.py`; durable briefing claim,
lease fencing, completion/failure, diagnostics, and loop behavior belong to
`backend/shiftly/jobs/reporting.py`; and the worker consumes those package
modules directly.

## Responsibility rules

- API adapters parse bounded input, authenticate, call public services, and map
  domain failures. They do not own business transactions.
- Services own workflows and transactions. Repositories own SQL and use the
  caller's connection where atomic policy and data changes must stay together.
- Every protected write rechecks actor and expected store inside its transaction.
  A client role, hidden control, object ID, or `storeId` is never authority.
- Inventory owns authoritative stock posting. Counts and production create
  immutable movements and update the balance projection atomically. Forecasts,
  camera input, and future receiving cannot write balances directly.
- PostgreSQL migrations are additive and ordered. No ORM or second identity/store
  system is planned.
- Durable commands are idempotent. A reclaimed worker lease is fenced so a stale
  worker cannot overwrite a newer result. External provider calls may repeat
  after a crash and are not exactly once.
- Blocking database and provider work must stay off the async event loop. Heavy
  or retryable work belongs in the durable worker rather than request-lifetime
  background tasks.

## Accounts and scope

All supported staff flows use individual accounts. Invitation activation grants
baseline crew authority; later role assignment is an authorized administrative
operation. Crew, production, and manager accounts have one active store. Owners
and authorized administrators may switch only within their business scope.
Production has production/inventory capabilities and no reporting capability.

Opaque native bearer sessions and browser cookies are transport forms over the
same server-side, hashed, expiring, revocable session model. Native clients clear
private state after identity or scope changes; they do not implement a parallel
permission model.

## Inventory and production flow

A business owns the shared product catalog. Stores own shelf placements, balances,
counts, movements, production logs, and forecasts. Product/package identities are
stable; archived or redirected records preserve references. Exact decimal strings
cross the API boundary and PostgreSQL `NUMERIC` values remain authoritative.

A whole-store count progresses draft -> review -> posted. Posting checks versions,
scope, completeness, and authorization, then writes movements and balances in one
transaction. Production confirmation snapshots recipe inputs, deducts recipe
quantity × batches × 1.01, and posts atomically. Reversal is explicit and
constrained by later physical counts. Forecasts read a bounded store snapshot,
compute exact facts, and ask the configured provider for structured advisory
suggestions in the durable worker. Output is validated and cannot write stock or
recipes. Full rules are in [INVENTORY.md](INVENTORY.md).

Barcode camera capture performs a lookup/catalog workflow without saving a photo.
Shelf-photo proposals, invoice receiving and offline stock posting are future
boundaries and must enter stock through reviewed inventory commands.

## Known coupling

Open findings from the 2026-09-23 architecture audit, still present in `df53f98`:

- **Identity internals.** `AccountsService` composes mixins that call each other's
  private helpers.
  - The report repository takes the account policy lock directly.
  - The store repository calls the private `accounts._audit`.
  - New modules must use the public `require_selected_store(...)` boundary and own
    their audit records instead of copying this pattern.
  - Identity value types already moved to `identity/contracts.py`.
- **Broad reads under a global lock.** The account management projection, the
  authorized-store evaluation and the unpaginated selected-store report inbox run
  under the schema-wide policy lock.
  - This is a measured-later scaling risk, not an observed outage.
  - Measure before narrowing the lock, and keep concurrent revocation guarantees.

The audit's provider/worker dependency finding was resolved on 2026-10-11. The
provider transport now lives in `runtime/provider.py`, durable jobs in
`jobs/reporting.py`, and root `reporting.py` is a facade.

## Architectural decisions

| Date | Decision |
| --- | --- |
| 2026-09-22 | React Native/Expo is the primary phone/tablet client. The browser remains a compatibility surface; no separate React web rewrite. |
| 2026-09-22 | Native clients get opaque bearer tokens over the existing session records; no JWT or second identity store. |
| 2026-09-23 | Keep the modular Python backend; no rewrite or microservice split. Inventory gets its own service/router boundary. |
| 2026-09-24 | Individual accounts only; shared crew, password-only manager login and public signup retired. |
| 2026-09-29 | A single movement ledger plus balance projection serves counts and production; production uses a fixed 1% allowance. |
| 2026-10-01 | Forecasts run as durable jobs analyzing supplied records with strict structured output; no model training. |
| 2026-10-02 | Canonical stock units stay `each`/`g`/`kg`; package labels may use pounds; volume needs an explicit net weight. |
| 2026-10-11 | [ENGINEERING.md](../ENGINEERING.md) adopted. Provider/job implementation moved out of the legacy facade. `psycopg-pool` remains the only runtime pool dependency. |

## Failure and release boundaries

Health must distinguish process/database readiness from worker progress. Private
responses use no-store behavior and security headers; logs and stored failure
diagnostics must omit credentials and private report bodies.

Local tests, browser rendering, and native exports are distinct evidence. None
proves hosted cutover, production ownership mapping, physical-device behavior,
signed-build readiness, or store publication. Preserve the browser fallback and
migration compatibility until hosted parity and rollback have been rehearsed.
