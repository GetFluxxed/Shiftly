# Shiftly database

Updated 2026-10-25. PostgreSQL is the system of record. The applied schema is
defined by immutable files in `migrations/`; code and this summary do not replace
those files.

## Migration history

Migrations `001` through `029` are present and must run in filename order.

| Range | Purpose |
| --- | --- |
| 001-003 | reports, briefing jobs/results, manager sessions, removal of image submission |
| 004-010 | stores, legacy manager/crew compatibility, Head's Up, store-scoped report identity |
| 011-013 | weekly cache, briefing recovery/leases, runtime worker status |
| 014 | businesses, individual users, memberships, sessions, invitations, recovery and audit |
| 015-016 | business catalog, SKU history, store products/shelves and container amounts |
| 017-018 | count sessions/lines, postings, balances, immutable stock movements and versions |
| 019-020 | recipes/revisions, production logs/requests and production account role |
| 021-022 | package definitions, package SKU links, canonical product and redirect links |
| 023 | store forecasts, forecast jobs and idempotent request records |
| 024 | explicit package/container weight-unit constraints |
| 025 | guarded draft count expansion for active catalog products without shelf assignments |
| 026 | immutable recipe-only ingredient quantities on recipe revisions |
| 027 | recipe ingredient sections; the same catalog product may appear in base and Variegato |
| 028 | store-scoped invoice drafts and line snapshots; immutable closed history, no stock posting |
| 029 | private invoice image jobs, leases, provenance and idempotent upload request mapping |

Never edit an applied migration. Add the next numbered migration and document
forward recovery. Back up valuable data before migration and rehearse fresh setup,
upgrade/data preservation, and recovery with disposable databases.

## Ownership and relationships

- `businesses` owns the shared catalog and business-level authority.
- `stores` belongs to a business and owns operational state.
- `account_users`, `business_memberships`, and
  `account_store_memberships` define identity and scope.
- `account_sessions` stores hashes of opaque credentials; invitations and
  password-reset records are server-side, expiring, and single use.
- Reports retain typed display metadata and may reference the verified actor.
  Briefing jobs/results, weekly cache, Head's Up, and worker status support the
  reporting runtime.
- `inventory_products` and `inventory_packages` are business-scoped.
  Historical SKUs, canonical links, and redirects preserve identity.
- Store product/shelf placement is configuration; it does not create stock.
- `inventory_stock_movements` is immutable history.
  `inventory_stock_balances` is the transactionally updated projection.
- Counts snapshot product/configuration and baseline versions. A posted count
  creates stock movement(s); drafts and review do not.
- Recipe revisions and production log ingredient snapshots preserve what was
  confirmed. Recipe revisions also retain `reference_ingredients` as a bounded
  JSON array of names, exact decimal quantities, units and an optional section.
  Catalog ingredient rows use `(revision_id, product_id, section)` as their key.
  Sections are `base` (the default for earlier data) and `variegato`. The same
  product in both sections still deducts from one product stock total. These recipe-only rows
  have no catalog identity and never generate stock deductions. Idempotency
  request tables prevent duplicate posting.
- Forecast records, jobs, and request keys are store scoped. Forecast output is
  advisory and does not mutate balances.

Foreign keys and composite business/store constraints prevent cross-scope links.
Application authorization remains required; a foreign key alone is not access
control.

## Quantity and history invariants

SKUs and barcodes are strings so leading zeros survive. New product base units
are `each`, `g`, and `kg`. Exact `NUMERIC` arithmetic is authoritative;
clients send decimal strings. Package/container sizes describe conversion or a
full container, not current stock.

The first posted count establishes a balance without inventing a prior zero.
Uncounted differs from explicitly counted zero. All required count lines must be
complete, and stale balance/configuration versions must fail rather than overwrite
newer work. Corrections and reversals append linked history; posted rows are not
silently rewritten or deleted.

Referenced products and packages are archived or redirected instead of erased.
Historical recipe, count, movement, and production snapshots retain the conversion
facts used at the time.

## Operation and recovery

Run migrations as an explicit release step:

```sh
python -m backend.shiftly.runtime.migrate
```

API/worker startup checks schema readiness and must not race to apply migrations.
Runtime commands and hosted sequencing are in [DEPLOYMENT.md](DEPLOYMENT.md);
disposable test/recovery database commands are in [TESTING.md](TESTING.md).
`TEST_DATABASE_URL` must never fall back to `DATABASE_URL`.

Hosted backup availability, restore timing, migration rehearsal, and the contents
of any production database are operational evidence and are not asserted here.
