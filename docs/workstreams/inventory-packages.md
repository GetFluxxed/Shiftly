# Package options and mixed inventory counts

Decision: 2026-10-01. Implementation and local verification evidence are recorded
below; CI, physical-device and hosted-release acceptance remain separate. This extends the existing catalog and count
boundaries and precedes [camera and invoice readiness](camera-and-invoice-readiness.md).

## Product and package identities

One stable company product is the ingredient or supply consumed by production.
Its store balance is measured in its existing fixed base unit (`each`, `g`, `kg`).
A package is a named, versioned conversion into that base unit, with zero or more
reserved barcodes. Package names need not match the product name. A case can
explicitly contain a whole number of one leaf package; it cannot introduce a
recursive packaging tree. At most 40 options, including archived options, belong
to one product. Barcodes and former aliases remain reserved in the company.

Examples: Bacio Base can have 2 kg and 2.5 kg options with separate names/codes.
Spoons can have a 1,000-item box and a case containing ten boxes (10,000 items).
Different spoon types remain separate products unless an owner explicitly
establishes equivalence. No package or shelf assignment establishes stock.

Migration 021 seeds one default package only where a real full-container amount
already exists. Unknown amounts stay unknown. Original product IDs, units, names,
SKUs, quantities, shelf placements and historical records remain intact. Existing
product forms retain their default-container reference, synchronized with the
active default package. Package edits bump the product version so open counts
cannot finalize against changed configuration. Active cases protect their leaf
conversion; archive dependent cases, explicitly update the conversion and restore
only when it is consistent.

## Counts and production

New count snapshots include the active package names, amounts, versions and
barcodes. Original count snapshots remain readable with their existing total or
full-container measurement. The additional package measurement sums exact decimal
`package count × saved full amount` plus a measured partial in the compatible unit.
Uncounted remains distinct from an explicitly saved zero. Package observations
are saved to a draft; only normal count approval changes the running balance.

A case’s contents are counted once: one case, or its loose full boxes and loose
items. Opening a case changes the breakdown and not the total. The UI explains
this distinction; the software cannot determine whether a person physically
counted an object twice. Each partial is a whole number of loose items; mass
partials accept grams or kilograms and exclude packaging weight.

Example: two 10,000-spoon cases, three 1,000-spoon boxes outside those cases and
250 loose spoons total 23,250. One 2 kg Bacio package, one 2.5 kg package and 250 g
partial total 4.75 kg. A recipe calling for 1 kg consumes 1.01 kg and leaves
3.74 kg, regardless of the packaging used. Recipes and production movements still
reference the same stable product ID; production does not guess which physical
package was opened. Package/location breakdowns represent the last count.

Count history retains the saved conversions. Later package edits, archive or
barcode changes do not reinterpret completed observations. Existing count baseline
versions, store locking, authorization and idempotent posting remain authoritative.

## Explicit linking of existing catalog entries

Migration 022 adds retained source-to-canonical links. An owner can review two
active products, their compatible units and package sizes, then explicitly combine
an uncounted duplicate into the selected canonical product. The source product,
SKU aliases and package records remain present; scanning their barcodes follows
the reviewed link to the canonical package. Store listings and shelf assignments
are unioned, and affected versions/audit records are updated atomically.

This setup action requires both products to have no count snapshots, balances,
movements or recipe revisions anywhere in the company, and no open company count.
It is intentionally not a historical stock merger. If history exists, the user
gets a blocker explaining the need for a reviewed reconciliation; no quantity,
recipe or old count is changed. Reconciliation of established stock requires its
own preview of overlapping quantities, explicit movement provenance and recipe
revision policy. Do not bypass the blocker with archive/delete or direct SQL.

Combining requires owner authority even when another account can manage packages.
The selected store and authority are checked in the transaction; replay must also
revalidate owner authority. Version checks reject outdated previews. No similar
names or shared supplier text automatically establish ingredient equivalence.

## Native workflow and acceptance

- Catalog → item → Packages & barcodes: add/edit/archive named options and their
  explicit full amounts or case composition; preserve drafts on recoverable errors.
- Unknown barcode: explicitly choose a new product or add a package to an existing
  company product. A recognized code shows the existing product/package.
- Count entry: compact package quantity controls plus loose items or net partial
  weight, with an immediate exact total and a measured-total alternative.
- Owner linking: select the main item, inspect sizes and affected shelf links,
  resolve blockers, then confirm. Keep original records and aliases reserved.

Verification must cover additive upgrade/default seeding and restoration, original
row preservation, package-specific barcode lookup, scope/capability/revocation,
version and replay conflicts, case dependency lifecycle, count snapshot precision,
recipe-plus-1% consumption, history retention, phone/tablet rendering, state
restoration and the explicit linking guard. Disposable PostgreSQL is mandatory for
tests. Back up the local demo before applying migrations; record CI, local runtime
and physical-device evidence separately.

## Verification and rollout

- Backend inventory, package linking, mixed counts, account upgrade and runtime
  migration checks: 218 tests passed across the focused suite and the corrected
  migration assertion rerun. The five initial failures expected the old total of
  20 migrations; the new total is 22. No behavior assertions were removed.
- Upgrade rehearsal on a private backup of the current demo: migrations 021–022
  seeded 39 known-size package options; every original row and original column
  across 40 existing tables matched its baseline. No product was combined.
- A fresh restore of the upgraded rehearsal dump matched the upgraded database.
  Both package integrity trigger functions matched the final migration SQL.
- Adjacent rendered inventory journeys passed (package setup/counting, catalog
  scanning, camera scanner and inventory restoration), including layouts from
  320 to 1440 px, owner combining and stale-draft rejection: 29 passed. The
  final four package journeys passed again after restoration corrections.
- Mobile typecheck and 111 unit checks passed. Scanned drafts retain their route
  context across warm/cold restoration; a new code starts its own draft. Strict
  shape validation retains all 40 package counts and rejects corrupted maps.
  The response parser preserves valid barcode aliases beyond 40; 40 limits package
  options, not former aliases. Final iOS and Android exports completed.
- Local demo upgrade completed after stopping the API and taking another private
  backup: 021–022 applied, 39 packages seeded, all original columns/rows across
  40 tables preserved. The API restarted healthy and Expo advertises the local LAN.
  No products were automatically combined and no count/balance was changed.
- No new CI, hosted deployment or physical-device result is claimed.

## Labelled pounds and metric stock — 2026-10-02

The package label and the stock unit are separate. Product base units remain
`each`, `g` or `kg`; a new product entered using pounds stores its balance in kg.
Existing products keep their fixed base unit. Full-container and package forms
accept pounds (`lb` in the API, `lbs` on screen) and retain the entered amount/unit
alongside the canonical metric amount. For example, one 50 lb bag contributes
22.6796185 kg, and two full bags plus 500 g net partial contribute 45.859237 kg.
Changing a package reference never creates stock or changes a posted count.

Conversion uses decimal arithmetic and the exact factor 0.45359237 kg per pound.
Migration 024 widens package and default-container references to nine decimal
places, matching stock precision, and adds nullable label metadata. Existing rows,
identities, balances and count history are preserved; the upgrade does not infer
label weights for existing products. Pounds accept at most six input decimals;
metric references accept nine. Conversions needing more than nine canonical
decimals round half up once at configuration time, retain the original input,
and show an approximate conversion preview. Values that round to zero or exceed
the package limit are rejected. Counting multiplies the saved reference exactly.

Default-package and product-container metadata stay synchronized. Name-only edits
retain original labels. Cases derive their canonical size from their child package
and do not carry an independent label conversion. Count snapshots retain package
label metadata and canonical amounts; later edits cannot reinterpret those saved
references. Package combination retains labels and still blocks conversions that
cannot preserve the recorded canonical amount exactly.

The UI keeps partial counts in kg/g and shows the pounds label with its metric
equivalent. Barcode-free products continue to use manually assigned internal SKUs.
Litres are not added in this slice: a later volume-labelled package needs an
explicit product-specific net contents weight; never assume one litre is one kg.

Local verification and rollout:

- 73 focused backend package, quantity, mixed-count and retry checks passed.
  Another 14 package-link checks and 33 migration/account/API upgrade checks passed.
  The retry regression reconstructs the pre-024 request fingerprint and response.
- Mobile typecheck and 120 native tests passed; final iOS and Android bundles
  exported successfully. A final typecheck followed the read-only and package
  size guards.
- Sixteen distinct rendered native journeys passed across pounds entry, package
  setup, catalog/scanning and adjacent product workflows. The new end-to-end
  journey saved a barcode-free 50 lb product, restored its label, and posted two
  full bags plus 500 g as 45.859237 kg. Layout checks covered 320–1440 px; phone
  product and count screenshots were inspected. One initial journey failed due
  to a test selector using `g` instead of the existing `Grams` label; its corrected
  rerun passed.
- Private backup → disposable upgrade → upgraded backup restore preserved every
  original row/column across 44 tables. Migration 024 was then applied locally
  after stopping the API/worker and taking a fresh private backup; the same
  original-data check passed. API health, worker heartbeat and Expo status passed
  after restart. No stock or count was automatically reinterpreted.
- Product/package draft keys are versioned for the new unit field. Old unsaved
  drafts reset once rather than having an old numeric value assigned a new unit;
  saved products, packages and count drafts/history remain intact.
- CI, hosted deployment and physical iPhone acceptance are not claimed here.

## Inventory navigation audit — 2026-10-02

Inventory screens previously chose a fixed back destination, losing the page that
opened them. This skipped the catalog, count session, history or stock detail in
several flows. A bounded inventory-only route trail now records immediate parents;
forward links, form completion and Back have distinct behavior. Revisited pages
retain the immediate origin. New-product completion replaces its form while
preserving the catalog or shelf that opened it. Creating a shelf keeps Open Shelves
as its parent. Package combinations omit an obsolete source-product parent only
when that product is the immediate parent.

Audited journeys include catalog → product → packages; shelf → new product;
stock → product → physical count; count start → entries → individual entry/review;
history → review → entries; and scanner → code choices → new product or existing
product/package. Scanner camera and choice screens return one internal step at a
time. Returning to scanner refreshes the saved barcode lookup and preserves the
code/picker or unfinished draft. Explicit new-product cancellation discards its
draft; ordinary Back keeps it. Count entry header/footer share the unsaved-entry
confirmation, and the header is disabled during save. Return to counting opens
the entries after the server successfully reopens the count.

The existing scoped checkpoint persists the sanitized trail (at most 12 known
Inventory routes, 4,096 serialized characters). It retains only allowed count and
package parameters; no credentials, server records, external URLs or arbitrary
route destinations. Existing account/store/permission invalidation applies.
Missing/malformed origins use each screen's immediate-parent fallback. Same-stack
Back uses Expo dismissal; crossing the app's separate hidden tab stacks uses
replacement because stack-only POP_TO cannot select another tab.

Local evidence: mobile typecheck and 125 native tests passed. Twenty-nine distinct
browser-rendered native journeys passed, including five navigation regressions,
cold restoration, draft protection, package combination and camera exit. The two
initial new journey failures were resolved by waiting for the destination/save
before the next test action and rerunning them successfully. Boundary tests also
caught and corrected accidental nested trail retention. The renderer enforces the
same-stack limitation for dismissal. Final iOS and Android exports passed.
Physical iPhone gestures/hardware navigation and CI are not claimed by these checks.
No API/schema/data changes were required for this navigation revision.

## Catalog measurement correction and mobile copy — 2026-10-02

Catalog cards keep their compact structure and gain a permission-gated **Change**
action. Product details show a short measurement summary with the same action,
rather than permanently displaying measurement fields and explanatory paragraphs.
The editor follows the shelf-name sheet: a bottom sheet on phones, centered dialog
on tablets, scrollable fields, fixed Save/Cancel actions, and explicit loading,
retry and stale-edit recovery. Saving refreshes catalog data while retaining its
search/filter/page. Editing the name or SKU must be saved or discarded before
opening a separate measurement edit from product details.

The dedicated `GET/POST /api/mobile/inventory/products/{id}/measurement` boundary
requires catalog management and inventory access. GET returns current product
state, change blockers and a current-recipe count, without exposing recipe names.
POST rechecks selected store, policy, version and dependencies in the mutation
transaction; writes are audited and idempotent. Count creation and correction
share the existing account-policy lock. Unauthorized replay remains denied.

A mistaken counting unit can change among each/g/kg only before the product has
any count snapshot, stock balance, movement or production-log evidence anywhere
in the business. Combined catalog identities, redirected packages, multiple
packages or nondefault packages block correction because their conversions need
a separate reviewed workflow. A single existing default package keeps its ID,
barcode aliases and active state; it requires an explicit replacement amount.
An inactive default remains inactive with its legacy product-container mirror
cleared. Name, SKU, product ID, shelves and archived state are preserved. There
is no migration and this workflow never creates or converts stock.

Changing the counting unit clears the draft amount. Container references accept
each/g/kg/lbs using the established exact conversion rules; ordinary amount-only
edits use the existing product editor. A litre-labelled container still requires
its actual net weight. Volume alone is insufficient and no one-litre-equals-one-kg
assumption or guessed density is introduced.

Current recipes require acknowledgement before correction. Their saved units and
quantities remain immutable. Recipe reads additionally expose the current catalog
unit, and the editor detects mismatches, selects the current unit controls and
requires a fresh amount before saving a new revision. Remembered recipe drafts
include the unit signature in their baseline, so an older `each` draft cannot
silently become kg. Existing production checks block a unit-mismatched recipe
against current stock. Previous recipe revisions remain readable and unchanged.

Renaming a SKU and archiving a product deliberately retain its earlier barcodes.
The product detail hint now states this directly. Correct the existing product
instead of recreating it under the same barcode. Barcode reassignment remains
outside this change. Heavy Cream and its Stracciatella recipe are not automatically
edited; the user must supply the actual container weight and recipe quantity.

A mobile copy review covered inventory, scanner, shelves/counts, packages,
production/recipes, Today, account/team/owner tools, activation and reports.
Redundant descriptions and implementation terms were removed or condensed, and
actions use direct labels. Essential invitation privacy/expiry, permission scope,
consequential confirmations, uncertain-save recovery, +1% production allowance,
unknown stock and forecast limitations remain. The reference was Apple's
[Writing guidance](https://developer.apple.com/design/human-interface-guidelines/writing).
Legacy browser pages were not rewritten by this mobile pass.

Local verification: mobile typecheck and 128 unit checks passed; iOS and Android
exports passed. Focused backend correction checks passed (12), alongside the
related package/container/production regression set (75 before the final inactive
package preservation check). Twenty-five account, Heads Up and restoration
rendered journeys passed. Fifty-one distinct inventory, measurement, production,
scanner and reporting journeys passed across the focused runs and corrected
reruns. Checks exposed an undefined optional draft field that broke JSON draft
restoration; using an explicit null fixed it. A compact empty assigned-products
row also prevents a first-assignment shelf-picker jump. Other initial failures
were outdated copy selectors or a save assertion racing the response; corrected
selectors wait for completion without weakening persistence assertions.

The measurement sheet was inspected at 320 and 1024 px and in short landscape;
its footer stays inside the viewport across 320/768/1024/1440 px and 568×320.
Native typecheck and both exports passed again after the final shelf adjustment.
The existing local API was restarted; API/worker health and Expo status passed,
and the new endpoint rejects unauthenticated reads. No live inventory or recipe
values were changed and no commit, publication or hosted deployment was performed.
These checks do not establish physical-device or hosted/CI acceptance.


## Publishing verification — 2026-10-03

The first published CI run passed mobile checks and both native exports, but
exposed two test-environment issues: three minimal identity settings fixtures
omitted the forecast provider key, and two rendered journeys wrote screenshots
to a macOS-only temporary directory. The fixtures now explicitly disable the
provider, and screenshots use pytest-owned temporary folders on every platform.
Production behavior and test assertions are unchanged. The focused identity suite
(17 tests) and both affected rendered journeys passed locally after correction.
The pull request records CI results for the exact published revision.
