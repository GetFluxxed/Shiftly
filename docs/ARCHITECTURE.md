# Shiftly architecture

Updated 2026-10-11. This is the current source boundary; delivery order lives in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), operational topology in
[DEPLOYMENT.md](DEPLOYMENT.md), and policy adoption in
[engineering-adoption](workstreams/engineering-adoption.md).

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
not expose `/api/mobile`.

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
transaction. Production confirmation snapshots recipe inputs, applies the defined
1% allowance, and deducts stock atomically. Reversal is explicit and constrained
by later physical counts.

Barcode camera capture performs a lookup/catalog workflow without saving a photo.
Shelf-photo proposals, invoice receiving/OCR, and offline stock posting are future
boundaries and must enter stock through reviewed inventory commands.

## Failure and release boundaries

Health must distinguish process/database readiness from worker progress. Private
responses use no-store behavior and security headers; logs and stored failure
diagnostics must omit credentials and private report bodies.

Local tests, browser rendering, and native exports are distinct evidence. None
proves hosted cutover, production ownership mapping, physical-device behavior,
signed-build readiness, or store publication. Preserve the browser fallback and
migration compatibility until hosted parity and rollback have been rehearsed.
