# Shiftly implementation backlog

Updated: 2026-09-22. Native delivery priority:
[NATIVE_APP_ROADMAP.md](NATIVE_APP_ROADMAP.md). Domain source of truth:
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

**Current delivery override:** Accounts & Access integration `7ecb61d` is published
in PR #10 over backend PR #9. Native account/reporting delivery is now the first
client priority. The package/status notes below retain the earlier domain
baseline; use the native roadmap for current app sequencing.

Historical main baseline: `e01e84e`. F0 recovery/contract work, F1 services/FastAPI and the
local F2 runtime are implemented. F3 includes pinned dependencies and browser
CI. The focused verification follow-up adds both-transport API contracts and
an automated upgrade/outage/restore rehearsal. See
[verification evidence](workstreams/focused-verification.md) for checks and
remaining review/merge requirements. Hosted staging, production cutover and
required-check administration remain release work. A1 navigation and A2 named accounts/permissions are implemented; I1 onward remain planned.

## Ordered work packages

| ID | Work package | Depends on | Required completion evidence |
| --- | --- | --- | --- |
| F0 | Preserve/reconcile the older worktree, repair worker recovery, capture current contracts | Current main | Worker survives nested failures; current crew/manager tests pass; source of each retained change documented |
| F1 | Extract services and introduce a FastAPI app factory and compatibility routers | F0 | Existing endpoint/cookie/error/security behavior passes contract tests on both transports |
| F2 | Separate web/worker entry points, coordinate migrations, add staging and recovery checks | F1 | Restart, queue recovery, restore and transport rollback rehearsed |
| F3 | Add browser CI, reproducible dependencies, code/dependency checks, required merge checks | F0; finish before cutover | Critical phone/browser flows and required checks demonstrated |
| A1 | Manager Operations/Inventory navigation and selected-store context | F1 | Manager can switch spaces and store context without crossing authorization boundaries |
| A2 | Explicit manager identity, inventory permissions, membership lifecycle and audit records | F1 | Named actors and revocation tests cover all inventory commands |
| I1 | Item catalog, decimal units, packs, weight/tare profiles and supplier identifiers | A2 | Pilot item data validates; incompatible conversions are rejected |
| I2 | Areas, racks, shelves, bins, assignments, store pars and optional shelf targets | I1 | Configuration and changes are store-scoped and historical versions remain usable |
| I3 | Movement history, balances, receipts, waste, transfers and corrections | I1, I2 | Rebuild and concurrent/idempotent-posting tests pass |
| I4 | Count sessions, partial-container weighing, version checks and approvals | I3 | Sealed-plus-open example and concurrent-count/receipt cases pass |
| I5 | Digital tracker and deterministic below-par views | A1, I4 | Book quantity, partials, source, freshness, pars and history are visible |
| C1 | Private image uploads and phone capture | A1, A2, I4 | Permission denial, validation, store isolation and interrupted uploads tested on pilot devices |
| C2 | Durable image analysis and shelf-context proposals | C1, F2 | Bounded jobs, strict results, uncertainty and provider failure tests pass |
| C3 | Count review, overlap resolution, partial-weight linkage and camera pilot | C2, I5 | Repeat images/open containers cannot inflate stock; agreed quality thresholds measured |
| M1 | Native offline drafts/outbox and reconnect conflict handling | N1; affected services have idempotency/version checks | Agreed device matrix verifies interrupted writes, authorization recheck, no duplicate posting and private draft cleanup |
| S1 | Sales ingestion, import deduplication, recipes and usage mappings | I3 | Known examples, refunds, stale data and unmapped sales handled visibly |
| S2 | Demand, cover, lead-time/par alerts and forecast explanations | S1, I5 | Reproducible calculations and pilot error measurements; estimates remain separate from confirmed stock |
| R1 | Stretch: invoice entry/import and line-level receiving checklist | I3, I5 | Manual partial receiving, discrepancies and receipt replay tests pass |
| R2 | Stretch: barcode/SKU mapping, scanning and confirmed receipt posting | R1, C1 | Case/unit conversions, repeat scans, unknown codes and duplicate receipt requests tested |
| N1 | Priority: React Native + Expo account/reporting app for phones and tablets | Verified Accounts & Access integration and FastAPI services | Native API authorization tests, typecheck/bundling, then separate iPhone/Android and tablet evidence before release |

F3 and inventory discovery can run alongside the backend foundation. Catalog and
shelf discovery should produce real pilot items, full weights, tare profiles,
units, pars, photos and sales samples before dependent implementation begins.
N1 begins before catalog delivery; native inventory and capture follow I/C packages.
M1 offline replay waits for command idempotency and conflict handling.

## Definition of done

- Acceptance criteria from the implementation plan and inventory specification
  are demonstrated with fixtures or pilot evidence appropriate to the change.
- Existing reports and sessions remain compatible unless a documented migration
  explicitly changes a contract.
- Store isolation, actor authorization, idempotency, unit conversion and concurrent
  writes are tested wherever the package introduces those behaviors.
- AI is mocked in routine tests; separately recorded evaluations use approved
  store evidence and explicit cost limits.
- Additive migration, deployment and recovery steps are documented and rehearsed
  before production promotion.
- User-visible errors, pending states and incomplete coverage have a usable path
  forward.
- Documentation distinguishes implemented behavior from planned behavior.

## Next bounded task

The [shared company catalog and first shelf](workstreams/inventory-foundation-and-shared-catalog.md)
are implemented as a bounded subset of I1/I2. Enter the real pilot products and
confirm the first shelf on an iPhone. Next, define the pilot package/base-unit
conversions before implementing opening counts and the movement ledger.
Weights, pars and the broader location hierarchy follow. N1 and native Team/Owner administration exist. Preserve their
behavior and the browser app. Hosted cutover and signed native distribution are
separate release tasks.
