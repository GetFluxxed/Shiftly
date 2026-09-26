# Native current inventory and reviewed counts

Status: implemented and locally verified, based on f9a7c9d. No existing demo quantities
are invented. Product catalog and shelf configuration remain separate from
count observations and stock posting.

## Workflow and scope

- Native phone/tablet screens: Current inventory, Count inventory, Review count,
  Count history and count detail. No browser redirect.
- One open whole-store count per store. Authorized counters share that count;
  optimistic versions prevent one edit silently overwriting another. Individual
  entries have an explicit Save action and server confirmation. Only saved entries
  survive navigation/restart; clear unsaved warnings accompany form changes.
- Snapshot every active store product with each active shelf placement, or one
  Unassigned location when no shelf is assigned. Count only the physical amount at
  that location; totals add locations for the same product. A new catalog product
  must be assigned to the store before it is part of a count.
- Snapshot previous balances and product names/SKUs, fixed stock units, container
  references, versions, and shelf names. Later configuration changes require a
  new count before finalization; the old draft can be cancelled without altering
  stock. Never silently add/remove count lines mid-session.
- Each line starts uncounted. Zero requires confirmation. Store either a total
  measurement or full-container count plus combined net partial amount. Convert
  g/kg exactly into the fixed product base unit. Each quantities are whole numbers.
  Multiple partial containers are combined by the counter in this first slice;
  separate scale observations and tare deduction are later extensions.
- Count date identifies the store's business day, chosen explicitly by the user;
  preserve server UTC start/observation/review/posting times separately. First use
  assumes counting at a stable stock cutoff (normally after service). During-service
  reconciliation with receipts/usage follows when stock movements are implemented.
- Draft → review → posted. Review freezes entries. An approver can return a count
  to draft, cancel it, or finalize it. All lines must be counted before review and
  posting. Counts with no store products cannot be created.
- Current inventory uses committed stock only, labelled Last counted inventory.
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
Save each entry before leaving. Review shows product totals across locations and
changes since the previous finalized count; an approver then finalizes the update.
