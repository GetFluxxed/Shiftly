# API baseline

## Transport verification — 2026-09-21

The existing routes and pages are implemented on both the legacy HTTP server
and FastAPI. The focused verification follow-up runs the complete contract
suite against both, including session expiry/revocation, manager membership
scope, selected-store writes and request-supplied store-ID spoofing.

Malformed login requests return `400` with `Invalid login request.` Other JSON
write routes return `400` with `Request is empty or too large.` for empty or
oversized bodies, and `Invalid report format.` for invalid JSON/non-object/
undecodable bodies. Invalid Head's Up requests now return JSON instead of
disconnecting the legacy client. Authentication precedes report/Head's Up body
validation.

Compatibility routes do not redirect trailing slashes. Unknown GET paths return
HTML `404`; unknown POST paths return `404 {"error":"Not found."}`. Unsupported
methods retain legacy `501`, including an empty HEAD body. FastAPI's automatic
`/docs`, `/redoc` and `/openapi.json` HTTP endpoints are disabled for this existing
surface. A future versioned module can deliberately define its own methods and
documentation. FastAPI retains the existing security headers and applies
`Cache-Control: no-store` to API responses, including session responses.

See [verification evidence](workstreams/focused-verification.md) for release gates.

Updated: 2026-09-20. The first sections describe implemented behavior. The
versioned inventory routes below are proposed contracts for the
[implementation plan](IMPLEMENTATION_PLAN.md), not available endpoints.

## Authentication endpoints

### POST /api/auth/login
- Accepts storeCode, role, password
- Returns a session cookie for manager or crew
- Errors: 400, 401, 429

### POST /api/auth/signup
- Requires admin key and store metadata
- Creates a store, manager account, membership, and manager session
- Errors: 400, 403, 409, 429, 503

### POST /api/auth/add-manager
- Creates another manager record for an existing store
- Requires admin key and store code

### POST /api/auth/logout
- Clears both manager and crew session cookies

### GET /api/auth/status
- Reports whether the current user is authenticated and whether the role is manager or crew

## Report endpoints

### GET /api/reports
- Requires manager authentication
- Returns reports for the authenticated manager’s stores

### POST /api/reports
- Requires crew access, including an authorized manager's selected-store session
- Validates payload, checks duplicate/cooldown protections, runs quality gate, and queues report
- Returns 202 while job is pending

### GET /api/heads-up
- Returns store-scoped current Head’s Up message
- Works for crew or manager if store is known

### POST /api/heads-up
- Requires manager authentication
- Saves a store-level Head’s Up message

## Overview endpoints

### GET /api/managers
- Requires manager authentication
- Returns manager activity list for the current store

### GET /api/weekly-overview
- Requires manager authentication
- Returns a validated, cached summary for the session store
- Includes `reportCount`, `includedReportCount`, and `truncated` to disclose coverage
- Returns 202 with `status: pending` and `retryAfter` when generation is busy
- Returns 503 for a handled generation failure

## Health endpoint

### GET /api/health
- Returns server health and DB config status
- Status 200 for healthy DB; 503 when database not ready

## Compatibility note

These routes are treated as the compatibility contract for the current browser app. Any future changes should preserve the path, payload structure, cookies, and response codes unless an explicit contract update is planned.

The FastAPI transition must deliberately preserve existing validation errors and
cookie behavior. Add contract tests before replacing adapters; a framework's
default response format is not an approved breaking change.

## FastAPI integration status

The FastAPI app and legacy server expose the same authentication, report,
Head's Up, manager-list, weekly and Accounts & Access services. Protected pages
resolve the same server-side principal as the APIs. Public files are explicitly
allowlisted; unknown, private, traversal and repository paths are not served.

## Accounts & Access

Named login uses `POST /api/accounts/login` with `storeCode`, `username` and
`password`. The HttpOnly `shiftly_account_session` cookie identifies the verified
person and selected store. `GET /api/accounts/status` returns `authenticated`,
`actor` (user/store/business IDs, username/display name, role, capabilities and
named provenance) and authorized `stores`. Roles/permissions in the request never
grant authority. The older JSON `role` field remains a reporting-UI projection.

The complete route/field/result/error contract is in the
[account backend handoff](workstreams/codex-accounts-permissions.md#legacy-http-contract-and-copilot-integration).
Both transports accept the same camelCase bodies for team invitations/reissue,
activation, password change/reset, memberships, owner operations, suspension,
store switching, shared-crew cutover and logout/logout-all. Operator recovery
issuance stays outside HTTP; the public `reset-password` endpoint only redeems
an independently issued, expiring, single-use token.

Named account mutations, report submissions and Head's Up updates accept optional
`expectedStoreId`. The browser sends the store shown when the form was prepared.
The adapter compares it with the authenticated selected store: a mismatch returns
409 without performing the write; malformed IDs return 400. This is a precondition,
not authorization or store selection. The service still revalidates the session
in the write transaction, and store switching rotates the token. Legacy report
payloads remain compatible. Cross-store draft data is cleared when browser tabs
observe a changed account/store.

Mixed named/legacy cookies resolve one principal. Empty, malformed, duplicated,
expired or revoked named cookies cannot fall back to legacy access. A named and
legacy-manager pair must identify the same mapped person and selected store;
shared crew cannot prove equivalence. Explicit sign-in clears incompatible
cookies. Legacy logout preserves its original two-cookie response when no named
cookie is supplied; Accounts logout clears all three.

`accounts.html` requires named authentication. `inventory.html` additionally
requires `inventory.view` and presents an empty workspace only; stock operations
remain future work. `activate.html` is public for supervised activation/recovery,
but tokens are submitted in JSON, never URL parameters or browser storage.
Every account API response is non-cacheable; mutation origins and Fetch Metadata
are checked. Error bodies remain `{"error": "safe message"}`.

## Proposed inventory API

New module base: `/api/v1/stores/{store_id}`. Resolve the authenticated actor's
membership and action permission for this store, then verify that every nested
item/location/photo/job/invoice ID belongs to it. A client-supplied store ID is
never sufficient authorization.

| Method and relative path | Planned purpose |
| --- | --- |
| GET/POST `/inventory/items` | Paginated catalog and item creation |
| GET/PATCH `/inventory/items/{item_id}` | Item, pack and weight-profile configuration with version checks |
| GET/POST `/inventory/locations` | Shelf/location hierarchy and assignments |
| GET/PUT `/inventory/items/{item_id}/par` | Store-item par and change history |
| GET `/inventory/balances` | Book quantities, sealed/open breakdown, locations and verification timestamps |
| GET `/inventory/movements` | Paginated movement history and evidence references |
| POST `/inventory/adjustments` | Authorized manual adjustment, waste or usage with reason |
| POST `/inventory/transfers` | Atomic paired movement between authorized locations |
| POST `/inventory/counts` | Start a scoped draft with server-recorded baseline versions |
| POST `/inventory/counts/{count_id}/observations` | Manual counts and weighed container readings |
| POST `/media/uploads` | Create an authorized inventory-image upload |
| POST `/media/uploads/{upload_id}/complete` | Validate the uploaded object and enqueue processing |
| GET `/jobs/{job_id}` | Authorized durable job status and reviewable result references |
| GET `/inventory/counts/{count_id}` | Coverage, proposals, partial measurements and proposed stock differences |
| POST `/inventory/counts/{count_id}/commit` | Approve and atomically reconcile a reviewed count |
| POST `/inventory/counts/{count_id}/corrections` | Begin an auditable correction of a posted count |
| POST `/inventory/sales/imports` | Import and deduplicate sales input for usage estimation |
| GET `/inventory/insights` | Par gaps, shortage estimates, inputs, freshness and confidence |
| POST `/inventory/receiving/invoices` | Expected invoice lines; structured/manual input first |
| POST `/inventory/receiving/scans` | Stretch: map a scan event to a draft receipt line and pack size |
| POST `/inventory/receiving/receipts` | Manual or scan-assisted draft accepted delivery quantities |
| POST `/inventory/receiving/receipts/{receipt_id}/commit` | Post the accepted delivery exactly once |

Finalize request/response schemas with each work package and publish OpenAPI
contracts. Suggested common fields are stable IDs, explicit units, decimal
quantities serialized as strings, actor/source references, UTC timestamps,
store timezone where relevant, and record versions.

Require `Idempotency-Key` for stock-posting and replayable upload/import/scan
commands. The same key and body return the original result; reuse with a
different body returns a conflict. Recheck authorization even on replay.
Validate draft `expectedVersion` and stored scope baselines at approval; stale
counts return 409 with a review path and no partial posting.

For the new API, document 401 for missing authentication, 403 for missing action
permission, scoped not-found responses that do not expose other stores, 409 for
conflicts, 422 for validated input errors, 429 for admission limits, and 503 for
unavailable dependencies. Use a consistent error code/message/request ID shape.
Do not apply that new shape retroactively to legacy clients without adapters.

Return 202 plus an authorized job reference for analysis/import work. A camera
result is a proposal; completion of analysis does not mean stock was posted.
Separate book quantity, observed quantity, and estimated quantity in responses,
including freshness, coverage and conversion versions.
