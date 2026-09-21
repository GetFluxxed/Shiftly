# GitHub Copilot foundation handoff

## Assignment identity

- Branch: `codex/f0-contract-browser-tests`
- Worktree: `/Users/getfluxxed/projects/Shiftly-codex-f0-contract-browser-tests`
- Common Round 1 base: `eca1c71a26e53e69abf47c2a3e321ab1ab2de3fe`
- Base resolution command: `git log -1 --format=%H origin/main -- docs/parallel/ROUND_01.md`
- Scope: API compatibility tests, browser coverage, and reproducible CI

The application, migrations, current UI assets, shared fixtures, existing
regression tests, and Codex-owned worker files were treated as read-only.

## Changes

- Added HTTP contract fixtures and tests under `tests/contracts/` covering:
  - malformed login and invalid roles
  - manager and crew cookies, status, logout, and expired sessions
  - store isolation
  - report submission and handled malformed input
  - Head's Up visibility
  - weekly pending, ready, partial coverage, and provider failure responses
- Added Playwright fixtures and browser flows under `tests/browser/` covering:
  - mobile viewport crew login, submission, and logout
  - manager review and safe rendering of employee-controlled text
  - manager Head's Up editing and crew visibility
  - weekly pending-to-ready behavior and partial coverage disclosure
- Added `scripts/run_browser_tests.py` for a pinned Chromium test command.
- Added `requirements-dev.txt`, `requirements.lock`, and
  `requirements-dev.lock`.
- Extended `.github/workflows/ci.yml` with pinned installation, Chromium setup,
  compile and dependency checks, the contract/browser suite, and failure
  artifacts.

No application implementation files were changed.

## Isolation and test doubles

- Every database test depends on the existing `isolated_database` fixture and
  therefore uses a random disposable PostgreSQL schema selected only through
  `TEST_DATABASE_URL`.
- Contract and browser fixtures start `ThreadingHTTPServer` on an ephemeral
  loopback port.
- Provider calls are replaced at the service boundary with deterministic
  responses. No OpenAI request, production database, or production data is
  used.
- Browser tests use Playwright Chromium emulation, including a 390x844 mobile
  viewport. This is not a real iPhone or Android device test.
- CI uses Python 3.12, PostgreSQL 16, and the pinned Chromium/Playwright
  dependency set.

## Evidence

Local disposable database:

```text
postgres:16-alpine
127.0.0.1:55433
database: shiftly_test
```

Commands:

```sh
python3 -m pip install -r requirements-dev.lock
python3 -m playwright install chromium
TEST_DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55433/shiftly_test \
DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55433/shiftly_test \
OPENAI_API_KEY=test-key ADMIN_SIGNUP_KEY=test-admin-key \
python3 -m pip check
python3 -m compileall -q server.py auth.py config.py database.py reporting.py routes.py security.py store_service.py tests
TEST_DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55433/shiftly_test \
DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55433/shiftly_test \
OPENAI_API_KEY=test-key ADMIN_SIGNUP_KEY=test-admin-key \
python3 -m pytest -q --browser chromium --tracing=retain-on-failure --screenshot=only-on-failure
```

Result:

```text
88 passed in 16.76s
No broken requirements found.
```

The disposable PostgreSQL container was stopped after the run. Browser
failure artifacts are written under `test-results/` when a test fails.

## Confirmed defects

No application defect was confirmed by the contract or browser suite. The
initial test run exposed and then corrected a test-only missing helper import
in `test_cross_store_reports_are_not_visible`; the final run passed.

## Remaining work and coordinator requests

- The browser suite is browser emulation only. Real iPhone/Android capture,
  installation, permissions, reconnect, and device-specific behavior remain
  outside this assignment.
- Codex still owns worker recovery and must be integrated before the combined
  Round 1 validation.
- After Codex merges, merge updated `origin/main` into this branch without
  rewriting published history and rerun the full suite plus browser checks.
- Required branch protection/status-check settings were not changed. The
  coordinator should configure merge-required CI checks in repository settings
  if permissions allow.
- No shared fixture, application implementation, migration, or planning file
  changes are requested from the coordinator.
