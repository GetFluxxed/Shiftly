# Codex prompt: complete services and runtime foundations

Implement the Codex lane of Round 3 in GetFluxxed/Shiftly. The goal is to finish
remaining service boundaries and runtime separation while GitHub Copilot ports
all existing HTTP/browser workflows to FastAPI. Deliver usable implementation,
regression coverage and integration evidence, not another planning-only slice.

## Checkout and authority

Fetch origin. Resolve the immutable publication commit with:

```sh
git log -1 --format=%H origin/codex/docs-integration-readiness -- docs/parallel/ROUND_03.md
```

If the user supplies its full SHA, use that instead. Create a separate worktree
on `codex/integration-services-runtime` from that commit. Preserve any existing
branch/worktree and all older uncommitted work; do not reset or repurpose them.
The code baseline is `818a03cb1bcff67c6c36a3ddbbd73a1028894dff`, with PRs #1–#4
merged and green CI. The publication commit adds only documentation.

Read `docs/parallel/ROUND_03.md`, this prompt, `README.md`,
`docs/IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/API.md`,
`docs/TESTING.md`, and all four existing workstream handoffs. This round's
ownership and gates supersede historical assignment restrictions. Treat older
baseline prose as historical, not evidence that merged code is missing.

## Exact ownership

You may edit only:

- `backend/shiftly/identity/**`, `backend/shiftly/stores/**`,
  `backend/shiftly/runtime/**`, `backend/shiftly/jobs/**`.
- `auth.py`, `security.py`, `store_service.py`, `routes.py`, `server.py`,
  `reporting.py`, `database.py`, `config.py`, limited to extraction, explicit
  composition, compatibility delegation, and runtime/resource changes.
- `requirements.txt`, `requirements-dev.txt`, `requirements.lock`,
  `requirements-dev.lock`, `.env.example`, only for required dependencies/settings.
- Optional new `migrations/013_runtime_operations.sql`, additive runtime
  coordination/heartbeat records only; first verify the number is unused.
- New `tests/identity_services/**`, `tests/runtime_services/**` and
  `docs/workstreams/codex-integration-runtime.md`.

Everything else is read-only, particularly the FastAPI app/core/API subtree,
report-service subtree, parent package markers, CI, UI, production/local existing
manifests, migrations 001–012, existing tests and `tests/conftest.py`, shared
plans, and Copilot's handoff. Do not edit a test outside your lane to fix a new
regression. Report a necessary ownership change with a reproduction and proposal.

## Milestone A: usable identity/store services, publish early

1. Extract login (auto/crew/manager), workspace signup, add-manager, session
   creation/lookup/revocation/logout, manager/store membership selection,
   manager-account listing, and Head's Up read/write. Reuse current business
   rules and SQL behind repositories. Keep current account model and sign-in
   inputs; do not add username sign-in or inventory permissions in this round.
2. Use ordinary values/results and explicit configuration, database, clock,
   token/password, provider and admission dependencies as needed. No service
   imports an HTTP framework, handler, `server.py` or `routes.py`. Token issuance
   and session persistence belong to services; cookie parsing/serialization,
   request parsing and status/header mapping belong to adapters.
3. Remove remaining `routes._server_module()` dependency lookup. Keep legacy
   public wrappers and call-time injection/monkeypatch behavior intact. Avoid
   duplicating account SQL, credential verification, rate-limit logic or report
   providers in the legacy and new paths.
4. Preserve invalid-input ordering/messages, signup/add-manager protections,
   login in-flight reservations, hashed credentials/tokens, expiry/logout,
   active-account/store/membership checks and legacy selected-store fallback.
   A body field cannot supply trusted actor/store authority. Preserve the
   membership-wide manager inbox versus session-store weekly/Head's Up split.
5. Publish a working composition entry point under `backend/shiftly/runtime/`
   with explicit injected dependencies, no construction side effects, and no
   requirement to import Copilot's app. Include report-service composition using
   the existing implementation, provider behavior, shared capacity and wake
   semantics; do not rewrite the read-only report package.
6. Add direct service tests and run the unchanged whole suite before and after
   extraction. Commit and push this useful checkpoint early. In your handoff,
   name its SHA and concrete exported callables/signatures, result/error types,
   service construction/lifetimes and a short adapter-use example. Copilot must
   be able to implement against working code rather than proposed interfaces.

## Milestone B: complete runtime separation while Copilot ports adapters

1. Provide independently runnable migration and briefing-worker commands under
   your `runtime`/`jobs` packages. Separate web startup, migrations and worker
   processing. Preserve `server.initialize_database()` as a compatibility
   wrapper for current tests and legacy fallback. The new API/worker entry paths
   must not each silently migrate on startup.
2. Serialize migration application with a database-backed lock held through
   version checks/application; bound lock waits and use transactions. Fresh,
   repeated and concurrent runs must be safe. Never rewrite old migrations.
3. Reuse the existing durable queue and processing algorithm. Keep lease-bearing
   claim IDs intact, delayed bounded retries, stale completion/failure fencing,
   sanitized errors and resilience when recording a failure also fails. A
   separate worker discovers new work through polling even without the web
   process's in-memory wake signal. Cleanly handle SIGTERM and bounded shutdown;
   demonstrate recovery after an actual process restart with disposable data.
4. Provide explicit bounded DB resources: connection/pool checkout and query/lock
   timeouts, rollback/reset and resource closure. Prefer supported small
   dependencies over inventing a pool; if adding one, update all relevant locks
   for Python 3.12 and check current official documentation/package metadata.
   Keep existing dependency pins unless a demonstrated conflict requires change.
5. Preserve the weekly repository's dedicated connection/session-lock contract.
   Either use a bounded dedicated closing connection path for weekly work or a
   pool adapter that explicitly releases advisory locks and resets state before
   reuse. Test success/failure/cancellation and contention; no transaction should
   remain open through external weekly AI generation.
6. Publish worker progress/queue-age information that a separate API process can
   read. Missing/stale heartbeats must degrade, idle polling must not pretend a
   job completed, and DB health must not fabricate worker health. Preserve the
   existing diagnostic fields and provide the provider Copilot will inject.
7. Target one API process and one independent worker first. Preserve rate limits
   and bounded AI/weekly concurrency in this supported topology, with an explicit
   constraint against unsupported multi-web-process startup. Record distributed
   admission as a later scale-out prerequisite; do not add Redis or unrelated
   infrastructure merely for anticipated replicas.
8. Keep legacy startup working for rollback, including an explicit mode that
   avoids a second embedded worker when the separate worker owns processing.
   Defaults must preserve existing tests and current deployment behavior. Do not
   change `render.yaml`, deploy, or delete the legacy transport.

## Validation and handoff

Use separately named disposable PostgreSQL 16 resources with random ports,
explicit `TEST_DATABASE_URL`, and deterministic mocked AI. Never load application
or production data/secrets. Subprocess tests must inject their own safe settings
and provider mocks; parent monkeypatches do not cross process boundaries.

Run all existing tests, contracts, Chromium flows and recovery/report-service
checks plus your new direct-service/runtime suites. Add meaningful checks for
session revocation/expiry and cross-store denial, failure rollback, concurrent
login budgets, pool exhaustion/timeouts, lock cleanup, concurrent migrations,
heartbeat staleness, worker crash/restart and claims finishing after lease loss.
Use bounded waits and cleanup. Run compilation, `pip check`, and `git diff --check`.

Record commands, versions, counts, tested SHAs, cleanup and exact interfaces in
`docs/workstreams/codex-integration-runtime.md`. Include CLI commands, required
settings, pool/connection ownership, shutdown behavior, migration/rollback
compatibility and concrete dependencies for Copilot. Do not claim FastAPI browser
parity based on your unchanged legacy-server suite. Copilot supplies final
combined transport/rehearsal evidence after consuming your final commit.

Publish milestone commits on your feature branch and prepare a draft PR against
main. Copilot may merge your published commits into its own branch, so preserve
history and keep exported interfaces stable or additive. Do not merge Copilot
into your branch, edit its files, message/dispatch work to it, or claim its
results. If PR tooling is unavailable, supply a compare link and prepared body.

Finish the owned work, report out-of-scope dependencies, and stop for integration
review. Do not push main, merge PRs, force-push, deploy, change the production
entry point, or implement inventory/camera/app-shell features. Gate D in Round 3
is the measurable condition for the coordinator to start those feature branches;
Gate P remains the additional production-release condition.
