# Codex Round 3 service and runtime handoff

Branch: `codex/integration-services-runtime`.
Planning base: `e55d7ea340874cabfa26c3f41bfb3ea53f4ba8b2`.
Integrated code baseline: `818a03cb1bcff67c6c36a3ddbbd73a1028894dff`.

## Published checkpoint A

The initial commit containing this handoff is the usable identity/store service
checkpoint. Resolve its SHA from this branch's history; subsequent runtime
commits will record that exact supplied SHA here. Runtime separation is still
pending at this checkpoint; do not claim Gate D/P complete.

Implemented: login/auto-role selection, workspace and manager creation, session
issuance/lookup/logout, active membership and selected-store rules, crew fallback
to a manager session, store/account lists, Head's Up, shared single-process
admission and framework-independent composition of the existing report services.
Legacy adapters delegate instead of discovering `server.py`. The retired
`routes._server_module` name remains `None` only for unchanged tests that replace
it; no path calls it, and routes no longer import the server.

Account creation now includes its first session in the same transaction as the
store/account/membership. This preserves successful responses and prevents a
failed session insert from leaving a partially created workspace or manager.
A token uniqueness failure is mapped through the existing conflict response.
Existing password hashing, report policies and AI prompts are unchanged.

## Public interface for Copilot

Import `build_services` from `backend.shiftly.runtime`:

```python
services = build_services(
    settings=settings,
    connection_factory=connect,
    provider=provider,
    weekly_connection_factory=dedicated_connect,  # optional at A; see below
    admission=admission,                         # optional, one instance per app
    clock=clock,                                 # optional Unix-seconds callable
    wake=wake,                                   # optional zero-argument callback
    weekly_capacity=capacity,                    # optional shared semaphore (2)
    session_ttl=28800,
)
```

Construction performs no database/provider work, starts no threads and does not
import server/routes/reporting/FastAPI. Build once per app so admission/weekly
capacity are shared, not once per request. The returned `Services` has:

- `identity`: `IdentityService`.
- `stores`: `StoresService`.
- `reports`: existing `ReportsService`.
- `submission`: existing `ReportSubmission`.
- `weekly`: existing `WeeklyOverviewService`.
- `admission`: `AdmissionControl` (single process).

`provider(report, prompt)` returns the existing AI dictionary. The quality prompt
and weekly prompt are supplied by composition. `connection_factory()` supplies a
transactional connection context; weekly connections must **close the underlying
session** on exit to release the repository's advisory lock. Passing a pool's
return-to-pool context as the weekly factory is unsafe. Runtime B will supply the
bounded dedicated weekly factory without changing this signature.

### Identity/session operations

- `identity.login_payload(fields, *, client_key)` normalizes login fields then
  calls `login(store_code, role, password, *, client_key)`.
- `identity.admit_account_creation(client_key, *, action="signup")` checks admin
  configuration, then atomically reserves the shared signup/add-manager budget.
  Call **before parsing the account request body**, so malformed requests retain
  legacy config/rate-limit ordering. Use action `add_manager` for that endpoint.
- `identity.signup(fields)` / `identity.add_manager(fields)` validate the parsed
  account payload and atomically create records plus session. These do not repeat
  the admission reservation; adapters must call the preflight above first.
- These three successful account/login operations return `SessionResult` with
  `role`, `token` (excluded from repr), `response` (existing JSON dictionary), and
  `ttl`. Adapters serialize the appropriate crew/manager cookie using current
  Path/HttpOnly/SameSite/Secure/Max-Age rules. Login is 200; creation is 201.
- `identity.manager_id(manager_token)` returns ID or a false value; blank,
  missing, expired, inactive or revoked sessions have no authority.
- `identity.selected_store(manager_token, manager_id)` verifies the pair and
  membership; legacy null store selection is resolved/persisted as before.
- `identity.crew_store(crew_token, manager_token="")` first resolves a valid crew
  session, then permits the existing manager selected-store fallback.
- `identity.logout(manager_token="", crew_token="")` deletes both supplied
  session hashes. Adapters must expire **both** cookies and return the existing
  authenticated-false body; never log raw session tokens.

`IdentityError` is exported from `backend.shiftly.identity`; `str(error)` is the
legacy public message. Translate `error.code` as follows:

| Code | HTTP status |
| --- | --- |
| invalid | 400 |
| unauthenticated | 401 |
| forbidden | 403 |
| not_found | 404 |
| conflict | 409 |
| limited | 429 |
| unavailable | 503 |

JSON/body parsing and its pre-existing endpoint-specific errors remain adapter
responsibilities. Unexpected database/provider exceptions are not disguised as
successful authentication. Services receive a peer identity from the adapter;
do not trust arbitrary forwarded headers or a body field for `client_key`.

### Store/report operations

- `stores.store_for_code(code)` -> `(store_id, name)` or None.
- `stores.manager_username(manager_id)` -> name or None.
- `stores.manager_accounts(store_id)` -> existing activity list.
- `stores.heads_up(store_id)` -> existing message/update dictionary.
- `stores.save_heads_up(store_id, message)` normalizes the message and returns
  the same dictionary after commit. Caller must authorize manager + selected store.
- `admission.report_limited(client_key)` consumes/checks the existing 30/hour
  submission budget, before parsing/submitting just as the legacy adapter does.
- `submission.submit(trusted_store_id, fields)` -> `(report_id, created_at)`;
  quality rejection/validation/runtime mappings are unchanged from F1.
- `reports.list_for_manager(trusted_manager_id)` retains membership-wide scope.
- `weekly.overview(trusted_selected_store_id)` retains 202 busy, bounded source,
  shared capacity, cache fingerprint and coverage behavior.

No new inventory permissions or explicit username sign-in were added. Trusted
IDs must come from session lookup, not request payloads. The framework-independent
services do not implicitly authenticate a caller's arbitrary store argument.

## Checkpoint A evidence

Local Python 3.14.7, pytest 8.4.2, psycopg 3.3.5, Playwright/Chromium, disposable
PostgreSQL 16 (`shiftly-round3-codex-db`, ephemeral localhost port 65131).
Application DATABASE_URL/OPENAI_API_KEY were empty; only TEST_DATABASE_URL selected
the disposable DB, and existing fixtures block external provider traffic.

- Before edits: **176 passed in 24.82s**.
- Extraction first full run: 174 passed, 2 failed because report compatibility
  tests replace the retired server lookup name. Retained the unused None hook;
  did not edit or weaken those tests.
- New direct-service suite: **17 passed in 2.81s**.
- Final checkpoint A full suite: **193 passed in 27.28s**, including all unchanged
  contracts/browser/recovery/report-service checks.
- Compilation, `pip check`, and whitespace checks passed.

Commands:

```sh
DATABASE_URL='' OPENAI_API_KEY='' TEST_DATABASE_URL=<disposable-dsn> \
  python3 -m pytest -q --browser chromium --tracing=retain-on-failure --screenshot=only-on-failure
python3 -m compileall -q backend/shiftly/identity backend/shiftly/stores backend/shiftly/runtime \
  auth.py security.py store_service.py routes.py server.py reporting.py tests/identity_services
python3 -m pip check
git diff --check
```

Coverage adds direct signup/login/logout, session revocation/expiry, cross-store
and forged-ID denial, legacy null-store fallback, first-session failure rollback,
concurrent admission, provider-free identity flows, report-service composition,
and isolated import/construction without HTTP or legacy runtime modules.

The temporary database remains in use for milestone B. Final cleanup and runtime
evidence will be appended before delivery. No hosted CI or FastAPI business-route
parity is claimed by this checkpoint. Copilot owns the final combined transport
and release rehearsal; the coordinator owns Gate D/P integration decisions.
