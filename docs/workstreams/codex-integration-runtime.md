# Codex Round 3 service and runtime handoff

Branch: `codex/integration-services-runtime`.
Planning base: `e55d7ea340874cabfa26c3f41bfb3ea53f4ba8b2`.
Integrated code baseline: `818a03cb1bcff67c6c36a3ddbbd73a1028894dff`.

## Published checkpoint A

Usable service checkpoint: `daef3767f3908d329c4f11ec6b4ab14b1660ce1f`, published
before runtime work so Copilot could consume the real interfaces.
Runtime code checkpoint: `1c403a807b76d3a6679fec403fca062226f15d98`.
The final documentation commit records these tested code snapshots. Both owned
milestones are complete; Gate D/P still require the combined integration and
external evidence described below.

Implemented: login/auto-role selection, workspace and manager creation, session
issuance/lookup/logout, active membership and selected-store rules, crew fallback
to a manager session, store/account lists, Head's Up, shared single-process
admission and framework-independent composition of the existing report services.
Legacy adapters delegate instead of discovering `server.py`. The retired
`routes._server_module` name remains `None` only for unchanged tests that replace
it; no path calls it, and routes no longer import the server.

Account creation now includes its first session in the same transaction as the
store/account/membership. This preserves successful responses and prevents a
failed session insert from leaving a partially created workspace or manager.
A token uniqueness failure is mapped through the existing conflict response.
Existing password hashing, report policies and AI prompts are unchanged.

## Public interface for Copilot

Import `build_services` from `backend.shiftly.runtime`:

```python
services = build_services(
    settings=settings,
    connection_factory=connect,
    provider=provider,
    weekly_connection_factory=dedicated_connect,  # optional at A; see below
    admission=admission,                         # optional, one instance per app
    clock=clock,                                 # optional Unix-seconds callable
    wake=wake,                                   # optional zero-argument callback
    weekly_capacity=capacity,                    # optional shared semaphore (2)
    session_ttl=28800,
)
```

Construction performs no database/provider work, starts no threads and does not
import server/routes/reporting/FastAPI. Build once per app so admission/weekly
capacity are shared, not once per request. The returned `Services` has:

- `identity`: `IdentityService`.
- `stores`: `StoresService`.
- `reports`: existing `ReportsService`.
- `submission`: existing `ReportSubmission`.
- `weekly`: existing `WeeklyOverviewService`.
- `admission`: `AdmissionControl` (single process).

`provider(report, prompt)` returns the existing AI dictionary. The quality prompt
and weekly prompt are supplied by composition. `connection_factory()` supplies a
transactional connection context; weekly connections must **close the underlying
session** on exit to release the repository's advisory lock. Passing a pool's
return-to-pool context as the weekly factory is unsafe. Runtime B will supply the
bounded dedicated weekly factory without changing this signature.

### Identity/session operations

- `identity.login_payload(fields, *, client_key)` normalizes login fields then
  calls `login(store_code, role, password, *, client_key)`.
- `identity.admit_account_creation(client_key, *, action="signup")` checks admin
  configuration, then atomically reserves the shared signup/add-manager budget.
  Call **before parsing the account request body**, so malformed requests retain
  legacy config/rate-limit ordering. Use action `add_manager` for that endpoint.
- `identity.signup(fields)` / `identity.add_manager(fields)` validate the parsed
  account payload and atomically create records plus session. These do not repeat
  the admission reservation; adapters must call the preflight above first.
- These three successful account/login operations return `SessionResult` with
  `role`, `token` (excluded from repr), `response` (existing JSON dictionary), and
  `ttl`. Adapters serialize the appropriate crew/manager cookie using current
  Path/HttpOnly/SameSite/Secure/Max-Age rules. Login is 200; creation is 201.
- `identity.manager_id(manager_token)` returns ID or a false value; blank,
  missing, expired, inactive or revoked sessions have no authority.
- `identity.selected_store(manager_token, manager_id)` verifies the pair and
  membership; legacy null store selection is resolved/persisted as before.
- `identity.crew_store(crew_token, manager_token="")` first resolves a valid crew
  session, then permits the existing manager selected-store fallback.
- `identity.logout(manager_token="", crew_token="")` deletes both supplied
  session hashes. Adapters must expire **both** cookies and return the existing
  authenticated-false body; never log raw session tokens.

`IdentityError` is exported from `backend.shiftly.identity`; `str(error)` is the
legacy public message. Translate `error.code` as follows:

| Code | HTTP status |
| --- | --- |
| invalid | 400 |
| unauthenticated | 401 |
| forbidden | 403 |
| not_found | 404 |
| conflict | 409 |
| limited | 429 |
| unavailable | 503 |

JSON/body parsing and its pre-existing endpoint-specific errors remain adapter
responsibilities. Unexpected database/provider exceptions are not disguised as
successful authentication. Services receive a peer identity from the adapter;
do not trust arbitrary forwarded headers or a body field for `client_key`.

### Store/report operations

- `stores.store_for_code(code)` -> `(store_id, name)` or None.
- `stores.manager_username(manager_id)` -> name or None.
- `stores.manager_accounts(store_id)` -> existing activity list.
- `stores.heads_up(store_id)` -> existing message/update dictionary.
- `stores.save_heads_up(store_id, message)` normalizes the message and returns
  the same dictionary after commit. Caller must authorize manager + selected store.
- `admission.report_limited(client_key)` consumes/checks the existing 30/hour
  submission budget, before parsing/submitting just as the legacy adapter does.
- `submission.submit(trusted_store_id, fields)` -> `(report_id, created_at)`;
  quality rejection/validation/runtime mappings are unchanged from F1.
- `reports.list_for_manager(trusted_manager_id)` retains membership-wide scope.
- `weekly.overview(trusted_selected_store_id)` retains 202 busy, bounded source,
  shared capacity, cache fingerprint and coverage behavior.

No new inventory permissions or explicit username sign-in were added. Trusted
IDs must come from session lookup, not request payloads. The framework-independent
services do not implicitly authenticate a caller's arbitrary store argument.

## Checkpoint A evidence

Local Python 3.14.7, pytest 8.4.2, psycopg 3.3.5, Playwright/Chromium, disposable
PostgreSQL 16 (`shiftly-round3-codex-db`, ephemeral localhost port 65131).
Application DATABASE_URL/OPENAI_API_KEY were empty; only TEST_DATABASE_URL selected
the disposable DB, and existing fixtures block external provider traffic.

- Before edits: **176 passed in 24.82s**.
- Extraction first full run: 174 passed, 2 failed because report compatibility
  tests replace the retired server lookup name. Retained the unused None hook;
  did not edit or weaken those tests.
- New direct-service suite: **17 passed in 2.81s**.
- Final checkpoint A full suite: **193 passed in 27.28s**, including all unchanged
  contracts/browser/recovery/report-service checks.
- Compilation, `pip check`, and whitespace checks passed.

Commands:

```sh
DATABASE_URL='' OPENAI_API_KEY='' TEST_DATABASE_URL=<disposable-dsn> \
  python3 -m pytest -q --browser chromium --tracing=retain-on-failure --screenshot=only-on-failure
python3 -m compileall -q backend/shiftly/identity backend/shiftly/stores backend/shiftly/runtime \
  auth.py security.py store_service.py routes.py server.py reporting.py tests/identity_services
python3 -m pip check
git diff --check
```

Coverage adds direct signup/login/logout, session revocation/expiry, cross-store
and forged-ID denial, legacy null-store fallback, first-session failure rollback,
concurrent admission, provider-free identity flows, report-service composition,
and isolated import/construction without HTTP or legacy runtime modules.

The temporary database remained in use after checkpoint A for milestone B.
See the final evidence/cleanup below. This checkpoint did not claim hosted CI or
FastAPI business-route parity. Copilot owns the combined transport/release
rehearsal; the coordinator owns Gate D/P integration decisions.

## Runtime checkpoint B: concrete integration interface

Import `build_runtime` from `backend.shiftly.runtime.application`:

```python
runtime = build_runtime(settings=settings, provider=optional_provider)
# Construction is side-effect-free. In lifespan, off the async event loop:
runtime.open()  # opens bounded resources, requires migrated schema; never migrates
try:
    services = runtime.services
    connect = runtime.resources.connection
    worker_status_provider = runtime.worker_status  # zero-argument callable
    readiness = runtime.schema_status()
finally:
    runtime.close()  # off the async event loop
```

`runtime.services` retains checkpoint A's public interface. A provider override
is a deterministic `provider(report, prompt)` callable; otherwise `make_provider`
binds the explicit API key/model to the existing provider transport. It does not
silently replace an explicitly empty API key with another environment key.

The current FastAPI app/core/API files are deliberately untouched. Copilot must
connect this bundle to its lifecycle/dependencies and inject the shared worker
reader. The current foundation's default health provider still observes only
its process until Copilot performs that integration. Existing factory callers
that inject fake/caller-owned connections must retain that ownership and need
not open an unrelated default pool. `build_services` remains available for those
injected contexts; `build_runtime` is the default resource-owning composition.

### Commands and startup order

With explicit environment settings and the dependencies installed, from the
repository root:

```sh
python3 -m backend.shiftly.runtime.migrate
python3 -m backend.shiftly.jobs.worker
```

Run the worker as its own supervised process. Run the coordinated migration once
before starting the new API/worker instances. Neither the worker command nor
`ApplicationRuntime.open()` applies migrations; both refuse an unready schema.
The CLI settings are resolved using `load_settings(load_env=False)`, with database
connections/provider credentials explicitly passed to queue processing.

For the legacy web server alongside that worker:

```sh
SHIFTLY_WORKER_MODE=external python3 server.py
```

That mode checks schema readiness, does not launch its embedded worker, and reads
shared worker health. Default `embedded` mode keeps existing startup behavior,
including migration compatibility and the old worker diagnostics. Stop the
embedded worker before switching to a separate worker; do not run both modes
against the same live queue. No production entry point or manifest was changed.

`server.initialize_database()` remains a compatibility wrapper and respects the
configured migration lock timeout. A schema-scoped PostgreSQL transaction advisory
lock covers migration version checks, all SQL and version recording. A failed
upgrade rolls back that batch. Repeated and concurrent commands were tested with
actual independent processes. Migration 013 only adds `runtime_worker_status`;
account/report/queue schemas and migrations 001–012 are unchanged. The addition
can remain for application rollback; do not remove migration 012 recovery state.

### Resource and shutdown contracts

| Setting | Default | Meaning |
| --- | --- | --- |
| `WEB_CONCURRENCY` | 1 | Any other value is rejected by the new resource/service composition |
| `DB_POOL_MAX_SIZE` | 4 | Maximum pooled regular connections per resource-owning process |
| `DB_POOL_TIMEOUT` | 3 seconds | Pool checkout/startup and dedicated-capacity wait |
| `DB_CONNECT_TIMEOUT` | 5 seconds | libpq connection timeout |
| `DB_STATEMENT_TIMEOUT_MS` | 10000 | Server-side statement timeout |
| `DB_LOCK_TIMEOUT_MS` | 2000 | Query/migration lock wait |
| `DB_IDLE_TRANSACTION_TIMEOUT_MS` | 30000 | Idle transaction timeout |
| `SHUTDOWN_TIMEOUT` | 5 seconds | Worker join deadline and pool-close wait, separately |
| `WORKER_STALE_SECONDS` | 60 | External-reader maximum age of worker activity |
| `SHIFTLY_WORKER_MODE` | embedded | Legacy-only startup choice; use external alongside the separate worker |

`DatabaseResources(settings)` starts no threads or connections until `open()`.
Its `connection()` is a pooled transactional context with commit/rollback and
session reset (`DISCARD ALL`) before reuse, including advisory locks and temporary
state. Automatic prepared statements are disabled to keep that reset consistent.
Caller-supplied DSN options, notably disposable-schema search paths, are preserved.
Invalid/nonfinite/nonpositive budgets fail validation before database activity.

`weekly_connection()` is a **dedicated closing** context, bounded to two sessions
and a timed capacity wait. Weekly AI work remains outside a transaction while
holding its store lock; success, exceptions and cancellation close the physical
connection and release it. Do not replace this with the regular pool context.
The worker uses one such dedicated session for its singleton ownership lock.
At defaults, budget up to six connections for the API and five for the worker,
plus a temporary migration connection; ordinary observed usage is lower.
Legacy request handlers retain dedicated connections with the new timeouts rather
than silently gaining a global pool.

`psycopg-pool==3.3.2` is the only added dependency. It supports Python >=3.10,
including the Python 3.12 CI target, according to its
[package metadata](https://pypi.org/project/psycopg-pool/3.3.2/).
Implementation uses its documented explicit-open, bounded checkout/close, and
reset interfaces: [Psycopg pool reference](https://www.psycopg.org/psycopg3/docs/api/pool.html).
`requirements-dev.txt`/`requirements-dev.lock` already include their runtime
counterparts, so the new dependency is inherited without duplicated pins or
unrelated dependency churn. Existing pins were retained.

The separate worker holds a database session lock so a second separate worker
fails to start. Loss of that connection stops processing and exits for supervisor
restart. The same queue claim/complete/fail implementation now accepts optional
injected connection/model arguments; existing signatures/callers still work.
`worker_loop` adds optional dependencies and retains the same retry/fencing logic.
Exact `ClaimedJobId` objects are passed through, never stripped to plain integers.
Committed jobs are discovered by polling even with no shared `JOB_WAKE` event.

SIGINT/SIGTERM stop new polling and allow a bounded join. If a provider remains
blocked beyond the budget, the command exits nonzero and leaves its claim for
lease recovery. Pool cleanup has its own bounded wait; configure supervisor
termination grace for those combined budgets and database timeouts. The working
thread is daemonized so a stalled provider cannot keep the process alive after
main returns. `run_worker()` is a process entry function: callers must let a
shutdown failure terminate the process rather than catch it and keep hosting work.

### Shared diagnostics

`DatabaseWorkerStatus(connection_factory, *, stale_seconds=60)` is callable and
also exposes `.snapshot()`. It preserves `status`, `state`, `running`,
`lastPollAgeSeconds`, `lastCompletionAgeSeconds`, `completedJobs`, and
`consecutiveErrors`; it adds `lastActivityAgeSeconds`, `queueDepth`, and
`oldestQueuedAgeSeconds`. Counts are per worker instance, not lifetime job totals.
Queue depth excludes terminal work; age measures outstanding queue residence.

Only the worker writes observations; reader calls cannot refresh them. Database
clock timestamps allow different processes to agree about age. Missing/stopped/
backoff/stale workers and unavailable storage degrade rather than appear healthy.
Idle polling does not increment completed jobs. New instances fence older status
writers, and a lost ownership connection cannot publish an initial registration
on top of its replacement. Publication failures log a fixed sanitized diagnostic
without terminating queue processing or refreshing the persisted timestamp.

`schema_status(connection_factory)` supplies `status`, `schemaReady`, and
`pendingMigrations`; `require_schema` rejects missing migration state. Copilot
should preserve the existing DB-based `/api/health` 200/503 semantics while exposing
schema readiness separately/additively and using the shared worker provider for
`/api/health/worker`. Successful DB probes never imply worker progress.

## Final validation and preservation evidence

Validated runtime code is published as
`1c403a807b76d3a6679fec403fca062226f15d98`; checkpoint A is
`daef3767f3908d329c4f11ec6b4ab14b1660ce1f`. The later handoff-only commit does not
change the tested application. Local toolchain:

- Python 3.14.7, pytest 8.4.2, psycopg 3.3.5, psycopg-pool 3.3.2.
- FastAPI 0.141.1, Uvicorn 0.53.0, Playwright 1.63.0, pytest-playwright 0.9.0.
- PostgreSQL 16.15 in a separately named `postgres:16-alpine` container.
- Additional dependency installed only in a disposable virtual environment;
  existing global packages were not changed.

Evidence:

1. Unchanged base: 176 passed; service checkpoint: 193 passed.
2. Runtime resource/migration/status tests initially: 28 passed in 3.23s.
3. Actual worker subprocess tests: 7 passed in 4.56s.
4. Combined runtime suite first full run: 230 passed in 35.19s.
5. Final run after making the legacy migration wrapper honor its configured
   lock budget and adding that regression: **231 passed in 35.49s**.
6. Compilation, installed-dependency consistency, whitespace and ownership checks
   passed. All 176 pre-existing cases/fixtures remained unchanged and unweakened.
   The 55 additions comprise 17 identity/store and 38 runtime cases.

The final command used the disposable environment's interpreter:

```sh
DATABASE_URL='' OPENAI_API_KEY='' TEST_DATABASE_URL=<disposable-dsn> \
  python3 -m pytest -q --browser chromium --tracing=retain-on-failure --screenshot=only-on-failure
python3 -m compileall -q backend server.py auth.py security.py store_service.py \
  routes.py reporting.py database.py config.py tests/identity_services tests/runtime_services
python3 -m pip check
git diff --check
```

New runtime checks cover pool exhaustion/reuse, rollback and session reset,
statement/lock timeouts, actual connection termination/replacement, dedicated
capacity, weekly success/error/cancellation/lock contention, clean construction,
invalid topology/settings, explicit provider configuration, fresh/repeated/
concurrent migration including two real CLI processes, atomic migration failure,
upgrade preservation, schema refusal, shared heartbeat fencing/staleness,
sanitized outage diagnostics, queue age, and legacy external-worker startup.

Real worker processes used explicit disposable DSNs and provider doubles with
outbound provider transport blocked inside each child. Checks demonstrate
completion without a web wake event, graceful termination, hard kill during a job,
restart after lease expiry, rejection of the old result with only one persisted
briefing, singleton enforcement, lost ownership exit, and bounded shutdown during
a blocked provider. No paid AI calls or application/production data were used.

The disposable database contained **zero leftover test schemas** after the final
run. It was then stopped/removed; worker/server subprocess fixtures terminated
their processes. Existing application containers were untouched. The temporary
virtual environment was removed after collecting versions/dependency evidence.
The implementation worktree is retained at
`/Users/getfluxxed/projects/Shiftly-codex-integration-services-runtime`.

The old `codex/reports-module` tracked patch fingerprint remained
`e7770a2e8cb17ec0315421b4302249c0392cb040c6db5d1231336693ee01e553`.
Its untracked work and the main project's three historical Round 2 local drafts
remain untouched. Ownership was audited against the explicit planning base:
37 changed paths, all within the assigned allowlist. The publication README and
Round 3 plan/prompts are inherited base commits, not implementation edits; if not
yet merged, the coordinator can merge/review that documentation branch first to
make the main-targeted implementation PR diff contain only this lane's work.

## Remaining integration dependencies and readiness

No out-of-allowlist implementation modification was required. Remaining owners:

- **Copilot:** `backend/shiftly/app.py`, `backend/shiftly/core/**`, and
  `backend/shiftly/api/**` must consume these real services/resources and the
  shared worker reader. Preserve the existing injection surface, HTTP contracts,
  security/cookies and authorization; perform blocking setup/cleanup off the
  event loop. Current application/browser tests here still target legacy HTTP.
- **Copilot:** its scripts/CI/rehearsal files must use the actual migration and
  worker commands, explicit safe subprocess providers, and one API process. Merge
  this final published lane into its branch and rerun all combined checks,
  two-transport browser/contract parity, backup/restore and transport rollback.
  Our restart and migration tests do not substitute for its complete rehearsal.
- **Coordinator:** update central status/API architecture/backlog documents from
  combined reviewed evidence. Verify hosted staging, backup policy, supervision,
  required merge checks/reviews and cutover approvals before production changes.
- **Scale-out:** login/submission admission and weekly capacity remain process
  local by design. `WEB_CONCURRENCY` values other than one are rejected by the
  new composition. Copilot must also pin the ASGI launcher to one worker and keep
  deployment replicas at one; this configuration guard is not distributed API
  instance admission. Shared limits are required before enabling scale-out.

This branch completes the assigned Codex services/runtime work. **Gate D is not
claimed** until Copilot's combined parity/rehearsal passes, both changes are
reviewed/integrated and CI is green. **Gate P is not claimed**: no live staging,
production deployment, real-device test or production restore was performed.
Hosted Python 3.12 CI remains an integration check; local evidence is Python 3.14.

## Draft PR preparation

Title: **Complete identity services and separate the durable worker runtime**

Body:

Existing account/store workflows still depend on HTTP handlers and server globals,
while the briefing worker and migrations start inside the web process. This
change extracts injectable account/session/store services, preserves legacy
adapters, and adds explicit migration/worker commands and a resource-owning
runtime bundle for the FastAPI integration lane.

The runtime adds bounded pooling with dedicated closing weekly sessions,
transaction-locked migrations, shared worker progress/queue-age diagnostics,
single-worker ownership and bounded shutdown. Existing delayed retries and
fenced claims remain intact. Migration 013 is additive. Account creation now
rolls back its first session, membership and account together on failure.
Default legacy startup and production deployment configuration remain unchanged;
external-worker mode supports the forthcoming transport cutover and rollback.

Validation: **231 local tests passed** (176 unchanged plus 55 new), including
Chromium flows, existing HTTP/recovery/report-service checks, direct identity
services, real worker kill/restart/lease fencing, competing workers, connection
loss, resource bounds and concurrent migration processes. Compilation, pip check,
whitespace and ownership audits passed. All databases were disposable and AI
mocked. See this handoff for interfaces, runtime settings and exact evidence.

Draft for integration review. Copilot still owns complete FastAPI adapter/browser
parity and the combined release rehearsal; this PR does not claim production
readiness, merge approval, deployment, or inventory implementation.

No GitHub PR connector or `gh` CLI was available in this environment. Per the
assignment's fallback, the branch is pushed with the prepared title/body above:
[Create the draft PR](https://github.com/GetFluxxed/Shiftly/compare/main...codex/integration-services-runtime?expand=1).
