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
