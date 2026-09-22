# Accounts & Access integration handoff

Date: 2026-09-22. Delivery branch: `codex/accounts-permissions-integration`.

Codex completed the FastAPI/browser integration after the user explicitly
requested takeover from the saved Copilot checkpoint. The original UI worktree
and its uncommitted files are preserved. This completes the first Accounts &
Access module for integration review; production cutover remains separate.

## Source and delivery revisions

- Verified project base: `9a31a930ebf6fa305e8919d1ff398177666b3577`.
- Consumed backend: `261637a2da7aaaa942acdcd2ac5764bece610b32`,
  [backend draft PR #9](https://github.com/GetFluxxed/Shiftly/pull/9). Its hosted CI passed.
- Copilot dependency merge: `8be4cd0d0842941159c8825c63131de9441ae537`.
- Integration starts from that merge plus the exact saved tracked/untracked
  Copilot changes. No UI branch was merged into the backend lane.
- Final implementation: `ab9c0ec378da67c2a30b4ffd6cf290aa3af09397`.
  The following documentation-only commit records this SHA and cleanup; the
  draft PR identifies the final branch head including that delivery record.

## Completed module

Both transports now provide named login/status, roster, invitations/reissue,
activation, supervised password-reset redemption, password changes, logout/
logout-all, store selection, store/business membership changes, suspension,
ownership transfer and shared-crew cutover. FastAPI explicitly maps the same
camelCase bodies documented in the backend contract. Recovery issuance remains
operator-only, after identity verification; no HTTP issuance endpoint exists.

All account, reporting and protected-page requests resolve one server-side
principal. Named crew reports persist verified actors; new named managers without
legacy IDs can use existing reporting. Historical text, report scope, worker/
queue behavior and existing reporting response shapes are preserved.

Cookie rules match across both transports, including empty, malformed, repeated
and conflicting cookies, even across multiple Cookie headers. Invalid named
sessions never fall back. Explicit login clears supplied incompatible cookies;
legacy login without them retains its single-cookie response. Legacy logout
retains its original two-cookie response without a named cookie; Accounts logout
clears/revokes all supplied cookie types. Existing assertions were preserved.

The account page offers real invitation, membership and owner workflows, with
permission-aware controls, server errors and confirmation for consequential
changes. Managers cannot expose global password recovery, suspension or ownership
controls. Store and business authority are displayed separately, and delegation
forms show current grants. Private activation codes/passwords never enter URLs,
logs or browser storage; invitation material clears on dismissal/context loss.

Operations routes to manager reporting for `reports.view`, crew reporting for
`reports.submit`, and account management otherwise. Inventory requires
`inventory.view` and honestly presents future work without fake stock actions.
Existing shared-login reporting stays usable until deliberate owner cutover.

Focus, visibility and history restoration recheck identity/store, clearing prior
private reports, rosters and unfinished drafts. Failed account rechecks hide
private content until verified. Forms send optional `expectedStoreId`; both
adapters compare it with the authenticated selected store, returning 409 without
writing after a store change (400 for malformed IDs). It never grants authority.
Services still revalidate the session in the write transaction, while switching
stores rotates/revokes the original token.

## Shared changes

- `routes.py`/FastAPI adapters add the store precondition and compatible explicit
  login cleanup; `security.py` consistently reads all Cookie headers.
- `AccountsService.roster` adds `businessRole`, `businessState`,
  `businessCapabilities` for the selected business. Missing delegation returns
  null/null/[]; revoked delegation stays explicitly revoked. Local membership
  fields and authorization policy are unchanged. Tests exclude unrelated business
  grants and people.
- `tests/browser/conftest.py` adds synthetic named fixtures, preserving all
  original database-isolation and fail-closed settings.
- CI adds the real account upgrade/restore rehearsal and its uploaded evidence,
  alongside the existing complete suite and release recovery.

## Original blocker and verification

The original command attached `TEST_DATABASE_URL` to compilation, then invoked
pytest without it. No fixture deleted the variable. The saved run reported
104 passed, 378 setup errors and 1 failure. Correctly passing the disposable
database to pytest produced **482 passed, 1 failed in 115.18s**, with zero setup
errors. The one real failure was FastAPI legacy logout returning an extra cookie;
it was fixed without weakening the original assertion or database safety rules.

All runs use disposable PostgreSQL 16 schemas/databases, explicit settings,
random local ports, mocked AI and Chromium. No production data, application
`.env`, or paid providers are used.

- HTTP/transport and existing authentication: **97 passed in 43.36s**.
- Lifecycle plus scoped roster metadata: **25 passed in 7.82s**.
- Account browser workflows: **16 passed in 17.30s**; owner delegation,
  suspension/restore and transfer: **2 passed in 3.68s**.
- Cross-tab privacy/history: **6 passed in 7.94s**, across both servers.
  Tests dispatch a standard focus event after tab activation because headless
  Chromium omitted desktop focus; all private-data/scope assertions remain.
- Mobile Accounts/Inventory and desktop owner screenshots were captured for
  visual inspection. This is viewport coverage, not a real-device deployment test.
- Python compilation, all six JavaScript syntax checks, `pip check` and diff
  checks passed. Final full suite: **588 passed in 194.58s**, with no failures,
  skips or weakened existing assertions.

Pass settings to pytest itself:

```sh
DATABASE_URL='' OPENAI_API_KEY='' SECURE_COOKIES=false \
TEST_DATABASE_URL='postgresql://TEST_USER:TEST_PASSWORD@127.0.0.1:TEST_PORT/TEST_DATABASE' \
python -m pytest -q --browser chromium --tracing=retain-on-failure \
  --screenshot=only-on-failure --junitxml=/private/tmp/shiftly-accounts-integration-full.xml
```

Both real recovery rehearsals passed on the combined implementation:

- Accounts: **1.93s**, 65,641-byte PostgreSQL archive, exact 20 tables, 7 sequences,
  33 FKs, 25 checks, 3 triggers and 2 functions. Covered 013→014 history, synthetic
  mapping, named actors, credentials/revocations, scoped access, restored reads/
  writes/login, replay denial and constraints.
- Release: **5.86s**, 63,851-byte archive, exact 20 tables, 7 sequences and 33 FKs.
  Fresh/upgrade/repeat/concurrent migration, separate API/worker, SIGKILL fencing,
  database outage/reconnect, current-code legacy rollback and restored API access.
- All four rehearsal databases were removed and all rehearsal processes exited.

Local evidence includes `/private/tmp/shiftly-ui-baseline.xml`,
`/private/tmp/shiftly-accounts-browser-flows.xml`,
`/private/tmp/shiftly-integration-accounts-rehearsal.log`, and
`/private/tmp/shiftly-integration-release-rehearsal.log`. Final JUnit and hosted
CI artifacts provide combined evidence. The owned disposable
`shiftly-accounts-integration-db` container was removed after all tests and
rehearsals finished. Delivery worktree:
`/Users/getfluxxed/projects/Shiftly-codex-accounts-integration`.
The original Copilot UI worktree, backend worktree and reports worktree were
preserved. No test servers or workers remain from these completed runs.

## Review and rollout

Publish as a stacked draft against `codex/accounts-permissions-services`, keeping
the integration diff separate from backend PR #9. No main merge or production
deployment is included. Real ownership mapping, enrollment and hosted staging
remain deliberate rollout steps; follow the backend migration/rollback runbook.
No new inventory/catalog tables, stock actions, media/training, sales or native
app implementation belongs to this module.

Changed areas: 13 root UI assets; FastAPI app, account/compat/static adapters and
dependencies; legacy cookie/context adapters; scoped roster metadata; browser,
transport and service tests; CI, API/testing/deployment and handoff documentation.
Migrations 001–014, dependency locks and production startup are unchanged by this
integration.
