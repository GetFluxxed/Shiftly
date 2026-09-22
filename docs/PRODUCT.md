# Shiftly product direction

Updated: 2026-09-22. Native client delivery:
[NATIVE_APP_ROADMAP.md](NATIVE_APP_ROADMAP.md). Domain delivery plan:
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Existing product

Shiftly supports named accounts with scoped crew/manager/admin/owner access,
shared crew sign-in during enrollment, shift reports, manager review, AI
briefings, weekly overviews, and a store Head's Up message. Original notes stay
available alongside generated summaries. Current inventory functionality is
not implemented.

## Expanded product

Shiftly's primary new experience is a native phone and tablet application built
with React Native, Expo and TypeScript, backed by the existing FastAPI services.
The existing browser application remains available while native workflows reach
parity. A separate React browser rewrite is outside this phase.

The manager window will offer two distinct spaces:

- **Operations:** existing reports, briefings, weekly overview, and Head's Up.
- **Inventory:** a running digital tracker, shelf/location setup, pars, camera
  counts, partial weights, shortage insights, and eventually invoice receiving.

Both spaces retain the same authenticated account and visible selected store.
Existing crew reporting remains available while the manager app evolves.

## Inventory capabilities in scope

| Capability | Intended user outcome |
| --- | --- |
| Catalog and units | Identify every item and its pack sizes and measurement units |
| Shelves | Store explicit area/rack/shelf/bin information, assignments and capacity |
| Par management | Update store-item targets with history; see items below target |
| Running tracker | See stock, source, freshness, location, and posted changes |
| Partial stock | Weigh opened inventory using explicit full weights and tare profiles |
| Phone photos | Review camera-proposed counts of visible stock and reconcile them |
| Shortage insight | Compare inventory with par and mapped sales demand, with explanations |
| App experience | Install on a phone, capture conveniently, and recover interrupted drafts |
| Stretch receiving | Scan codes against invoice lines and post accepted deliveries once |

Partial weights are part of the core inventory scope, not an optional stretch.
SKU/barcode invoice receiving is the stretch goal. The detailed workflows and
acceptance examples are in [INVENTORY.md](INVENTORY.md).

## Trust and usability rules

- Clearly distinguish physical observations, book inventory, and estimates.
- Human review precedes camera-generated stock changes.
- Open containers and sealed packages must never be counted twice.
- A repeat count reconciles stock rather than adding the entire count again.
- Typed employee names do not authorize inventory actions.
- Missing images or unavailable sales data are visible gaps, not invented values.
- A manager can inspect and correct history without silently deleting it.
- Manual counting, weighing, and receiving remain usable if AI is unavailable.

## Delivery boundaries

The next phases explicitly include FastAPI and inventory; the former
baseline-only exclusions no longer apply. Preserve current data and browser
contracts throughout the transport migration.

The first native slice covers named accounts and daily reporting; full native
account administration, stock workflows and camera assistance have separate gates.
Signed native distribution requires real-device verification and a release review.
Unattended camera stock posting, automatic purchasing, connected-scale hardware
and automatic invoice OCR remain outside the initial release. Camera quality and forecast claims require real-store pilot evidence.
