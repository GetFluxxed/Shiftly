# Codex F0 worker-recovery handoff

Date: 2026-09-20. Branch: `codex/f0-worker-recovery`.
Base: `eca1c71a26e53e69abf47c2a3e321ab1ab2de3fe`, matching the planning commit
resolved from fetched `origin/main` and `docs/parallel/ROUND_01.md`.

This completes the assigned worker-recovery portion of F0 only. It does not
complete all F0/F3 or Phase 0 gates. Stop here for integration review; no merge,
main push, deployment, FastAPI, inventory, or independent worker service.

## Ownership and changes

Exactly these five files belong to this change:

- `reporting.py`: durable retries, bounded claims, lease fencing, nested-failure
  recovery, structured diagnostics, progress observations, cooperative stop.
- `server.py`: additive worker status and embedded-thread startup/shutdown only.
- `migrations/012_briefing_job_recovery.sql`: new recovery metadata table.
- `tests/test_worker_recovery.py`: 37 worker regression/integration checks.
- `docs/workstreams/codex-foundation.md`: this evidence and review handoff.

No shared fixtures, existing tests, requirements, workflows, UI, other services,
central plans, or older migrations were edited. Migration 012 was unallocated
in the fetched origin at the start of this assignment.

## Before and after

Previously, an exception in `fail_job` escaped the worker's error handler and
terminated the thread. Failed jobs retried immediately; expired processing jobs
could exceed three attempts. A reclaimed job had no fencing against late writes.

The worker now catches failures while recording another failure, logs sanitized
codes, and keeps polling. Outage backoff is 2, 4, 8, 16, then 30 seconds maximum;
report-submission wakeups cannot bypass that pause. A stop signal can interrupt it.
Per-job retry eligibility is persisted in PostgreSQL: 30 seconds after the first
failed attempt, 60 after the second, and no automatic retry after the third.
Attempts are never reset. Claiming uses row locks with `SKIP LOCKED`.

Five-minute leases survive process restarts. Crashed final attempts are finalized
in bounded cleanup batches of 100. Completion and failure writes require the
current, unexpired lease and a processing job. An old worker, duplicate completion,
or an ambiguous commit acknowledgment cannot overwrite a newer attempt or reopen
a completed job. Briefing insertion and job completion remain one transaction;
the existing unique report/briefing protections and atomic report/job creation
remain intact. Original report notes are preserved.

Explicit briefing rejections, missing configuration/report errors, non-transient
provider 4xx responses, and database constraint errors are terminal. HTTP
408/409/425/429 and 5xx responses, transport errors, database operational errors,
and invalid/unknown processing results receive bounded retries. Provider wrappers
retain their existing RuntimeError-compatible API; classification inspects typed
causes, never raw exception text. New saved errors/logs contain only fixed codes
or a fixed rejection message, not provider reasons, SQL detail, notes or secrets.

### Callable compatibility and ownership

`claim_job()` still returns `(job_id, report_id)` or `None`; `job_report`,
`complete_job(job_id, report, briefing)`, and `fail_job(job_id, error)` keep their
argument lists. The returned job ID is an `int` subclass carrying its lease token
and attempt. Existing unpacking, integer comparison, SQL and JSON use work.
Pass that exact claim ID to completion/failure; converting it to a plain integer
or reconstructing it from storage loses ownership and safely returns `False`.
This deliberately prevents unfenced writes. Completion/failure return `True`
only for a committed transition; stale, duplicate and bare IDs return `False`.
All existing callers/tests continue to pass unchanged. A future independently
serialized worker interface must explicitly carry the lease token.

## Worker status contract

The legacy `/api/health` status code and stable fields retain their database
semantics: 200 for a reachable database, 503 otherwise. An additive `worker`
object reports actual process-local observations. `GET /api/health/worker`
returns that object directly, with 200 only for a worker recently polling or
processing; unstarted, starting, stopped, backing-off or stalled workers get 503.

Fields: `status`, `state`, `running`, `lastPollAgeSeconds`,
`lastCompletionAgeSeconds`, `completedJobs`, `consecutiveErrors`. Ages use a
monotonic clock. Sixty seconds without observed activity is stalled; a thread
stuck in a database/provider call cannot manufacture a heartbeat. Empty queue
polling is healthy but does not increment completion counts. Rejections, lost
leases, and unacknowledged commits do not claim a completed briefing. Counts are
local to this process, not a durable queue total. No job/store IDs or notes are
exposed through the public status surface.

Startup remains one web process plus one worker thread. The HTTP listener binds
before worker start. Normal shutdown signals the thread and waits up to five
seconds; uncompleted work remains reclaimable after lease expiry.

## Migration and rollout implications

012 adds `briefing_job_recovery`, keyed by the existing job ID with cascading
deletion, and stores the lease token, next retry time, and terminal marker. It
leaves every existing report/job/briefing row and status vocabulary unchanged.
Metadata is initialized lazily in the claim transaction. Existing failed jobs
without metadata use `finished_at` (or `created_at`) plus the same exponential
delay and three-attempt cap. Old rejected jobs cannot reliably be distinguished
from old transient failures; those legacy failures retain bounded retry behavior.
Historical error strings are not rewritten by this migration.

Apply migrations before running the new worker; the existing startup path does
so. Migration startup is repeatable and tested against pre-012 data, including
pending, delayed/due failed, stale processing, exhausted, and completed jobs.
Stop the old embedded worker before starting this version. Do not mix old and
new workers: older code ignores the terminal/retry metadata and fencing. The
schema addition can remain during rollback, but rolling back worker code loses
these guarantees; stop processing and plan forward recovery instead of running
an old worker over the live recovery queue. No migration/deployment was performed
against application or production data during this assignment.

## Validation evidence

Environment: Python 3.14.7, pytest 8.4.2, psycopg 3.3.5, disposable PostgreSQL 16
from `postgres:16-alpine`. The dedicated container was
`shiftly-f0-worker-recovery-db`, bound only to a random localhost port, with no
persistent volume. It was stopped/removed after testing. Existing application
containers were untouched. Tests used explicit `TEST_DATABASE_URL`, random
per-test schemas, and empty application DB/API-key environment overrides. The
shared fixtures block external AI/network transport; all AI results were mocked.
Fresh subprocess checks only claim database work and have an empty API key.

1. Before modifying the worker, ran the deterministic nested-failure test against
   the planning baseline: **1 failed**. The traceback showed `fail_job` raising
   `psycopg.OperationalError` out of `worker_loop` before a second claim.
2. After the fix, that same regression passed. The initial combined run passed
   **79 tests**, preserving the original 78 unchanged.
3. Expanded recovery run: **33 passed in 4.94s**.
4. Final combined run: **115 passed in 14.44s** (78 existing + 37 new).
   Command: `DATABASE_URL='' OPENAI_API_KEY='' TEST_DATABASE_URL=<disposable-dsn> python3 -m pytest -q`.
5. `git diff --check` passed; changed paths were checked against the allowlist.

New checks cover nested processing/persistence outages, eventual completion,
outage backoff, sanitized error classes, increasing durable delay, terminal
rejections, attempt exhaustion, fresh-process retry and lease recovery, expired
and stale writers, concurrent claims and duplicate completion, transaction
rollback, lost commit acknowledgment, progress versus polling, stalled/starting
status, additive real-HTTP health responses, cooperative shutdown, upgrade data
preservation, and repeated migration startup. Time is advanced through database
timestamps/injected waits or a fake monotonic clock, without long sleeps.

Hosted CI and Copilot's contract/browser suite have not been run on this branch.
Their Python 3.12 matrix remains an integration check; the local result above is
Python 3.14. No live AI evaluation, staging rollout, or production verification
is claimed.

## Older worktree comparison

Read-only inspection of `/Users/getfluxxed/.codex/worktrees/831c/Shift-Observer`
(`codex/reports-module`, base `b289865`) found uncommitted report repository/service
extraction, injectable AI client/service boundaries, and useful provider transport
and HTTP-to-worker tests. Its server retains the same nested-failure bug,
immediate retries and unfenced completion, so it is not a worker fix to port.
Its report/AI handoffs record 38/71-test milestones from that older baseline;
those are historical claims, not fresh test results from this assignment.

Later service extraction should compare `backend/app/modules/reports/`,
`backend/app/modules/ai/`, `tests/test_ai_client.py`, and
`tests/test_reports_module.py` deliberately. In particular, its worker retry test
expects immediate retry and a raw provider error string; retain the useful flow
coverage while reconciling those obsolete expectations. Do not merge its server
or duplicate queue/AI implementations wholesale. No files in that worktree were
modified, staged, committed, reset or removed. Its tracked patch fingerprint at
handoff inspection was SHA-256
`e7770a2e8cb17ec0315421b4302249c0392cb040c6db5d1231336693ee01e553`;
its untracked module/test/docs work remains present.

## Integration dependencies and remaining work

No blocking shared-file modification is needed for this assignment. Coordinator
follow-ups, outside this branch's ownership:

- `docs/API.md` and `docs/DATABASE.md`: document the additive worker status and 012
  recovery table/claim-handle contract after integration.
- `docs/IMPLEMENTATION_PLAN.md`, `docs/TASKS.md`, `docs/ARCHITECTURE.md`: record only
  this assigned F0 portion as complete; retain staging/restore, contracts/browser,
  CI/review enforcement and future service/worker lifecycle gates.
- `.github/workflows/ci.yml` and Copilot's owned contract/browser tests: run the
  combined result on the intended Python matrix. No CI/fixture edits requested
  here, and no work was sent to the other agent.
- `database.py` and `config.py` in F2: add explicit connection/statement timeouts
  and the planned bounded resource lifecycle. Existing database calls can block;
  this change detects stalled progress but cannot safely kill a Python thread.
- Monitoring configuration (including `render.yaml` if selected by the
  coordinator): consume `/api/health/worker` for worker alerts. The legacy DB-only
  health status is intentionally compatible and is not a worker readiness gate.

Terminal/manual replay controls, queue-age metrics, independent supervision,
lease renewal for longer tasks, and distributed status remain future work.
Provider execution is at least once across crashes; persistence is fenced and
idempotent, but an expired/crashed attempt can cause another paid generation in
real deployment. Current work makes no exactly-once provider guarantee.

## Draft PR preparation

Title: **Keep briefing workers alive with durable retries and lease recovery**

Suggested body:

When briefing generation fails and recording that failure also fails, the worker
currently exits. This change preserves processing through nested failures, adds
durable 30/60-second retries with a three-attempt cap, and fences late writes after
five-minute lease recovery. Migration 012 adds a separate recovery metadata table
without changing existing report/job rows. Worker diagnostics are sanitized and
progress is exposed additively while preserving the legacy health contract.

Validation: 115 tests passed locally with disposable PostgreSQL and mocked AI,
including the unchanged 78-test baseline, fresh-process recovery, concurrent
completion, upgrade/repeated startup, and HTTP worker status. The initial crash
regression failed before the fix. Changes stay within the five assigned files.
See `docs/workstreams/codex-foundation.md` for migration/rollout limitations and
coordinator follow-ups. Draft for integration review; do not merge or deploy yet.

PR creation tooling was unavailable at preparation: no GitHub connector or `gh`
CLI, and the available browser was signed out of GitHub. Per the assignment's
fallback, the pushed feature branch and this prepared draft are delivered with:
https://github.com/GetFluxxed/Shiftly/compare/main...codex/f0-worker-recovery?expand=1
