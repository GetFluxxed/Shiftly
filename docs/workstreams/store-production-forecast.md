# Store production reports and advisory forecasting

Decision date: 2026-10-01. The user brought an advisory production forecast forward
into the native Reports inbox. This is separate from the later sales, supplier,
reordering and evaluated forecasting phase. No camera, invoice or scale work is
included in this slice. Existing inventory and production history must survive.

## Native inventory and report experience

Shelf details begin with compact Assigned products rows. Each quantity is the
current **storewide** balance for that product, including posted counts and later
production movements, not a separate shelf balance. Unknown stock is `N/A`;
explicit zero is `0`. Assigning a product still creates no stock.

Current inventory uses compact Product, Quantity, Unit and Updated columns.
Search, shelf filters, pagination and product details remain available. Count
sessions are titled **Count** and show **Product accounted for: x/x**. A product
is accounted for only after every required location for that product is counted;
zero counts as entered, missing does not. Posting still requires all locations.

Reports opens directly to the inbox with Shift reports and Production reports
selectors. The redundant Report Inbox action is removed. Production records show
store, date, author, flavors, batches and recorded yields; reversals remain visible.
Production accounts continue to have no Reports or Store access.

## Authorization and source boundaries

Forecast reads and requests require `forecasts.view`, `reports.view`,
`production.view` and `inventory.view` together. Each request derives company and
store from the current authorized session. Writes recheck selected-store authority
inside their transaction, including idempotent retries. IDs supplied by the client
cannot expand scope. Jobs and snapshots retain their company/store ownership.

The snapshot combines a bounded 28-day history of confirmed, unreversed production,
its recorded recipe revisions and estimated ingredient deductions, relevant current
recipes with quantities/yields, store stock with count/movement freshness, and
recent shift notes. Company recipes are contextual reference data; another store's
production, stock and reports are excluded. Source text is untrusted input.

Use exact decimal arithmetic for facts. Production is not sales, absent dates are
not zero production, physical count differences are not measured consumption, and
unknown balances are not zero. Coverage and truncation must be disclosed.

## Advisory generation

Confirmed production queues a store analysis transactionally; provider work runs
later in the supervised durable worker. Authorized managers can also request an
analysis. Stable request identities and store/source/prompt/model deduplication
avoid duplicate work. Claims expire, retries are bounded, and stale workers cannot
complete another worker's claim. No model output writes inventory or recipes.

Use the existing server-side model configuration through the Responses API with
strict structured output and `store: false`. Validate recipe IDs, recommendation
dates, whole batch quantities and all output bounds. Input and output are bounded;
provider failures remain visible without exposing secrets or raw report content.
The model analyzes the supplied records per request. This does **not** fine-tune
or automatically train a model on company records.

Fewer than seven distinct recorded production days yields exact source facts and
an insufficient-history message, with no AI analysis or invented recommendations.
Seven days is only a minimum entry gate, not proof of forecast quality. Suggestions
for the next three days remain advisory and require later evaluation against real
outcomes. They are not purchasing deadlines or staffing instructions.

Show the snapshot date, data coverage, generation status and stale state. New
counts, production/reversals, recipe edits and relevant shift reports can make
saved analysis stale. Users can inspect recorded facts when generation is
unavailable. No API key is added or changed by this implementation.

## Verification and release boundaries

Required evidence covers wrong-store/company access, restricted/delegated/revoked
accounts, request replay, source scope and limits, recipe revisions, unknown stock,
sparse history, invalid model output, provider failure, lease expiry, exhausted
claims, stale completion, source changes and migration recovery. Tests use fake
providers and disposable PostgreSQL, never paid calls or live inventory fixtures.

Migration 023 adds forecast snapshots, request receipts and jobs. Back up the local
demo and rehearse additive upgrade plus restore before applying it there. Native
checks and rendered phone/tablet journeys precede device acceptance. CI, hosted
deployment, live model evaluation, physical-device acceptance and broader security
and policy review remain separate evidence gates.

## Local delivery evidence

Implemented and locally verified on 2026-10-01. The final review corrected partial
recipe snapshots, selected-report history scope, failed-job retry behavior,
provider refusal/incomplete-response handling, delayed native responses, and exact
quantity display at narrow widths.

- Native TypeScript and 117 tests passed; iOS and Android exports succeeded.
- Compact inventory and Reports rendered journeys passed at 320, 768, 1024 and
  1440 pixels, including a real forecast API envelope. Existing shelf and count
  navigation/assignment journeys also passed.
- Forecast source/service, simulated provider, independent authorization/recovery,
  and supervised worker checks passed. A seven-day fake-provider forecast completed
  without changing stock quantity or balance version. Expired/exhausted claims,
  concurrent retries, narrow delegated permissions and blocked-worker shutdown
  received independent checks. Existing production and migration checks passed.
- Migration 023 was rehearsed on a private copy of the local demo. All existing
  rows and original columns across 41 tables matched before/after. Restoring the
  upgraded backup reproduced the upgraded data.
- With the local API and worker stopped, a fresh private backup was taken and 023
  applied to the demo. Every existing row across those 41 tables remained unchanged.
  The refreshed API, supervised worker and local Expo server report healthy.

The local demo has no OpenAI API key configured. Its UI therefore reports AI
unavailable; no paid provider requests or real-model accuracy evaluation occurred.
Existing reports were not backfilled into forecast jobs; authorized requests and
new confirmed production trigger analysis once configuration is available.
Physical-device acceptance, live model evaluation, CI, commit/push and hosted
rollout were not performed as part of this slice.


## Shelf name editing refinement

On 2026-10-02, shelf renaming moved from the shelf detail form to the pencil action
on each Open Shelves card. Card taps still open assigned products. The edit window
prefills the name, offers Save/Cancel, preserves failed drafts, and requires a
fresh shelf version after a concurrent edit. The inline rename card is removed.
The window respects safe areas and scrolls within short phone/tablet viewports.

Local TypeScript, 117 mobile tests, and seven focused rendered shelf journeys
passed. The final window also passed full-button-visibility checks at 320 pixels
and in 768 × 360 landscape. Assignments, quantities and configuration permission
checks remain intact. Physical keyboard/device acceptance is separate.
