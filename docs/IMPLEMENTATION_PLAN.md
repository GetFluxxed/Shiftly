# Shiftly implementation plan

Updated 2026-10-25. This plan separates source implementation from release
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
| Invoice review and incoming previews | Implemented: manager/owner manual drafts, private photo extraction, received flags and non-posting projections | real invoice quality, device/privacy/worker and hosted acceptance |
| Receipt posting | Planned | partial receipts, duplicate receipt prevention, corrections/reversals and atomic stock posting contract |
| Offline count observations | Implemented in the native Count workspace; durable local queue | physical-device storage, reconnection and conflict acceptance |
| Temporary Saved scans inbox | Implemented; local checks, rendered journeys and native bundle exports passed | encrypted offline capture, reconnection review and original-account isolation on the pilot iPhone |
| October 31 iPhone pilot | Goal: installable GM count release candidate | Apple membership/signing, registered device or TestFlight path, HTTPS FastAPI, production data/account mapping and end-to-end device rehearsal |
| Offline stock posting | Planned; review/approval remain online | separate posting and release gate |

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

Recipes are business-scoped and revisioned, with separate Ingredients and
Variegato sections and optional recipe-only lines. Variegato identifies fixed
toppings for the planned partial-tray workflow. Current production still accepts
whole batches; partial amounts are not implemented. Confirmed production snapshots its
recipe, adds the defined 1% ingredient allowance, rejects missing/insufficient
stock as one transaction, and posts deductions once. Reversals require a reason
and cannot erase later physical-count authority.

Forecasts are store scoped and expose recorded facts separately from generated
analysis. They require bounded input, durable status, permission checks, and
idempotent requests. They are planning support only and never edit recipes,
production, or inventory.

## Next work packages

The immediate schedule is the eight-day October 23–31
[iPhone pilot](workstreams/iphone-pilot-2026-10-31.md). Freeze its product scope to
named-account authentication and roles, catalog/barcode capture, temporary Saved
scans, and count preparation/offline observation/synchronization. Defer production
expansion, shelf-photo counts and offline stock posting until after the count.
On October 25 the owner explicitly brought forward a bounded invoice photo/review
preview for managers and owners. This is an additional local feature, not evidence
that the signed-count pilot or hosted/privacy gates have passed. Its scope and
verification are in [invoice previews](workstreams/invoice-receiving-preview.md). A functional pilot requires an installed signed binary and a
reachable supported backend; source completion alone does not satisfy the goal.

The [interface consistency pass](workstreams/iphone-pilot-2026-10-31.md#interface-consistency-before-october-31)
aligns existing native inventory, production and account/workspace screens before
the pilot. Start with the catalog table and retain current theme, permissions and
workflows; broader feature additions remain deferred.

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
6. **Receiving follow-up.** Evaluate invoice photo accuracy on representative
   supplier documents. Extend reviewed drafts only after defining partial receipts,
   substitutions/damage, duplicate receipt detection and idempotent posting/reversal.
   Keep extraction and checkboxes unable to change stock until that contract passes.

### Recipe entry and partial-tray follow-up

Finish entering the supplied recipes and confirming their catalog mappings first.
Then extend the existing production preview/confirmation workflow to accept the
amount to make for a tray. Scale base ingredients by requested amount divided by
the recipe reference yield; add fixed Variegato once per tray construction or
remolding. Leftover gelato is reused without deducting its ingredients again.
Track fresh gelato amount and the number of trays being finished separately. Store the requested
amount and recipe revision in immutable production snapshots, retain the tracked
1% allowance, and preserve exact units, shortage checks, and retry safety. Do not
model a partial tray as fractional batches that also scale its toppings.

Nominal tray yield is not a requirement that all listed inputs sum to that yield:
inside additions and toppings can make the total input larger. Keep the source
amounts intact and show the planned quantities for review before confirmation.
The October 25 invoice-preview scope change does not complete this refinement or
waive the later stock-posting and shelf-photo gates.
See [the production contract](workstreams/production-and-assisted-inventory.md).

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
