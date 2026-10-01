# Production, assisted counting and forecasting

Decision date: 2026-09-29. The user approved these four next capabilities. This
contract supersedes the older camera-before-production ordering in the broad
inventory plan. Delivery proceeds in independently verified slices; a listed
future phase is not a claim that its UI, hardware or AI integration exists.

## Accepted product decisions

- A separate **Production** account type has crew-level inventory/Heads Up access,
  plus recipes and daily production. It has no shift Reports or Store workspace,
  cannot switch stores, cannot manage accounts, and cannot grant itself access.
  Invitations still activate baseline crew; an authorized administrator changes
  the role afterwards. Server authorization must match the hidden tabs.
- Recipes belong to the company catalog so stores can reuse the same ingredients
  and flavors. Stock and production logs always belong to the selected store.
- Each flavor has a named recipe, explicit batch yield and ingredient amounts.
  The native editor offers **4.5 kg** or **6 kg** as yield choices; ingredient
  amounts remain entered explicitly and are not rescaled when yield changes.
  Existing recipes retain their recorded yield until deliberately edited.
  Recipe editing creates a new revision; past production retains its old recipe.
- The ingredient picker uses the shelf page's compact cards, alphabetical search,
  **+ add / − remove**, and a clear amount/unit field per selected ingredient.
  SKU is shown only where choosing the ingredient requires disambiguation.
  Recipe summaries stay read-only until **New Recipe** or **Edit Recipe** opens
  a modal editor. Name, yield, instructions and ingredient controls live inside
  the editor with **Save Recipe** and **Cancel**. Cancel discards an unsaved draft;
  uncertain saves stay locked for recovery instead of permitting cancellation.
- Production staff select flavors and use batch counters to record several of
  the same flavor per day. Draft selection and review never deduct stock.
- An explicit confirmation records production and deducts **recipe quantity ×
  batches × 1.01 for every ingredient**. This is the user's chosen 1% allowance,
  replacing the earlier proposed ±1% measured tolerance. For example, 1 kg per
  batch × 2 batches = 2 kg recipe usage + 0.02 kg allowance = 2.02 kg deducted.
  Store recipe usage and allowance separately; label this as estimated usage,
  never as a scale-verified measurement.
- Scale readings will count inventory for an explicitly selected SKU/location.
  They will not verify production ingredient usage. Hardware connection is
  deferred until the user selects a scale and protocol.
- Forecasts are manager/owner, per-store views. Numerical calculations use the
  recorded data; the existing configured LLM explains the results. It cannot
  change stock or invent demand history.

## Slice 1 — Recipes and confirmed production

1. Extend the count-only stock model to one immutable movement history and a
   balance projection. Keep last physical count/date separate from last stock
   movement/date. Backfill existing count evidence without inventing quantities
   for unknown stock. Each product balance has a monotonically increasing version.
2. Add production account capabilities through the existing identity policy and
   a new migration. Preserve baseline crew invitations and single-store access.
3. Add revisioned recipe creation/editing, native ingredient cards and recipe
   viewing. Managers/owners manage recipes; production staff view/use them.
4. Add daily flavor selection, whole-batch counters, a server-calculated preview,
   explicit confirmation, and immutable store-scoped production history.
5. Confirm all ingredient deductions in one authorized transaction. Stable log
   identity plus request fingerprints prevent duplicate deduction after retries,
   lost responses, multiple devices or changed request IDs. Unknown opening stock
   and insufficient stock block the whole submission with actionable messages.
6. Managers/owners can reverse a complete confirmed log with a reason. Use exact
   original quantities, independent of later recipe edits. A physical count that
   supersedes the log blocks reversal; reconcile with a fresh count instead of
   adding old stock back after physical verification.
7. Snapshot the balance version when starting a count. A production change makes
   an older open count stale, even if a later reversal returns stock to the same
   quantity. The first slice requires a quiet counting period; cutoff-based
   reconciliation during active production is a later design.

Exact decimal strings cross the API; PostgreSQL NUMERIC/Decimal owns arithmetic.
Convert g/kg explicitly. Keep nine decimal places at most and reject quantities
that cannot be represented exactly rather than silently rounding each batch.
Theoretical recipe consumption may be fractional for an `each` ingredient because
of the 1% allowance; physical piece counts still require whole numbers. Yield is
recorded information, not a covert ingredient unit conversion. Finished-gelato
stock is not automatically received; that requires an explicit finished-product
mapping and future receiving workflow to avoid creating duplicate stock.

User recipes/yields are not seeded until supplied. No invented recipes become
company data. Library setup remains available inside the app.

## Catalog barcode scanning — 2026-09-30

The user brought barcode-assisted catalog entry forward so ingredient setup can
finish before shelf-photo counting. This is catalog identity capture, not a stock
receipt, physical count or AI inference. No provider calls, stored images or
schema migration are required.

The native route is **Inventory → Catalog → Scan product**. Expo Camera is included
in Expo Go; the SDK-compatible dependency is installed through Expo. Open camera,
scan one printed barcode, then review the company catalog result. Manual code entry
remains available when camera permission is denied or a label cannot be read.
A missing product opens the shared product form with its SKU filled and locked;
enter its name, base unit and optional full-container amount, then explicitly create
it. **Scan next product** continues the workflow. Catalog changes still require
`catalog.manage`; inventory viewers can look up codes but cannot create products.

`GET /api/mobile/inventory/products/lookup` performs bounded exact alias lookup
within the authenticated company, including old SKUs and archived products. Only
a successful response with an explicit missing result opens creation. It does not
infer absence from a network failure, fuzzy search or first-page results. An
archived match must be deliberately restored through existing product controls.

UPC-A and its leading-zero EAN-13 representation resolve to one canonical 13-digit
SKU; creation atomically reserves both strings in the existing SKU alias table.
All other zeros remain text. EAN-8, UPC-E, ITF-14, Code 128, Code 39, Code 93 and Codabar
follow the existing bounded SKU character rules; UPC-E is exact-only with no
expansion into other formats. Ambiguous existing UPC/EAN aliases block the action
for review. Concurrent saves cannot create a second product with the same reserved
code. Manual catalog creation keeps its existing SKU semantics. Supplier barcode
mapping to a different internal SKU/pack size remains a separate receiving phase.

The camera mounts only in the scanner, stops on background/navigation/error, and
suppresses repeated frames after the first accepted code. Permission is requested
on explicit user action, with settings/manual-entry alternatives after denial.
No microphone is requested and no photos are saved or uploaded. The code and new
product fields use existing account/store-scoped draft restoration; camera preview
state is not restored automatically. A lost create response can be checked by code
before retrying; the unique alias reservation also protects delayed/concurrent saves.

Physical iPhone/Android scanning, permission prompts, background return and torch
behavior remain device acceptance checks. Browser-rendered journeys exercise the
catalog workflow with manual entry; mocked camera events cover lifecycle boundaries
without claiming hardware verification. Shelf camera counting remains deferred
until the ingredient catalog is filled out.

Local verification completed: mobile TypeScript and 105 behavior tests; both
native platform exports; barcode identity/authorization/concurrency service checks
and the existing non-rendered inventory service suite; nine rendered catalog,
scanner and shelf journeys; and six mocked-native camera permission/lifecycle
journeys. Phone/tablet layouts were checked at 320, 390, 1024 and 1440 pixels.
A follow-up compact-form journey passed after visual refinement. These are local
results; this new slice has not been committed or verified by CI. Navigation blur
uses the existing focus cleanup; the camera harness separately exercises background
and unmount cleanup rather than a real native navigator. Physical camera/device
acceptance remains outstanding.

## Real-label barcode compatibility — 2026-09-30

The supplied iPhone failures exposed two concrete library/server mismatches. In
the installed `expo-camera` 57.0.6, `ios/Current/BarcodeScannerUtils.swift` removes
one leading zero from EAN-13 data while leaving its type as `ean13`. The backend
previously required 13 digits for that type. Its normalization boundary now accepts
exactly 12 digits only with a valid UPC check digit, restores the equivalent
leading-zero EAN-13, and looks up/reserves both strings. It does not pad arbitrary
lengths, weaken checksums, merge products or change manually entered SKU semantics.

The iOS ZXing path in `ios/barcode-scanning/ExpoCameraZXingProvider.swift` can emit
AVFoundation raw type names. The backend now explicitly accepts verified native
aliases, including `org.iso.Code39`, alongside the existing Expo short names.
Code 93 is enabled, with its actual Apple identifier `com.intermec.Code93`.
Observed Vision EAN-13 and Code 39 names are also supported. Guessed/fuzzy names,
QR codes and generic Interleaved 2 of 5 remain outside this contract; arbitrary
shipping numbers are not treated as validated GTIN-14 identifiers.

Independent local Apple Vision decoding confirmed these supplied retail labels:

| Printed code | Equivalent canonical catalog barcode |
| --- | --- |
| `085900233161` (peanut butter UPC) | `0085900233161` |
| `072965103249` (PNuttles UPC) | `0072965103249` |
| `0851085002553` (powder label) | `0851085002553` |
| `0817304018828` (powder label) | `0817304018828` |
| `652729105650` (Eagle Foods UPC) | `0652729105650` |

The milk supplier sticker decoded as Code 39 `6749118517`. Its stability across
deliveries is not established; the printed vendor item number is different.
The sugar screenshot did not decode reliably. Neither shipping sticker was
automatically saved as a catalog product. Request a close, straight-on source
label for the sugar and prefer manufacturer barcodes or explicitly chosen stable
internal SKUs when shipment identifiers vary. Missing package weights and case
contents are not inferred from barcodes or photos.

Native scanner controls now include bounded zoom in/out for small print, clearer
focus guidance, and Code 93 scanning. Zoom has no misleading optical multiplier;
the native device determines its effective magnification. Lookup failures retain
the received code and offer Scan again as well as Change code and Reload. The
existing camera lifecycle, one-result guard, permissions and manual fallback remain.

Local verification: TypeScript and 105 mobile tests passed; 57 focused service/API,
catalog and mocked-native camera tests passed against disposable PostgreSQL.
Coverage includes all five retail codes, the exact milk payload, native aliases,
checksum/length failures, lookup/create/replay, duplicate prevention, role/company
scope, archived aliases, preservation of shelf/count state, zoom bounds, repeated
frames, retry and manual recovery. Phone/tablet rendered captures were reviewed;
their camera and icon adapters do not establish physical-device behavior.

The running LAN demo API was refreshed and Expo served the updated iOS bundle.
Before/after full-row fingerprints match for all 20 products, 24 shelf assignments,
3 stock balances and 3 count-history records. No migration, stock adjustment,
catalog import, commit, push or hosted deployment was performed. Retrying the
physical labels on the iPhone, especially sugar and very small print, remains the
device acceptance step.

### Repeat scans and named catalog confirmation — 2026-09-30

An existing scan now says **[product name] is already in the catalog**, with View
product and Scan next product actions. It does not open the creation form. Archived
matches name the item and explain restoration. A concurrent duplicate discovered
while saving uses the same existing-product message instead of implying a new item
was created. A successful new save explicitly says the product was added.

The user identified Low-Heat Non-Fat Dry Milk, then confirmed the saved code
`6749118517` and said the report may have been a mistake. No milk-specific
recognition failure was reproduced. A new rendered journey drives actual native
scanner callbacks through catalog screens and the real API: create the milk, scan
again with both Expo and Apple Code 39 type names, verify the named result and the
absence of a creation form, and retain exactly one product without stock writes.

Read-only investigation separately found saved 14-digit identifiers that would
not match equivalent shorter retail scans. Valid EAN-8/UPC-A/EAN-13/ITF-14 values
now include equivalent zero-padded forms in their bounded alias lookup/reservation.
This follows [GS1's 14-digit representation rules](https://support.gs1.org/support/solutions/articles/43000734355-what-is-the-required-format-of-gtin-in-gs1-edi-standards-)
and [ITF-14 encoding guidance](https://support.gs1.org/support/solutions/articles/43000734528-what-type-of-gtin-can-be-encoded-in-itf-14-).
Only all-zero prefixes may be removed; nonzero case indicators remain distinct.
Canonical SKU responses, strict length/checksum validation, exact manual/internal
SKUs and UPC-E behavior stay intact. Ambiguous existing aliases require resolution;
the lookup never picks one arbitrarily. Existing products/aliases are not rewritten.

Verification: TypeScript and 105 mobile tests passed, as did 58 focused barcode,
catalog and native-camera-to-API journeys on disposable PostgreSQL. These include
same-code repeats, four existing padded-code examples, duplicate races, company
scope, archived items, manual recovery and unchanged stock. The named milk result
was visually reviewed in the phone renderer. The live local API was refreshed and
Expo served the updated iOS bundle. Existing 33 product rows and 41 alias rows
retained their fingerprints; an additional product was added during the session.
Shelf assignments, balances and count-history fingerprints were unchanged. No
migration, inventory adjustment, commit, push or hosted deployment was performed.
Physical-device acceptance remains separate from these simulated camera journeys.

### Publication review — 2026-10-01

Pre-publication review added explicit Android AppState blur/focus handling to the
scanner. A system overlay such as the notification drawer can emit blur without a
background state change. Blur now synchronously invalidates scan callbacks and
unmounts the preview; focus leaves it paused until deliberate resume. Listeners are
removed on cleanup. TypeScript checking and all ten focused rendered camera
permission/lifecycle tests passed after this change, including a same-tick stale
frame during blur. Physical Android acceptance remains separate. The checkpoint
includes the catalog scanner and compact, continuous shelf-assignment work; local
network settings and live inventory are not part of the Git change.

### Next prerequisite: packaging and mixed counts (not implemented)

Before shelf-photo counting, extend the existing stable ingredient/product identity
with explicitly defined package options and barcode mappings. One ingredient can
then have several manufacturer codes and full weights without separate unrelated
stock totals. Preserve current product IDs, shelf links, recipe references, balances
and history; any future schema change must be additive and rehearsed with an
existing-data backup. Existing count snapshots must retain their original sizes.

The intended count breakdown is sealed cases, loose full packages, and net partial
weight. Use exact, versioned conversions into the product's base unit; splitting a
case does not create stock or count the same contents twice. For standalone tubs,
the current full-container-plus-partial workflow remains appropriate. Powders and
distributed bulk need confirmed bag/case sizes and contents. Barcode-free items
retain stable internal SKUs. Do not silently equate different products or infer
case composition. Receiving, transfers and forecasts remain separate workflows.

## Slice 2 — Shelf camera proposals

Select the count and shelf, capture a photo, and receive suggested catalog matches
and full-container counts in a review page. Uncertain/hidden/open containers are
explicitly unresolved. Correct proposals before saving them as count observations;
normal count review/approval still controls stock changes. Multiple pictures must
not double-count overlapping objects or a full package plus its weighed partial.

Use the existing configured provider/model only after checking image support;
add a typed vision adapter rather than submitting photos as fake shift reports.
Keep provider work in durable jobs, bounded retries, private image storage, EXIF
removal, size/type/pixel validation, server-side credentials and authorized image
access/retention. Photo text is untrusted input. Strict structured output validates
catalog IDs, counts and confidence; missing/unknown stays missing. No fine-tuning
is needed to begin evaluation. Collect representative labeled shelf examples and
measure false matches/count error before enabling it for staff.

OpenAI documents that image object counts can be approximate; review is therefore
part of this product contract, not an optional polish step. See the official
[images and vision limitations](https://developers.openai.com/api/docs/guides/images-vision#limitations).

Exit gate: camera permission/denial, cancellation, upload failure, durable retry,
wrong-store image rejection, unknown SKU, overlapping photos and manual correction
work on a physical phone; deterministic tests make no paid provider calls.

## Slice 3 — Scale-assisted inventory counts (hardware deferred)

After choosing a scale, implement a small hardware adapter/bridge for its actual
USB/serial/Bluetooth/Wi-Fi protocol. App and browser use the same authenticated
count-observation service; browser hardware support must be verified on the
intended device rather than assumed.

The user selects **store → open count → shelf/location → SKU** before capturing a
stable reading. Show gross weight, explicit known tare, net weight and unit. Save
original measurement/device timestamp and a unique capture ID; convert g/kg into
the selected SKU's fixed base unit. A second reading can replace the same container
observation; intentionally counting another container requires another observation.
Duplicate transmissions/reconnections cannot add a measurement twice. Partial net
weight adds to that SKU's full-container subtotal in the draft count. Nothing
silently increments current stock outside count review and approval.

Exit gate: real hardware calibration/stability/unit/tare/error handling, explicit
SKU selection, duplicate/replay protection, multiple containers, reweigh, no
negative net weight, and phone/browser verification. Required input: scale model,
connection type, protocol/sample output and minimum useful measurement precision.

## Slice 4 — Manager/owner Forecast tab

Build daily and weekly tables/charts from confirmed production batches and the
snapshotted recipe usage/1% allowances. Reversed logs are excluded from net usage
but remain auditable. Physical count corrections are not ingredient consumption.
Show flavor batches/yields, ingredient use, comparison periods, data coverage,
last count and latest movement for the selected store.

Calculate predictions deterministically before requesting LLM explanations:
- Weekday demand needs enough comparable recorded weekdays; sparse history gets
  an explicit insufficient-data result rather than a confident recommendation.
- Days of cover uses current stock divided by a labeled historical/projected
  usage rate. Unknown stock, unrecorded days and zero demand are distinct states.
- Purchasing warnings also need supplier lead times, safety stock and receipts.
  Until those inputs exist, describe projected depletion, not a reliable ordering
  deadline. Do not infer sales from production or count differences.
- Recipe revisions and the 1% allowance remain visible to the calculation so a
  recipe edit cannot rewrite historical usage. Use business dates explicitly.

Give the LLM bounded aggregates, calculated values and data gaps through a typed
forecast adapter. Cache by store, data watermark, period, model and prompt version.
It explains trends and suggests production levels supported by those aggregates;
no tools or authority to post stock. Preserve a useful numeric view when AI fails.
Manager/owner access is enforced on the endpoint as well as the tab. Evaluate on
synthetic fixtures and later real labeled histories; no automatic training on
private store photos or recipes is part of this slice.

## Verification and release evidence

Slice 1 requires migration fresh/upgrade/data preservation and backup/restore,
exact decimal conversion/+1%, immutable recipe/log history, request replay,
concurrent submissions, cross-store/role denial, atomic insufficient-stock failure,
reversal and stale-count watermark tests. Native verification covers ingredient
plus/minus, batch counters, review/confirm, uncertain submissions, restoration,
permission changes and phone/tablet layouts. Physical iPhone acceptance is separate
from browser-rendered React Native journeys and JavaScript exports.

### Slice 1 implementation — 2026-09-29

Implemented locally: migrations 018–020, immutable stock movements, versioned
recipe/ingredient snapshots, exact 1% consumption allowance, atomic production
confirmation/reversal, and Production role permissions. The native workspace has
compact shelf-style ingredient cards, alphabetical catalog search, add/remove
controls, amount/unit fields, recipe drafts, daily flavor/batch selection, review,
confirmation and history. Managers/owners enter from **Today → Open Production**;
Production staff receive their own bottom tab without Reports or Store. Recipe
creation is native-first; the browser can view recipes and submit/review production.

Invitations still create crew accounts. Only authorized administrators/owners can
assign the Production role; managers cannot elevate an invited crew member. No
company recipe, opening balance or production account was fabricated for the demo.

A lost confirmation response keeps the original payload and identities frozen.
Recovery reads the original log; a 404 is not proof a delayed write cannot finish.
Explicit retry resends exactly the saved payload. A definitive validation/conflict
response allows correction, while connection/server failures remain unresolved.
Native recipe edits use the same conservative saved-request behavior. Private
context changes invalidate restored inputs and in-flight responses.

Local verification completed:
- TypeScript and 103 native tests; successful iOS and Android JavaScript exports.
- Four rendered native production journeys at phone/tablet sizes, and five real
  browser journeys covering confirmation, lost responses and changed store/access.
- Production service and transport parity checks (11), stock movement/upgrade
  checks (3), and focused account role/lifecycle checks (34). The broader account
  pass exposed one outdated role-choice assertion; it was corrected and rerun in
  the focused passing set. Existing count, migration and Heads Up checks passed.
- Exact decimal/+1%, concurrent submissions, replay, cross-store/role denial,
  immutable sealed snapshots, insufficient stock and injected rollback failures.
- PostgreSQL release recovery rehearsal through all 20 migrations, including a
  real archive restore of all 40 durable tables and 79 foreign keys. Fixtures
  include production, recipe revision, reversal and original count measurements.
- Backed up the local demo, applied 018–020, and compared every pre-existing table
  column/value before and after; all existing data was preserved. The local API,
  report worker and Expo service are healthy.

Physical iPhone/Android acceptance, current-revision CI and hosted deployment are
not yet verified at the local implementation checkpoint. Camera,
scale and Forecast remain the following phases above; none is represented as a
working integration by this implementation.


### Recipe editor UX revision — 2026-09-29

Implemented a read-only Recipe summary and a reusable native modal editor opened
by New Recipe or Edit Recipe. The modal uses a bottom sheet on phones and a
centered window on wider screens, with safe-area spacing, a scrollable ingredient
editor and fixed Save Recipe/Cancel actions. Yield is a dropdown for 4.5 kg or
6 kg. Name/yield/instructions/save/cancel fields remain hidden at rest. Cancel
resets the private draft; saved edits refresh the authoritative recipe summary.
Editing intent and unfinished inputs restore after reopening. Pending saves keep
the modal open and retain the original payload for exact retry.

Verified: TypeScript, 103 native tests, six rendered production/recipe journeys,
and iOS/Android exports. The rendered checks cover 320–1440 px widths, short
landscape layouts, cancel/new/edit, saved-summary refresh, older yield preservation,
draft restoration, and a lost recipe response followed by one identical retry.
Phone/tablet renders were visually reviewed. Device keyboard/VoiceOver acceptance
remains separate. No schema changes or hosted deployment were needed for this UI
revision.
