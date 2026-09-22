# Copilot FastAPI integration handoff

## Publication for integration review — 2026-09-21

The user requested publication and a PR after the diagnostic corrections.
The complete current worktree, including Copilot's adapters and the fixes below,
was byte-for-byte identical to the snapshot that passed 250 tests before this
publication-only documentation update. No additional application changes were
introduced for publication.

`origin/main` is now `5c67403a9c08707acd033de97b9eaf98667bf34c`, containing the
previous static foundation PR #5 and Codex runtime PR #6. Its tree matches the
pre-publication local HEAD `bab9d83`; incorporating this main tip changes history
only. The feature branch is `codex/integration-fastapi-parity`, with a draft PR
into `main` for review. Gate D and Gate P remain open as described below.


## Diagnostic correction — 2026-09-21

The previous checkpoint report below is historical. The runtime dependency is
now available and already merged: `bab9d83` consumes Codex final commit
`ffb61093a6dd943946d91de0f8c6b119c030a671`. Full adapters, browser parameterization
and the release runner existed as uncommitted work when this diagnosis began.
This correction preserves that work and does not claim it as a completed PR.

The user requested diagnosis and repair of Copilot's integration blockers. No
specific failure report accompanied the message, so these findings were
reproduced directly against an isolated copy of the current worktree:

1. **Health parity depended on the invoking shell.** FastAPI used an injected
   `openai_api_key="test-key"`; legacy read `OPENAI_API_KEY` from the environment.
   With the safe empty-key test invocation, the suite produced **242 passed,
   1 failed** (`test_health_has_compatible_status_and_stable_fields`). The fixture
   now sets the same fake key for both transports; all existing assertions stay.
2. **Backup/restore failed when local PostgreSQL clients were absent.** The
   fallback called `psycopg.Connection.executemany`, which does not exist. Even a
   cursor substitution would only copy selected rows, omit sequence state and
   fail to prove a real restore. The native plain-SQL path also lacked fail-fast
   SQL handling and restored into already migrated tables. Replaced both paths
   with a custom-format `pg_dump` archive and atomic, fail-fast `pg_restore`.
   Tools can run natively or inside explicitly selected disposable containers.
   Seven regression cases cover prerequisites, target identity, failures,
   timeouts, sanitized diagnostics and the container pipeline.

### Validation

- Disposable PostgreSQL 16 container `shiftly-copilot-diagnosis-db`, random
  localhost port 52616; synthetic databases only; deterministic AI in both web
  and worker children. No application `.env`, production data or paid AI.
- Isolated snapshot: `/private/tmp/shiftly-copilot-diagnosis`.
- Python 3.14.7; project pool dependency 3.3.2.
- Targeted parity/rehearsal regression tests: **16 passed in 1.23s**.
- Full combined suite including Chromium on both transports: **250 passed in
  44.37s**. No skipped or weakened assertions. Compilation and `pip check` passed.
- Full rehearsal passed: fresh/repeated/concurrent migrations, FastAPI startup,
  real separate worker, report completion, stale-job recovery, legacy startup,
  and real PostgreSQL backup/restore using the disposable container's clients.
- Additional restore validation: all **12** application/migration tables matched
  source rows exactly (live worker heartbeat excluded); **4** sequences and
  **11** foreign keys matched. The restored FastAPI process accepted manager
  login and returned both completed reports, original notes and linked briefings.
- Cleanup: the disposable database container was removed after validation. The
  temporary test environment was removed; original file backups were retained
  under `/private/tmp/shiftly-copilot-before-fix`. The older reports worktree
  retained its original tracked-diff fingerprint.

Full suite command (temporary database address is evidence, not a permanent
configuration):

```sh
DATABASE_URL='' OPENAI_API_KEY='' \
TEST_DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:52616/shiftly_test \
/private/tmp/shiftly-copilot-diagnosis-venv/bin/python -m pytest -q \
  --browser chromium --tracing=retain-on-failure --screenshot=only-on-failure
```

The rehearsal used source `shiftly_rehearsal_fixed`, restore `shiftly_restore`,
and `REHEARSAL_SOURCE_CONTAINER=REHEARSAL_RESTORE_CONTAINER=shiftly-copilot-diagnosis-db`.
The databases have different names within this one disposable container.
See `docs/TESTING.md` for a reproducible two-container invocation.

### Scope and remaining work

Only the runner, parity fixture, new backup regression tests, testing instructions
and this handoff were corrected. Application adapters, Codex runtime/service
files, shared fixtures and older worktrees were preserved. At the end of the
diagnostic correction, changes remained local with no commit, push, merge or
deployment. The subsequent user-authorized publication is recorded above.

**Gate D remains open.** This repairs two reproduced blockers, not every remaining
Round 3 requirement. Contract tests still need the full two-transport matrix;
malformed-input and unsupported-route parity need completion. The API middleware
already preserves JSON `no-store` responses. The release harness still lacks the full requested
outage/health and upgrade matrix; its stale-job setup is not itself a forced
worker-death proof. Runtime recovery tests provide separate coverage. CI wiring,
current API/deployment documentation, review and merged CI evidence remain due.
**Gate P remains open** pending hosted staging and deployment review.

## Historical independent checkpoint

## Assignment identity

- Branch: `codex/integration-fastapi-parity`
- Worktree: `/Users/getfluxxed/projects/Shiftly-codex-integration-fastapi-parity`
- Supplied baseline: `818a03cb1bcff67c6c36a3ddbbd73a1028894dff`
- Publication SHA resolved from `origin/codex/docs-integration-readiness`:
  `e55d7ea340874cabfa26c3f41bfb3ea53f4ba8b2`
- Publication commit: `Assign parallel service, FastAPI parity, and runtime integration work`

The required Codex Round 3 service checkpoint
`origin/codex/integration-services-runtime` was not published during this
implementation. The merged baseline does include the earlier framework-neutral
report services, but not the identity/store/runtime composition required for
public authentication and full endpoint parity.

## Implemented independent milestone

The FastAPI foundation now:

- preserves the existing injected health factory and worker-status behavior;
- serves only the explicit public asset allowlist:
  `/`, `/index.html`, `/about.html`, `/app.js`, `/auth.js`, `/manager.js`,
  and `/styles.css`;
- redirects `/crew.html` and `/manager.html` to `/` unless an explicit
  `page_access_provider(request, page)` dependency authorizes the page;
- rejects private, traversal, repository, and unknown paths;
- preserves security headers on public assets, redirects, and errors;
- adds transport parity tests for health fields/status, static response bodies,
  protected-page redirects, injected page access, traversal denial, and headers.

The protected-page provider is an explicit composition seam, not an
authentication implementation. No cookie parsing, identity SQL, or fake
authenticated success route was added.

## Route status

| Surface | FastAPI status |
| --- | --- |
| `GET /api/health` | Implemented and parity-tested |
| `GET /api/health/worker` | Implemented in the merged foundation |
| Public static assets | Implemented and parity-tested |
| Protected page redirects | Implemented for anonymous/default dependency |
| Protected page authorization | Blocked on Codex identity/store service |
| Auth/account/session endpoints | Blocked on Codex identity/store service |
| Reports, Head's Up, managers, weekly overview | Blocked on actor/store composition and adapter wiring |
| Legacy browser flows on FastAPI | Pending identity/store/runtime checkpoint |
| Separate worker/runtime and release rehearsal | Blocked on Codex runtime checkpoint |

No placeholder success responses were added for blocked routes.

## Changed-file ownership

Only the Round 3 Copilot allowlist was changed:

- `backend/shiftly/app.py`
- `backend/shiftly/api/**`
- `backend/shiftly/core/**`
- `tests/api_foundation/**`
- `tests/transport_parity/**`
- `.github/workflows/ci.yml` (existing compile target only)
- `scripts/run_api_dev.py`
- `docs/API.md`
- `docs/TESTING.md`
- `docs/DEPLOYMENT.md`
- this handoff

Dependencies, lockfiles, root services, report services, migrations, existing
fixtures/tests, UI files, deployment manifests, parent package markers, and
Codex-owned paths were not edited.

## Validation evidence

Environment:

- Python 3.14.7 local runtime; CI target remains Python 3.12
- PostgreSQL `postgres:16-alpine`
- Disposable database bound to `127.0.0.1:55435`
- Explicit `TEST_DATABASE_URL` and `DATABASE_URL`
- No production `.env` database, production data, or paid AI calls
- Existing Chromium browser tests retained against the legacy server

Command:

```sh
TEST_DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55435/shiftly_test \
DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55435/shiftly_test \
OPENAI_API_KEY=test-key ADMIN_SIGNUP_KEY=test-admin-key \
python3 -m compileall -q backend scripts tests

python3 -m pip check

TEST_DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55435/shiftly_test \
DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55435/shiftly_test \
OPENAI_API_KEY=test-key ADMIN_SIGNUP_KEY=test-admin-key \
python3 -m pytest -q --browser chromium \
  --tracing=retain-on-failure --screenshot=only-on-failure
```

Result:

```text
No broken requirements found.
182 passed in 24.37s
```

The disposable PostgreSQL container was stopped after validation. No release
rehearsal was claimed because the independent Codex runtime/worker checkpoint
is unavailable; a parent-process mock would not prove subprocess recovery.

## Gate assessment

- **Gate D — not complete.** Health/static parity is tested, but full
  authentication, report, browser, worker, and transport parity is blocked on
  the missing Codex identity/store/runtime service checkpoint. Coordinator
  review and merged combined evidence are still required.
- **Gate P — open.** Production still starts `server.py`; no hosted staging,
  independent worker, migration coordination, backup/restore rehearsal,
  rollback rehearsal, or deployment cutover was performed.

## Coordinator requests and next step

1. Publish and review `origin/codex/integration-services-runtime`.
2. Merge that exact SHA into this branch without recreating Codex-owned code.
3. Wire the published actor/store/session/resource interfaces into the existing
   explicit FastAPI composition seams.
4. Complete all auth/report/Head's Up/manager/weekly adapters and parameterize
   contract/browser flows for both transports.
5. Add the real subprocess release rehearsal only after Codex publishes its
   worker/runtime commands.
6. Rerun the complete suite and update this handoff with every consumed SHA.

The branch is intentionally ready for the dependency integration step and does
not claim production transport cutover.
