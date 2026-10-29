# Native current inventory and reviewed counts

> **Archived record.** Dated decisions and evidence as of its own revision; not current
> guidance. See the [archive index](README.md) and the maintained documents it links.

Status: implemented and locally verified, based on f9a7c9d. No existing demo quantities
are invented. Product catalog and shelf configuration remain separate from
count observations and stock posting.

## Workflow and scope

- Native phone/tablet screens: Current inventory, Count inventory, Review count,
  Count history and count detail. No browser redirect.
- One open whole-store count per store. Authorized counters share that count;
  optimistic versions prevent one edit silently overwriting another. Individual
  entries have an explicit Save action and server confirmation. Local unsaved drafts
  now survive navigation/restart through workspace restoration; they do not become
  shared count observations until explicitly saved.
- Snapshot every active business catalog product with each placement in the
  selected store, or one Unassigned entry when no shelf is assigned. Count only
  the physical amount at that shelf; totals add entries for the same product.
  Shelf assignment and a pre-existing store listing are not prerequisites.
- Snapshot previous balances and product names/SKUs, fixed stock units, container
  references, versions, and shelf names. Changes to captured products or shelves
  require a new count before finalization; the old draft can be cancelled without
  altering stock. A draft may append missing active catalog products through the
  audited include-catalog operation if every existing snapshot remains unchanged.
  Existing entries are never removed or rewritten by that operation.
- Each line starts uncounted. Zero requires confirmation. Store either a total
  measurement or full-container count plus combined net partial amount. Convert
  g/kg exactly into the fixed product base unit. Each quantities are whole numbers.
  Multiple partial containers are combined by the counter in this first slice;
  separate scale observations and tare deduction are later extensions.
- Count date identifies the store's business day, chosen explicitly by the user;
  preserve server UTC start/observation/review/posting times separately. First use
  assumes counting at a stable stock cutoff (normally after service). During-service
  reconciliation during active service is still deferred. Production now posts
  movements; an older open count must be cancelled and restarted if its captured
  stock versions changed.
- Draft → review → posted. Review freezes entries. An approver can return a count
  to draft, cancel it, or finalize it. All lines must be counted before review and
  posting. Counts with no active catalog products cannot be created.
- Current inventory uses committed stock only. Last physical count/date is shown
  separately from subsequent production deductions/corrections and stock updates.
  Uncounted/new products show Not counted, not zero. Preserve balances for archived
  products and visibly identify them; archiving does not remove physical stock.
- Previous quantity is nullable: the first count establishes an opening balance,
  not an increase from assumed zero. Subsequent differences are stock changes,
  not consumption or sales estimates.

## Authority and integrity

Reuse inventory.view, counts.submit and counts.approve. Crew can be granted view
and submit; managers already have approve in their one store. Admins use explicit
delegation; owners retain their existing authority. Every write revalidates the
selected store inside the policy transaction. Client IDs never select authority.

The count service/repository owns count SQL and transitions. Catalog/shelf code
owns configuration. Native adapters use the existing bounded request/error layer.
Migration 017 adds sessions, product snapshots, location observations, stock
balances and immutable opening/count-adjustment records with composite scope keys.
Finalization commits observations, movements and balances together. Request IDs,
record versions, baseline checks and a unique open-count constraint protect repeat
and concurrent requests. Database guards prohibit rewriting completed evidence.

Reads/search/history are paginated. Saved count details remain private, follow
existing session/store invalidation and require fresh authorization on resume.
Final posting stays online. Interrupted writes use the existing same-request retry
contract; an unchanged retry returns its saved result. No automatic blind replay.

## Delivery sequence

1. Update the implementation plan and add migration/service/API boundaries.
2. Implement exact measurements, save/resume, completeness, review and atomic
   finalization, current balances, location breakdown and historical comparisons.
3. Build the native screens in the existing cocoa/rose theme and permission shell.
4. Verify migration/data preservation, replay, concurrent writes, stale scope,
   permission revocation, exact quantities, immutability and real rendered journeys.
5. Back up and migrate the local demo; preserve products, shelves, accounts and
   reports; make the new experience available through the existing Expo server.
6. Follow with receipts/waste/transfers/corrections, photo/scale evidence, and only
   then evaluated usage forecasts and LLM-assisted production recommendations.

## Acceptance example

White Quella, base kg, full container 6 kg: two full containers plus 1,250 g net
partial = 13.25 kg. Previous count 18 kg → change -4.75 kg. A second shelf's amount
adds to that same SKU, never a duplicate product. Replaying finalization leaves
13.25 kg unchanged. Editing the catalog's container size afterward does not change
this count or its original measurement. An untouched line prevents posting;
explicit zero is valid. Cancelling a count preserves the previous inventory.

## Verification

Local verification in an isolated source copy and disposable PostgreSQL:

- 732 backend, browser and rendered-native tests passed, including count/store
  isolation, unknown versus zero, exact mass conversion, concurrent start/edit/post,
  unchanged-request replay, stale configuration/balances, rollback on audit failure,
  history immutability, search/pagination and archive retention.
- 79 mobile tests and TypeScript checking passed. iOS and Android native bundles
  exported successfully. No new runtime dependency was needed.
- Real native screens were exercised at phone and tablet sizes: save/resume,
  18 kg to 13.25 kg comparison, crew zero-count submission without approval rights,
  source shelf/measurement history and a lost response recovered without duplication.
  Screenshots were visually inspected; physical iPhone acceptance is still separate.
- The release recovery rehearsal passed and restored all 32 tables, 8 sequences
  and 58 foreign keys, with exact posted stock, original partial-weight entries
  and a resumable uncounted draft. Worker crash/outage and report recovery also passed.

These are local verification results for the inventory implementation. CI status
is recorded on the publishing pull request; the earlier successful account CI run
remains evidence for its own commit.

## Trying the module

Use Inventory → View current inventory or Count inventory. Owner/manager accounts
can count and approve within their authorized store. A crew account needs explicit
inventory.view and counts.submit grants; approval remains separate. The demo starts
without invented opening balances: finalize the first real count to populate stock.
Save each entry to the durable mobile queue described below; connected saves
upload automatically. The separate workspace checkpoint can recover unsaved
editor input, but does not make it a saved observation or update stock. Review shows product totals across locations and
changes since the previous finalized count; an approver then finalizes the update.


The 2026-09-29 [compact native inventory lists](inventory-foundation-and-shared-catalog.md#compact-native-inventory-lists--2026-09-29)
revision also covers current stock, shelf breakdowns, count entries, comparisons
and count history. Product SKUs are hidden in these displays while remaining
searchable. Count flows entered from Current Inventory retain that return
destination through entry saves, review and history. These are presentation and
navigation changes; the count contract above remains in force.

The [workspace restoration contract](NATIVE_APP_ROADMAP.md#workspace-restoration--2026-09-29)
now covers local count input and navigation continuity. Newer server line versions
or changed count state/configuration invalidate the corresponding unsaved draft.

## Production integration — 2026-09-29

Migration 018 introduces immutable stock movements and adds balance versions and
latest-movement references. Existing count postings and last physical count links
remain intact. Historical movement order follows each product's previous-count
chain, including tied timestamps. Snapshots include `previous_stock_version`; a
consumption/reversal pair cannot fool a stale count by returning to the same
quantity. Count posting and production use the same store lock and transactionally
maintained balance. See [the production contract](production-and-assisted-inventory.md).

## Compact count workspace — 2026-10-22

The selected concept A replaces the active count's stacked cards with a compact
product list in the existing cream/cocoa/rose theme. A shelf chooser, live search,
and All / Not counted filters sit above the list. New drafts start on Not counted.
Product progress stays storewide: a product placed on two shelves is complete only
after both shelf entries are saved. The Review action stays below the scrolling
list; submission and approval remain separate steps.

Tapping a row opens a bottom sheet on phones and a centered editor on tablets.
Package steppers, measured totals and optional partial amounts reuse the existing
exact conversion rules. None here fills an explicit zero; Save is still required.
An untouched entry cannot save its default zero. Successful saves close the sheet
and refresh the same list without navigating away. Shelf/search choices and the
open entry restore within the existing account/store workspace. Existing entry
draft keys and version/configuration baselines are preserved.

The old entry route delegates to the same editor so restored routes continue to
work. Pending saves block closing; uncertain writes retain their values for an
explicit retry or reload. Read-only history has no Save action. There are no API,
database, permission, stock arithmetic, dependency or theme changes.

Acceptance covers phone/tablet fit, in-place saves, explicit zero versus uncounted,
the same product on two shelves, mixed packages and partial weights, draft/filter
restoration, previous-server-version invalidation, uncertain-response retry, and
review/approval permissions. Physical-device keyboard and VoiceOver acceptance
remain separate from the rendered native-screen checks.

Local verification for this revision: TypeScript checking and all 128 existing
mobile unit tests passed; nine focused rendered journeys passed against a separate
disposable PostgreSQL database. These exercised the actual native components
through the browser test adapter, including the restore/save/error and permission
cases above. Phone/tablet screenshots were inspected. Final iOS and Android
bundles exported from the mobile checkout successfully. These checks do not claim
physical-device acceptance or CI verification; the change is local and uncommitted.

### Count popup lifecycle correction

Physical iPhone testing exposed a loading-to-editor transition that replaced the
native Modal during presentation, leaving the page visible but unable to receive
touches. The modal now stays mounted while its loading, error and editor contents
change. Close/back still applies the editor's pending-write and unsaved-draft guards.
No inventory or draft data was reset.

A focused regression asserts the same modal host through loading and read-error
retry, plus an interactive list after closing/reopening. It fails against the old
implementation and passes with the fix. All four count journeys and the draft
restoration journey passed (five checks); TypeScript and the iOS bundle passed.
The updated app is available locally; confirmation on the physical iPhone remains
with the tester after fully reopening Expo Go to clear the old native overlay.

## Durable mobile counting — 2026-10-22

The approved scope now includes a durable queue for **count observations only**.
This supersedes the online-only Save behavior described above. It does not queue
catalog changes, production, approval or stock posting. Opening a count while
connected prepares its full paginated snapshot, including package conversions and
shelf names. The snapshot must be complete and consistent before offline entry is
available; a partial download cannot advertise offline readiness.

Save commits the intended measurement to encrypted device storage before closing
the editor. Search, shelf selection, progress and totals use the prepared snapshot
with local saved entries applied. Uncounted still differs from explicitly saved
zero. The top-right draft label becomes a checkmark when all saved observations
are acknowledged by the server, or a sync icon while work is queued. The checkmark
does not mean every product has been counted. Routine status prose is omitted;
tapping the icon opens details, retry and any required conflict decisions.

### Integrity and access boundaries

- The count queue uses separate segmented SecureStore checkpoints. It is not part
  of the evictable UI-draft cache. Documents use the existing dual-bank manifest
  commit mechanism; a failed local write keeps the editor open and cannot report
  a successful save. There is no database migration or additional dependency.
- Scope includes service origin, business, store and individual user. Before a
  network upload, the client revalidates account access; the existing backend
  rechecks scope and permission in its mutation transaction.
- Each attempted upload has a durable request ID, expected server version and
  immutable measurement payload. An uncertain response retries that same
  operation. A newer local edit remains separately queued until the earlier
  operation is acknowledged. Retries cannot become additive stock operations.
- A conflicting server edit, changed configuration or closed count preserves the
  queued measurement. Explicit resolution is required; it never automatically
  replaces another counter's amount. Review and final posting require connectivity
  and a clear queue. Draft observations still do not change current inventory.
- A previously validated account can resume only its prepared count without a
  connection for up to 12 hours after its last successful access check. The
  encrypted authorization is bound to the token, identity, store, role and
  capabilities. This intentionally bounded offline access cannot discover remote
  revocation until reconnection; no offline server write is allowed. Expired or
  explicitly revoked access hides the workspace while retaining queued data.
- The restricted offline view exposes no other app tabs. Backgrounding hides
  private UI; foreground/cold resume attempts validation before restricted
  fallback. Explicit sign-out removes the offline authorization. Queued entries
  remain encrypted for recovery after the same person signs in again; another
  account/store cannot display or upload them.
- Upload retries run while the app is active, including reconnect/resume. This
  does not promise background OS execution. Expo Go also still needs its loaded
  JavaScript bundle; cold launch without Metro access is a separate development
  constraint from persisted count recovery in an installed native build.

### Acceptance and rollout evidence

Verification must exercise local storage failure, all-page preparation, multiple
queued saves, reload without the API, immutable replay after a lost response,
editing during acknowledgement, scope changes, expired/revoked authorization,
explicit conflict resolution and the review gate. Native exports and browser
adapters do not establish keychain/airplane-mode behavior on a physical device.
Device acceptance: prepare Count while connected, disable connectivity, save
several items, background and reopen, then reconnect with Shiftly foreground and
confirm the sync icon becomes a checkmark before review. No demo inventory reset,
commit, hosted deployment or CI result is implied by this local implementation.

Local verification: TypeScript and all 162 mobile unit tests passed. Focused
rendered journeys passed for multiple offline saves and cold API-disconnected
restore, uncertain-response replay, editing through acknowledgement, explicit
conflicts, cross-count review blocking, count/review/history navigation, draft
restoration, zero, mixed packages and pounds-to-metric totals. These used a
separate disposable PostgreSQL database, not demo inventory. iOS and Android
bundles exported successfully from the active project; the local Expo and API
health checks passed. Independent integration review found a cross-count review
gate bypass, which was fixed and covered by a passing regression. Physical-device
offline/keychain acceptance and exact-revision CI remain pending.

## Active catalog coverage — 2026-10-22

The count source previously joined through store listings, which are generally
created by shelf placement. Consequently, never-shelved catalog products were
absent even when the native “No shelf assigned” filter was selected. Counts now
start from the selected business’s active catalog and join only the selected
store’s shelves. Archived products are excluded. Missing store listings are
created in the count transaction to satisfy existing scoped foreign keys; this
creates no balance or movement. The first posted count establishes stock.

Existing drafts can use `POST /api/mobile/inventory/counts/{id}/include-catalog`
with a request ID, selected store and expected count version. It requires
`counts.submit`, the normal policy/store/count locks and an audit record. It adds
only whole missing products, leaves observations and their versions/IDs untouched,
and captures each added product’s current store baseline and package references.
The existing scope fingerprint must still match, and the full count must fit the
10,000-line limit. Review, posted and cancelled counts cannot expand; an approver
can return a review to draft first. Other configuration changes retain the normal
conflict behavior. Every added line starts uncounted, never zero.

The native count controller requests safe additions while preparing a connected
count or syncing queued entries. It uploads existing queued observations before
replacing the local snapshot with the expanded list. If connectivity fails after
expansion, the prior local generation and pending work remain readable. Server
line totals may temporarily exceed locally downloaded lines; review stays blocked
and the existing sync control retries preparation. An entry edited during that
download prevents replacement until it is synced. View-only accounts do not
request expansion. Migration 025 changes only the count-header guard to permit a
draft-to-draft fingerprint update with a version increment; captured evidence and
completed history retain their guards. Back up valuable data before applying it;
forward recovery uses a corrective migration, never a destructive down migration.

Verification: native type checking and 169 unit tests passed; 28 focused backend
count tests and five rendered count/offline journeys passed on disposable
PostgreSQL. The upgrade rehearsal from migration 024 preserved populated count headers,
observations, postings and balances, and repeat migration was a no-op. iOS and Android exports passed. The existing local demo was backed up before
migration 025; catalog, shelf, count, balance and movement row fingerprints were
identical before and after the upgrade. Expo and the restarted API/worker are
running locally. The current draft was confirmed to have 22 captured products
and 35 safely appendable active products; its expansion occurs through the
authorized app flow when reopened or synced. Physical iPhone acceptance remains separate from rendered tests.
