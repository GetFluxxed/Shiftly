# Documentation archive

Created 2026-10-21 during documentation consolidation from source revision
`df53f98`. Archived records are dated evidence: decisions, delivery notes and
verification results **as of their own revision**. They are not current guidance.
Their test totals, branch names, running-server statements and "next" lists
describe the past. Current behavior and plans are in the maintained documents
linked from the [README](../../README.md#documentation).

Removed documents remain available in Git history. The permalinks below point to
their last version, at `df53f98`.

## Archived records

Kept in this folder because they record owner decisions with their reasons, or
verification evidence (rehearsals, device feedback, real-label results) not
reproduced elsewhere. Apart from a one-line archive banner and links repaired so
they resolve, their content is unchanged.

| Record | Dates | Revision context | Contents | Superseded by |
| --- | --- | --- | --- | --- |
| [engineering-adoption.md](engineering-adoption.md) | 2026-10-11 | PR #21 (base `604683d`) | ENGINEERING.md adoption, reproducibility work, provider/job extraction, retained-gap register, verification record | [IMPLEMENTATION_PLAN](../IMPLEMENTATION_PLAN.md#accepted-legacy-deviations), [DEPLOYMENT](../DEPLOYMENT.md) |
| [NATIVE_APP_ROADMAP.md](NATIVE_APP_ROADMAP.md) | 2026-09-22 – 09-29 | PRs #12, #14, #17 | Native architecture decision, phase plan, Heads Up/restoration/production delivery evidence | [ARCHITECTURE](../ARCHITECTURE.md#architectural-decisions), [mobile README](../../apps/mobile/README.md), [IMPLEMENTATION_PLAN](../IMPLEMENTATION_PLAN.md) |
| [codex-accounts-permissions.md](codex-accounts-permissions.md) | 2026-09-22 | PRs #9, #11 (backend `33b7908`) | Account policy design, migration 014, operator mapping/recovery, account rehearsal evidence | [SECURITY](../SECURITY.md#roles-and-capabilities), [API](../API.md#accounts-apiaccounts), [DEPLOYMENT](../DEPLOYMENT.md#accounts-and-operator-procedures) |
| [focused-verification.md](focused-verification.md) | 2026-09-21 | PR #8 (tested `c65d13a`) | Both-transport contract suite, compatibility fixes, release recovery rehearsal | [TESTING](../TESTING.md) |
| [individual-accounts-release-2026-09-24.md](individual-accounts-release-2026-09-24.md) | 2026-09-24 | PR #13 | Decision retiring shared/public sign-in; invitation rules; iPhone confirmation; CI teardown fix | [SECURITY](../SECURITY.md), [PRODUCT](../PRODUCT.md#explicit-exclusions) |
| [account-settings-and-store-hub.md](account-settings-and-store-hub.md) | 2026-09-26 | PR #15 | Account/Store layout decisions; device-feedback navigation fix | [WORKFLOWS](../WORKFLOWS.md) |
| [inventory-foundation-and-shared-catalog.md](inventory-foundation-and-shared-catalog.md) | 2026-09-23 – 09-30 | PRs #12, #14, #17, #19 | Shared catalog/shelf design, native error contract, compact lists, evidence | [INVENTORY](../INVENTORY.md#catalog-and-shelves), [API](../API.md#errors-and-recovery) |
| [inventory-counts.md](inventory-counts.md) | 2026-09-25 – 09-29 | PRs #14, #17 | Count contract, worked example, rehearsal evidence | [INVENTORY](../INVENTORY.md#counts) |
| [production-and-assisted-inventory.md](production-and-assisted-inventory.md) | 2026-09-29 – 10-01 | PRs #17, #19, #20 | 1.01 allowance decision, production design, barcode scanning and real-label evidence, camera/scale/forecast phase design | [INVENTORY](../INVENTORY.md#recipes-and-production), [camera and invoice plan](../workstreams/camera-and-invoice-readiness.md) |
| [store-production-forecast.md](store-production-forecast.md) | 2026-10-01 – 10-02 | PR #20 | Advisory forecast decision (no training), source boundaries, evidence | [INVENTORY](../INVENTORY.md#advisory-forecasts) |
| [inventory-packages.md](inventory-packages.md) | 2026-10-01 – 10-03 | PR #20 | Package/case design, combining guard, pounds labels, unit correction, navigation audit, evidence | [INVENTORY](../INVENTORY.md#units-containers-and-packages) |

## Removed documents

Their accepted rules and unique facts were moved into the maintained documents
before removal.

| Document (last version) | Date | Why removed | Unique content now in |
| --- | --- | --- | --- |
| [docs/HANDOFF.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/HANDOFF.md) | 2026-09-22 | Duplicate handoff; mostly superseded "mobile web first"/F0 sequencing | [IMPLEMENTATION_PLAN](../IMPLEMENTATION_PLAN.md) |
| [docs/IMPLEMENTATION_HANDOFF.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/IMPLEMENTATION_HANDOFF.md) | 2026-09-20 | Self-declared pre-integration baseline | [ARCHITECTURE](../ARCHITECTURE.md) |
| [docs/TASKS.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/TASKS.md) | 2026-09-22 | Competing backlog ("I1 onward planned" after delivery) | [IMPLEMENTATION_PLAN](../IMPLEMENTATION_PLAN.md#roadmap); deferred items in [INVENTORY](../INVENTORY.md#future-inventory-rules) |
| [docs/parallel/ROUND_01.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/parallel/ROUND_01.md) | 2026-09-20 | Completed agent coordination round | — |
| [docs/parallel/ROUND_03.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/parallel/ROUND_03.md) | 2026-09-21 | Completed agent coordination round | — |
| [docs/prompts/CODEX_FOUNDATION.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/prompts/CODEX_FOUNDATION.md) | 2026-09-20 | Completed agent prompt | — |
| [docs/prompts/COPILOT_FOUNDATION.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/prompts/COPILOT_FOUNDATION.md) | 2026-09-20 | Completed agent prompt | — |
| [docs/prompts/CODEX_INTEGRATION_RUNTIME.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/prompts/CODEX_INTEGRATION_RUNTIME.md) | 2026-09-21 | Completed agent prompt | — |
| [docs/prompts/COPILOT_FASTAPI_INTEGRATION.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/prompts/COPILOT_FASTAPI_INTEGRATION.md) | 2026-09-21 | Completed agent prompt | — |
| [codex-foundation.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/workstreams/codex-foundation.md) | 2026-09-20 | Lane handoff (worker recovery, PR #2) | Worker health semantics in [DEPLOYMENT](../DEPLOYMENT.md) |
| [copilot-foundation.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/workstreams/copilot-foundation.md) | 2026-09-20 | Lane handoff (contract/browser tests, PR #1) | [TESTING](../TESTING.md) |
| [codex-f1-report-services.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/workstreams/codex-f1-report-services.md) | 2026-09-21 | Lane handoff (PR #4); "no FastAPI" statements superseded | [ARCHITECTURE](../ARCHITECTURE.md) |
| [copilot-f1-api-foundation.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/workstreams/copilot-f1-api-foundation.md) | 2026-09-21 | Lane handoff (PR #3) | [API](../API.md) |
| [codex-integration-runtime.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/workstreams/codex-integration-runtime.md) | 2026-09-21 | Lane handoff (services/runtime, PR #6) | Resource defaults and worker rules in [DEPLOYMENT](../DEPLOYMENT.md) |
| [copilot-fastapi-integration.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/workstreams/copilot-fastapi-integration.md) | 2026-09-21 | Lane handoff (FastAPI parity, PRs #5, #7) | [API](../API.md) |
| [copilot-accounts-permissions.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/workstreams/copilot-accounts-permissions.md) | 2026-09-22 | Duplicate of the archived accounts record (integration lane) | [SECURITY](../SECURITY.md), [API](../API.md) |
| [react-native-foundation.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/workstreams/react-native-foundation.md) | 2026-09-22 | Foundation handoff; its gates were delivered | [mobile README](../../apps/mobile/README.md) |
| [architecture-bloat-audit-2026-09-23.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/workstreams/architecture-bloat-audit-2026-09-23.md) | 2026-09-23 | Snapshot audit; remediations applied or tracked | [ARCHITECTURE](../ARCHITECTURE.md#known-coupling) |
| [browser-theme-2026-09-26.md](https://github.com/GetFluxxed/Shiftly/blob/df53f9852f8856f4ddc943d3212a6bde17379fbe/docs/workstreams/browser-theme-2026-09-26.md) | 2026-09-26 | Completed theme note; palette lives in `apps/mobile/src/ui/theme.ts` and `styles.css` | [mobile README](../../apps/mobile/README.md#visual-theme) |
