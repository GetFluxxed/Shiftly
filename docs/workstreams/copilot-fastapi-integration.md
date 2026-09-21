# Copilot FastAPI integration handoff

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
