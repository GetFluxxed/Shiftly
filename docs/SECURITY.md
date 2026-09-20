# Shiftly security model and planned inventory controls

Updated: 2026-09-20. Current behavior and future controls are separated below.

## Implemented baseline

The current application uses shared store crew credentials, individual manager
records, store memberships, hashed session tokens, expiry checks, parameterized
SQL, and cookie/security headers. Cookies are HttpOnly and SameSite=Strict;
Secure behavior depends on configured deployment settings.

Login failures and in-flight attempts share a normalized client/store budget.
Weekly generation is bounded. These admission controls are process-local and
must be coordinated before deploying multiple API processes.

Manager login currently accepts store code, role and password and searches the
store's candidate manager credentials. A stored username is not yet an explicit
login selector. Typed crew names remain self-reported metadata, not proof of
identity. Inventory permissions, an inventory audit log, and media storage are
not implemented yet.

## Identity transition

For inventory, use an explicit individual account and authorized store
membership. Introduce store + username + password selection and account/session
lifecycle through a documented client transition. Preserve existing report
sessions during transport migration; do not silently treat an ambiguous legacy
login as sufficient identity for new audited approvals.

Store context must be validated server-side for every operation. The current
report list spans authorized memberships, while several other manager views use
the selected store; define and test the inventory contract as one explicit store.
Review role and membership revocation, account recovery and shared-device logout.

## Planned permission model

| Actor | Inventory access |
| --- | --- |
| Shared crew session | None by default; existing reporting remains available |
| Identified authorized manager | View/count/approve/adjust/configure/receive within granted stores |
| Optional named stock counter | View and submit draft observations only where explicitly granted; no automatic approval or configuration rights |
| Store administrator capability | Manage store memberships and inventory grants with an audit record |

Implement action permissions such as inventory view, count, approve, adjust,
configure, and receive, even if the pilot grants them together to managers.
Hiding a navigation link is not authorization. Retain server checks on nested
items, locations, photos, jobs, invoice lines, exports, idempotent replays and
reconnected drafts. Reject mismatched store relationships at the database layer
where possible.

## Planned stock and evidence controls

- Record actor, store, action, occurrence/recording times, source, old/new values
  and reason for approvals, par changes, adjustments, receipts and corrections.
- Apply stock-posting idempotency and version checks in the same transaction as
  the movement and balance update. Recheck permission on retry.
- Preserve original measurements, image evidence references and conversion
  versions. Correct posted history through linked events.
- Keep image objects private. Validate uploaded bytes/type/dimensions, restrict
  retention, strip unnecessary location metadata, and authorize each retrieval.
- Treat photos, OCR text, barcodes, invoice contents and provider output as
  untrusted input. Require validated proposals and authorized stock approval.
- Keep AI/storage credentials server-side. Do not log credentials, signed URLs,
  or unnecessary report/photo content. Document which evidence reaches providers.
- Define limits for payloads, per-store jobs, retries and provider spend.

## Planned application controls

Preserve current cookie/security behavior through FastAPI contract tests. Define
origin/CSRF checks for state-changing browser requests and use an explicit CORS
allowlist if a later client requires cross-origin access. Validate trusted proxy
configuration before relying on forwarded client-address headers.

Enable same-origin camera access only for inventory capture surfaces; do not
enable microphone access as a side effect. HTTPS and a usable denied-permission
fallback are part of the camera acceptance gate.

The installable app caches public application assets, not authenticated API
responses or private photos by default. Saved drafts have explicit retention,
clear device ownership/sync state, and a logout cleanup policy; reconnect always
revalidates authorization and inventory versions. Native device authentication
and secure storage require their own later design.

See [INVENTORY.md](INVENTORY.md) for evidence, weighing and receiving rules and
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the delivery gates.
