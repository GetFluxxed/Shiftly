# Codex F1 report-services handoff

Prepared: 2026-09-21. Branch: `codex/f1-report-services`.
Base: `2e0e2ec6205bd874bfa1c318120786c70061f916` (both Round 1 PRs merged).
Assignment: the supplied Round 2 Codex prompt, not the historical Round 1 allowlist.

This completes the report-services slice of F1 only. The legacy server remains
the runtime entry point. No FastAPI app, endpoint cutover, authentication
extraction, independent worker, inventory, UI or deployment work is included.
Stop here for coordinator integration review.

## Changed files and ownership

- `backend/shiftly/reports/__init__.py`: service exports only.
- `backend/shiftly/reports/errors.py`: transport-independent rejection/busy outcomes.
- `backend/shiftly/reports/service.py`: input normalization, submission policy,
  quality-gated orchestration, enqueue/wakeup and manager result formatting.
- `backend/shiftly/reports/repository.py`: the existing report/job SQL and a
  store-bound weekly source/cache session.
- `backend/shiftly/reports/weekly.py`: bounded generation, source fingerprints,
  complete-report coverage, validation and cache orchestration.
- `reporting.py`: per-call composition and backwards-compatible report/weekly
  wrappers; worker/provider implementations remain unchanged.
- `routes.py`: report-specific imports and submission adapter only.
- `server.py`: report submission composition and its compatibility wrapper only.
- Three new test files under `tests/report_services/`: services, PostgreSQL
  repositories, and legacy adapter compatibility (40 checks).
- `docs/workstreams/codex-f1-report-services.md`: this handoff.

No parent package markers were created: `backend/` and `backend/shiftly/` work as
namespace packages until Copilot adds its owned markers. No other application
services, existing tests/fixtures, requirements, lockfiles, CI, migrations,
deployment/UI assets or central plans were changed. No work was sent to Copilot.

## Service interfaces

All constructors are free of I/O. The package imports no server, route, framework,
configuration loader, database singleton, authentication or provider module.
Dependencies are explicit objects/callables; there is no service registry.

| Interface | Contract |
| --- | --- |
| `prepare_report(fields)` | Returns normalized employee/shift/notes with the existing limits, validation order and messages; unrelated payload fields are ignored. |
| `ReportsRepository(connect)` | Accepts a factory returning a dedicated closing connection context manager; owns existing PostgreSQL statements and transactions. |
| `ReportsService(repository, *, cooldown_seconds, similarity_threshold, clock, wake)` | `clock()` returns Unix seconds; `wake()` is the existing worker signal callback. The repository exposes `latest_for_employee`, `enqueue`, and `for_manager`. |
| `ReportsService.ensure_submission_allowed(store_id, employee, notes)` | Enforces the unchanged store/employee cooldown and normalized similarity policy. |
| `ReportsService.queue_report(employee, shift, notes, store_id)` | Returns `(report_id, created_at)` after atomic report/job commit, then wakes the worker. This lower-level API deliberately retains legacy behavior; use `ReportSubmission` for user submissions. |
| `ReportsService.list_for_manager(manager_id)` | Returns the existing inbox dictionaries, scoped across the manager's memberships rather than only one selected store. |
| `ReportSubmission(*, ensure_allowed, quality_gate, enqueue)` | Receives three explicit callables. `submit(store_id, fields)` normalizes, checks policy, calls quality, then enqueues once and returns the saved tuple. |
| `ReportRejected` | A quality rejection before persistence; `.reason` retains the reason/fallback that the HTTP adapter returns with 422. |
| `WeeklyOverviewService(repository, *, provider, capacity, model, prompt, max_reports, max_input_chars)` | `overview(store_id)` generates/returns the selected-store cached result. `provider(report, prompt)` owns AI transport; all instances share the caller-supplied capacity gate. |
| `ReportsRepository.weekly_session(store_id)` | Context-managed, store-bound session exposing `source_rows(limit)`, `cached_result(fingerprint)`, and `save_result(fingerprint, report_count, result)`. |

Authorization stays in the adapter. These services accept trusted manager/store
IDs supplied after cookie/session checks; passing user-controlled IDs directly
would bypass that boundary. They do not authenticate by themselves. Report
payloads cannot override the supplied store. SQL preserves membership-wide inbox
access and selected-store weekly source/cache access as distinct policies.

The repository requires dedicated, closing connections, as the existing
`database.db_connection` provides. Weekly connections use autocommit and retain
a nonblocking store advisory lock until close, without holding a transaction
through provider work. A future pool adapter must explicitly preserve lock
release semantics rather than simply returning that connection to a pool.

## Legacy compatibility and preserved behavior

`reporting.queue_report`, `ensure_submission_allowed`, `database_reports`,
`normalized_notes`, `weekly_overview`, and the existing weekly helpers delegate
to the extracted implementation. `reporting.WeeklyOverviewBusy` remains an alias
to the same exception class used by the service and server. Existing report/job
function signatures and result shapes are preserved.

Composition occurs per call so replacements of `reporting.db_connection`,
`call_openai`, clock/settings, `JOB_WAKE`, and `WEEKLY_GENERATION_SLOTS` remain
effective. No replacement provider, wake event or capacity gate is constructed
inside the services. The weekly provider prompt, model-sensitive cache hash,
input bounds and coverage semantics are unchanged.

`server.routes_submit_report(handler)` now explicitly supplies the current
`server.is_crew`, `ensure_submission_allowed`, `validate_report`, and
`queue_report` dependencies. This retains all existing test/adapter replacement
points without making the report route import `server.py` for discovery.
Direct `routes.submit_report(handler)` remains supported using its legacy
module defaults; it also accepts explicit `submission` and `resolve_store`
keywords. New adapters should supply dependencies explicitly.

HTTP parsing, route dispatch, authorization, rate limits and response mapping
stay in the route. Normalization order/limits, rejection reasons, 400/401/422/429/
503 behavior, duplicate/cooldown rules and original report notes retain their
existing meaning. No general validation-policy or error-contract rewrite was
included. The current cookie/security-header/browser behavior is unchanged.

Queue creation still uses the current store-scoped `ON CONFLICT` guard and commits
the source report and pending job together. It does not adopt the old worktree's
check-before-insert approach. Worker lease-bearing IDs, claims, attempt limits,
completion fencing, failure handling, monitoring and AI transport are untouched.
An AST comparison against the base verified all 16 worker/provider definitions
unchanged; all original server definitions/startup and non-report route functions
also remain unchanged.

## Test evidence

Local environment: Python 3.14.7, pytest 8.4.2, psycopg 3.3.5, Playwright 1.63.0,
pytest-playwright 0.9.0, cached Chromium build 1243, and PostgreSQL 16.15.
Only `shiftly-f1-report-services-db` was created, using `postgres:16-alpine`,
no persistent volume and an ephemeral localhost port (55935). It was stopped
and removed after validation; application containers were untouched.

Every database check used explicit `TEST_DATABASE_URL` and the existing random
schema fixtures. `DATABASE_URL` and `OPENAI_API_KEY` were empty before tests;
fixtures supplied the scoped database and deterministic provider responses.
No application `.env` database, production data, or paid AI calls were used.

Commands (the explicit interpreter was needed because the shell PATH varied):

```sh
DATABASE_URL='' OPENAI_API_KEY='' TEST_DATABASE_URL=<disposable-dsn> \
  /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest -q \
  --browser chromium --tracing=retain-on-failure --screenshot=only-on-failure

/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m compileall -q \
  backend/shiftly/reports server.py reporting.py routes.py tests/report_services
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pip check
git diff --check
```

- Unchanged merged baseline before editing: **125 passed in 23.84s**.
- Extracted implementation with existing tests still unchanged: **125 passed in 23.59s**.
- Initial new-test run: 39 passed and one test failed because it supplied a UUID
  for an integer manager ID. Corrected only the new test to use an absent integer
  ID; no application behavior or existing assertion was changed for that failure.
- Final combined suite: **165 passed in 24.60s** (125 existing + 40 new), including
  the real Chromium flows, HTTP contracts, and all 37 worker recovery checks.
- Compilation, dependency consistency and whitespace checks passed.
- Ownership audit confirmed only assigned paths. Existing tests and fixtures
  are unchanged, not skipped or weakened.

New checks cover service calls without HTTP/SQL, injected clocks/providers and
repositories, validation/policy ordering, quality rejection/outage with no write,
trusted store selection, limits, post-commit wakeup, rollback and concurrent
duplicates, manager memberships, worker result continuity, selected-store weekly
generation/cache, capacity and session release, seven-day source expiry, and
legacy injection/status behavior. A fresh subprocess blocks imports of legacy
runtime/framework modules and thread startup while importing/constructing the
services, proving independence from pytest's already-loaded server fixtures.

A golden source fingerprint was captured from the base's pure weekly functions
before extraction and used to verify that the service consumes an existing valid
cache entry without calling AI. Configuration/source changes still invalidate it.

Hosted CI for this feature branch and Copilot's new FastAPI foundation are not
claimed as tested here. The local run is Python 3.14; integration must retain the
Python 3.12 CI gate. Chromium emulation is not real mobile-device validation.

## Older-worktree provenance

Read-only comparison used
`/Users/getfluxxed/.codex/worktrees/831c/Shift-Observer/backend/app/modules/reports/service.py`
and `repository.py`. The useful ideas retained are an explicit repository/clock,
plain normalized report values and injected service configuration. The actual
SQL/behavior was extracted from the merged Round 1 baseline, including the safer
atomic duplicate guard, bounded weekly cache and worker fixes absent in that old
version. No old server, queue implementation, unbounded weekly query, or immediate
retry expectation was copied wholesale.

The old worktree remains uncommitted and untouched. Its tracked patch SHA-256 was
`e7770a2e8cb17ec0315421b4302249c0392cb040c6db5d1231336693ee01e553`
both before and after this assignment; its untracked service/docs/tests remain.
The main checkout's three local Round 2 planning files were also left untouched.

## Remaining dependencies and integration

No blocking modification outside the allowlist was needed. Remaining boundaries:

- `routes._server_module()` remains for login/signup/add-manager workflows;
  `auth.py`, `security.py` and `store_service.py` still contain handler-oriented
  identity/admission helpers. Allocate identity extraction and those adapters
  separately; this change makes no claim that all server dependencies are gone.
- `reporting.py` remains the legacy composition/provider/worker home. Services
  accept its provider/wake/capacity through injection; future FastAPI composition
  should supply the reviewed equivalents rather than duplicate them.
- `database.py`/`config.py` resource lifetimes, explicit timeouts, pooled/session
  cleanup, coordinated migrations and worker separation remain F2 work. No schema
  migration, cache rebuild or data backfill is required for this extraction.
- Copilot owns parent package markers, the app/core/API foundation, requirements
  and CI. Its package markers must remain free of startup side effects. Include
  the new package in CI compile/import coverage after integration; ordinary
  pytest collection already includes these service tests.
- Coordinator owns updates to `docs/ARCHITECTURE.md`, `docs/API.md`,
  `docs/IMPLEMENTATION_PLAN.md` and `docs/TASKS.md`. Record only this F1 slice as
  complete; full endpoint/identity parity, staging/restore and cutover gates
  remain open.

Review and merge this branch first. Copilot can then incorporate updated
`origin/main` into its own branch and rerun the combined suite without changing
these owned files. No work was merged, force-pushed or deployed by this agent.

## Draft PR preparation

Title: **Extract report services without changing legacy workflows**

Body:

Report submission and weekly generation currently mix business rules, SQL and
server-global dependency lookup. This change moves those rules and queries into
framework-independent report services/repositories, and injects the existing
dependencies through thin legacy adapters. Existing report/weekly functions,
HTTP behavior, store boundaries, queue transactions, cache fingerprints and
worker recovery guarantees remain compatible.

Validation: 165 tests passed locally (125 unchanged baseline + 40 new), including
Chromium flows, HTTP contracts and all worker recovery tests. Direct-service
tests cover dependency isolation, rollback, duplicate races, tenant scope and
weekly caching. Compilation and dependency checks pass; no migration or new
dependency is required. See this handoff for interfaces and integration limits.
Draft for coordinator review; this completes only the report-services slice of
F1 and does not change the production entry point.

No GitHub PR connector or `gh` CLI was available, and the available browser was
confirmed signed out. Per the assignment's fallback, deliver the pushed branch,
the title/body above and this comparison link for draft creation:
https://github.com/GetFluxxed/Shiftly/compare/main...codex/f1-report-services?expand=1
