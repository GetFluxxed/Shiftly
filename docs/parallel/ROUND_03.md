# Round 3: finish compatibility and prepare feature development

Prepared: 2026-09-21. These are implementation assignments, not completion claims.

## Starting point and objective

The integrated code baseline is `818a03cb1bcff67c6c36a3ddbbd73a1028894dff`.
PRs #1–#4 are merged and its [CI passed](https://github.com/GetFluxxed/Shiftly/actions/runs/35659723156).
Worker recovery, report services, and a development FastAPI health foundation
exist. Full endpoint parity, identity extraction, and runtime separation do not.
Older baseline paragraphs in central planning files predate these changes.

Complete the next three integration steps in one coordinated round:

1. Extract remaining account/session/store services while preserving behavior.
2. Port the existing API and browser application to FastAPI and prove parity.
3. Deliver a separately runnable worker, coordinated migrations, bounded
   resources, and reproducible cutover/recovery rehearsals.

The user's priority is to begin new-feature development as soon as this is
verified. Publish useful milestones during the round; do not spend another round
only producing health scaffolding. Do not promise a completion date or bypass
checks to meet a same-day target. Inventory, camera, and app-shell implementation
are not assigned here. They receive bounded feature assignments after Gate D.

## Common immutable base

The publication branch is `codex/docs-integration-readiness`. Both agents fetch
origin, then resolve and record the same planning commit:

```sh
git log -1 --format=%H origin/codex/docs-integration-readiness -- docs/parallel/ROUND_03.md
```

Start a separate worktree/isolated checkout at that commit, which contains both
these prompts and the merged baseline. The coordinator freezes this document
until the round ends. An explicitly supplied full publication SHA takes
precedence over this lookup. If the branch/ref is unavailable, report that
specific dependency; do not guess a newer base or use the old worktree.

Preserve existing branches/worktrees and all uncommitted work. In particular,
leave `codex/reports-module` and the local historical Round 2 documents untouched.
Do not reset a branch, force-push, or discard another agent's work.

## Exclusive file ownership

These are whole-file ownership boundaries even when the allowed change is scoped.
An unlisted file is read-only. Existing shared tests are not a catch-all escape.

| Owner | Exact editable files/directories | Restrictions |
| --- | --- | --- |
| Codex | `backend/shiftly/identity/**`, `backend/shiftly/stores/**`, `backend/shiftly/runtime/**`, `backend/shiftly/jobs/**` | New framework-independent services, composition/resources, migration and worker commands; own subtree package markers only |
| Codex | `auth.py`, `security.py`, `store_service.py`, `routes.py`, `server.py`, `reporting.py`, `database.py`, `config.py` | Extraction/delegation, explicit dependencies, compatibility wrappers and runtime lifecycle only; preserve report and recovery semantics |
| Codex | `requirements.txt`, `requirements-dev.txt`, `requirements.lock`, `requirements-dev.lock`, `.env.example` | Only dependencies/settings required for this round; retain working test/browser pins |
| Codex | Optional `migrations/013_runtime_operations.sql` | Additive runtime heartbeat/coordination records only; verify number is free; no inventory or account-model redesign |
| Codex | `tests/identity_services/**`, `tests/runtime_services/**`, `docs/workstreams/codex-integration-runtime.md` | New lane-local tests/fixtures and implementation handoff |
| Copilot | `backend/shiftly/app.py`, `backend/shiftly/api/**`, `backend/shiftly/core/**` | FastAPI adapters, dependencies, security/static delivery and lifecycle integration; reuse Codex services |
| Copilot | `tests/api_foundation/**`, `tests/contracts/**`, `tests/browser/**`, `tests/transport_parity/**`, `tests/release_rehearsal/**` | Preserve existing assertions; parameterize contracts/browser flows for both transports and add coverage |
| Copilot | `.github/workflows/ci.yml`, `scripts/run_api_dev.py`, `scripts/run_browser_tests.py`, `scripts/rehearse_release.py`, `deploy/compose.integration.yml` | CI, local launch and disposable release rehearsal only; no live infrastructure changes |
| Copilot | `docs/API.md`, `docs/TESTING.md`, `docs/DEPLOYMENT.md`, `docs/workstreams/copilot-fastapi-integration.md` | Actual endpoint/test/rehearsal evidence and explicit remaining deployment gates |
| Coordinator after integration | `README.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/TASKS.md`, `docs/DATABASE.md`, this round and prompt files | Reconcile status from final combined evidence; not concurrent implementation ownership |

Both agents leave `tests/conftest.py`, all root `tests/test_*.py`,
`tests/report_services/**`, `backend/shiftly/reports/**`, existing migrations
001–012, `backend/__init__.py`, `backend/shiftly/__init__.py`, root HTML/CSS/JS,
`render.yaml`, and `docker-compose.yml` unchanged. Static pages are reused as-is.
Copilot does not edit dependency files; dependency requests go to Codex's lane.
Codex does not edit the FastAPI app or its core/API subtree.

Before each commit, audit its changed paths against the owner's allowlist.
A required unowned change needs an explicit coordinator scope decision; describe
its path, minimal reproduction and proposed fix in the handoff, then continue
independent work. No weakening assertions or silently skipping a failing route.

## Parallel execution and dependency exchange

Use branches `codex/integration-services-runtime` (Codex) and
`codex/integration-fastapi-parity` (Copilot, or the platform's assigned branch).

### Checkpoint A: service contract, early in the round

Codex first publishes a tested, usable identity/store extraction commit and
handoff. Document real exported callables, signatures, data/error types and
ownership of session tokens, selected store, membership-wide reports, credentials,
rate-limit reservations and database transactions. Provide an explicit composition
entry point under `backend/shiftly/runtime/` with injected configuration,
connection/provider/clock/limits as needed. Do not merely publish an aspirational
interface or leave adapter consumers to invent missing behavior.

Copilot starts immediately on endpoint inventory, baseline characterization,
transport-neutral clients, browser parameterization and independent report/health
adapter work. It then reads the published contract and consumes the actual
services. No fake handler objects, duplicated identity SQL, stub success routes,
or hard-coded authentication while waiting for the dependency.

### Checkpoint B: parallel completion

After A, Codex continues worker, migration and resource work without changing the
published service surface unnecessarily. Copilot completes all HTTP/static
adapters and two-transport parity. Record any additive interface revisions in the
handoff with the supplying commit SHA. Neither agent edits the other's files.

Copilot is authorized to fetch and merge **published commits** from
`origin/codex/integration-services-runtime` into its own feature branch to test
real integration before either PR merges to main. This is a dependency merge,
not approval to merge a PR or push main. Record every imported SHA; do not cherry
pick or recreate Codex changes as Copilot-owned commits. Resolve only conflicts
inside your ownership; escalate any other conflict. Use a stacked draft PR
against Codex's branch while it is unmerged, if the platform supports that.

### Checkpoint C: combined evidence

Copilot incorporates Codex's final published SHA, installs its final lockfiles,
and runs all checks and release rehearsals on the combined tree. Codex runs its
whole existing suite plus its new tests on its own final branch. Branch-local
success alone is insufficient for integration approval. If Codex changes again,
Copilot must update and rerun affected checks before claiming the combined result.

Neither agent waits indefinitely: publish completed work and the exact missing
commit/interface/tooling dependency if a peer is unavailable. Mark incomplete
checks pending and resume the same branch when the dependency arrives.

## Compatibility and resource rules

- Preserve existing routes, request/response shapes, validation order/messages,
  cookies, redirects, security headers, size limits and authorization. Explicitly
  compare FastAPI's default 422/404/405/redirect behavior with the legacy server;
  document surprising legacy behavior instead of silently changing the contract.
- Keep shared crew access and current manager sign-in behavior. Username-based
  authentication, new inventory permissions and membership administration are A2,
  not part of this compatibility migration. Never trust an actor/store in a body.
- Manager inbox membership scope and selected-store weekly/Head's Up scope differ;
  retain both. Preserve legacy sessions, inactivity/revocation and selected-store
  fallback behavior, original notes, duplicate/cooldown rules and weekly caching.
- No business service imports `server`, `routes`, FastAPI or an HTTP handler.
  FastAPI uses shared services, not an HTTP proxy or emulated legacy handler.
  Preserve legacy monkeypatch points through late-bound compatibility wrappers.
- App construction/import performs no database/AI/thread/network work. Lifespan
  manages only resources it owns. API startup does not apply migrations or launch
  a briefing worker. Blocking database/AI/password work stays off the event loop.
- Preserve the worker's bounded attempts, delayed retries, fenced claims and
  exact lease-bearing job IDs. Separate-process polling must discover committed
  jobs without relying on a web process's `JOB_WAKE` event.
- Pool checkout/connection/query waits and shutdown are bounded. Weekly advisory
  locks must release on success, exceptions and cancellation before a connection
  is reused; closing a pool context is not necessarily closing a DB session.
- The initial verified topology is **one API process and one separate worker**.
  Preserve admission/concurrency limits within that topology. Reject or clearly
  prevent unsupported multi-web-process configuration in supplied launch paths;
  shared cross-replica admission is a prerequisite for later scale-out, not an
  excuse to expand this round into distributed infrastructure.
- Health reflects the separate worker through shared progress evidence, including
  stale/missing state and queue age. Web polling cannot manufacture a heartbeat.
  Keep current health routes compatible; distinguish DB availability, schema
  readiness and worker progress. No secrets/report content in operational logs.
- No public hosting, production database access, paid AI, deployment, or production
  runtime change. `render.yaml` stays on the legacy entry point until Gate P.

## Validation and completion gates

All database checks use distinct disposable PostgreSQL 16 resources with explicit
`TEST_DATABASE_URL`, random schemas/ports, mocked AI and fail-closed provider
boundaries. Isolate subprocess environments too; inherited `.env` or test mocks
in the parent are not sufficient. Clean up only resources created for the run.

### Gate D: ready for new-feature development

Required on the final combined code, then reviewed and merged with green CI:

- Existing regression/recovery/report-service suites still pass unweakened.
- Identity/store services have direct tests; old route-to-server lookup is gone.
- All existing routes/pages work through FastAPI, with full contract/browser
  parity and store-boundary tests on both transports.
- Independent worker and migration commands work; crash/restart, lease recovery,
  duplicate execution protection, DB outage, bounded resources, shared worker
  monitoring and cleanup are demonstrated.
- A disposable rehearsal demonstrates fresh migration, upgrade from the current
  baseline, repeat/concurrent migration safety, backup/restore, FastAPI start,
  report completion across worker restart, and application rollback to legacy
  against the forward-compatible schema. No claim of destructive schema rollback.
- Final handoffs name tested SHAs, commands, versions, counts, artifacts, cleanup,
  ownership checks and remaining external gates. No unresolved data-loss,
  authorization, regression or unavailable-core-check blocker is hidden.

After Gate D, allocate A1/A2 and I1 feature branches: manager workspace navigation,
explicit identity/permissions, and item/unit/weight/shelf discovery. Inventory
commands remain dependent on verified identity/store boundaries. Manual inventory
and partial weighing precede camera counting, forecasts and receiving. Do not
call those modules implemented merely because their foundation passes.

### Gate P: ready for production cutover or feature release

In addition to D: actual staging with separate secrets/data, real hosting/process
supervision and recovery/rollback evidence, verified required CI checks/reviews,
backup policy and approved deployment configuration/costs. A local Compose
rehearsal is useful evidence, not proof that hosted staging exists. Missing host
access is a named coordinator dependency; no permission to create paid resources
or deploy is implied. Shared multi-replica limits are required before scale-out.

This distinction allows reviewed feature development after D while external
release prerequisites are completed. It does not waive production safeguards.

## Deliverables and integration order

1. Codex opens a draft PR with milestone commits and its final handoff.
2. Copilot opens a draft PR containing its changes and recorded Codex dependency
   merges, plus the final combined test/rehearsal evidence.
3. Coordinator reviews both, integrates Codex first, then retargets Copilot to
   main if necessary and verifies its remaining diff and final combined CI.
4. Coordinator updates central status documents, records whether D/P passed,
   and issues the first feature assignments only when D passes.

Both agents commit/push only their feature branch; neither merges main, deploys,
starts inventory, or dispatches messages/tasks to the other agent. If PR tooling
is unavailable, deliver the pushed branch, compare link and prepared title/body.

## Assignments

- [Codex: services and runtime](../prompts/CODEX_INTEGRATION_RUNTIME.md)
- [Copilot: FastAPI parity and release rehearsal](../prompts/COPILOT_FASTAPI_INTEGRATION.md)
