# Shiftly implementation plan

Updated: 2026-09-20. Baseline inspected: `53fdd36` on `main`.

**Verification update — 2026-09-21:** PRs #1–#7 are merged through `e01e84e`.
Services, FastAPI compatibility, durable worker and migration commands are now
implemented. The focused verification branch addresses the remaining request
compatibility and release-rehearsal gaps. See
[current evidence and gate status](workstreams/focused-verification.md).
Gate D requires review and merge of these follow-up fixes with green CI; hosted
staging and production cutover remain Gate P. The original baseline below is
historical; the feature ordering and acceptance requirements remain applicable.

**Client direction update — 2026-09-22:** The user selected a phone and tablet
app built with React Native. [NATIVE_APP_ROADMAP.md](NATIVE_APP_ROADMAP.md) now
authorizes native client delivery with Expo and TypeScript in `apps/mobile`,
reusing the verified Accounts & Access services. It supersedes the earlier
mobile-web-first choice and orders native work alongside the domain phases below.
The existing browser app remains available during migration.

This is the authoritative domain implementation sequence for the next Shiftly release.
It replaces the earlier baseline-only backlog. It describes planned work, not
features that already exist. Product rules and worked inventory examples are in
[INVENTORY.md](INVENTORY.md); technical boundaries are in
[ARCHITECTURE.md](ARCHITECTURE.md); executable work packages are in
[TASKS.md](TASKS.md).

**Current delivery — 2026-09-23:** Native accounts/reporting and account management
are implemented in the active worktree. The [shared company catalog and first shelf](workstreams/inventory-foundation-and-shared-catalog.md)
are also implemented: one company catalog reused across store listings and shelf
placements, with additive migration 015 and native screens. This completes the
bounded product/SKU storage and shelf-assignment slice; quantities, conversions
and camera work follow. Historical F0/F1 instructions below are evidence,
not a request to repeat completed work.

## 1. Intended outcome

Evolve Shiftly into a modular application backed by FastAPI. Preserve crew
reporting and manager briefings, and add a separate **Inventory** workspace
accessible from the manager window, using the same store membership and account.

The inventory workspace will let a manager:

- Define items, package sizes, measurement units, and explicit shelf locations.
- Set and update store par levels and optional shelf replenishment targets.
- Maintain a running digital inventory tracker with quantities, provenance,
  freshness, change history, and corrections.
- Photograph shelves with a phone, review suggested items and quantities, and
  reconcile approved observations into inventory.
- Weigh open inventory using explicit item-specific weight references and
  container tare weights, combining partial quantities with unopened stock.
- See below-par items, estimated days of cover, and potential shortages using
  available inventory and sales-derived demand where the inputs support it.
- As a stretch goal, scan item barcodes/SKUs during invoice receiving, match
  delivered quantities to invoice lines, and post confirmed receipts to the
  same inventory tracker.

## 2. Historical starting baseline and constraints

- The backend is split across configuration, database, authentication, security,
  routes, reporting, and store services. HTTP still uses `ThreadingHTTPServer`;
  FastAPI is not installed or implemented yet.
- PostgreSQL migrations 001–011, disposable-database tests, and GitHub Actions
  exist. The last verified suite passed 78 tests, and CI passed for `53fdd36`.
- The manager browser UI already includes reports, briefings, weekly overviews,
  and Head's Up. Inventory, photo storage, sales imports, and receiving do not
  exist yet.
- Crew access is shared. Typed employee names are report metadata, not verified
  identities for inventory approvals.
- Background briefing processing still runs inside the web process. The
  reviewed worker error path can terminate processing when recording a failed
  job also fails; recovery and worker monitoring remain prerequisites.
- The older `codex/reports-module` worktree contains uncommitted work based on
  `b289865`. Preserve it, compare useful pieces against current `main`, and port
  selected changes through review rather than treating it as the new baseline.

## 3. Planning decisions

| Decision | Direction |
| --- | --- |
| Application architecture | One modular application with a FastAPI API and separately supervised durable workers |
| Existing functionality | Preserve current URLs, cookie behavior, data, and browser workflows during migration |
| Inventory navigation | Manager window → Inventory; dedicated workspace with a return path to manager operations |
| First client | React Native + Expo phone/tablet app first; keep the existing browser application during migration, without a separate React web rewrite |
| First stock entry method | Manual counts, receipts, and partial weights establish the trusted workflow before vision automation |
| Camera results | Proposals that require review; photos cannot directly post stock changes |
| Partial items | Explicit scale measurements and item-specific conversions; photos alone do not establish remaining weight |
| Inventory authority | PostgreSQL movement history and approved count reconciliations; the digital sheet is a view of those records |
| Sales forecasting | Explainable estimates with input freshness and confidence; no silent changes to confirmed inventory |
| SKU receiving | Stretch goal after item mappings, units, and receipt posting are reliable |

These are implementation defaults. Store-specific measurements, sales mappings,
and acceptance thresholds must be supplied or validated before their phase is
enabled. Discovery can proceed while the foundation is built.

## 4. Delivery phases and exit gates

### Phase 0 — Establish the delivery baseline

1. Reconcile the old worktree, update handoff records, and work from current
   `main` in bounded feature branches. Preserve uncommitted work.
2. Turn the known worker failure into a regression test and implement recovery,
   bounded retries, useful logs, and worker progress monitoring.
3. Capture current API behavior and critical crew/manager browser flows. Include
   authentication, malformed inputs, partial weekly results, and failures.
4. Add reproducible dependency versions, automated code/dependency checks, and
   browser testing to the existing isolated PostgreSQL CI workflow. Verify that
   required checks and review are enforced on merges.
5. Establish staging with separate secrets and data. Rehearse backup restoration,
   migration execution, and application rollback.

**Exit gate:** current workflows pass; worker recovery is demonstrated; staging
and restore evidence are recorded; useful older work is accounted for.

### Phase 1 — Introduce FastAPI without breaking existing clients

1. Introduce an application package and factory, typed request/response models,
   shared configuration, and explicit database/authentication dependencies.
2. Extract domain services from HTTP handlers. Remove route imports of
   `server.py`; keep SQL and AI calls behind service/repository interfaces.
3. Add FastAPI compatibility adapters for existing endpoints. Compare status
   codes, response bodies, cookies, authorization, and security headers against
   the current implementation. Deliberately map validation errors where FastAPI
   defaults differ from the existing contract.
4. Separate web and durable worker entry points. Use application lifespan for
   resource setup/cleanup; execute migrations once through a coordinated release
   step, rather than independently from every web or worker instance.
5. Add bounded database pools, dependency timeouts, liveness/readiness, worker
   heartbeat/queue-age monitoring, and shared limits before multiple API replicas.
6. Run the existing browser against FastAPI in staging, then switch the deployed
   web entry point with a documented rollback path. Avoid introducing inventory
   data changes in the transport cutover.

**Exit gate:** the existing application passes contract and browser tests on
FastAPI; service tests run without a live HTTP server; restarts recover jobs;
staging cutover and rollback both succeed.

### Phase 2 — Manager app workspace, identity, and inventory catalog

1. Add manager navigation between **Operations** and **Inventory**, an explicit
   selected store, phone-friendly layouts, and persistent deep links.
2. Require identifiable individual accounts for inventory actions. Move manager
   authentication toward store + username + password through a documented
   compatibility transition. Add membership lifecycle, revocation, and an audit
   trail before permitting stock approvals.
3. Define inventory view, count, approve, adjust, configure, and receive
   permissions. Initially grant these to authorized managers; additional stock
   counters can be added with narrower permissions. Shared crew sessions receive
   no inventory access by default.
4. Implement item catalog, base units, pack conversions, required weight
   references for weighed items, supplier identifiers, and archive/version rules.
5. Implement store → area → rack → shelf → bin locations, shelf assignments and
   reference images, capacity, and optional shelf targets.
6. Implement store-item par settings, change history, and item/location filters.
   Keep shelf replenishment targets distinct from store purchasing par.

**Exit gate:** a manager can open Inventory, configure a store's real pilot items
and shelves, and update pars; unauthorized users and other stores are excluded;
historical records survive configuration edits.

### Phase 3 — Running inventory and partial-weight counts

1. Implement an append-only movement history for opening balances, receipts,
   usage, waste, transfers, count adjustments, and reversals. Update its balance
   projection in the same database transaction.
2. Deliver the digital tracker, showing base quantity, package equivalents,
   sealed/open breakdown where known, par gap, location, last physical count,
   last change, and whether a displayed value is measured or estimated.
3. Add count sessions with explicit scope, complete/partial coverage, draft
   observations, review, version checks, atomic approval, and correction history.
4. Add open-container weighing, tare deduction, unit conversion, multiple partial
   containers, measurement timestamps, and versioned full-content weight profiles.
5. Add manual receipt entry now; scanning remains a later acceleration of this
   same receipt service. Add idempotency for retries and concurrent-write tests.

**Exit gate:** the sealed-plus-partial worked example in [INVENTORY.md](INVENTORY.md)
passes; repeat approval and repeated weighing do not add stock twice; concurrent
receipts/counts require a safe reconciliation; balances can be rebuilt from history.

### Phase 4 — Phone camera and shelf-assisted counting

1. Enable phone capture and gallery upload inside the Inventory count flow.
   Associate every image with a store, location, count session, actor, and time.
2. Add private media storage, upload validation, retention, thumbnail generation,
   and authorized retrieval. Make upload interruption recoverable.
3. Run image analysis as a durable job that proposes catalog matches, quantities,
   packaging, and uncertain regions. Use shelf assignments as context, not as
   proof of what is present.
4. Support multiple pictures per shelf, overlap review, missed/hidden items,
   mixed products, retakes, manual corrections, and links to partial measurements.
5. Require review of complete packages versus open containers before committing
   the combined count. Display untouched locations and unresolved coverage.
6. Evaluate on representative store photos with verified counts. Record count
   error, item-match accuracy, correction effort, latency, and cost by item type.

**Exit gate:** a phone photo plus weighed open stock produces a reviewable count;
approval updates the tracker exactly once; overlapping images and open containers
cannot inflate stock; unresolved images can be completed manually. Pilot quality
thresholds are agreed and measured before camera counting is enabled broadly.

### Phase 5 — App experience and resilient mobile workflows

The primary app is React Native with Expo. Extend the implemented native shell
with camera/weighing flows and explicit upload/reconnect states when their domain
modules are ready. Keep final stock posting online and authorized. Any later
saved drafts need private device storage, version revalidation, and clear pending
status; they must never appear as posted counts before server confirmation.

Test supported iPhone/Android devices, camera denial, background/return, rotation,
poor connectivity, and sign-out. Preserve the existing browser app during migration.
Native distribution and real-device acceptance are separate release requirements.

**Exit gate:** the agreed native device matrix completes capture → weigh → review
→ post with privacy and stock accuracy preserved through interruption and retries.

### Phase 6 — Par, sales, and shortage insights

1. Ship deterministic below-par indicators from Phase 3 balances first.
2. Introduce a sales-source adapter, beginning with a validated import format if
   the store's POS integration is not selected. Import identifiers, timestamps,
   units, refunds/voids, and source freshness; prevent duplicate imports.
3. Map sold products to inventory items or effective-dated recipes with explicit
   yields and unit conversions. Total sales dollars alone are insufficient to
   calculate item consumption without an agreed empirical mapping.
4. Estimate usage, days of cover, reorder points, and quantities using item
   demand, pars, lead times, review periods, safety stock, and reliable incoming
   deliveries. Show explanations and data limitations alongside each result.
5. Keep projections separate from confirmed stock and historical count evidence.
   Measure forecast error against later verified counts and actual sales.

**Exit gate:** known sales/recipe examples produce reproducible quantities;
stale/missing data is visible; forecasts do not double-subtract usage or promise
unsupported runout dates; a manager can inspect why an item is flagged.

### Phase 7 — Stretch: scan-to-receive invoices

1. Reuse manual receiving and catalog conversions. Map scanned UPC/EAN/GTIN or
   vendor barcodes to the internal SKU and correct pack size.
2. Capture/import expected invoice lines, then scan delivered products to advance
   the receiving checklist. Allow quantity entry and repeated legitimate scans.
3. Handle unknown codes, substitutions, shortages, damaged goods, over-deliveries,
   partial deliveries, returns, and corrections without silently closing a line.
4. On confirmation, post accepted delivered quantities to the movement history
   once and update the digital tracker. Preserve invoice/receipt evidence.
5. Start with manual invoice entry or structured import; automatic invoice OCR
   is a separately evaluated extension and is not required for barcode receiving.

**Exit gate:** replaying an upload or receipt request cannot duplicate inventory;
case-to-unit conversions are correct; a partial receipt leaves the remainder
outstanding; checklist status matches actual accepted deliveries.

## 5. Cross-phase rules

- Preserve original reports and migration history; introduce additive migrations
  and backfills with explicit rollback/forward-recovery plans.
- Every inventory object and action is scoped to an authorized store. Treat
  nested object IDs, photos, job IDs, exports, and offline drafts the same way.
- Photos, sales estimates, and typed names are evidence or inputs; they do not
  bypass permissions or create verified identities.
- Human approval records actor, time, source, previous/new values, and reason.
  Correct posted events through linked reversals, not silent edits/deletions.
- Store quantities using decimal precision and explicit units; preserve the
  conversion profile used by each historical event.
- Gate new modules by store for pilots. Failure in inventory or vision must not
  prevent crew reporting or manager access to original notes.
- Bound AI work, retention, payload sizes, retries, and per-store costs. Test
  provider failures without making paid calls in the normal suite.
- Each work package includes schema/API/UI implications, acceptance tests,
  documentation, staging evidence, and migration considerations as applicable.

## 6. Inputs required at each decision gate

| Needed before | Input or decision | Default until settled |
| --- | --- | --- |
| Native client delivery | Supported iPhone/Android phones and tablets; device acceptance | React Native + Expo first; retain existing browser workflows |
| Phase 2 catalog | Pilot store, item list, base units, case sizes, shelf layout, pars | No invented store values |
| Phase 3 weighing | Full net weights, tare profiles, scale precision, partial-item list | Manual scale entry; no assumed weights |
| Phase 3 approvals | Who may count, approve, adjust, and configure | Identified authorized managers only |
| Phase 4 media/AI | Consented sample photos, retention policy, provider, cost and accuracy gates | Human review for every proposed count |
| Phase 6 forecasting | POS/export source, recipes or usage mappings, sales cadence, lead times | Below-par alerts; no unsupported sales forecast |
| Phase 7 receiving | Supplier SKU/barcode mappings, invoices, case sizes | Manual receiving remains available |

## 7. Immediate next work package

Implement the shared company catalog and first store shelf described in the
[inventory foundation](workstreams/inventory-foundation-and-shared-catalog.md).
Reuse existing business/store permissions and the prepared native API boundary.
Start with named shelves and product/SKU assignments; follow with inventory
quantities and photo workflows at their existing acceptance gates. F0/F1 and the
local runtime are implemented; hosted cutover remains a separate release task.
