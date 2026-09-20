# GitHub Copilot implementation prompt: API contracts and browser CI

You are implementing the GitHub Copilot lane for GetFluxxed/Shiftly. Complete
the bounded assignment below, not the entire roadmap. Codex independently owns
worker recovery and its backend files. Do not edit those files or implement
FastAPI/inventory while this baseline test work is in progress.

## Read and establish your checkout

Read `docs/IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/TASKS.md`,
`docs/TESTING.md`, `docs/API.md`, and `docs/parallel/ROUND_01.md`.

Fetch origin and resolve the common planning commit with
`git log -1 --format=%H origin/main -- docs/parallel/ROUND_01.md`. Record the SHA.
Use an isolated checkout/worktree at that commit on
`codex/f0-contract-browser-tests`. If the platform creates its own branch name,
record that branch and use it exclusively. Preserve any existing work rather
than resetting it. Never use the shared main checkout or the older uncommitted
`codex/reports-module` worktree.

## Objective

Implement the contract-capture portion of F0 and browser/CI coverage portion of
F3 so the next FastAPI migration has a dependable compatibility baseline. This
round establishes test behavior against the existing server; it does not create
the new application, inventory screens, or a frontend rewrite.

## Your editable files

- New files under `tests/contracts/` and `tests/browser/`, including local fixtures
- `.github/workflows/`
- `requirements.txt`, plus new `requirements-dev.txt`, `requirements.lock`, and
  `requirements-dev.lock` where needed for a documented reproducible install
- New `scripts/run_browser_tests.py`, if a runner is necessary
- New `docs/workstreams/copilot-foundation.md`

Everything else is read-only, including `server.py`, `reporting.py`, all other
backend modules, migrations, current HTML/JS/CSS, `tests/conftest.py`, existing
regression tests, `render.yaml`, and central planning documents. Do not add
unneeded runtime dependencies or change provider/model settings.

## Required implementation

1. Add HTTP contract tests for existing authentication, cookies, role/store
   access, input errors, reports, Head's Up, and weekly overview behavior.
   Include malformed requests, missing/expired credentials, cross-store access,
   successful report submission, pending weekly results, partial coverage, and
   handled dependency failures. Assert documented stable fields rather than
   forbidding additive metadata or coupling tests to worker polling cadence.
2. Add browser tests of actual existing pages: crew login/submission, manager
   login/review, Head's Up, logout, weekly pending-to-ready behavior, partial
   coverage disclosure, and safe rendering of untrusted text. Include a mobile
   viewport. Clearly distinguish browser emulation from actual phone testing.
3. Use a real disposable PostgreSQL database, ephemeral HTTP ports and isolated
   test fixtures. Reuse the existing test database safety guard. Stub external
   AI and paid/network services at test boundaries; do not bypass authentication
   for the flows whose authentication is under test.
4. Extend CI to run existing Python tests plus the contract/browser suite. Make
   browser/tool versions and Python dependency installation reproducible. Keep
   browser/test packages in development dependencies where practical, and retain
   the existing runtime dependency semantics. Add useful failure artifacts
   without secrets or production data.
5. Add focused automated code/dependency checks that produce actionable results.
   Inspect merge-check enforcement if permissions allow, but record any required
   repository-settings changes for the coordinator instead of altering settings.

## Test ownership and defect handling

Do not silently fix backend/UI defects or weaken assertions to hide them. Record
each confirmed defect with a minimal reproduction, expected behavior, affected
path and requested owner action in your handoff. Finish independent passing
work. Clearly report any failing checks; do not present them as passing.

Keep fixtures local to your new test directories. If a shared-fixture change is
truly necessary, request a coordinated ownership change. Cleanup must remove
only the disposable resources created by your tests.

## Deliver and stop

Run the full existing suite and your new checks. Write
`docs/workstreams/copilot-foundation.md` with base SHA, changed files, commands,
test/CI evidence, fixture isolation, chosen dependency strategy, confirmed bugs,
remaining F3 work and any requested shared-file/settings changes.

Review the changed-file list against your allowlist. Commit only your changes,
push only your feature branch, and open a draft PR if available; otherwise give
the pushed branch and compare URL. Do not merge, push main, deploy, force-push,
or start the next phase.

After the coordinator merges Codex, merge updated `origin/main` into your branch
without rewriting published history and rerun the combined suite and browser
checks. Refer conflicts in unowned files to the coordinator. If that integration
has not happened yet, report the PR as ready for that step rather than waiting
indefinitely or merging the other branch yourself.
