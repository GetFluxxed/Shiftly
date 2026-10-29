# Shiftly security model

Updated 2026-10-23. This records implemented controls in the current source.
Hosted configuration and operational verification remain separate evidence; see
[DEPLOYMENT.md](DEPLOYMENT.md).

## Identity and sessions

Supported staff access uses individual username/password accounts activated by a
single-use, expiring invitation. Invitation activation starts with baseline crew
authority. Elevated roles are assigned later by an authorized owner or
administrator; there is no public manager/admin/owner signup.

Credentials use salted password hashes. Browser and native sessions are opaque,
random, stored server-side as hashes, expiring, revocable, and tied to credential
version. Native bearer tokens live in SecureStore; browser sessions use protected
cookies. The server rejects mixed credential forms. Password reset and invitation
tokens are never trusted for role or store claims.

Shared crew login, password-only manager login, and public signup were retired on
2026-09-24. `/api/auth/signup` and `/api/auth/add-manager` always return 403, and
public request authentication rejects shared/legacy cookies. Compatibility tables
and adapters preserve existing data during migration but do not authorize new
feature access.

Invitation links carry only an opaque secret in the URL fragment, never role,
store or username claims. Opening a link previews the bound username and store
without consuming it. Activation rechecks the issuer's current authority under the
policy lock and consumes the token, creates the account and opens the session in
one transaction. Expired, revoked, replaced or used tokens cannot activate.
Reissuing invalidates the earlier code. Older unaccepted invitations that carried
elevated roles or extra grants cannot activate.

## Roles and capabilities

Defined in `backend/shiftly/identity/accounts_policy.py`. Capability strings:
`reports.submit`, `reports.view`, `reports.manage`, `inventory.view`,
`counts.submit`, `counts.approve`, `receipts.draft`, `receipts.post`,
`stock.adjust`, `configuration.manage`, `catalog.propose`, `catalog.manage`,
`memberships.manage`, `production.view`, `production.submit`, `production.manage`,
`recipes.manage`, `forecasts.view`.

| Role | Effective capabilities | Administration limits |
| --- | --- | --- |
| Owner | All capabilities in the owned business, every store | Appoints owners/admins, transfers ownership, suspends accounts (only with authority over the target's whole account history) |
| Admin | Exactly the explicit business delegation intersected with store grants | Assigns roles within its delegation; cannot appoint admins |
| Manager | Crew capabilities plus `reports.view`, `reports.manage`, `counts.approve`, `receipts.post`, `stock.adjust`, `configuration.manage`, all production capabilities, `recipes.manage`, `forecasts.view`; optional `memberships.manage` | With `memberships.manage`, may invite baseline crew only; cannot edit memberships or promote anyone. Never receives `catalog.manage` through a store grant |
| Production | `inventory.view`, `counts.submit`, `receipts.draft`, `catalog.propose`, `production.view`, `production.submit` | No reporting, Store workspace, account management or store switching |
| Crew | `reports.submit`; optional `inventory.view`, `counts.submit`, `receipts.draft`, `catalog.propose` | No approval, posting, adjustment or administration |

Stores not yet enabled for accounts expose only reporting capabilities.
Self-escalation and removing or suspending the last active owner are denied.
Removing one store membership keeps the person's other stores. Heads Up reads are
limited to manager, crew and production roles, and writes to managers; owners and
admins have no Heads Up access.

## Restricted offline counts

A completed count download can grant only that count's local workspace up to 12
hours after a successful account validation. Its SecureStore authorization binds
the session token, user, business, store, role and capabilities. Offline access
cannot learn about remote revocation until reconnection; this exposure is bounded
by the authorization window. Normal network requests remain blocked offline.
Backgrounding hides private UI, and every upload requires a new access check plus
the backend transaction's authorization. Explicit revocation/sign-out removes the
offline authorization. Expiry prevents local access without deleting queued work.

Count snapshots and immutable queued observations use separate encrypted
SecureStore checkpoints, isolated by service origin and individual account/store.
They survive app closure and sign-out for recovery by the same authorized account.
Replacing a clean active count retires the prior cache; pending data cannot be
evicted by UI draft limits. Device storage failure prevents a success indication.
Review and stock posting remain online. Physical keychain, expiry/revocation and
cold-launch acceptance are still required before release; see the
[count contract](archive/inventory-counts.md#durable-mobile-counting--2026-10-22).

## Temporary offline catalog intake

Catalog managers with `inventory.view` may save local capture drafts while their
session is online and verified. Opening Saved scans also explicitly prepares a
12-hour offline capture grant, bound to the same bearer session, user, business,
store, role and capabilities as the count grant. Each present grant is validated
independently; a count grant does not imply catalog access, nor vice versa.
Concurrent preparation preserves both grants without extending offline expiry.
Network writes remain blocked in the restricted offline workspace.

At most 100 raw-code/name/measurement drafts use an atomic encrypted checkpoint
partitioned by service origin and owner. No photo, stock balance or full catalog
cache is stored here. Captures are acknowledged only after durable commitment;
failed, corrupt or full storage cannot silently evict drafts. Permission changes,
lock, sign-out and expiry hide the inbox. Pending drafts remain for the same
account to recover after revalidation, with every local action checking scope.

Online review performs a fresh lookup before offering a product/package action.
Existing products, aliases, archived records and uncertain writes use the normal
catalog conflict flow. The draft is removed only after explicit completion or
discard, never on a lookup/network error. Backend authorization still controls
all catalog writes. Local intake is not a server backup; resolve pending scans
before changing the API origin, reinstalling or handing off the device. A new
origin cannot adopt another origin's queued work automatically.

Retire this temporary inbox only after a replacement safely migrates or drains
pending drafts. Physical SecureStore, permission and cold-launch acceptance are
still pending; see the [pilot contract](workstreams/iphone-pilot-2026-10-31.md).

## Authorization and tenancy

The server derives the actor, business, selected store, role, and capabilities.
Crew, production, and managers have one active store. Owners and delegated
administrators may switch only inside their authorized scope. Production lacks
reporting capabilities and the native Reports/Store surfaces.

Every protected write revalidates the selected store and capability inside the
same database transaction as the mutation. Policy mutations, session issuance and
revocation, and privileged writes share one schema-scoped PostgreSQL advisory
transaction lock, which serializes them across processes. This includes
last-owner races and revocation racing a write. Nested product, package, shelf, count,
movement, recipe, log, forecast, membership, and report IDs are checked against
that scope. Submitted roles, client-side visibility, and object IDs do not grant
access.

Account and inventory changes produce scoped audit/change history. Invitation,
membership, ownership-transfer, suspension, count posting, production posting,
and reversal paths preserve actor and reason where their contracts require it.

## Data integrity and sensitive data

- Reports commit original notes and a durable briefing job together. Provider
  failure cannot erase the original report.
- Durable job leases are recoverable and fenced against stale completion.
  Diagnostics are sanitized; external provider execution is not exactly once.
- Count posting and production posting use idempotency/version checks and update
  movement history plus balance projection atomically.
- Decimal quantities and explicit units prevent floating-point stock changes.
- Barcode capture saves no photo. Invoice photos use explicit upload consent,
  manager/owner scope plus inventory/receipt capabilities, decoded JPEG/PNG byte
  and pixel limits, orientation normalization and metadata stripping. Private
  database bytes are removed after successful/terminal analysis or expiry cleanup
  by the worker; backups have their own operator-controlled retention. No public
  media URL or arbitrary image URL fetch exists. See [invoice previews](workstreams/invoice-receiving-preview.md).
- Invoice extraction is a validated proposal. Review, received flags and incoming
  projections never write balances or movements. Shelf-photo counting is planned.
- Forecast output is advisory, store scoped, and cannot post stock.
- Private native checkpoints exclude passwords, invitation/recovery codes, and
  ordinary account rosters; access changes invalidate stored private state.

## HTTP, input, and provider controls

FastAPI applies security headers, bounded request parsing, same-origin checks for
browser writes, and explicit native credential handling. Secure cookies and HTTPS
are required for hosted use. Local cleartext HTTP is limited to loopback/private
LAN development. `EXPO_PUBLIC_*` values are public and may contain only the API
origin, never credentials.

Provider keys, database URLs, admin keys, session tokens, account codes, report
bodies, and private inventory data must not enter source control or logs. Automated
tests mock provider calls and fail unexpected paid requests. Provider output does
not grant authority and must pass domain validation before use.

## Remaining release evidence

Before a production claim, verify the exact deployed revision, HTTPS/cookie
configuration, allowed origins, real account/business mapping, database backup and
restore, migration/rollback procedure, log redaction, worker supervision, rate
limits, and provider budgets. Physical-device checks must cover secure storage,
revocation, backgrounding, camera permission, and private-state clearing.

Account endpoints are listed in [API.md](API.md#accounts-apiaccounts). Inventory
integrity rules are in [INVENTORY.md](INVENTORY.md). Release security gates are in
the [implementation plan](IMPLEMENTATION_PLAN.md#roadmap).
