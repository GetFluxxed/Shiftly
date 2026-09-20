# Shiftly implementation backlog

Updated: 2026-09-20. Source of truth:
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

The baseline at `53fdd36` has 78 previously verified tests and passing CI. All
work packages below are planned, not completed. Use small reviewed changes;
each package includes tests, documentation and rollout considerations.

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
| M1 | Installable mobile web shell, saved drafts and reconnect conflict handling | A1; release after C3 | Agreed iPhone/Android matrix completes capture-to-post and logout/sync tests |
| S1 | Sales ingestion, import deduplication, recipes and usage mappings | I3 | Known examples, refunds, stale data and unmapped sales handled visibly |
| S2 | Demand, cover, lead-time/par alerts and forecast explanations | S1, I5 | Reproducible calculations and pilot error measurements; estimates remain separate from confirmed stock |
| R1 | Stretch: invoice entry/import and line-level receiving checklist | I3, I5 | Manual partial receiving, discrepancies and receipt replay tests pass |
| R2 | Stretch: barcode/SKU mapping, scanning and confirmed receipt posting | R1, C1 | Case/unit conversions, repeat scans, unknown codes and duplicate receipt requests tested |
| N1 | Later native app delivery | Stable versioned API and pilot evidence | Separately scoped native authentication, device storage and distribution plan |

F3 and inventory discovery can run alongside the backend foundation. Catalog and
shelf discovery should produce real pilot items, full weights, tare profiles,
units, pars, photos and sales samples before dependent implementation begins.
M1 shell design can start earlier; its full release gate includes camera flows.

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

Start the two bounded assignments in [Round 1](parallel/ROUND_01.md): Codex owns
worker recovery; GitHub Copilot owns contract/browser tests and CI. They use
separate branches/worktrees and explicit, disjoint file ownership. Integrate
their results sequentially before allocating FastAPI implementation work.

Then prepare **F1** as the first FastAPI implementation change.
Do not merge the older worktree wholesale or combine framework migration with
the complete inventory feature set in one release.
