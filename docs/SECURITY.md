# Shiftly security model

Reviewed against source revision `df53f98` on 2026-10-21. This records implemented
controls in the current source. Hosted configuration and operational verification
remain separate evidence; see [DEPLOYMENT.md](DEPLOYMENT.md).

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
- Barcode camera capture saves no photo. Shelf-photo analysis and invoice
  extraction are not implemented, so there is no image storage or retention to
  claim. Their required controls are in the
  [camera and invoice plan](workstreams/camera-and-invoice-readiness.md#read-only-security-and-recovery-gate).
- Forecast output is advisory, store scoped and cannot post stock. Provider
  requests use `store: false`; nothing trains a model on company records.
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
