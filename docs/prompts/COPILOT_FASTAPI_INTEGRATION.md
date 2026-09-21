# GitHub Copilot prompt: full FastAPI parity and release rehearsal

Implement the Copilot lane of Round 3 in GetFluxxed/Shiftly. Codex owns the
remaining identity/store extraction, shared service composition and separate
worker/runtime. You own all FastAPI adapters, current-browser compatibility,
CI and disposable release rehearsal. Finish the existing application migration
in development; do not stop at the already-implemented health foundation.

## Checkout and authority

Fetch origin. Resolve the publication commit with:

```sh
git log -1 --format=%H origin/codex/docs-integration-readiness -- docs/parallel/ROUND_03.md
```

An explicitly supplied full publication SHA takes precedence. Start an isolated
checkout/worktree at that commit on `codex/integration-fastapi-parity`, or record
the platform-assigned branch. The code baseline is
`818a03cb1bcff67c6c36a3ddbbd73a1028894dff` with PRs #1–#4 merged and passing CI;
the publication commit adds documentation. Preserve older worktrees/branches,
including the uncommitted `codex/reports-module`; do not reset or reuse them.

Read `docs/parallel/ROUND_03.md`, this prompt, `README.md`,
`docs/IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/API.md`,
`docs/TESTING.md`, and the four existing workstream handoffs. Current Round 3
ownership supersedes historical assignments. Use actual code as the behavior
baseline; central plan baseline paragraphs still predate the merged foundations.

## Exact ownership

You may edit only:

- `backend/shiftly/app.py`, `backend/shiftly/api/**`, `backend/shiftly/core/**`.
- `tests/api_foundation/**`, `tests/contracts/**`, `tests/browser/**`,
  new `tests/transport_parity/**` and `tests/release_rehearsal/**`.
- `.github/workflows/ci.yml`, `scripts/run_api_dev.py`,
  `scripts/run_browser_tests.py`, new `scripts/rehearse_release.py`,
  new `deploy/compose.integration.yml`.
- `docs/API.md`, `docs/TESTING.md`, `docs/DEPLOYMENT.md`,
  new `docs/workstreams/copilot-fastapi-integration.md`.

All other paths are read-only. This includes root Python services, Codex's
identity/stores/runtime/jobs trees, report services, dependencies and lockfiles,
all migrations, `tests/conftest.py`, root regression tests, report-service tests,
parent package markers, all HTML/CSS/JavaScript, `render.yaml`, existing
`docker-compose.yml`, central plans/README and the other agent's handoff.
Dependency additions belong to Codex: record the package/reason there as an
integration request. Preserve every existing assertion in tests you own; extend
or parameterize rather than replacing legacy coverage with weaker API tests.

## Milestone A: begin independent coverage immediately

1. Inventory every route, static allowlist, method, request limit, validation
   order, status/error body, redirect, cookie and security/cache header in the
   current server. Include all authentication/account, report, weekly, Head's Up,
   manager listing, health, sign-in and protected-page flows. Characterize
   unsupported paths/methods too; do not silently substitute framework defaults.
2. Extend your existing transport fixtures so the same contract and Chromium
   behavior tests can run against both servers. Keep all original legacy cases.
   Begin with legacy characterization and implemented FastAPI health/report
   primitives while Codex publishes real identity/store service contracts.
3. Use injected dependencies and existing report services for independent adapter
   work. Do not emulate a handler, proxy HTTP to `server.py`, duplicate identity
   SQL/rules, or invent placeholder authentication while services are pending.

## Milestone B: consume Codex and complete all adapters

Codex publishes a working service checkpoint early on
`origin/codex/integration-services-runtime`, documented in
`docs/workstreams/codex-integration-runtime.md`. Read its actual exported APIs.
You are authorized to fetch and merge published commits from that branch into
**your feature branch**, record the exact SHAs, and build on them before main
integration. This is a dependency merge, not permission to merge PRs or push main.
Do not cherry-pick/recreate Codex code as your own or edit its files. Use a stacked
draft PR targeting Codex's branch while it remains unmerged, if supported.
Resolve conflicts only inside your ownership; report others to the coordinator.

1. Wire the services into the existing app factory with explicit injectable
   settings, repositories/resources, provider, actor/store resolution and limits.
   Preserve the current `create_app` injection surface and independent app tests.
   Lifespan opens/closes app-owned resources; imports/factory construction perform
   no DB/AI/thread work. No embedded worker or automatic migration in API startup.
2. Port these existing business endpoints completely: auth status/login/signup/
   add-manager/logout; GET and POST reports; GET and POST Head's Up; GET managers;
   GET weekly overview. Preserve both health routes and enumerate any additional
   dispatch behavior found during characterization. Business rules come from
   shared services, not copied SQL or handler calls.
3. Serve the existing sign-in/about/crew/manager pages and explicitly allowed
   assets without changing them. Preserve protected-page redirects and block
   traversal, `.env`, source files, repository content and private paths. Do not
   mount the entire repository as a public static directory.
4. Preserve malformed/non-object JSON behavior, size limits, duplicate/cooldown
   and quality rejection codes, pending weekly responses, provider failures and
   stable response fields. Deliberately map FastAPI's default 422/404/405 and
   trailing-slash behavior to the captured contract or record a specific
   coordinator decision needed; don't hide incompatible differences in tests.
5. Preserve both cookies on logout, cookie attributes and session behavior;
   auto/crew/manager login, admin-key signup/add-manager, inactive/expired/revoked
   sessions and store membership boundaries. Never derive trusted actor/store
   from submitted IDs. Preserve membership-wide reports versus selected-store
   weekly/Head's Up. Avoid unrelated login or inventory permission redesign.
6. Preserve security headers on success/errors/static/redirects and existing JSON
   cache behavior. Do not broaden CORS, camera permissions or trusted proxy
   behavior. Treat framework docs/schema exposure as an explicit surface decision
   and disable it by default if it would expose an unintended production route.
7. Keep blocking database, AI and password work off the async event loop. Enforce
   body limits before unbounded buffering. Use Codex resource/time-out/provider
   interfaces, including its safe weekly connection semantics and separately
   observed worker health; do not retain process-local fake worker progress.

## Milestone C: combined parity and disposable release rehearsal

After Codex publishes its final runtime commit, merge that exact SHA into your
branch, install the final locked dependencies, and run the combined suite.
If its branch advances again, update the integrated SHA/evidence accordingly.

1. Run unchanged baseline/recovery/report-service tests plus all new identity,
   runtime and API tests, the full two-transport contract matrix, and real
   Chromium flows on both servers. Include small-screen viewport coverage,
   signup/login/logout, original notes and completed briefs, Head's Up, weekly
   pending/ready/outage, protected static pages and cross-store negative cases.
   Test providers must be mocked; viewport coverage is not real-phone validation.
2. Extend CI for the combined suite on Python 3.12/PostgreSQL 16, with locked
   dependencies, compilation, `pip check`, meaningful browser failure artifacts,
   and a reproducible bounded runtime/release check. Do not weaken, skip or remove
   tests to hide unavailable adapters. If factoring fixtures is necessary, do it
   within your owned subdirectories, not `tests/conftest.py`.
3. Supply local disposable orchestration and a rehearsal runner using Codex's
   actual migration and worker commands. No fake worker used for release proof:
   exercise a real separate process with deterministic provider injection. Use
   distinct resources, random ports and no app/production `.env` or persistent
   application volumes. Child processes need their own fail-closed AI settings.
4. Demonstrate fresh migration, upgrade from the current schema, repeated and
   concurrent migration safety, API/worker startup, accepted report completion,
   worker termination/restart and recovery, DB outage/degraded health, graceful
   shutdown, and no duplicate stored briefing after recovery. Include pool/lock
   behavior through actual adapters, not only unit mocks.
5. Create synthetic data, back it up, restore to a second disposable database,
   validate important rows/relationships, and run application smoke checks.
   Demonstrate transport rollback to legacy on the forward-compatible schema,
   with exactly the intended worker active. Do not claim destructive schema
   downgrade or a live-host restore from this local rehearsal.
6. Keep the verified deployment shape to one API process plus one independent
   worker. Document connection/process budgets, schema readiness, health routes,
   fresh/stale worker evidence and scale-out restrictions. Keep `render.yaml`
   unchanged; provide concrete future cutover/rollback instructions and list
   external staging/hosting/review-policy requirements without provisioning them.

Use explicit `TEST_DATABASE_URL`, distinct disposable PostgreSQL resources,
random schemas/HTTP ports, mocked AI and bounded waits throughout. Clean up only
resources created for this run. Preserve a failed check's evidence and identify
its owner. A provider mock in a parent process is not a subprocess mock.

## Deliver, assess readiness, and stop

Update your API/testing/deployment docs to describe implemented behavior and
exact launch/test/rehearsal commands. Record base, all consumed Codex SHAs, final
combined SHA, changed-file ownership, versions, test counts, CI/artifact links,
cleanup, route matrix and known differences in
`docs/workstreams/copilot-fastapi-integration.md`.

Assess Round 3 Gate D (ready for feature development) and Gate P (ready for
production) separately. Never mark D complete with untested or skipped core
parity/recovery checks. Missing hosted staging access can leave P open without
pretending the local rehearsal proves it exists. Only the coordinator confirms
D after review/merge/green CI and starts new feature assignments.

Commit/push only your feature branch and prepare a draft PR. When Codex is merged,
the coordinator can retarget your stacked PR to main and verify the final diff.
If PR tooling is unavailable, give the pushed branch, comparison link and exact
prepared title/body. If the peer's required commit is unavailable, deliver the
completed independent milestone, name the blocked interface, and resume this
same branch when provided; do not wait indefinitely or fake completion.

Stop for integration review. Do not merge PRs, push main, force-push, deploy,
change the production entry point, dispatch messages/tasks to Codex, or begin
inventory, camera, sales, receiving or app-shell implementation.
