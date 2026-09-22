# Focused development-readiness verification

Verified: 2026-09-21. Branch: `codex/focused-verification`.
Merged starting point: `e01e84ef629a3d1e04b63dd19455c3ce9b0a558c` (PR #7).
Tested implementation: `c65d13a2a695bf57d372a4d6b5c1a6cc8320450b`.
Subsequent documentation changes do not change that tested implementation.

## Result and gate status

The focused technical verification passes. The original merged baseline passed
250 tests locally, and its exact-commit [GitHub CI passed](https://github.com/GetFluxxed/Shiftly/actions/runs/35686513340).
The expanded final implementation passes **357 tests**, including Chromium
browser flows and API contracts against both legacy and FastAPI. The enhanced
release rehearsal also passes. No assertions were weakened or tests skipped.

Gate D still requires review and merge of this follow-up with green CI, because
the verification reproduced defects and this branch contains their fixes. Use
the verification PR's check results for its current hosted status. Once merged,
begin A1/A2 (manager navigation and inventory actors/permissions), then I1
(catalog, units, packs and weight profiles), on a fresh branch from current main.

Gate P remains open: hosted staging, process supervision, backup policy, required
merge-check administration and approved deployment configuration still require
separate release work. Production configuration and entry points were unchanged.

## Findings and corrections

The initial added request-edge matrix reproduced 27 failures across empty/large
body messages, Head's Up error handling and FastAPI routing defaults:

- FastAPI caught its own size-limit exception as a conversion error, returning
  the wrong message. Parse conversion and range validation are now separate.
- Login consistently uses its existing `Invalid login request.` contract.
- Malformed Head's Up writes previously disconnected the legacy client. They now
  return a controlled JSON error. Undecodable JSON uses the same invalid-format
  response as malformed JSON on both transports.
- FastAPI's trailing-slash redirects, unknown-path JSON errors and automatic
  405 responses differed from the existing client surface. Compatibility errors
  now preserve GET HTML 404, POST JSON 404 and unsupported-method 501. Automatic
  documentation routes are disabled on this surface. Explicit future routes can
  still declare additional HTTP methods; there is no global GET/POST-only filter.

Contracts use real HTTP listeners for both transports and the same service-level
provider substitutions. Tests retain pending/ready/failed weekly behavior and
add cookie attributes, account creation, expired/inactive/revoked authority,
membership-wide inboxes, selected-store writes and ignored body/query store IDs.

## Recovery and data-preservation evidence

The final rehearsal passed all of these on PostgreSQL 16.15:

1. Apply migrations 001–012, create a historical report/job/briefing, upgrade to
   013 and compare retained rows, sequences and foreign keys.
2. Apply a fresh schema to the restore database; repeat migrations and run two
   concurrent migration commands successfully.
3. Start FastAPI without a worker and observe missing-worker health. Start a
   separate worker and complete a submitted report without an in-process wake.
4. Submit another report, wait for a real worker claim, kill the process with
   SIGKILL, then recover the expired lease in a replacement process. Exactly one
   briefing exists after two attempts; original notes remain intact.
5. Observe stale-worker health and pending queue depth. Lease and heartbeat
   timestamps are advanced after the actual crash to avoid a multi-minute wait;
   the claim and crash are not simulated database states.
6. Temporarily refuse connections to the disposable source database and terminate
   its sessions. API health returns 503; the worker exits after losing ownership.
   Restore access, reconnect the API and restart the worker successfully.
7. Start the legacy application against the forward-compatible schema and read
   completed reports with the existing manager session.
8. Stop activity, create a real PostgreSQL custom archive, restore atomically and
   compare **12 durable tables, four sequences and 11 foreign keys**. Transient
   worker observations are intentionally excluded. Start the restored FastAPI,
   reuse the preserved session, sign in again and retrieve completed reports.

The suite separately verifies stale-claim fencing, single-worker ownership,
bounded shutdown, resource cleanup and provider/DB failure behavior. CI now
runs this complete rehearsal after pytest and uploads its log plus JUnit/browser
artifacts. Routine tests and child processes cannot make paid provider calls.

## Reproducibility

Local environment: Python 3.14.7, PostgreSQL 16.15 (`postgres:16-alpine`),
psycopg 3.3.5, psycopg-pool 3.3.2, FastAPI 0.141.1, Uvicorn 0.53.0 and
Playwright 1.63.0. Dependencies came from `requirements-dev.lock` in a new virtual
environment. Hosted CI uses its existing Python 3.12 runner and PostgreSQL 16.

Final full suite: **357 passed in 70.91 seconds**. Final routing/parity/rehearsal
subset: **115 passed**. Compilation, `pip check` and `git diff --check` passed.
The unmodified starting main passed **250 tests in 45.01 seconds**.

Use [TESTING.md](../TESTING.md) to create disposable resources and set the URLs.
The final local run used container `shiftly-focused-verification-db`, loopback
port 59190, and separate `shiftly_test`, `shiftly_rehearsal_final` and
`shiftly_restore_final` databases. These are recorded evidence, not persistent
application settings. Commands:

```sh
DATABASE_URL='' OPENAI_API_KEY='' SECURE_COOKIES=false \
  python -m pytest -q --browser chromium --tracing=retain-on-failure \
  --screenshot=only-on-failure --junitxml=verification.xml

DATABASE_URL='' OPENAI_API_KEY='' python scripts/rehearse_release.py
```

The first command requires `TEST_DATABASE_URL`; the second requires the two
`REHEARSAL_*_DATABASE_URL` values and native PostgreSQL tools or explicit
`REHEARSAL_SOURCE_CONTAINER` / `REHEARSAL_RESTORE_CONTAINER`. Both rehearsal
databases must be fresh and disposable; the runner temporarily disables source
connections and replaces restore-target contents.

The created database container was removed after the final checks. Test HTTP,
API and worker processes exited. Existing project worktrees and their uncommitted
files were preserved; all follow-up implementation changes are on this branch.
