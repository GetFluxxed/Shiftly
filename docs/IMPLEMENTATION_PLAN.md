# Shiftly implementation plan

Updated 2026-10-25. This plan separates source implementation from release
evidence. An item marked **implemented** exists in this checkout. Local/CI,
physical-device, and hosted verification are recorded independently; none implies
another.

This is the single prioritized roadmap. Product intent is in [PRODUCT.md](PRODUCT.md);
per-client screens are in [WORKFLOWS.md](WORKFLOWS.md); rules are in
[INVENTORY.md](INVENTORY.md), [SECURITY.md](SECURITY.md), and
[ARCHITECTURE.md](ARCHITECTURE.md). Superseded backlogs and handoffs are listed in
the [archive index](archive/README.md). The engineering adoption record is in
[archive/engineering-adoption.md](archive/engineering-adoption.md).

## Status matrix

This 2026-10-21 snapshot describes source revision `df53f98` and is retained as historical
CI and deployment evidence; it predates the current source and delivery state
recorded below. Each column is separate evidence; one never implies another.

- **Source:** present in `df53f98`.
- **Local:** dated local verification recorded in an [archived delivery record](archive/README.md).
- **CI:** GitHub Actions [run 38652749388](https://github.com/GetFluxxed/Shiftly/actions/runs/38652749388)
  passed on `df53f98` (2026-10-14): Python/browser suite, native type checks/tests,
  iOS/Android JavaScript exports and both recovery rehearsals. It is automated
  evidence only.
- **Device:** physical-device evidence recorded in the repository.
- **Deployed:** running in a named hosted environment.
- **Operational:** accepted by the owner for real store use.

| Capability | Source | Local | CI | Device | Deployed | Operational |
| --- | --- | --- | --- | --- | --- | --- |
| FastAPI runtime, separate worker, explicit migrations | Yes | 2026-10-11 | Yes | n/a | No | No |
| Individual accounts, invitations, store scope | Yes | 2026-09-24 | Yes | Owner's iPhone via Expo Go confirmed sign-in and account flows, 2026-09-24 | Browser flows: unverified (see note) | No |
| Native team/owner administration, Store hub | Yes | 2026-09-26 | Yes | iPhone feedback fixed 2026-09-26; re-check after fix not recorded | No | No |
| Shift reports, briefings, Heads Up (native) | Yes | 2026-09-29 | Yes | Not recorded | No | No |
| Weekly Overview | Browser only | 2026-09-21 (both transports) | Yes | n/a | Unverified | No |
| Catalog, shelves, container amounts | Yes | 2026-09-30 | Yes | Not recorded | No | No |
| Barcode scan-to-catalog | Yes | 2026-10-01 | Yes | iPhone label failures reported 2026-09-30; fixes not yet re-tested on device | No | No |
| Packages, pounds labels, item combining, unit correction | Yes | 2026-10-02 | Yes | Not recorded | No | No |
| Reviewed whole-store counts, stock and movements | Yes | 2026-09-29 | Yes | Not recorded | No | No |
| Recipes and production (1.01 allowance, reversal) | Yes | 2026-09-29 | Yes | Not recorded | No | No |
| Store production reports and advisory forecast | Yes | 2026-10-01 (fake provider only) | Yes | Not recorded | No | No |
| Native workspace restoration | Yes | 2026-09-29 | Yes | Not recorded | No | No |
| Contextual native route returns and Back controls | Yes | 2026-10-29: unit and real-router fixture journeys | Not yet verified | Android hardware/iOS gesture re-check pending | No | No |
| Shelf-photo proposals, invoice receiving, offline posting, scale capture | No | — | — | — | — | — |

**Deployment note.** The most recent owner-reported hosted setup (recorded
2026-10-21, not independently re-verified) is the legacy browser runtime on a free
Render web service with a paid PostgreSQL 18 database. The revision running there
is not recorded. No environment serves the native API. Details and configuration
drift are in [DEPLOYMENT.md](DEPLOYMENT.md#hosted-environment-observations).

## Roadmap

The roadmap below is the 2026-10-21 plan; current source and delivery status are
recorded in the sections below.

Release tiers:

- **Dev:** development prerequisite.
- **Pilot:** required before named staff use real data in one store.
- **Public:** required before broader or public release.

Items 1–3 proceed together. Items 4–7 depend on them.

### 1. Real catalog, packages, recipes and opening stock (Dev → Pilot)

**Prerequisites:** none beyond current source.

**Done when:**
- Every in-scope ingredient has one catalog identity, a correct base unit, package
  definitions with sourced amounts, and stable barcodes or internal SKUs.
- Duplicate items are resolved through owner-reviewed combining, or recorded for
  reconciliation where history exists.
- Every active flavor has an owner-reviewed recipe whose production preview matches
  recipe × batches × 1.01.
- A real whole-store opening count is posted through draft → review → posted.
- Volume-labelled ingredients have an owner-supplied net weight (see
  [open decisions](#open-owner-decisions)).

### 2. Physical-device testing and current defects (Pilot)

**Prerequisites:** item 1 data on the pilot devices.

**Done when:** the supported phone/tablet matrix (to be named) passes these
journeys, with the device model and OS recorded:
- sign-in, store scope and revocation;
- barcode scanning: permission, zoom, small labels and the previously failing
  sugar/milk labels;
- mixed package/partial counts and count approval;
- recipe editing and production confirm/reverse;
- uncertain-write recovery;
- background/force-close restoration;
- keyboard, text scaling and VoiceOver/TalkBack basics.

Open inventory/production defects are triaged with owner and severity, and blockers
are fixed with regression evidence. Re-confirm the 2026-09-26 tab/Back navigation fix.

### 3. Hosted mobile support, recovery, security and release operations (Pilot → Public)

**Prerequisites:** owner approval of hosting cost and access.

**Done when:**
- A named staging environment runs FastAPI plus the separate worker, with
  coordinated migrations, at a recorded revision.
- Health, worker supervision, backup/restore and rollback are rehearsed there and
  recorded, as described in [DEPLOYMENT.md](DEPLOYMENT.md#hosted-staging-and-release-gate).
- The [configuration drift](DEPLOYMENT.md#configuration-drift-and-compatibility-checks)
  is resolved or accepted.
- Production ownership mapping is rehearsed.
- The security, permission and recovery review in the
  [camera and invoice plan](workstreams/camera-and-invoice-readiness.md#read-only-security-and-recovery-gate)
  has dispositions for every finding.
- Backup frequency, retention, recovery targets and a secondary operator are
  confirmed.
- Signed development builds exist for the pilot devices.
- **Public:** a production cutover is approved by the owner, plus signed store
  builds, privacy disclosures and support ownership.

### 4. Native Weekly Overview (Pilot)

**Prerequisites:** none.

**Done when:** managers can read the existing weekly summary in the native Reports
area with the same store scope, coverage disclosure and pending/failure states as
the browser. This was recorded as remaining native parity work on 2026-09-22.

### 5. Evaluate advisory forecasts (Pilot)

**Prerequisites:**
- item 1 data;
- at least seven recorded production days;
- a provider key and spend limit approved for evaluation.

**Done when:** forecast suggestions are compared with actual production over an
agreed period, against quality targets the owner has set. Results, model and
prompt version are recorded; prompts or rules change only with new evidence. No
staff decision relies on a forecast before this.

### 6. Reviewed shelf-photo assistance (Pilot → Public)

**Prerequisites:** items 1–3, plus the privacy and operating-policy readiness in the
[camera and invoice plan](workstreams/camera-and-invoice-readiness.md).

**Done when:** Gate A (private prototype), Gate B (named staff pilot) and Gate C
(public) pass in order. Proposals never post stock; normal count review applies.

### 7. Invoice receiving (Pilot → Public)

**Prerequisites:**
- items 1–3;
- supplier/barcode and package mappings;
- a receipt posting contract.

**Done when:** the invoice receiving gate in the
[camera and invoice plan](workstreams/camera-and-invoice-readiness.md#deferred-invoice-photo-receiving)
passes. Extraction creates proposals only; posting is idempotent and reviewed.

### Deferred

- **Scale-assisted counts:** blocked until the owner selects a scale model,
  connection type and protocol. Rules are in [INVENTORY.md](INVENTORY.md#future-inventory-rules).
- **Offline stock posting:** blocked until a server idempotency/conflict design is
  approved. Local restoration remains the only offline-tolerant feature.
- **Approved future inventory capabilities** (pars, sales insights, transfers,
  location hierarchy and others listed in [PRODUCT.md](PRODUCT.md#approved-future-capabilities)):
  scheduled after items 1–3, ordered by pilot need.

## Open owner decisions

These are unresolved. Documentation does not decide them.

| Decision | Why it matters |
| --- | --- |
| Browser commitments | Keep, extend or retire browser pages after native parity? Should `inventory.html` gain workflows or be removed? Is the browser part of public release? |
| Historical product reconciliation | How to merge duplicate products that already have counts, balances or recipe history (combining is blocked today) |
| Volume-labelled products | Net weight to record for litre-labelled goods (for example, Heavy Cream used in Stracciatella); no density is assumed |
| Forecast quality targets | Acceptable error, evaluation period and who reviews results before staff rely on suggestions |
| Image retention and storage | Retention/deletion for shelf and invoice images, derived data and provider logs; storage provider |
| Capture permissions | Whether existing `counts.submit` / `receipts.draft` suffice for photo capture or a narrower grant is needed |
| Privacy and operating policies | Jurisdictions, notices, counsel review and staff procedures (see the camera plan) |
| Receiving rules | Partial, substitution, damage, return and correction handling; supplier identifier ownership |
| Hosting and recovery | Staging resources and cost; backup targets; secondary operator; Render database version/plan of record |
| Device matrix | Which iPhone/Android phone and tablet models define pilot acceptance |
| Mutation replay retention | Inventory/production replay records currently never expire; choose a retention policy before growth |

## Current delivery status and remaining evidence

| Workstream | Source state | Release evidence still required |
| --- | --- | --- |
| FastAPI/service foundation | Implemented | exact-revision hosted cutover, supervision and rollback |
| Individual accounts/invitations | Implemented; shared/public login retired | production ownership mapping and hosted enrollment rehearsal |
| Native reports, Heads Up, team/owner | Implemented | supported-device and signed-build acceptance |
| Time Tracking device demo | Implemented: named crew, shift history, compact roster, independent 3:30 / 5:30 timers and modal-only 10 / 30 minute break countdowns; local model/rendered checks and native exports passed | owner accepted compact layout in Expo Go; break device acceptance, account linking, push delivery and operational use remain pending |
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

## Accepted legacy deviations

The engineering adoption on 2026-10-11 ([record](archive/engineering-adoption.md))
retained these known gaps under [ENGINEERING.md](../ENGINEERING.md#retroactive-adoption-for-existing-projects).
The owner (Derek) decides each disposition; a maintainer performs the work.

| Item | Impact | Disposition / closure evidence |
| --- | --- | --- |
| No confirmed hosted staging | Local success cannot prove platform supervision, networking or recovery | Close via roadmap item 3 with recorded evidence |
| Backup schedule, retention, recovery targets and secondary operator unconfirmed | Recovery is not yet an operating commitment | Owner assigns targets and access; verify an actual hosted restore |
| First production owner is an explicit operator task | An empty production database cannot self-enroll | Keep public signup closed; use the reviewed [operator procedure](DEPLOYMENT.md#accounts-and-operator-procedures) |
| Legacy browser adapter and test globals remain | Import-time settings and broad fixtures | Retain while browser compatibility is supported; narrow only in scoped work with contract tests |
| Schema-wide policy lock and broad roster reads | Possible contention as staff/history grow; no outage measured | Measure with representative sizes before changing locks |
| Dependency license/advisory review incomplete | Pinning does not prove security or distribution rights | Review material dependencies before release and on consequential updates |
| Hosted manifest still runs the legacy runtime | Native API not hosted; forecast jobs are not processed in embedded mode | Resolve in roadmap item 3; see [DEPLOYMENT.md](DEPLOYMENT.md#configuration-drift-and-compatibility-checks) |

## Cross-cutting invariants

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
[individual account contract](archive/individual-accounts-release-2026-09-24.md).

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
zero. See [inventory counts](archive/inventory-counts.md).

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
See [the production contract](archive/production-and-assisted-inventory.md).

## Cross-workstream invariants

- Preserve migration and transaction history; correct posted records through
  linked movement/reversal behavior.
- Use decimal strings at APIs and exact database arithmetic. Never silently
  reinterpret units.
- Treat nested IDs, jobs, media, retries and restored drafts as scoped resources.
- Never automatically replay an uncertain stock-affecting write.
- Keep provider work bounded, observable and mocked in tests. It can never
  authorize or post inventory.
- Record source, local, CI, device, deployment and operational evidence separately.
- Add no new service, framework, identity store or persistence system without an
  accepted requirement and a documented owner and exit path.
