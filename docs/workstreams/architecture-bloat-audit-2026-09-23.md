# Architecture and bloat audit — 23 September 2026

## Decision

Continue with the current React Native app and modular Python backend. A rewrite is not justified by this audit. The main risk is **unclear boundaries between old and new implementations**, rather than excessive file count or dependencies.

Before the first shelf, separate ordinary feature errors from session failures and give inventory its own API/service boundary. Keep the reporting worker, account lifecycle, and existing browser workflows stable during that slice. Defer their larger extractions to separate changes with existing regression coverage.

The agreed first outcome is: **create a named shelf in a selected store, create/select products with SKUs, and assign those products to the shelf.** Placement describes what belongs there; it does not assert quantity on hand.

This document is the analysis and proposed sequence. No application code, permissions, database schema, or deployment was changed during the audit.

## Remediation follow-up

The small enabling changes are tracked in the [inventory foundation and shared
company catalog](inventory-foundation-and-shared-catalog.md). Findings and source
line references below describe the original audit snapshot; implementation status
and current contracts live in that follow-up. The larger worker/read-query changes
remain deferred as recommended.

## Baseline and method

Audited `/Users/getfluxxed/projects/Shiftly-codex-react-native`, branch `codex/react-native-foundation`, commit `9cbc230`, **including the current uncommitted account screens, account administration service, and theme changes**. This is the native app worktree. The older `codex/reports-module` worktree is not the implementation baseline and was left untouched.

The pass covered the source inventory, Python import graph, runtime composition, both server transports, native transport/session/UI patterns, account policy and transaction ownership, reporting/jobs, migrations, test organization, CI, deployment manifests, and current planning documents. Critical dependency paths were traced manually. File sizes and static imports are indicators, not proof of a defect or measured performance problems.

| Area | Source files | Physical lines |
| --- | ---: | ---: |
| Root Python/browser source | 23 | 3,296 |
| Backend package | 48 | 4,135 |
| Native app source | 38 | 1,551 |
| Tests, including native tests | 44 | 7,795 |
| Operational scripts | 3 | 608 |
| SQL migrations | 14 | 300 |

Counts exclude dependencies, generated Expo directories, documentation, and lockfiles. Backend totals include operator/rehearsal modules; native totals include thin route files. Physical lines understate the complexity of compact JSX. The largest application files are `reporting.py` (474 lines), `accounts_lifecycle.py` (439), and `server.py` (384). None of these sizes alone warrants splitting a file.

Fresh verification: native TypeScript checking passed and **45/45 native tests passed**. The audit's AST scan parsed the Python source. The full PostgreSQL/browser/recovery suites were not rerun in this analysis-only pass; earlier verification is not presented as a fresh result. No production environment or load benchmark was inspected.

## Findings and their causes

### 1. Feature conflicts are coupled to the entire signed-in workspace

**Priority: address before the shelf UI. Confirmed current behavior.**

Evidence:

- [Session controller](../../apps/mobile/src/session/controller.ts#L172): every private-request `403` or `409` advances the session epoch and locks the whole workspace.
- [API client](../../apps/mobile/src/api/client.ts#L3): errors retain only a message and HTTP status.
- [Error adapter](../../backend/shiftly/api/accounts.py#L29): the response drops the service error code.
- [Account lifecycle](../../backend/shiftly/identity/accounts_lifecycle.py#L101): an already-used username is a normal `conflict`, so the problem exists before inventory.
- [Controller tests](../../apps/mobile/tests/controller.test.ts#L91): the current tests explicitly require broad `403`/`409` invalidation.

**Root cause:** an HTTP status is doing two jobs: describing a failed operation and deciding whether the user's identity/store is still trustworthy. An inventory duplicate SKU or concurrent edit would trigger the same global lock as a changed store.

**Targeted remedy:** introduce stable, machine-readable distinctions for invalid/expired identity, invalid store context, denied action, duplicate identifier, and stale record. Keep the existing human-readable error for compatibility. Native sessions must still clear or revalidate on actual identity/access changes; correctable business conflicts should stay in the form. Retain conservative handling for unknown legacy responses. Merely returning the current generic `conflict`/`forbidden` code is insufficient—the distinct causes need representation.

**Proof needed:** duplicate username/SKU preserves the current form and session; revoked membership and stale selected-store requests still hide private data; delayed results from a previous store remain discarded.

### 2. New features currently have to reach into shared transport code

**Priority: establish the inventory boundary during the first slice; consolidate old account dispatch later.**

Evidence:

- [Legacy account dispatch](../../routes.py#L226), [browser FastAPI dispatch](../../backend/shiftly/api/accounts.py#L83), and [native account dispatch](../../backend/shiftly/api/mobile.py#L57) repeat command-to-field mapping.
- [Native adapter](../../backend/shiftly/api/mobile.py#L16) imports general helpers from the sibling browser accounts router.
- [Native client](../../apps/mobile/src/api/client.ts#L26) centrally enumerates account/report paths and has feature-specific uncertain-write messages at lines 47–53.
- [Team forms](../../apps/mobile/src/accounts/TeamScreens.tsx#L51) assemble endpoint strings and payloads directly in UI code.

**Root cause:** transport mechanics, feature contracts, and account-specific behavior share the same boundaries. Native and browser credentials legitimately differ; repeating business command translation across transports is the part that can drift.

**Targeted remedy:** a dedicated inventory router and typed native inventory API module. Extract only the common transport/context helpers needed to register that router independently of browser account routes. Preserve fixed-origin/path validation when adding inventory URLs. Let feature code provide uncertain-write recovery guidance; never add automatic write retries without a server deduplication contract. Avoid a generic CRUD framework or a new routing system.

Later, consolidate account command validation/dispatch while retaining separate cookie and bearer adapters. Do not turn the native adapter into one growing file containing every module.

### 3. Account files are split physically, but transactions and private helpers still bind domains together

**Priority: avoid copying this dependency pattern into inventory; deeper identity cleanup can follow.**

Evidence:

- [AccountsService](../../backend/shiftly/identity/accounts.py#L7) composes core, lifecycle, and administration mixins. Administration calls private methods defined by the other mixins.
- [Identity service](../../backend/shiftly/identity/service.py#L13) owns shared `IdentityError`/`SessionResult` types, then lazily constructs AccountsService at line 45. Account core/policy/lifecycle import those types back from the service. Static import analysis therefore finds a cycle. Lazy imports currently accommodate it; this is **not** a demonstrated startup failure.
- [Report repository](../../backend/shiftly/reports/repository.py#L18) imports the account-core lock and performs authorization inside persistence work.
- [Store repository](../../backend/shiftly/stores/repository.py#L53) calls `accounts.require` and the private `accounts._audit` method.

**Root cause:** transaction ownership and public cross-module contracts are implicit. Splitting methods into more mixin files does not reduce their shared dependencies.

**Targeted remedy:** inventory owns its short transaction and calls the existing public [transaction-scoped `accounts.require`](../../backend/shiftly/identity/accounts_core.py#L188) within that same transaction. Derive store/business scope from the validated actor and explicitly enforce the selected-store precondition. Inventory queries take that transaction; they do not receive the whole AccountsService or call private account helpers. Inventory records its own change events rather than putting stock/location events into account audit history.

A later small extraction can put identity errors/session value types in a neutral module, preserving public import compatibility. Refactor mixins only when a clear independent responsibility emerges. Do **not** move authorization outside the write transaction: the current lock/recheck prevents a revocation racing a write.

### 4. The new runtime still depends on the legacy reporting implementation

**Priority: before new photo/AI jobs; not a shelf prerequisite.**

Evidence:

- [Provider factory](../../backend/shiftly/runtime/provider.py#L5) calls `reporting.call_openai`.
- [External worker](../../backend/shiftly/jobs/worker.py#L32) imports root `reporting` and uses its claim, execution, completion, and failure functions.
- [Root reporting module](../../reporting.py#L20) loads settings at import time and combines process globals, provider transport, queue persistence, worker orchestration, and compatibility facades.
- [Global test fixtures](../../tests/conftest.py#L12) import the old server/reporting modules and patch their process state even for tests elsewhere in the repository.

**Root cause:** service extraction stopped before provider/worker ownership was fully moved. The compatibility facade still owns implementation that the new runtime needs, so dependencies point both ways across the migration boundary.

**Targeted remedy, separately:** move provider transport into an explicit provider module and queue persistence/worker execution under `backend/shiftly/jobs`. Leave root reporting functions as backward-compatible delegates. Narrow legacy fixtures to tests that need them as the dependency moves. Preserve lease ownership, retries, failure recovery, wake/poll behavior, and deterministic provider injection.

Shelf creation and product placement do not need a provider or job worker. Wiring them into reporting would create avoidable coupling. A microservice split is unnecessary.

### 5. Read amplification is combined with a schema-wide policy lock

**Priority: before substantial store/team growth; measure before redesigning locks.**

Evidence:

- [Policy lock](../../backend/shiftly/identity/accounts_core.py#L21) serializes protected operations within the database schema across processes.
- [Management projection](../../backend/shiftly/identity/accounts_administration.py#L7) loads the roster and, for owners, a business directory. It issues additional queries per member/person while retaining policy protection.
- [Administration screen wrapper](../../apps/mobile/src/accounts/AdminComponents.tsx#L13) loads that projection for each team/owner screen, including small forms.
- [Authorized stores](../../backend/shiftly/identity/accounts_core.py#L192) evaluates policy per candidate store; [report inbox](../../backend/shiftly/reports/repository.py#L89) then returns all authorized reports without pagination.

**Root cause:** broad read projections and repeated row-by-row policy queries share a correctness-first global serialization mechanism. Returning a larger dataset is currently the default way to supply a smaller screen.

**Consequence:** query cost grows with people, stores, and report history; long protected reads can delay unrelated protected writes. This is a structural scaling risk, not a measured current outage.

**Targeted remedy:** batch member policy inputs, separate form choices from roster/directory pages, and bound list queries. Add pagination and explicit response records before large datasets. Keep inventory lists bounded from their first implementation. Retain the policy lock for the pilot; any narrower lock scheme needs concurrent revocation/ownership tests and measurements first.

### 6. Multiple planning/runtime baselines make it easy to develop against the wrong system

**Priority: clarify before shelf implementation; hosted cutover remains a separate delivery.**

Evidence:

- [Implementation plan](../IMPLEMENTATION_PLAN.md#L14) supersedes mobile web with React Native near the top, but its phase-5 section, decision table, and immediate-next-work section still refer to older sequencing.
- [Architecture ownership section](../ARCHITECTURE.md#L145) treats multi-store organization as undecided; migration 014 and account services already implement businesses and business memberships.
- [Render manifest](../../render.yaml#L9) still starts `server.py`, which does not provide `/api/mobile`. [Deployment documentation](../DEPLOYMENT.md#L3) explicitly says hosted FastAPI cutover is pending.

**Root cause:** historical plans remain mixed with current instructions while both runtimes remain supported. Preserving the old deployment is deliberate; treating it as the native deployment would be a mistake.

**Targeted remedy:** designate the native roadmap plus a current implementation status as the entry point, label historical sections, and document this first-shelf slice. Reuse existing business/store identity; do not introduce a second organization hierarchy. Local shelf development can use the current FastAPI demo. Hosting that feature requires a separately verified FastAPI/worker/migration rollout; this audit does not establish production readiness.

### 7. Strong lower-level tests do not yet cover the whole native screen journey

**Priority: add focused coverage with the shelf slice.**

CI already checks native types/tests, bundles iOS/Android, runs Python/browser tests, and rehearses database/worker recovery. This is useful protection, not test bloat.

The 45 native tests primarily cover transport/session behavior and two administration helpers. They do not render the full create/edit/navigation flows. Type checking and a successful bundle cannot prove that a shelf form retains input after a conflict or that a real phone shows the right store after switching.

**Targeted remedy:** test the new service/API boundaries and a small number of actual shelf screen interactions, then exercise the flow on the iPhone. Keep existing session race/revocation tests. Do not create large snapshot suites that merely mirror JSX.

## What should stay

- Thin Expo route files, shared visual components, and centralized theme/font values are useful separation, not excess abstraction.
- Session epochs, secure credential storage, private-state clearing, focus/background cleanup, and current-policy validation protect account/store boundaries. Simplify their contracts, not their guarantees.
- Numbered additive migrations, constraints, isolated database tests, and recovery rehearsals protect existing data. Do not squash or rewrite migrations 001–014 for appearance.
- The old browser surface still has a supported runtime and rollback role. It is not demonstrated dead code and should not be deleted to reduce line counts.
- Keep one deployable application with cohesive modules. No event bus, plugin system, generic repository layer, or additional service is necessary for the first shelf.

## First-shelf implementation sequence

### A. Small enabling changes

1. Add the explicit error distinctions and update native handling/tests. Preserve conservative treatment of ambiguous old responses and existing browser contracts.
2. Isolate the shared native request/context helpers so inventory can register its own router. Keep all credential validation and selected-store rules.
3. Update current sequencing/ownership documentation. Review the current uncommitted account/theme work as the baseline; do not overwrite it or combine unrelated worker refactoring into this feature.

Do not make completion of all seven findings a prerequisite for shelves.

### B. One bounded inventory module

Recommended organization—not a scaffold to create in full before it is useful:

```text
backend/shiftly/inventory/     service, persistence, domain errors/contracts
backend/shiftly/api/           independent native inventory router
apps/mobile/src/inventory/    typed feature API, shelf/product screens
apps/mobile/app/(app)/        thin inventory routes
migrations/015_*.sql          additive catalog/location/assignment schema
```

The service owns validation and transactions; the router owns HTTP parsing/authentication delivery; native screens own interaction and presentation. Register the service in the existing composition root and the router in the existing app factory. Inventory must not import root `server`, `routes`, `reporting`, or account mixin internals.

Recommended initial data model:

| Concept | Minimum useful contract |
| --- | --- |
| Catalog product | Stable ID, existing business ID, name, string SKU, explicit base unit, active state. Decide/document SKU normalization and enforce business-scoped uniqueness; retain leading zeros. |
| Store product | Explicit listing connecting an existing catalog product to the selected store; enforce that store and product belong to the same business. No duplicate product identities per shelf. |
| Location | Stable ID and code, store ID, editable display name, kind `shelf`, active state. A root-level shelf can work immediately; leave room for a same-store parent without requiring area/rack setup screens today. |
| Assignment | Unique store/location/store-product relationship. The same product may belong on multiple shelves. Database relationships must reject cross-store/cross-business references. |
| Change history | Actor, scope, operation, target, timestamp, and relevant before/after values recorded with the change. This is configuration history, not stock movement history. |

Use existing `businesses`, `stores`, and named account IDs. A business catalog with store listings fits existing shared-catalog permission semantics; document this choice before the migration. Today only the shelf location kind needs UI. Broader hierarchy validation and additional kinds can follow when that feature is introduced.

Recommended use of existing permissions:

- `inventory.view`: see shelves and assigned products in the selected authorized store.
- `configuration.manage`: create/rename shelves and assign/remove listed products at that store.
- `catalog.manage`: create/edit shared product identities and SKUs. Owners have it; explicitly delegated accounts may have it. A manager's local role alone must not silently grant shared-catalog authority.

The server enforces these capabilities; screen visibility is only guidance. Each write rechecks current access and selected-store context within its transaction. Required capabilities must also be reflected in the UI entry path.

Native flow: **Inventory → Shelves → Create shelf → Shelf details → Add products**. Offer product/SKU creation when authorized and an empty-catalog explanation otherwise. Show the selected store throughout and preserve the existing visual theme. A product assignment should be independently addable/removable, not replace every assignment from a possibly stale form.

Use uniqueness and explicit idempotent assignment semantics to prevent duplicate placement. For creation, define a request-identity/deduplication contract or clear refresh-before-retry recovery; do not blindly replay uncertain writes. Keep the first release online; do not build offline synchronization for this slice.

Excluded from this first slice: quantities, stock balances, purchasing pars, pack conversions, receipts, counts/approval, camera uploads, image recognition/training, and forecasting. None is necessary to establish a named shelf with assigned SKUs.

### C. Acceptance and regression gates

The shelf is complete when:

1. An authorized account creates a named shelf in one store, creates/selects a product with its SKU, assigns it, and sees the same data after refresh/restart.
2. Duplicate SKU and invalid form data show actionable local errors without locking the whole app or losing the draft.
3. A product can be assigned to more than one shelf; duplicate assignment cannot create duplicate rows. Removing placement does not delete the product.
4. Switching stores cannot show or modify the previous store's shelves. Crafted requests and database constraints reject foreign store/business relationships.
5. Crew with view access can read; unauthorized writes fail; a membership revoked during a write cannot allow that write to commit afterward under stale authority.
6. Repeated/uncertain requests cannot silently create duplicate configuration. Scope and actor are recorded with successful changes.
7. Migration 014 → 015 and a fresh database both succeed; existing account/report records and migration behavior remain intact. Reapplying the coordinated migration is safe.
8. Existing account/report service and transport tests, native checks, and relevant browser compatibility checks pass. Exercise shelf creation/assignment, correction, store switching, and app background/return on the iPhone; bundling alone is insufficient.

After this slice: isolate provider/jobs before camera work; optimize bounded reads before larger pilots; retire compatibility code only after hosted cutover and an explicit support decision. The measure of success is that the next inventory feature changes inventory files plus a small registration point, rather than reopening reporting and account internals.
