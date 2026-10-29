# Shiftly inventory rules

Reviewed against source revision `df53f98` on 2026-10-21. This is the maintained
contract for catalog, packages, quantities, counts, stock, production and
forecasts. The first part describes implemented behavior. The
[future rules](#future-inventory-rules) section is approved design for work not yet
built. Endpoints are listed in [API.md](API.md#native-inventory-and-counts); screens
in [WORKFLOWS.md](WORKFLOWS.md). The dated decision and verification records are
[archived](archive/README.md).

Source owners: `backend/shiftly/inventory/` (catalog, packages, shelves, counts,
movements), `backend/shiftly/production/`, `backend/shiftly/forecasts/`, and
`apps/mobile/src/inventory/`, `apps/mobile/src/production/` and
`apps/mobile/src/reports/`.

## Scope and authority

- A **business** owns one shared product catalog and its recipes. Each **store**
  owns its product listings, shelves, counts, balances, movements, production logs
  and forecasts. No second organization system exists.
- Every protected write calls `accounts.require_selected_store(...)` inside the
  mutation transaction and derives business, store and actor from the result.
  A submitted `storeId`, hidden control or object ID never grants authority.
- Capabilities: `inventory.view` (read), `catalog.manage` (shared products and
  packages), `configuration.manage` (store shelves and listings), `counts.submit`
  (enter and submit counts for review), `counts.approve` (post, reopen or cancel a
  count), `recipes.manage`, `production.view`, `production.submit` (confirm
  production), `production.manage` (reverse a log) and `forecasts.view`.
  Combining duplicate products requires the owner role.

## Catalog and shelves

- A product has a stable ID, a name (1–160 characters), a SKU (1–64 ASCII
  letters/digits and `._/-`, starting with a letter or digit), a fixed base unit
  and an active/archived state.
- SKUs and barcodes are strings; leading zeros are kept. Uniqueness uses a
  trimmed, case-insensitive key within the business. Former SKUs stay reserved
  aliases and remain searchable.
- Editing a name or SKU changes the same shared product for every store. Versions
  reject stale edits (`409 stale_record`); duplicates return
  `409 duplicate_identifier`.
- Archive instead of deleting. Archived products keep their history, balances and
  shelf placements (labelled archived) and block new placements. An authorized
  user can restore them.
- Shelves (1–120 characters, unique per store) are store configuration. Assigning
  a product creates or reactivates the store listing and a placement. Removing it
  deactivates only that placement. **A placement never creates stock.**
- Catalog lists and pickers are A–Z by normalized name with a stable ID tie-break
  and an opaque cursor. Lists return at most 40 records per page. Lists are live,
  not snapshots.
- Not yet exposed: store-listing deactivation, shelf deletion and a location
  hierarchy.

## Units, containers and packages

- **Canonical stock units** are `each`, `g` and `kg`. A product's base unit is
  fixed at creation. Legacy `ml`/`l` products stay readable, but new volume
  products are rejected.
- **Full-container amount** (`containerAmount`) is the net contents of one full
  container in the base unit. It is a reference, never an amount on hand. Unknown
  stays `null`, never zero.
- **Packages** are named, versioned conversions into the base unit, with reserved
  barcodes. There are at most 40 options per product, including archived ones. A
  case may contain a whole number of one leaf package; packaging cannot nest
  further. Package edits bump the product version, so open counts cannot finalize
  against changed configuration.
- **Package labels** may be entered in `each`, `g`, `kg` or `lb`.
  - Pounds convert with the exact factor 0.45359237 kg/lb. The canonical amount
    is rounded half-up once, at configuration time, to nine decimals. The original
    label amount and unit are kept for display.
  - Pound input accepts at most six decimals.
  - Example: a 50 lb bag is 22.6796185 kg.
  - Cases derive their size from the child package and carry no label of their own.
- **Volume-labelled goods** need an explicit, product-specific net weight. Shiftly
  never assumes 1 litre = 1 kg or any density. Which net weights to use is an
  [open decision](IMPLEMENTATION_PLAN.md#open-owner-decisions).
- **Correcting a mistaken base unit** is allowed only while the product has no
  count, balance, movement or production-log evidence anywhere in the business,
  and no combination links, multiple packages or non-default packages. Current
  recipes must be acknowledged; their saved revisions stay unchanged and the
  editor requires a fresh amount before a new revision. Correction never creates
  or converts stock.

## Barcodes

- Scanning is catalog identity lookup only. It saves no photo, calls no AI, and
  creates no stock or receipt.
- Lookup is an exact, bounded alias search within the company, including former
  SKUs and archived products. A creation form opens only after an explicit
  "missing" response, never after a network failure.
- UPC-A and its leading-zero EAN-13 form resolve to one canonical 13-digit SKU,
  and both strings are reserved.
- Valid EAN-8, UPC-A, EAN-13 and ITF-14 values also match equivalent zero-padded
  forms. Only all-zero prefixes are removed; non-zero case indicators stay distinct.
- UPC-E matches exactly, with no expansion.
- Ambiguous existing aliases block the action for review.
- Accepted symbologies include EAN-8, UPC-E, ITF-14, Code 128, Code 39, Code 93 and
  Codabar, plus verified native type names (for example, `org.iso.Code39`). iOS
  EAN-13 values with the leading zero stripped are normalized when the UPC check
  digit is valid.
- Supplier shipment stickers may change per delivery. Prefer manufacturer barcodes
  or stable internal SKUs. Supplier-to-pack mappings belong to future receiving.

## Combining duplicate products

An owner may combine an uncounted duplicate into a canonical product after
reviewing a preview of units, package sizes and affected shelves.

- Both products must have no count snapshots, balances, movements or recipe
  revisions anywhere in the company, and no company count may be open.
- The source product, its aliases and packages are retained. Scans follow the
  link to the canonical product, and listings and placements are unioned.
- Combining is not a historical stock merger. When history exists, the action is
  blocked; reconciling it needs a separately designed, reviewed workflow (an
  [open decision](IMPLEMENTATION_PLAN.md#open-owner-decisions)).
- Similar names or supplier text never establish equivalence automatically.

## Counts

**Session rules**

- There is one open whole-store count per store. It snapshots every active store
  product at each active shelf placement, or at one "Unassigned" location.
- The snapshot captures names, units, container/package references, versions and
  previous balances (nullable).
- Lines are never added or removed mid-session. Configuration or stock changes
  make the count stale; cancel it and start a new one.

**Entering counts**

- Each line starts uncounted, and saving zero requires confirmation.
- An entry is one of:
  - a measured total;
  - full containers plus a net partial; or
  - package counts plus loose items or a net partial.
- Mass partials accept g or kg (packaging excluded) and convert exactly. `each`
  quantities are whole numbers.
- A case's contents are counted once. Opening a case changes the breakdown, not
  the total. The software cannot detect a person physically counting an object
  twice.
- Worked example: two 6 kg containers plus a 1,250 g net partial is 13.25 kg.

**Lifecycle**

- The lifecycle is draft → review → posted, with reopen (review → draft) and cancel.
- Every required line must be counted before review and posting.
- Drafts and review never change stock.
- Posting rechecks versions, scope, completeness and authority. It then writes
  observations, immutable movements and balances in one transaction.

**Effect on stock**

- The first posted count establishes the opening balance; there is no assumed
  prior zero.
- Later differences are stock adjustments, not consumption or sales.
- Count history keeps the saved conversions. Later package or container edits
  never reinterpret posted counts.
- Counts assume a stable stock cutoff, normally after service. Reconciling during
  active service is deferred.

## Stock and movements

- `inventory_stock_movements` is immutable history.
  `inventory_stock_balances` is the transactionally maintained projection, with a
  monotonically increasing version.
- The last physical count date is shown separately from later movements.
- Unknown stock is shown as not counted (`N/A`), never zero. Shelf rows show the
  storewide balance, not a per-shelf balance.
- Count posting and production share a store lock. A production change makes an
  older open count stale, even if a reversal returns the same quantity.

## Recipes and production

**Recipes**

- Recipes are business-scoped and revisioned. Each edit creates a new revision;
  past production keeps its original revision.
- Yield is recorded information (the native editor offers 4.5 kg or 6 kg). It never
  rescales ingredient amounts or acts as a unit conversion.
- Recipe g/kg entries keep the original entry and convert exactly to the catalog
  base unit.

**Confirming production**

- A production draft and its preview never deduct stock.
- On confirmation, each ingredient is deducted by **recipe quantity × confirmed
  batches × 1.01**.
  - Recipe usage and the 1% allowance are stored separately.
  - Example: 1 kg per batch × 2 batches = 2 kg + 0.02 kg = 2.02 kg.
  - The deduction is an estimate, not a weighed measurement.
- Confirmation is a single transaction. Unknown opening stock, insufficient stock,
  an inactive ingredient or a changed unit blocks the whole submission. At most 500
  unique ingredients are allowed per submission.
- `each` ingredients may show fractional theoretical use because of the allowance.

**Retries, reversal and limits**

- A stable log ID plus request fingerprints prevent duplicate deductions. An
  uncertain result freezes the payload until the original log is checked or the
  exact submission is retried.
- `production.manage` can reverse a complete confirmed log, with a reason, using
  the original quantities. A later physical count that supersedes the log blocks
  reversal.
- Finished product is not received into stock automatically.
- Scale readings will never verify production usage.

## Advisory forecasts

**Access and inputs**

- Viewing or requesting a forecast requires `forecasts.view`, `reports.view`,
  `production.view` and `inventory.view` together.
- A snapshot covers the selected store only and is bounded to the last 28 days. It
  includes:
  - confirmed, unreversed production with its recipe revisions and deductions;
  - relevant current recipes;
  - stock with count and movement freshness;
  - up to 50 recent shift notes.
- Source text is treated as untrusted. Coverage and truncation are disclosed.

**Deterministic part**

- Source facts (daily batches, ingredient usage, stock as-of) are calculated
  exactly from recorded data.
- Fewer than seven distinct production days returns the facts with an
  insufficient-history message and no model analysis.
- Production is not sales, missing days are not zero, count differences are not
  consumption, and unknown stock is not zero.

**Model-generated part**

- The configured provider model receives the bounded snapshot and returns a
  summary, trends, risks, limitations and per-recipe batch suggestions for the next
  three days. The call uses the Responses API with strict structured output and
  `store: false`.
- Output is validated against active recipes, the allowed dates and whole-batch
  bounds.
- Suggestions are advisory. They are not purchasing deadlines or staffing
  instructions, and no output can change stock or recipes.

**Processing and freshness**

- Confirmed production queues an analysis transactionally. Authorized managers
  may also request one.
- The separate worker processes jobs with request idempotency, leases and bounded
  retries.
- New counts, production, reversals, recipe edits or relevant reports mark the
  saved analysis stale.

**No training**

- Each request analyzes the supplied records. Nothing trains or fine-tunes a model
  on company data.
- Forecast quality has not been evaluated against real outcomes (see
  [roadmap item 5](IMPLEMENTATION_PLAN.md#5-evaluate-advisory-forecasts-pilot)).

## Retries and conflicts

- Every native inventory/production write carries `expectedStoreId` and a UUID
  `requestId`. An identical replay by the same actor and store returns the
  original result. The same ID with different content is `409 state_conflict`.
- Authorization is rechecked before a replay.
- Clients never retry an uncertain write automatically.
- Replay records currently have no expiry; choosing a retention policy is an
  [open decision](IMPLEMENTATION_PLAN.md#open-owner-decisions).
- Error codes and native recovery behavior are in [API.md](API.md#errors-and-recovery).

## Future inventory rules

Approved design for unbuilt capabilities. Implementation must follow these rules
or record an explicit owner decision changing them.

**Shelf-photo proposals.** These are governed by the
[camera and invoice plan](workstreams/camera-and-invoice-readiness.md):
- A photo is an observation, not a receipt.
- Proposals are reviewed and saved as count observations; normal count approval
  changes stock.
- Re-photographing the same shelf must not increase stock. Overlapping photos and
  a full package plus its weighed partial must not double count.
- Coverage distinguishes counted zero from not observed; hidden or occluded stock
  is never automatically zero.
- Photos never infer partial weight or hidden quantities. Text inside images is
  untrusted input.

**Scale-assisted counts** (deferred until hardware is chosen):
- The user selects store → open count → location → SKU before capturing a stable
  reading.
- Store gross weight, explicit tare, net weight, unit, device time and a unique
  capture ID.
- A reweigh replaces that container's observation. Duplicate transmissions cannot
  add twice.
- Reject negative net weight. Flag readings above expected capacity rather than
  clamping them.
- Formulas: `net = gross − tare`; `combined = sealed × full net + Σ open net`.
  Calibration changes must not rewrite old counts.

**Receiving.** See the camera and invoice plan:
- Barcodes map explicitly to supplier, item and pack level. Case codes differ from
  unit codes.
- Track expected, accepted, rejected and outstanding quantities, including
  partial, damaged, substituted and returned goods.
- Posting is idempotent and line-level. A short delivery never marks an invoice
  fully received.

**Movements.** Waste, usage, transfers and manual adjustments need a reason, an
actor and a source reference. Transfers post balanced source/destination entries
atomically. Corrections use linked reversals or replacements.

**Pars and insights:**
- Each store-item has one par in the base unit, with history. Optional shelf
  targets are not summed into purchasing par.
- Alerts compare book or measured stock with par, using separate labels for below
  par, projected shortage and count needed.
- Sales-based estimates are a separately labelled view. They use an accounting
  watermark so already-counted sales are not deducted twice. Unmapped sales stay
  visible as missing coverage.
- Formulas:
  - `gap = max(0, par − usable)`
  - `days of cover = usable / expected daily usage`
  - `reorder point = lead-time usage + safety stock`
- Zero or unknown demand is insufficient evidence for a runout date. Automated
  ordering is excluded.

**Locations:** area → rack → shelf → optional bin, with optional capacity and
reference images. Planned placement never proves presence.

### Future acceptance scenarios

| Scenario | Required result |
| --- | --- |
| Same photo/upload/approval replayed | One observation/posting; unchanged stock on replay |
| Two overlapping shelf pictures | Overlap resolved before approval; no double counting |
| Missing/hidden shelf contents | Explicit incomplete coverage; no automatic zero |
| Container reweighed or reference edited | Draft replaced or conflict shown; posted history preserved |
| Receipt or another count during counting | Conflict/review; no overwritten movements |
| Cross-store item, photo, job, invoice or location ID | Denied without exposing other-store data |
| AI outage or poor recognition | Durable failure state and manual completion; no invented stock |
| Sales import replay/refund/unknown mapping | No duplicate usage; gaps remain visible |
| Barcode case versus individual unit | Correct conversion to base units |
| Invoice received twice or partly received | Exactly one posting; remainder outstanding |
