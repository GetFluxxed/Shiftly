# Shiftly inventory module specification

Status: first catalog/shelf slice implemented, 2026-09-23. Delivery order is
controlled by [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). This remains the
broader specification; only the slice below is implemented. Quantities, camera
processing and sales integrations remain future work.

## Current first slice — 2026-09-23

Implemented directly in React Native: a shared company catalog with
add/edit/archive/restore, named shelves in a selected store and product/SKU
assignment/removal. Reuse identical
company products across stores without duplicating their identities. Follow the
[inventory foundation and shared company catalog](workstreams/inventory-foundation-and-shared-catalog.md); stock quantities, camera processing and the broader specification below
remain later work. Migrations 015–016, the independent inventory service/router, and
native catalog/shelf screens implement this slice. Store-listing deactivation,
shelf deletion and area/rack/bin hierarchy are not yet exposed.

## Manager workspace

Entry point: **Manager → Inventory**, with the selected store visible throughout
and a direct return to Operations. Inventory is a distinct Shiftly workspace,
sharing authentication and store membership with the rest of the application.

Planned views:

| View | Purpose |
| --- | --- |
| Overview | Below-par items, stale counts, unresolved drafts, and later shortage estimates |
| Digital inventory | Running quantities, locations, sealed/open amounts, pars, freshness, and history |
| Count inventory | Manual or camera-assisted shelf counts, partial weights, review and approval |
| Shelves and locations | Area/rack/shelf/bin definitions, assigned items, capacity and reference photos |
| Items and pars | Item details, units, pack conversions, weight references, store pars and audit history |
| Receiving | Manual receipts first; invoice checklist and barcode scanning as the stretch phase |
| Insights | Sales mappings, demand estimates, forecast explanations and data quality |
| History | Posted movements, counts, corrections, actors and supporting evidence |

The tracker is the application's digital sheet, backed by transactional data.
Spreadsheet import/export may be added for convenience; an external sheet is
not a second inventory authority or a prerequisite.

## Standard containers — implemented refinement

The catalog now stores the net amount per full container, in each, grams or
kilograms. White Quella can use a kg base with a full-container amount of `6`.
The form displays `6 kg = 6000 g`; container size is visible in catalog cards and
shelf assignments. Existing products can add/edit this reference with version
checks. An unknown size stays blank. New litre/millilitre products are disabled.
The catalog and shelf's catalog picker are alphabetized before pagination/search.

Actual partial measurements remain a later count/scale integration. Store each
future observation's original amount/unit, net value after known tare, product
ID and configuration version; normalize grams/kilograms exactly into that same
SKU's base unit. A 1,250 g net partial contributes 1.25 kg alongside full 6 kg
containers. It is not a separate SKU and must not be counted again as a full
container. Changing the current container reference must not recalculate already
posted quantities. This revision stores standard contents only, not a current
back-stock balance or purchasing target.

## Item and shelf information

Each store item needs a stable ID and internal SKU, name/category, base stock
unit, display unit, purchased pack/case conversions, active/archive state, and
effective-dated configuration. Preserve supplier identifiers separately from the
internal SKU. Retain leading zeros in barcode strings.

For weighed stock, require an explicit reference profile before enabling partial
counts: net contents per full package, mass unit, supported tare/container
profiles, measurement precision, and expected tolerance. If a store wants a
weight converted to pieces, it must also provide a validated per-piece mass;
otherwise the authoritative quantity remains mass. A density conversion from
mass to volume is item-specific and must never be assumed.

Locations form a store-owned hierarchy: **area → rack → shelf → optional bin**.
Store a stable code/label, parent, description, optional dimensions/capacity,
reference image, planned item assignments, and optional facing/depth guidance.
The same item can occupy multiple locations. Planned placement does not prove
that the item or expected number of packages is actually present.

Maintain one store-item par target in the item's base unit, with actor, reason,
effective time, and history. Optional shelf targets control internal
replenishment and must not be summed into purchasing par without an explicit
rule. Editing par changes alerts; it does not change stock.

## Quantities and the movement history

Use decimal quantities and explicit measurement dimensions (`count`, `mass`, or
`volume`). Persist original measurements as well as normalized values and the
conversion version. Avoid accumulating rounded package equivalents; round only
for presentation or an explicit ordering rule.

Every posted change has a store, item, location, quantity delta, unit, movement
type, actor, occurrence time, recording time, reason, and source reference.
Support opening balance, receipt, usage, waste, transfer, count adjustment, and
reversal. A transfer posts balanced source/destination entries atomically.

The running book balance is the sum of posted movements. Display its last
physical verification separately: a ledger value is not a claim that the shelf
has just been measured. Sales-derived estimates are an additional labeled view,
not silent replacements for the book balance.

Posting a count or receipt atomically records movements, updates the balance
projection, and records its approval. Require an idempotency key with a unique
constraint scoped to store and operation; reuse with different content is a
conflict. Repeated requests return the original result, not a second movement.
Posted records are corrected through linked reversals or replacement events.

## Count sessions and camera observations

1. Select store and scope: one shelf, several locations, or a full store count.
2. Capture the baseline versions and identify which items/locations are covered.
3. Enter manual quantities or capture images. Store capture and observation
   times separately from upload/analysis times.
4. Review proposed catalog matches and package counts. Mark open containers,
   unknown products, hidden stock, and incomplete areas explicitly.
5. Attach weighed partials to the same session and location. Resolve overlap
   across pictures and between full-package detections and open containers.
6. Show observed quantities, existing balance, proposed adjustments, excluded
   areas, unresolved questions, and evidence before approval.
7. Validate permission and baseline versions and commit the reconciliation once.

Session states: `draft → analyzing → review → committed`, with recoverable
analysis errors, cancellation, and an explicit `conflict` state. Manual sessions
can move directly from draft to review. Correcting a committed session creates a
linked adjustment workflow; it does not reopen history for silent changes.

A picture is an observation, not a receipt. An observed quantity replaces the
count basis for the reviewed scope through an adjustment; it is not added to
the old stock quantity. Re-photographing the same shelf must not increase stock.

Coverage must distinguish counted zero from not observed. An unphotographed
shelf, occluded package, or failed recognition never automatically means zero.
Review coverage before zeroing an expected item. Keep untouched locations intact.
Use stable observation IDs and image checksums for exact retries; near-duplicate
views still require overlap review because checksums cannot detect physical
duplicates across different pictures.

If a receipt, usage, transfer, another count, or relevant conversion edit changes
the counted scope while a session is open, reject stale approval with a conflict
and require review/recount. In the initial pilot, keep counted scopes quiet
during measurement where practical. Do not blindly overwrite newer movements.

## Partial inventory by weight

The store defines explicit reference weights for each item it weighs. A count
records each open container separately: item, location, container/session ID,
gross scale reading, tare profile or explicit tare, measurement unit, scale
precision, time, and actor. The default workflow is manual scale entry; connected
scales and reading the scale display from a photo are later integrations.

```text
net contents = gross measured weight - container tare
partial package equivalents = net contents / reference full-package net weight
combined stock = sealed packages × full-package net weight + sum(open net contents)
```

Reject negative net weight, zero/negative reference weights, unknown conversions,
and incompatible dimensions. Flag readings above an item's expected container
capacity for review; do not silently clamp them. Store the profile version used
so later calibration changes cannot rewrite old counts.

**Worked example, using illustrative weights:**

- A full package contains 1,000 g net.
- A photo shows eight containers: six sealed and two open.
- Open container A: 850 g gross − 100 g tare = 750 g contents.
- Open container B: 350 g gross − 100 g tare = 250 g contents.
- Inventory is `6 × 1,000 + 750 + 250 = 7,000 g`, or seven package equivalents.

The two open containers are excluded from the sealed package count. They are
not also counted as two full packages. Reweighing a container replaces its draft
measurement; it does not append another amount of stock. Opening a package is a
representation change, not a receipt or consumption event by itself.

If the prior book quantity for the same unchanged scope was 5,500 g, approval
posts a **+1,500 g count adjustment**, not a +7,000 g receipt. If a delivery arrives
during the count, version checks require reconciliation before approval.

## Phone capture and media handling

Capture should support the rear camera plus an existing-photo upload fallback,
retakes, upload progress, orientation correction, and recovery after a dropped
connection. Live browser camera access requires a secure context and permission;
the file-input capture option also needs device testing rather than assuming
identical behavior across phones. See [MDN camera access](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
and [MDN capture attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/capture).

The current server sends `Permissions-Policy: camera=()`. During the camera
phase, enable same-origin camera access specifically for the inventory capture
surface, retain microphone restrictions, and test both denial and approval.

Use private object storage, opaque keys, store-scoped access checks, and expiring
authorized retrieval. Validate decoded image type, file size and pixel limits;
normalize orientation and strip unnecessary location metadata. Set retention
and deletion rules for originals and derived images. Keep provider credentials
on the server and retain analysis/model version and correction history.

Images are untrusted evidence. Text printed in an image cannot become an
instruction to change records. Analysis output must satisfy a strict schema;
unknown or uncertain items remain unresolved until a person corrects them.
Do not infer hidden quantities, remaining contents, or weight from packaging
appearance alone. Shelf geometry/facings can suggest a review, never certify
stock the image does not show.

Evaluate representative pilot images by item identity accuracy, quantity error,
coverage, human correction effort, latency, and cost. Agree numeric thresholds
from the store's real examples before release; no accuracy promise is assumed in
this plan. Manual completion remains available for every supported item.

## Par and sales-based shortage insights

Initial alerts use measured/book inventory versus the store's par. Later insights
may use a separately labeled estimated balance based on sales since the last
applicable count and known movements. Track an accounting watermark so a sale
already reflected in a later physical count or posted usage is not deducted again.

Sales inputs need store, source IDs, timestamps/timezone, sold product/variant,
quantity, refunds/voids, and import freshness. Map packaged retail sales directly
through unit conversions; map prepared products through versioned ingredient
recipes, yields, and relevant modifiers. Unmapped sales remain visible as missing
coverage. Dollar-only sales require a store-approved historical usage relationship
and are labeled a lower-confidence estimate, not an exact item deduction.

```text
below-par gap = max(0, par - usable inventory)
days of cover = estimated usable inventory / expected daily item usage
reorder point = expected usage during supplier lead time + safety stock
target stock = max(par, expected usage during lead time + review period + safety stock)
```

Treat zero/unknown demand as insufficient evidence for a runout date. Account for
closed days and delivery dates; a delivery after the predicted shortage does not
prevent that shortage. Suggested orders consider reliable incoming stock,
committed outgoing stock, vendor pack sizes, and applicable capacity limits.
Round purchase quantities to valid packs after converting to the base unit.

Show the underlying quantities, data window, last count, sales freshness,
mapping coverage, lead-time assumptions, and confidence. Provide separate labels
for **below par**, **projected shortage before delivery**, and **count needed**.
Do not post a forecast as an actual stock movement. Measure prediction error
against later counts; automated ordering is outside the initial scope.

## Stretch goal: barcode/SKU invoice receiving

Choose or enter an invoice and its expected lines. Scan a product code, resolve
it to the store item and pack conversion, then record accepted delivered
quantity. Scanning updates the draft receiving checklist immediately; confirming
the receipt posts inventory and marks the received quantities on invoice lines.

Barcode values are not necessarily internal SKUs or unique physical packages.
GS1 product identifiers can appear on many identical units; explicitly map code,
supplier, item, and pack level. See [GS1 barcode guidance](https://www.gs1.org/standards/barcodes).
Keep leading zeros and distinguish a case code from a single-unit code.

Browser `BarcodeDetector` support is limited, so choose a tested fallback decoder
and retain manual code entry rather than making the native API mandatory. See
[MDN BarcodeDetector](https://developer.mozilla.org/en-US/docs/Web/API/BarcodeDetector).

Differentiate duplicate network events from legitimate repeated scans of the
same product: use unique scan-event IDs, not just the barcode, for retry handling.
For a pilot, allow barcode scan → quantity entry per invoice line to reduce
accidental repeated camera detections. An unknown code requires an authorized
mapping or a manual unresolved line.

Track expected, scanned, accepted, rejected, and outstanding quantities. Support
partial deliveries, damaged goods, overages, substitutions, returns, and reversal
of mistakes. A short delivery must not mark the invoice fully received. Unique
receipt-posting keys and line-level history prevent repeated confirmations or
imports from adding inventory twice.

Invoice OCR and direct supplier integrations can follow once structured/manual
invoice entry and scan-to-receive are dependable. The stretch feature uses the
same ledger, unit conversions, authorization, and audit rules as manual receipts.

## Proposed data groups

Names are design vocabulary; final tables and migrations are chosen per phase.

| Group | Records and relationships |
| --- | --- |
| Catalog | Store items, unit/pack conversions, weight profiles, container tare profiles, supplier/barcode mappings |
| Locations | Store-owned location hierarchy, shelf assignments, reference images, optional location targets |
| Policies | Versioned store-item pars, lead times, safety stock, permissions |
| Inventory | Movement events, balance projections, paired transfers, reversals and source references |
| Counting | Sessions, scope/version snapshots, observations, open-container measurements, approval records |
| Media and jobs | Private images, analysis jobs/results, model versions, uncertainty and corrections |
| Demand | Sales import batches/lines, source deduplication keys, recipes/conversions, forecast snapshots |
| Receiving | Suppliers, invoices/lines, scan events, receipt lines, discrepancies and posting links |

Use database constraints to prevent cross-store relationships, invalid units,
duplicate postings, and orphaned evidence. Preserve referenced historical item,
location, and conversion records through archiving/versioning.

## Release acceptance scenarios

| Scenario | Required result |
| --- | --- |
| Same photo/upload/approval replayed | One observation/posting; unchanged stock on replay |
| Two overlapping shelf pictures | Overlap resolved before approval; no double counting |
| Missing/hidden shelf contents | Explicit incomplete coverage; no automatic zero |
| Eight containers in the worked example | Six sealed plus 1,000 g open = 7,000 g total |
| Container reweighed or reference weight edited | Draft replaced or conflict shown; posted history preserved |
| Receipt or another count during counting | Conflict/review; no overwritten stock movements |
| Cross-store item, photo, job, invoice or location ID | Access denied without returning other-store data |
| AI outage or poor recognition | Durable failure state and manual completion; no invented stock |
| Sales import replay/refund/unknown mapping | No duplicate usage; corrections and gaps remain visible |
| Insufficient sales history | Below-par/count-needed guidance; no precise runout claim |
| Barcode case versus individual unit | Correct conversion to base units |
| Invoice received twice or partly received | Exactly one receipt posting; remainder stays outstanding |
| Interrupted/offline draft | Clear unsynced state; authorization and version checks on reconnect |
