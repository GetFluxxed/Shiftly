# Inventory foundation and shared company catalog

Updated: 2026-09-23. This is the current entry point for the implemented first inventory slice.
It follows the [architecture audit](architecture-bloat-audit-2026-09-23.md) and
supersedes older instructions to repeat F0/F1 or start a mobile-web client.

## Status and boundaries

The prerequisite change separates recoverable feature conflicts from session
failures, extracts reusable HTTP/native helpers, moves identity value types out
of the legacy service, and adds a public transaction-scoped selected-store check.
Existing browser response shapes, bearer/cookie separation, policy locks,
revocation checks, and account/theme work are preserved.

The shared catalog and first shelf are now implemented: additive migration 015,
an independent inventory service/router and native catalog/shelf screens.
Migration 016 adds full-container amounts and alphabetical catalog pagination;
migrations 001–015 remain unchanged. Catalog add/edit/archive/restore,
shelf create/rename and product assignment/removal are available.

Import jobs, stock quantities, store-listing deactivation, shelf deletion,
area/rack/bin hierarchy and photo processing are not implemented. Hosted FastAPI
cutover, worker/provider extraction, large-team query optimization and physical
device acceptance remain separate work at their audit gates.

## One company catalog, many store layouts

Use the existing **business** as the company boundary. Store each product once
in PostgreSQL, with a stable internal product ID and its current SKU. Authorized
stores in that business select from the same catalog. Store listings and shelf
placements reference that product; they do not copy it into new product records.
The app provides the searchable, editable list. A spreadsheet/CSV can later be an
import/export format, with preview and validation, rather than a second database.

```text
Company / existing business
  Shared product catalog: product ID, SKU, name, base unit, active state
    Store A listing → Shelf A1 / Shelf A2
    Store B listing → Shelf B1
    Store C listing → different subset and arrangement
```

Example: SKU `000184`, “Vanilla gelato, 5 L tub,” is one catalog product. Two
stores can assign it to differently named shelves. Editing its descriptive name
updates the shared product shown in both stores. Neither store's stock count nor
shelf layout is copied or changed by that edit.

| User action | Implemented behavior (unless marked planned) |
| --- | --- |
| Add a product | An owner or account with `catalog.manage` creates the company product once. It is available for selection at stores in that business. |
| Assign an existing SKU to a shelf | An account with store `configuration.manage` selects the product; the transaction creates/reactivates the store listing when appropriate and adds the shelf placement. It does not create a second product. |
| Edit name or SKU | Update the same stable product ID, show that the edit applies company-wide, record actor/history, and reject a conflicting SKU. Use record versions to prevent overwriting a newer edit. |
| Remove from one shelf | Remove only the active placement; keep the product and other placements. |
| Stop carrying at one store | Planned. The first slice creates/reactivates listings when assigning a shelf; it does not yet expose listing deactivation. |
| Remove from the company list | Archive the product, show affected-store scope, block new placements, and clearly mark retained references as archived. Preserve history and allow an authorized restore. Avoid hard deletion of referenced products. |
| Open another store | Reuse the same catalog; select the applicable products and create local shelves. A later copyable shelf template can accelerate repeated layouts without linking stock balances. |

Shelf assignment is enough to establish planned placement. It does **not** create
an opening stock balance or claim that an item is physically present.

## Identity and editing rules for the migration

- Reuse `businesses`, `stores`, and named account IDs from migration 014. Do not
  introduce another company/organization system.
- Product IDs remain stable even if the SKU changes. A SKU is text, never an
  integer: preserve leading zeros. For the initial catalog, trim surrounding
  whitespace, retain display spelling, and use an explicitly normalized
  case-insensitive key for uniqueness within the business. Reject empty/control
  characters. SKUs are 1–64 ASCII letters/digits and `._/-`, starting with a
  letter/digit; product names allow 1–160 characters. Shelf names allow 1–120.
- Reserve former SKUs as aliases for the same product when identifiers change;
  prevent reuse for another product in the same company. Supplier codes and
  barcodes are separate identifiers and can be added without changing product IDs.
- The product form requires name, SKU, and an explicit base unit (`each`, `g`,
  `kg`). Stored legacy volume units remain readable. The base unit cannot be changed after creation. A material
  change of product/pack meaning creates a new product or reviewed configuration
  version; it must not reinterpret historical quantities by silently editing a unit.
- Company products, store listings, and locations carry scope in their keys.
  Composite foreign keys must reject cross-company and cross-store relationships,
  independently of application validation. A product can occupy multiple shelves;
  each store/product/shelf placement is unique.
- Product archive and store-listing removal preserve change history. Catalog
  archive must not silently delete shelves or any future stock/movement history.
- Lists are bounded and searchable from their first implementation. Do not fetch
  every company's products or use the account-management projection as a catalog.

These are the implemented defaults for this slice; no real catalog
has been imported. CSV import, pack conversions, barcode scanning, count sheets,
stock movements, photo training/recognition, and reusable shelf templates follow
separately. They are not prerequisites for the first usable shelf.

## Implemented module boundaries

- `backend/shiftly/inventory`: own catalog/location validation, persistence, and
  configuration change history. The service owns the database transaction.
- `backend/shiftly/api/inventory.py`: register an independent native router in
  the existing app factory. Use `core.native` for bearer validation and native
  errors, `core.http` for shared HTTP mechanics, and bounded request parsing.
  No inventory router needs to import the browser accounts router.
- Inside every protected write transaction call
  `accounts.require_selected_store(token, capability, connection=connection,
  expected_store_id=...)`. This checks the actual session's selected store and
  cannot use a submitted ID to switch authority to another authorized store.
  Use the returned actor's business/store/user IDs for data and audit records.
  Keep the transaction short and retain its policy lock through the write.
- Inventory repositories take the caller's connection; they do not import
  account mixins, root `server`, `routes`, or `reporting`. Do not call account
  `_audit` for inventory events.
- `apps/mobile/src/inventory`: own typed requests/responses, validation, screens,
  and uncertain-write guidance. Use shared UI/theme and thin Expo routes.
  Feature URLs stay relative to the fixed `/api/mobile` namespace.
- Reads require the appropriate store-scoped `inventory.view` capability;
  shelf/listing changes require `configuration.manage`; shared product changes
  require `catalog.manage`. Owners have shared catalog authority; local manager
  role alone does not confer it. Preserve existing explicit business delegation.
- Provide safe repeat behavior for creates and assignment changes. Use unique
  request IDs/deduplication for creation; repeated identical assignment requests
  should return the existing placement. Same request ID with different content
  is a conflict. Never replay a timed-out write blindly.

## Native errors and recovery

Native identity/domain errors keep `error` and add `errorCode`. Browser adapters
retain their existing `{error}` bodies and HTTP statuses. Older or ambiguous
native errors still receive conservative handling.

| HTTP / errorCode | Native behavior |
| --- | --- |
| 401 / `session_invalid` (or any 401) | Clear local credentials and private state. |
| 403 / `access_changed` | Lock/hide the old workspace and require revalidation. |
| 409 / `store_context_changed` | Lock/hide stale store context. |
| 403 / `permission_denied` | Revalidate access immediately. Preserve the form if access is unchanged; invalidate it if account/store/grants changed or validation fails. |
| 409 / `duplicate_identifier`, `state_conflict`, `stale_record` | Return the actionable error to the current form without resetting the whole workspace. `stale_record` is reserved for versioned feature edits. |
| Unknown or missing code on 403/409 | Preserve the old conservative workspace invalidation. |

Services annotate only known causes through `IdentityError.reason`, preserving
existing `IdentityError.code` categories for legacy adapters. Feature code supplies
`RequestOptions.uncertainMessage`; this text is never sent to the server. The
transport supplies a conservative fallback and never retries writes automatically.

## Use the first shelf

1. Sign in as an owner or an account with shared catalog management permission.
2. Open **Inventory → Company catalog → Add product**. Enter the real product
   name, SKU and base stock unit. Leading zeros in the SKU are retained.
3. Open **Inventory → Shelves**, enter a shelf name, and create it.
4. Select products from the company catalog. Reopening the shelf loads the saved
   placements from PostgreSQL. A manager with configuration permission can also
   create shelves and select existing company products.
5. Switch stores to reuse the company catalog with independent shelf layouts.

The catalog starts empty; no example products or actual shelf names are inserted
by the migration. Add the real pilot list through the app. CSV import and copyable
shelf templates are later conveniences. Opening quantities need a separate count
and movement workflow; assigning a product does not establish a stock balance.

## Full-container refinement — 2026-09-23

The user's accepted scope is standard full-container contents now, with actual
partial measurements stored and combined under the same SKU in the later
photo/scale counting workflow. Each product has optional `containerAmount` in its
fixed base unit; new product forms offer each/g/kg. Decimal strings and PostgreSQL
NUMERIC preserve exact values, and gram/kilogram conversion does not use floating
point arithmetic. The form displays both mass units, and catalog/shelf cards show
the full-container reference. Unknown existing sizes remain unknown.

A standard 6 kg White Quella container is one product identity. Later, two full
containers and a measured 1,250 g net partial contribute 13.25 kg to that SKU.
Store the original observation, tare assumptions and configuration version with
future counts. Updating the catalog reference must not reinterpret posted stock.
No count balances, scale capture or image-processing routes are introduced here.

Catalog results and the shelf product picker are A–Z across all pages, including
search results. Normalized names plus stable IDs break ties; an opaque cursor
retains its last-seen position even if that product is subsequently renamed.
Refresh to reconcile other concurrent catalog changes; pagination is not a frozen
snapshot. Shelf and assignment pagination are unchanged.

Verification: **99 focused backend/API/migration/rendered tests passed**, including
015→016 preservation, existing product edits, precise partial-mass conversion,
old-request replay, name ties across multiple pages, malformed cursors and the
native 6 kg form. **68 native tests**, TypeScript checking and iOS/Android bundle
exports also passed. Rendered phone/tablet screens were visually reviewed. All
verification used isolated source and disposable PostgreSQL before local rollout.

Local rollout: backed up the existing demo, applied only migration 016 and
verified that product identities/units/versions, shelf placements and existing
account/report counts were preserved. Through the normal owner-authorized API,
set the user's existing White Quella product to a 6 kg full-container reference,
retaining its SKU and shelf assignment. Other unknown sizes remain blank. The
live Expo iOS bundle includes the revised form and conversion display, and the
LAN API is healthy. Hosted deployment and physical-device release acceptance remain separate from
this verified development-branch checkpoint.

## Product-storage verification — 2026-09-23

Built and tested in an isolated source copy against disposable PostgreSQL before
applying the reviewed files to the active native worktree:

- **32 storage/API/migration tests passed:** company/store isolation; database
  composite-key enforcement; duplicate/current/former SKU collisions; leading
  zeros; explicit catalog delegation; stale product/shelf edits; archive/restore;
  concurrent retry deduplication; rollback on audit failure; revocation while a
  write waits; bounded search/pagination; fresh migration and 014→015 upgrade.
- **471 existing backend/API/runtime tests passed:** accounts, identity, browser
  and native adapters, contracts, reports, migrations and runtime operations.
- **33 rendered/Chromium tests passed:** 30 existing browser cases plus 3 new
  native-screen journeys at phone/tablet sizes using the real session controller,
  API and database. The new journeys create and reopen a product/shelf assignment,
  switch stores, preserve duplicate/stale drafts, archive/restore, lock private
  content and hide unauthorized crew controls.
- **65 native tests and TypeScript checking passed.** New cases cover request-ID
  reuse, response validation, SKU/version preservation and fixed-origin queries.
- **iOS and Android production JavaScript bundles exported successfully.**

The rendered harness uses React Native Web with test-only router, icon, secure
credential and native-dialog/lifecycle adapters. It exercises actual feature
components and API/session logic; it does not establish physical-device release
readiness. Verify keyboard, focus/background-return and navigation on the pilot
iPhone before store rollout. The repository CI now installs locked mobile
dependencies for these rendered journeys as part of its backend/browser job.

For local verification, install the locked Python/mobile dependencies and
Playwright Chromium, set `TEST_DATABASE_URL` to disposable PostgreSQL, then run
`pytest -q tests/inventory_services --browser chromium`. Node must be on PATH;
`NATIVE_TEST_NODE` may point to an explicit Node executable. From `apps/mobile`,
run `pnpm check` and `pnpm export:native`.

The writes keep the existing policy lock through authorization and commit. This
preserves current revocation/concurrency behavior; changing lock granularity is
separate measured work. Reads and lists do not build account-management views.
Mutation replay records currently have no expiry. Choose retention deliberately
before growing usage rather than silently weakening repeat protection.

## Local demo availability — 2026-09-23

Applied migration 015 to the existing local iPhone demo after creating a PostgreSQL
backup and validating its archive index. Existing business/store/account/report
counts were unchanged. The catalog and shelves start empty. The updated local API
passed authenticated inventory reads for owner, manager and crew accounts with the
expected catalog permissions; verification sessions were signed out afterwards.

The Mac's Wi-Fi address had changed. Expo and its public API setting were restarted
with the current address, and the actual iOS development bundle was fetched over
the LAN and checked for the catalog screens and matching API address. Expo, the
API and the existing worker remain running. Scan the refreshed Expo code when
reconnecting; an older saved development URL may point to the previous address.
This is a local demo update, not a hosted deployment or physical-device acceptance.

## Prerequisite verification — 2026-09-23

Validated in an isolated source copy before applying the exact reviewed files to
the active native worktree:

- TypeScript checking passed; **61 native tests passed** (16 new regression cases).
- **422 backend/API tests passed**, covering account services, identity, both HTTP
  transports, request contracts, reporting, selected-store transaction rollback,
  and revocation while waiting for authorization.
- **24 Chromium account-flow/context tests passed** against disposable PostgreSQL.
- Static comparison confirmed existing authorization conditions and transaction
  logic were preserved; changes there are neutral imports, error reasons, and
  the separately tested public selected-store boundary. Extracted bearer/session
  helper implementations are unchanged.

The iPhone demo database and running services were not used for the prerequisite
tests. These historical results cover the cleanup only; the later product-storage
verification above covers migration 015 and the inventory screens. No production
deployment or real-device shelf acceptance is claimed.
