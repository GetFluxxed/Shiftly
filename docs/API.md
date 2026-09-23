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

Updated: 2026-09-23. The first sections describe implemented behavior. The
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

## Native account/report adapter — 2026-09-22

The React Native client uses **FastAPI-only** `/api/mobile` endpoints. The legacy
`python server.py` entry point does not serve this namespace. Existing browser
cookie endpoints and CORS policy are unchanged. The native app uses the same
account services, PostgreSQL session records, permission checks and revocation.

Send one `Authorization: Bearer <opaque session token>` header on protected
requests. Duplicate/malformed authorization headers and any known browser auth
cookie, including an empty cookie, are rejected. Responses do not set cookies.
Login, activation and store switching return the existing account response plus
`sessionToken` and `expiresIn` in seconds. Current sessions last eight hours;
there is no refresh token. Keep the token in platform-protected storage, require
HTTPS for release traffic, and exclude tokens from diagnostic logging.

| Method and path | Behavior |
| --- | --- |
| POST `/api/mobile/accounts/login` | Named login with `storeCode`, `username`, `password`; returns actor, stores and session token |
| POST `/api/mobile/accounts/activate` | Redeem `token` and set `password`; returns an authenticated session |
| POST `/api/mobile/accounts/reset-password` | Redeem independently issued recovery `token` with new `password`; sign in afterward |
| GET `/api/mobile/accounts/status` | Current actor and authorized stores; no bearer gives `authenticated: false`, invalid/revoked bearer gives 401 |
| GET `/api/mobile/accounts/team` | Server-authorized current-store roster, using the existing scoped account contract |
| POST `/api/mobile/accounts/switch-store` | `storeId` target and `expectedStoreId` current context; rotates the token |
| POST `/api/mobile/accounts/password` | `currentPassword`, `newPassword` and `expectedStoreId`; `change-password` is an alias |
| POST `/api/mobile/accounts/logout` | Idempotently revoke the supplied session; no current-store precondition |
| POST `/api/mobile/accounts/logout-all` | Revoke this account's sessions; requires `expectedStoreId` |
| GET `/api/mobile/reports` | Reports from all currently authorized `reports.view` stores, adding `storeId` and `storeName` to each browser-compatible report record |
| POST `/api/mobile/reports` | Named `reports.submit` workflow with existing report fields and required `expectedStoreId`; 202 with `date` and `status: "pending"` |
| GET `/api/mobile/heads-up` | Selected-store `{message, updatedAt}` for `reports.view` or `reports.submit`; `updatedAt` may be null |

Native account administration also exposes POST `invitations`,
`invitations/reissue`, `memberships`, `business-memberships`, `transfer-ownership`,
`suspend` and `cutover` below `/api/mobile/accounts/`. Request fields and authority
match the existing Accounts & Access operations. Native Team and Owner screens
now cover these workflows, using GET `/api/mobile/accounts/management` for scoped
form choices and directory data.

All protected POST bodies except logout must include a positive integer
`expectedStoreId` matching the authenticated session's selected store; missing or
invalid values return 400 and a different store returns 409. This is a form
context guard, not an authorization grant. Shared services recheck actor access
within mutation transactions. Public login, activation and reset are exempt.

Native identity/domain failures retain `error` and add `errorCode`. Browser
response shapes are unchanged. Known conflicts remain local to forms; invalid
sessions or store context invalidate private state. See the
[error/recovery contract](workstreams/inventory-foundation-and-shared-catalog.md#native-errors-and-recovery).
Existing HTTP categories remain: identity validation
400, authentication 401, permission 403, scoped not-found 404, conflicts 409,
admission limits 429 and unavailable dependencies 503. Report quality rejection
returns 422. Existing origin/Fetch Metadata checks still apply if those browser
headers are present; native callers do not gain a wildcard browser origin policy.
Sensitive API responses remain non-cacheable. Do not automatically replay
uncertain writes; an offline outbox requires a separately implemented idempotency
and conflict contract.

## Implemented native catalog and shelves

Migrations 015–016 and `/api/mobile/inventory` provide the first product-storage slice.
All endpoints require an individual bearer session and current selected-store
`inventory.view`. Product writes additionally require `catalog.manage`; shelf
and assignment writes require `configuration.manage`. Company catalog records
are shared across that business; shelves are scoped to the selected store.

| Method / path under `/api/mobile/inventory` | Request / result |
| --- | --- |
| GET `/products` | `q` literal name/current-or-former-SKU search, `state=active\|archived\|all`, optional opaque `after` cursor; returns `{items,nextCursor}` in name order |
| POST `/products` | `name`, `sku`, `baseUnit`, optional `containerAmount`; returns the created product |
| GET `/products/{id}` | Returns product `{id,name,sku,baseUnit,containerAmount,active,version}` |
| POST `/products/{id}` | `name`, `sku`, `version`, optional `containerAmount`; returns updated product; base unit cannot change |
| POST `/products/{id}/state` | `active` boolean and `version`; archive/restore without deleting history |
| GET `/shelves` | Optional `after`; returns `{items,nextCursor}` |
| POST `/shelves` | `name`; returns shelf `{id,name,storeId,version}` |
| GET `/shelves/{id}` | Shelf plus `products:{items,nextCursor}`; optional `after` pages assignments |
| POST `/shelves/{id}` | `name`, `version`; returns renamed shelf |
| POST `/shelves/{id}/products/{productId}` | `active` boolean and shelf `version`; returns `{shelf,productId,assigned}` |

Every POST also requires `expectedStoreId` and a UUID `requestId`. The native
session supplies the selected store; the server rechecks its actual authority
inside the write transaction. Success returns 200, including a replay. An
identical request from the same actor/store returns its original saved result;
reuse with different content is `409 state_conflict`. Authorization is checked
before replay. Data, history and replay result commit together. The client never
automatically retries an uncertain write: retrying an unchanged form in the same
mounted screen reuses its request ID. After leaving the screen, refresh/search
before recreating a possibly saved item. Replay records have no expiry in this
slice; retention needs an explicit later policy.

Lists contain at most 40 records. The catalog and catalog picker sort by
normalized, case-insensitive product name with UUID as a stable tie-breaker. Its
opaque `p1.` cursor carries the last name/ID and remains scoped by the authenticated
company and current filter. Old UUID catalog cursors require a fresh first page.
Shelf and assignment lists retain UUID pagination. Lists are live, not snapshots;
refresh from the first page to reconcile concurrent name/filter changes. Products: name 1–160 characters; SKU 1–64 ASCII letters/digits and
`._/-`, beginning with a letter/digit, retaining leading zeros; base unit is
`each`, `g` or `kg`. Previously stored volume products remain readable; the API
rejects creating new `ml`/`l` products. Shelf names are 1–120 characters. Trimmed,
normalized case-insensitive keys reserve current and former SKUs per company
and shelf names per store. Former SKUs stay searchable. Duplicate identifiers
return `409 duplicate_identifier`; outdated versions return `409 stale_record`.
These preserve the native draft and permit explicit reload. Mutations accept
at most 12,000 request-body bytes and enforce the existing origin policy.

`containerAmount` is the net contents of one full container in the product's
fixed base unit. Send a positive decimal **string** with at most nine integer and
six fractional digits; `each` requires a whole number. Responses use canonical
decimal text, e.g. `"6"` for a 6 kg container. `null` means unknown, never zero.
On edit, omission preserves the existing value; explicit `null` clears it. The
same optimistic version, catalog authority, audit and retry rules apply. No size
is guessed by migration 016. Base units remain immutable; editing the reference
amount does not post stock. Future counts must retain the configuration version
and original measured amount/unit used at posting rather than recomputing history
from an edited current size. Exact gram/kilogram conversion helpers are available;
quantity storage, tare profiles, scale/photo ingestion and count posting are later
work. For example, two full 6 kg containers plus a net 1,250 g partial would be
13.25 kg for the same SKU. No item-to-mass or mass-to-volume conversion is inferred.

Assignment creates/reactivates the store listing without duplicating the
company product. Removal deactivates only that placement. Archive preserves
existing assignments, labels their products archived and blocks new assignments.
This API records planned placement only; it has no quantities, stock movements,
store-listing deactivation, shelf deletion, image uploads or CSV imports.
The existing browser inventory page remains an empty workspace.

## Proposed broader inventory API

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
