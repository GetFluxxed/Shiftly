# Codex implementation prompt: worker recovery

You are implementing the Codex lane for GetFluxxed/Shiftly. Complete the bounded
assignment below, not the entire roadmap. GitHub Copilot is independently adding
API/browser tests and CI; obey the exclusive ownership rules to avoid conflicts.

## Read and establish your checkout

Read `docs/IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/TASKS.md`,
`docs/TESTING.md`, `docs/API.md`, and `docs/parallel/ROUND_01.md`.

Fetch origin. Resolve the common planning commit with
`git log -1 --format=%H origin/main -- docs/parallel/ROUND_01.md`, record its SHA,
and create an isolated worktree on `codex/f0-worker-recovery` at that commit.
If that branch/worktree already exists, inspect and preserve it instead of
resetting it. Do not work in the shared main checkout. The old
`codex/reports-module` worktree is read-only and must retain its uncommitted work.

## Objective

Implement the worker-recovery part of F0 while preserving existing report,
authentication, and browser behavior. Do not start FastAPI or inventory yet.

The known failure is in `reporting.worker_loop`: when processing fails and
`fail_job` also raises, the worker exits. A database-only health check can later
appear healthy even though no worker processes jobs.

## Your editable files

- `reporting.py`
- `server.py`, limited to worker startup/status integration
- New `tests/test_worker_recovery.py`
- Optional new `migrations/012_briefing_job_recovery.sql`, only if durable retry
  scheduling requires it and 012 is still unallocated
- New `docs/workstreams/codex-foundation.md`

All other files are read-only. In particular, do not modify requirements,
workflows, shared test fixtures, existing regression tests, UI files, other
services, deployment configuration, or central planning documents. Put any
needed cross-file proposal in your handoff for the coordinator.

## Required implementation

1. Add a deterministic failing regression for the nested-failure termination.
   Demonstrate recovery after database/provider failures, including inability to
   persist the initial failure, without an uncontrolled retry loop.
2. Keep processing alive through transient failures; implement bounded attempts,
   delayed retry/backoff, and expired-job recovery that remains correct after
   process restart. Distinguish terminal/rejected work from retryable failures.
3. Preserve atomic report/job creation, existing completion behavior, duplicate
   protection, and the current callable job/report interfaces. Do not reset
   attempts indefinitely or double-complete a job after lease recovery.
4. Add sanitized structured diagnostics and meaningful worker progress/status.
   Do not log secrets or raw report notes. Preserve `/api/health` compatibility;
   any worker-status surface is additive and must not falsely claim progress.
5. Keep this round compatible with the current single web-process startup.
   Independently deployed workers and the FastAPI lifecycle belong to later F2.
6. Inspect the older worktree read-only and record any useful worker/service
   work for later comparison. Do not copy its old server wholesale or merge it.

## Validation

Use only an explicitly configured disposable `TEST_DATABASE_URL`; do not use
the application database. Stub paid AI/network calls. Run the existing suite
and meaningful new tests for nested failures, eventual recovery, delayed retry,
terminal attempts, lease reclaim, duplicate completion, and status behavior.
Prefer injected clocks/events over long real-time sleeps. Test migration upgrade
and repeated startup if adding 012. Release all temporary processes and databases.

Do not change existing tests merely to accommodate a regression. If a needed
change is outside your allowlist, report the exact dependency and continue
unblocked work rather than editing another owner's files.

## Deliver and stop

Write `docs/workstreams/codex-foundation.md` with base SHA, changed files,
behavior before/after, test evidence, migration implications, remaining issues,
older-worktree findings, and any requested shared-file changes. Be explicit that
this completes only the assigned F0 portion, not all Phase 0 gates.

Review your changed-file list against the allowlist, commit only your changes,
push only `codex/f0-worker-recovery`, and open a draft PR if tooling is available.
Otherwise provide the pushed branch and compare URL. Do not merge, push main,
deploy, force-push, or start the next phase. Return the PR/commit, test results,
and anything needed from the coordinator for integration.
