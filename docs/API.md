# Shiftly API

Reviewed against source revision `df53f98` on 2026-10-21. Only implemented routes
are listed. Request and response details beyond these tables are defined by the
named service modules and their tests. Planned interfaces (photo uploads,
receiving, sales imports) have no routes yet; their rules are in
[INVENTORY.md](INVENTORY.md#future-inventory-rules) and the
[camera and invoice plan](workstreams/camera-and-invoice-readiness.md).

## Transports and runtimes

| Transport | Credential | Served by |
| --- | --- | --- |
| Browser compatibility API (`/api/auth`, `/api/accounts`, `/api/reports`, `/api/heads-up`, `/api/managers`, `/api/weekly-overview`, `/api/production`, `/api/health*`) | HttpOnly cookies | FastAPI routers in `backend/shiftly/api/` (`compat.py`, `accounts.py`, `production.py`, `health.py`, `static.py`) **and** legacy `server.py`/`routes.py` |
| Native API (`/api/mobile/...`) | `Authorization: Bearer <session token>` | FastAPI only: routers in `backend/shiftly/api/` (`mobile.py`, `inventory.py`, `counts.py`, `production.py`, `forecasts.py`) |

Both transports use the same services, the same hashed, expiring and revocable
PostgreSQL sessions, and the same policy. FastAPI's automatic `/docs`, `/redoc`
and `/openapi.json` are disabled. All API responses are `Cache-Control: no-store`
and carry the existing security headers.

### Browser cookies

- `shiftly_account_session`: the named-account session. It is HttpOnly, `Path=/`
  and `SameSite=Strict`, and is `Secure` when `SECURE_COOKIES=true`.
- Legacy `shiftly_manager_session` and `shiftly_crew_session` cookies are
  compatibility only. Shared crew and password-only manager sign-in are retired;
  public request authentication rejects shared/legacy credentials.
- Empty, malformed, duplicated, expired or revoked named cookies never fall back to
  legacy access.
- Explicit sign-in clears incompatible cookies. Account logout clears all three.
- Browser writes check Origin/Fetch Metadata for same-origin requests.

### Native bearer sessions

- Login, activation and store switching return the account response plus
  `sessionToken` and `expiresIn` (seconds). Sessions last eight hours, with no
  refresh token.
- Duplicate or malformed `Authorization` headers are rejected, as is any browser
  auth cookie sent alongside a bearer token. Native responses never set cookies.
- Release traffic requires HTTPS. The client keeps tokens in SecureStore and out of
  logs.

## Common request rules

- **Store precondition.** Protected native POSTs (except logout) and named-account
  browser writes include `expectedStoreId`. A missing or invalid value returns 400;
  a different selected store returns 409. This guards form context; it never
  grants or selects authority. Services recheck the session and capability inside
  the write transaction.
- **Idempotency.** Native inventory, count, production and forecast writes require
  a UUID `requestId`:
  - An identical replay by the same actor/store returns the original result.
  - The same ID with different content is `409 state_conflict`.
  - Authorization is rechecked before replay.
  - Clients never retry an uncertain write automatically.
- **Versions.** Edits and transitions send the record's `version`. An outdated
  version returns `409 stale_record`.
- **Bounds.** JSON bodies are capped at about 10–100 KB depending on the route
  (accounts 20 KB, inventory 12 KB, production 40 KB, reports 100 KB). Lists are
  paginated with opaque `after` cursors. Quantities cross the API as decimal
  strings.

## Errors and recovery

Error bodies are `{"error": "safe message"}`. Native identity/domain errors add
`errorCode`. Status categories:

| Status | Meaning |
| --- | --- |
| 400 | Validation (`validation_failed`) |
| 401 | Unauthenticated |
| 403 | Forbidden |
| 404 | Scoped not-found |
| 409 | Conflict |
| 422 | Report rejected by the quality check |
| 429 | Admission limit |
| 503 | Dependency unavailable; no database details are exposed |

Native client behavior by code:

| HTTP / `errorCode` | Native behavior |
| --- | --- |
| 401 / `session_invalid` (or any 401) | Clear local credentials and private state |
| 403 / `access_changed` | Lock the workspace and revalidate |
| 409 / `store_context_changed` | Lock stale store context |
| 403 / `permission_denied` | Revalidate; keep the form only if access is unchanged |
| 409 / `duplicate_identifier`, `state_conflict`, `stale_record` | Show the error on the current form without resetting the workspace |
| Unknown or missing code on 403/409 | Conservative workspace invalidation |

## Browser compatibility API

### Sign-in and status (`/api/auth`)

| Route | Behavior |
| --- | --- |
| POST `/api/auth/login` | Same individual-account login as `/api/accounts/login` (`username`, `password`; optional legacy `storeCode`) |
| POST `/api/auth/signup`, `/api/auth/add-manager` | Always `403` "Accounts require an invitation." |
| POST `/api/auth/logout` | Revokes supplied sessions and clears cookies |
| GET `/api/auth/status` | `authenticated`, legacy `role` projection (`manager`/`crew`) and `managerName`; named sessions also expose `actor` |

### Accounts (`/api/accounts/...`)

All routes are served by `backend/shiftly/api/accounts.py` (FastAPI) and
`routes.account_route` (legacy).

| Method / suffix | Body / result |
| --- | --- |
| GET `status` | `{authenticated, actor, stores}` |
| GET `team` | Selected-store roster; requires team authority |
| POST `login` | `username`, `password` (optional `storeCode`); sets the named cookie |
| POST `invitation-details` | `token`; previews the bound username/store without consuming it |
| POST `activate` | `token`, `password`; sets the named cookie |
| POST `reset-password` | `token`, `password`; redeems an operator-issued reset |
| POST `logout`, `logout-all` | Revoke this session / all of this account's sessions |
| POST `switch-store` | `storeId`; rotates the session |
| POST `password` | `currentPassword`, `newPassword`; revokes sessions |
| POST `invitations`, `invitations/reissue` | `username`, `displayName`, `role`, `capabilities`, `expiresIn`, `reason` / `userId` |
| POST `memberships` | `userId`, `role`, `capabilities`, `active`, `reason` |
| POST `business-memberships` | `userId`, `role` (`admin`/`owner`), `capabilities`, `active`, `reason` |
| POST `transfer-ownership` | `userId`, `reason`; clears the caller's cookies |
| POST `suspend` | `userId`, `suspended`, `reason` |
| POST `cutover` | Optional `storeId`, `reason`; disables shared crew sign-in for the store |

**Results and limits**

- `actor` contains `userId`, `username`, `displayName`, `storeId`, `businessId`,
  `role`, sorted `capabilities` and `provenance: "named"`. The roster returns stored
  grants plus `lastSignInAt`.
- Invitation and reissue return a one-time `token`. Never log it or place it in a
  URL query.
- Invitations expire within 60 seconds to 7 days (default 24 hours); resets within
  60 seconds to 1 day.
- New passwords are 8–1024 characters.
- Recovery issuance is operator-only (see [DEPLOYMENT.md](DEPLOYMENT.md#accounts-and-operator-procedures)).

### Reports, Heads Up and overview

| Route | Who | Behavior |
| --- | --- | --- |
| GET `/api/reports` | `reports.view` | Reports for the selected store (unpaginated) |
| POST `/api/reports` | `reports.submit` | Validates, deduplicates, runs the quality check (422 on rejection), queues a briefing; returns `202 {date, status: "pending"}` |
| GET `/api/heads-up` | Manager, crew, production | `{message, updatedAt}` for the selected store |
| POST `/api/heads-up` | Manager | `message` (at most 1,000 characters); one current message per store |
| GET `/api/managers` | `reports.view` | Store managers with last sign-in |
| GET `/api/weekly-overview` | `reports.view` | Cached weekly summary with `reportCount`, `includedReportCount`, `truncated`; `202 {status: "pending", retryAfter}` while generating; 503 on handled failure |

### Production (`/api/production/...`)

These are the same routes and rules as the native production API, using the
browser cookie. The browser page exposes only recipe listing, preview, confirm and
log listing.

### Health

| Route | Behavior |
| --- | --- |
| GET `/api/health` | 200 when the database is reachable, otherwise 503. Body includes `status`, `openaiConfigured`, `databaseConfigured`, `secureCookies` and a `worker` object |
| GET `/api/health/worker` | 200 only when the worker is recently polling or processing; otherwise 503. Database health never implies worker progress |

## Native API (`/api/mobile`)

### Accounts, reports and Heads Up

`/api/mobile/accounts/{operation}` accepts the same operations and bodies as the
browser accounts API, plus GET `management`:
- `management` returns selected-store members, server-derived form choices and
  eligible actions; only owners receive the business directory.
- `status` without a bearer token returns `{authenticated: false}`; an invalid
  bearer returns 401.
- `password` also accepts the alias `change-password`.

| Route | Who | Behavior |
| --- | --- | --- |
| GET `/api/mobile/reports` | `reports.view` | Selected-store reports, each labelled with `storeId`/`storeName`; switch stores to see another store |
| POST `/api/mobile/reports` | `reports.submit` | As browser, plus `expectedStoreId`; `202` |
| GET `/api/mobile/heads-up` | Manager, crew, production | Selected-store message |
| POST `/api/mobile/heads-up` | Manager | `message`, `expectedStoreId` |

### Native inventory and counts

All routes are under `/api/mobile/inventory`. Rules are in [INVENTORY.md](INVENTORY.md).

| Route | Capability | Purpose |
| --- | --- | --- |
| GET/POST `/products` | view / `catalog.manage` | Search (`q`, `state=active\|archived\|all`, `after`); create (`name`, `sku`, `baseUnit`, optional `containerAmount`) |
| GET `/products/lookup` | view | Exact barcode/SKU alias lookup (`sku`, `barcodeType`) |
| GET/POST `/products/{id}` | view / `catalog.manage` | Read; edit name, SKU, container amount (`version`) |
| POST `/products/{id}/state` | `catalog.manage` | Archive/restore (`active`, `version`) |
| GET/POST `/products/{id}/measurement` | `catalog.manage` | Read blockers; correct a mistaken base unit |
| GET/POST `/products/{id}/packages` | view / `catalog.manage` | List; create a package or case |
| POST `/products/{id}/packages/{packageId}` | `catalog.manage` | Edit a package |
| POST `/products/{id}/packages/{packageId}/state` | `catalog.manage` | Archive/restore a package |
| GET `/products/{id}/combine-preview` | Owner | Preview combining into `targetProductId` |
| POST `/products/{id}/combine` | Owner | Combine (`targetProductId`, `sourceVersion`, `targetVersion`, `confirmed`) |
| GET/POST `/shelves` | view / `configuration.manage` | List; create |
| GET/POST `/shelves/{id}` | view / `configuration.manage` | Shelf with paged products; rename |
| POST `/shelves/{id}/products/{productId}` | `configuration.manage` | Assign/remove (`active`, shelf `version`) |
| GET `/count-status` | view | Open-count dashboard |
| GET `/stock`, `/stock/{productId}` | view | Current balances (`q`, `shelf`, `after`); product location and count detail |
| GET/POST `/counts` | view / `counts.submit` | Count history; start the store's count (`businessDate`) |
| GET `/counts/{id}`, `/counts/{id}/lines`, `/counts/{id}/lines/{lineId}` | view | Count detail; lines (`q`, `shelf`, `missing`, `after`) |
| POST `/counts/{id}/lines/{lineId}` | `counts.submit` | Save a line entry (`entry`, `version`) |
| GET `/counts/{id}/comparison` | view | Differences from the previous count |
| POST `/counts/{id}/review` | `counts.submit` | Draft → review |
| POST `/counts/{id}/post`, `/reopen`, `/cancel` | `counts.approve` | Post to stock; return to draft; cancel |

### Native production and forecasts

All routes are under `/api/mobile/production`; the browser uses the same routes
under `/api/production`.

| Route | Capability | Purpose |
| --- | --- | --- |
| GET/POST `/recipes` | `production.view` / `recipes.manage` | Search; create (`name`, `yieldAmount`, `yieldUnit`, `instructions`, `ingredients`) |
| GET/POST `/recipes/{id}` | `production.view` / `recipes.manage` | Read; save a new revision (`version`) |
| POST `/preview` | `production.view` | Server-calculated deductions and issues; no stock change |
| GET/POST `/logs` | `production.view` / `production.submit` | History; confirm production (`logId`, `businessDate`, `entries`, `requestId`) |
| GET `/logs/{id}` | `production.view` | Log with ingredient snapshots |
| POST `/logs/{id}/reverse` | `production.manage` | Reverse with `reason` |
| GET/POST `/forecast` (native only) | All four forecast capabilities | Latest advisory forecast (optional `logId`); request a new analysis (`requestId`) |
