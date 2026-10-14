# Shiftly security model

Updated 2026-10-11. This records implemented controls in the current source.
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

Shared crew login, password-only manager login, and public signup are retired
product flows. Compatibility tables/adapters may preserve existing data during
migration but do not authorize new feature access.

## Authorization and tenancy

The server derives the actor, business, selected store, role, and capabilities.
Crew, production, and managers have one active store. Owners and delegated
administrators may switch only inside their authorized scope. Production lacks
reporting capabilities and the native Reports/Store surfaces.

Every protected write revalidates the selected store and capability inside the
same database transaction as the mutation. Nested product, package, shelf, count,
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
- Barcode camera capture saves no photo. Shelf-photo analysis and invoice/OCR
  are planned and therefore have no implemented storage/retention claim.
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

The detailed account contract is
[individual-accounts-release-2026-09-24.md](workstreams/individual-accounts-release-2026-09-24.md).
Inventory integrity rules are in [INVENTORY.md](INVENTORY.md).
