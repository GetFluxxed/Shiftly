# Shiftly implementation plan

Updated 2026-10-11. This plan separates source implementation from release
evidence. An item marked **implemented** exists in this checkout. Local/CI,
physical-device, and hosted verification are recorded independently; none implies
another.

The project engineering policy and adoption gaps are tracked in
[engineering-adoption](workstreams/engineering-adoption.md). Architecture and
operational details belong in [ARCHITECTURE.md](ARCHITECTURE.md),
[TESTING.md](TESTING.md), and [DEPLOYMENT.md](DEPLOYMENT.md).

## Product outcome

Deliver one store-scoped operations system in which staff use individual
invitation accounts, submit shift work, maintain a shared business catalog,
perform reviewed physical counts, record production, and inspect explainable
store forecasts. PostgreSQL is authoritative. Human-reviewed inventory commands,
not provider output or client state, change stock.

The React Native/Expo client is the primary phone/tablet experience. Existing
browser pages remain a compatibility surface while hosted parity and rollback
are proven.

## Delivery state

| Workstream | Source state | Release evidence still required |
| --- | --- | --- |
| FastAPI/service foundation | Implemented | exact-revision hosted cutover, supervision and rollback |
| Individual accounts/invitations | Implemented; shared/public login retired | production ownership mapping and hosted enrollment rehearsal |
| Native reports, Heads Up, team/owner | Implemented | supported-device and signed-build acceptance |
| Business catalog and store shelves | Implemented | pilot data review |
| Packages and barcode capture | Implemented | physical camera/permission/zoom/torch matrix |
| Current stock and reviewed counts | Implemented | pilot concurrency and recovery rehearsal |
| Recipes and production | Implemented, including 1% allowance and reversals | pilot operational acceptance |
| Store-scoped forecasts | Implemented as advisory output | provider budget/quality monitoring and hosted worker evidence |
| Shelf-photo assisted counts | Planned | privacy, retention, samples, accuracy and review design |
| Receiving/invoice workflow | Planned | supplier/barcode mapping and posting contract |
| Offline stock posting | Planned | idempotency/conflict design; local checkpoints are not an outbox |

## Implemented foundations

### Runtime and reporting

FastAPI composes framework-independent services and repositories. Migrations are
an explicit step. One API process and one separately supervised durable worker are
the supported initial topology. Reporting preserves original notes when briefing
generation fails, bounds retries, recovers expired leases, and fences stale
workers. The reporting provider and durable job implementation live in
package-owned runtime/job modules; root `reporting.py` remains a compatibility
facade.

Exit evidence: local and CI checks may establish source behavior. Production
readiness additionally requires hosted database migration, worker supervision,
health observation, rollback, and exact-revision verification.

### Accounts and authorization

Individual invitation activation grants baseline crew access. Authorized
owners/admins assign production, manager, or delegated administration afterward.
Crew, production, and managers have one active store; owners and permitted
administrators switch within their authorized business. Production has no Reports
or Store surface.

Every protected write derives actor/scope server-side and rechecks it within the
mutation transaction. Shared crew login, password-only manager access, and public
signup are retired. See the
[individual account contract](workstreams/individual-accounts-release-2026-09-24.md).

### Catalog, packages, and shelves

A business owns one catalog of stable product identities and reserved SKU/barcode
aliases. Stores configure their own products and shelf placements. Package
definitions support exact contained amounts and weight labels. Archive/canonical
redirect behavior preserves history.

The native barcode workflow supports camera and manual entry, normalizes supported
retail forms, finds existing/archived records, and can create a product or attach
a package with appropriate authority. It saves no photo and does not change stock.

### Stock and counts

Store balances are a projection of immutable movements. Whole-store counts enforce
one open count per store, preserve uncounted versus zero, use exact decimal units,
and move draft -> review -> posted. Posting checks completeness, configuration,
baseline versions, authorization, and request identity, then writes history and
balances atomically. The first count establishes stock without an invented prior
zero. See [inventory counts](workstreams/inventory-counts.md).

### Recipes, production, and forecasts

Recipes are business-scoped and revisioned. Confirmed production snapshots its
recipe, adds the defined 1% ingredient allowance, rejects missing/insufficient
stock as one transaction, and posts deductions once. Reversals require a reason
and cannot erase later physical-count authority.

Forecasts are store scoped and expose recorded facts separately from generated
analysis. They require bounded input, durable status, permission checks, and
idempotent requests. They are planning support only and never edit recipes,
production, or inventory.

## Next work packages

1. **Engineering adoption and release operability.** Complete the provider/job
   ownership boundary, reproducible dependency locks, service/dependency ownership,
   current runbooks, and the baseline evidence recorded in the adoption workstream.
2. **Hosted rehearsal.** On an authorized staging environment, rehearse migrations,
   ownership mapping, separate API/worker supervision, health, backup/restore,
   rollback, and native API configuration for the exact revision.
3. **Device acceptance.** Exercise supported iPhone/Android phone and tablet
   layouts, SecureStore lifecycle, access revocation, keyboard/text scaling,
   network interruption, background restoration, and barcode camera behavior.
4. **Pilot acceptance.** Validate real catalog/package inputs, count concurrency,
   production/reversal practice, forecast limitations, and operational ownership
   with a designated store.
5. **Shelf-photo discovery.** Only after privacy/retention, provider cost, consent,
   representative samples, and measurable accuracy gates are approved, design a
   reviewed proposal flow. A photo cannot infer partial weight by itself.
6. **Receiving discovery.** Define supplier identifiers, invoice ownership,
   partial/substitution/damage behavior, and idempotent receipt posting. OCR is a
   separate optional evaluation.

## Cross-workstream invariants

- Preserve migration and transaction history; correct posted records through
  linked movement/reversal behavior.
- Use decimal strings at APIs and exact database arithmetic. Never silently
  reinterpret units.
- Treat nested IDs, jobs, media, exports, retries, and restored drafts as scoped
  resources.
- Keep inventory and forecast failures independent of report submission.
  Submission quality gating currently requires the provider; once accepted,
  original report notes must survive background briefing failures.
- Do not automatically replay an uncertain stock-affecting write.
- Keep provider work bounded, observable, mocked in normal tests, and unable to
  authorize or post inventory.
- Record implementation, local/CI verification, physical-device verification,
  and hosted deployment as separate facts.
- Do not add a new service, framework, identity store, or persistence system
  without a concrete accepted requirement and documented owner/exit path.

## Decision inputs for future phases

Shelf-photo work needs approved devices, consented representative images,
retention/deletion rules, accuracy/cost thresholds, and named reviewers. Receiving
needs supplier/barcode mappings, package conversions, invoice formats, and rules
for partials, substitutions, damage, returns, and correction. Offline posting
needs a server idempotency/conflict protocol and UX for unresolved outcomes.
Until those inputs exist, manual reviewed workflows remain authoritative.

## Historical plans

Earlier phases and parallel-round documents preserve how the service, accounts,
and initial inventory foundations were delivered. Their web-first sequencing,
shared-login transition, migration ranges below `024`, test totals, and
"inventory planned" language are historical and do not describe the current
source. The current contracts linked above take precedence.
