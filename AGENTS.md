# Shiftly agent instructions

Applies throughout this repository. Adapted on 2026-09-26 from the supplied
three-model workflow and Shiftly's current implementation decisions. Follow
system/developer instructions and the user's current request first; use applicable
directory guidance for more specific conventions.

## Start with the actual project state

- Verify the repository root, branch, worktree and working changes before editing.
  A tool's starting directory or an old conversation may refer to another checkout.
- Inspect relevant code, tests and documentation. Preserve existing uncommitted
  work; do not reset, clean, overwrite or stage unrelated changes.
- Use `rg` for file/text discovery. Batch independent reads, but keep dependent
  edits and state-changing operations ordered.
- Investigate the root cause before cutting code or splitting files. File count
  and file size alone do not prove bloat. Extend an existing boundary where it
  fits; avoid parallel implementations, generic frameworks and speculative rewrites.
- Keep changes proportional to the task. Preserve supported behavior outside its
  scope; justify new dependencies and configuration changes. Never remove or
  weaken checks merely to make a build pass.

## Read the current decisions

Use these documents as entry points, then inspect the relevant implementation:

| Concern | Source |
| --- | --- |
| Domain delivery order | [Implementation plan](docs/IMPLEMENTATION_PLAN.md) |
| Native client and device acceptance | [Native roadmap](docs/NATIVE_APP_ROADMAP.md), [mobile setup](apps/mobile/README.md) |
| Individual accounts and invitations | [Account release contract](docs/workstreams/individual-accounts-release-2026-09-24.md) |
| Company catalog and store shelves | [Inventory foundation](docs/workstreams/inventory-foundation-and-shared-catalog.md) |
| Current stock and reviewed counts | [Count contract](docs/workstreams/inventory-counts.md) |
| Broader inventory rules and future phases | [Inventory design](docs/INVENTORY.md) |
| Module boundaries and known coupling | [Architecture](docs/ARCHITECTURE.md), [bloat audit](docs/workstreams/architecture-bloat-audit-2026-09-23.md) |
| Verification and recovery | [Testing](docs/TESTING.md), [CI workflow](.github/workflows/ci.yml) |
| Schema and deployment | [Database](docs/DATABASE.md), [deployment](docs/DEPLOYMENT.md) |

Older sections of the architecture, security, database and planning documents
describe historical baselines or proposed features. The account release and
inventory workstream contracts above supersede their shared-login, web-first and
earlier inventory sequencing assumptions. Check actual code and migrations before
claiming a feature exists. If code conflicts with an accepted contract, investigate
and document the discrepancy rather than treating the implementation as permission
to discard the rule.

Record consequential design decisions and delivery evidence in the relevant
workstream document. Update plans when scope changes; distinguish implemented,
locally verified, CI verified, device verified and deployed states. Do not copy
transient branch names, network addresses or test totals into this instruction file.

## Model ownership and delegation

Use the lightest available model that can finish reliably without avoidable rework.
These are role assignments, not permission to bypass host/tool constraints:

| Model | Responsibility |
| --- | --- |
| Astra (`gpt-6-astra`) | Lead: requirements, architecture, data/API design, security, migration/concurrency strategy, difficult root-cause analysis, acceptance criteria and final review. |
| Sol (`gpt-5.6-sol`) | Substantial implementation: native screens, services, migrations, integrations, nontrivial debugging/refactors and meaningful tests within the agreed design. |
| Luna (`gpt-5.6-luna`) | Explicitly bounded, low-risk work: known renames/imports, documentation from settled behavior, fixtures, mechanical corrections and specified small UI changes. |

- Delegate to Sol or Luna when a concrete subtask can proceed independently
  alongside useful lead work. Do not hand off vague objectives such as "improve
  inventory" or "fix permissions." Define the design and observable result first.
- The lead may implement directly when work is small, tightly coupled to its
  reasoning, requires a prototype, or delegation would cost more than it saves.
  Unavailable models/tools are not a reason to stop: use the current capable model
  and state material limitations. Never claim delegation or independent review
  that did not happen.
- Use internal subagents for delegated work. Create a separate user-visible task
  only when the user explicitly requests one. Keep a coherent workstream together;
  summarize verified state when context becomes stale instead of restarting blindly.
- Give agents disjoint file ownership where possible and name one integration
  owner. They share a workspace. Serialize overlapping edits, Git/index operations,
  migration numbering and database changes; inspect status again before integrating.
- Astra retains design and final-review responsibility for authentication,
  authorization, persistence, migrations, concurrency, public APIs, infrastructure,
  major dependencies and changes that affect long-term extensibility. Sol can
  review routine Luna work; Luna is not the final reviewer for sensitive changes.
- Security or persistence work requires an established design. A "mechanical"
  migration is not automatically low risk; Luna may assist only with an explicitly
  specified transformation that receives lead review.

For delegated work provide: **Task, Goal, Context, Relevant files, Requirements,
Constraints/file ownership, Acceptance criteria, Verification, Escalate if**.
Include edge cases, expected inputs/outputs and behavior that must remain intact.
Break large features into bounded packages before assigning them.

Escalate Luna → Sol → Astra as complexity increases; requirement or architectural
conflicts can go directly to the lead. Report attempts, evidence/errors, affected
files, current hypothesis and the decision needed. Pause the affected part while
continuing independent work. Avoid repeated retries without new evidence.

## Development and review loop

1. Understand the request, current implementation, risks and unresolved decisions.
2. Define the smallest coherent design, acceptance criteria and verification plan;
   update the relevant workstream if the design changes.
3. Implement within existing boundaries, delegating independent work when useful.
4. Integrate, verify changed behavior and review failures at their root cause.
5. Review against the design, reconcile documentation and report actual evidence
   and remaining limitations. Measure before and after performance changes.

Resolve routine implementation choices autonomously. Ask for missing information
only when it materially changes the outcome or is needed for authorization. Do
the already-authorized preparation before requesting approval for a final action.

## Architecture and native experience

- React Native, Expo and TypeScript in `apps/mobile` are the primary phone/tablet
  experience. Build inventory screens natively; do not redirect them to a browser
  or start a separate React web rewrite without an approved scope change.
- Reuse shared controls, accessibility patterns and the existing cocoa/rose theme.
  Keep Expo routes thin and feature contracts/screens in their feature modules.
  Provide clear loading, error, empty, saving and unsaved-change states.
- FastAPI adapters under `backend/shiftly/api` parse/authorize/translate requests.
  Domain services own workflows and transactions; repositories own SQL and take
  the caller's connection. Register modules through the app/runtime composition.
- New inventory code must not import root `server`, `routes` or `reporting`, account
  mixin internals, or another feature's HTTP router. Reuse `core.http`, `core.native`
  and public account contracts; inventory owns its own audit/change records.
- Keep existing PostgreSQL/psycopg boundaries. Avoid an ORM, microservice split,
  second organization system or worker rewrite as a side effect of a feature.
  Expensive image/provider work belongs in durable jobs when that phase is added.
- Keep feature conflicts separate from identity failures. Known duplicate/stale
  record errors should preserve the form; invalid sessions or changed store/access
  must hide private state and trigger existing invalidation/revalidation behavior.
  Preserve conservative handling of unknown errors and delayed stale responses.

## Accounts and authorization

- All staff use individual usernames/passwords. Activation is invitation-only
  into baseline crew access. Tokens are opaque, single-use, expiring and bound
  server-side; links do not carry trusted role/permission claims. Consumption and
  account activation are atomic and recheck issuer authority.
- No public manager/admin/owner signup. Authorized administrators/owners assign
  permitted roles after activation; bootstrap ownership remains an operator action.
  Invitations must not grant elevated access.
- Crew and managers have one active store and cannot switch stores. Owners/admins
  can switch only within their authorized scope. Reports use the selected store.
- Reuse the existing business/store identity and capability policy. A hidden
  button, submitted role, object ID or `storeId` never grants authority.
- Every protected write calls the public
  `accounts.require_selected_store(..., connection=connection, expected_store_id=...)`
  inside the same transaction as the mutation. Derive scope/actor from its result;
  keep policy protection through the write and validate nested object scope.
- Preserve opaque native bearer sessions, SecureStore lifecycle, session epochs
  and private-state invalidation. Do not introduce a second client permission model.
- Shared crew credentials, password-only manager login and public signup are
  intentionally retired. Backward compatibility with these flows is not required;
  preserving existing data and supported individual-account workflows is required.

## Inventory integrity

- One shared catalog per existing business, with store listings and shelf
  placements referencing stable product IDs. A shelf assignment does not create
  stock. Keep SKUs as strings, retain leading zeros and reserve former aliases.
  Archive referenced products rather than deleting their history or balances.
- New product base units are `each`, `g`, `kg`. Preserve readable historical data.
  Use exact decimal strings at API boundaries and decimal/NUMERIC arithmetic for
  authoritative quantities; no floating-point stock calculations or silent unit
  reinterpretation. Full-container sizes are references, not amounts on hand.
- Preserve original measurements and snapshotted conversion references. Two full
  6 kg containers plus 1,250 g net partial equals 13.25 kg of the same SKU.
- One open whole-store count per store. Uncounted is distinct from explicitly
  counted zero; the first posted count establishes stock without assuming a prior
  zero. Draft/save/review actions do not change current inventory.
- Enforce draft → review → posted transitions and separate `inventory.view`,
  `counts.submit` and `counts.approve`. All required lines must be counted; stale
  versions, scope, configuration or baselines must produce actionable conflicts.
- Post stock, balance projections and immutable history atomically. Preserve
  request idempotency and recheck authorization on retries. Never blindly replay
  an uncertain write or silently overwrite another counter's saved work.
- Count differences are stock changes, not measured consumption. Receiving,
  waste, transfers, corrections, offline queues, camera/scale automation and
  forecasts have separate delivery gates. Future AI results are reviewed proposals;
  they cannot directly overwrite stock or infer partial weight from a photo alone.
- Keep catalog, stock and history reads bounded/searchable. Preserve alphabetical
  catalog ordering across pages. Aggregate a store's shelf measurements under the
  same SKU while keeping each store's balances independent.

## Data, tests and local operation

- Add versioned migrations; do not rewrite applied migration history. Rehearse
  fresh setup, upgrade/data preservation and recovery for schema changes. Back up
  existing demo data before migrating it. Do not invent opening balances or require
  destructive down migrations as the definition of reversibility.
- Database tests require explicit `TEST_DATABASE_URL` pointing to disposable
  PostgreSQL, never a fallback to application `DATABASE_URL` or `.env`. Recovery
  rehearsals use separate disposable source/restore databases. Never use live demo
  data as fixtures. Keep provider tests deterministic and free of paid AI calls.
- Choose verification for the change: focused service/API tests for backend
  behavior; native type/tests and relevant rendered journeys for UI behavior;
  migration/concurrency/recovery checks for data changes. Test behavior, failures
  and boundaries rather than mirroring implementation details.
- Native checks from the repository root: `pnpm --dir apps/mobile check` and,
  when appropriate, `pnpm --dir apps/mobile export:native`. Backend and recovery
  setup/commands live in `docs/TESTING.md`; current CI is `.github/workflows/ci.yml`.
  Use the repository's pinned dependency files and package manager.
- Documentation-only changes need content/link/diff review, not an application
  test run. Respect explicit user directions about local checks and report any
  resulting verification limits. Do not repeat passing suites without a changed
  dependency, new failure or unresolved concern; complete applicable required checks.
- Native exports and browser-rendered phone/tablet journeys do not prove physical
  device behavior, signed-build readiness or store publication. Report separately.
- Keep Expo/API testing on the local LAN unless the user explicitly authorizes
  public exposure. Put changing local API addresses in ignored mobile `.env.local`,
  not committed source. Never commit secrets, tokens, database dumps or runtime
  artifacts, or expose them in logs and handoffs.
- Local native development does not imply hosted FastAPI cutover. Commit, push,
  merge and deployment are separate actions; stay within the user's authorization.
  When publishing is requested, verify CI for the exact published revision and
  report its status accurately. Earlier CI results do not verify new changes.
