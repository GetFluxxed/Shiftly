# Workflows: browser vs. mobile

This document records only the differences between the browser and mobile versions
of Shiftly, followed by a list of documentation that needs attention.

- **Code baseline:** `origin/main` at `df53f98` (PR #21, engineering adoption). The
  local branch `codex/docs-integration-readiness` predates the mobile app, so paths
  below refer to `origin/main`.
- **Browser:** the HTML/JS pages served by FastAPI (`backend/shiftly/api/static.py`)
  and the legacy `server.py`. Page access is gated in
  `backend/shiftly/app.py` (`_default_page_access_provider`).
- **Mobile:** the Expo Router routes in `apps/mobile/app/`, backed by screens in
  `apps/mobile/src/`. Tab visibility is gated in `apps/mobile/app/(app)/_layout.tsx`.
- Scope is user-facing views only. (The Expo app also has a web build target; it is
  treated as mobile here, not as the browser client.)

## Platform route inventory

### Browser pages

| Page | Access | Views on the page |
| --- | --- | --- |
| `/` (`index.html`) | Public | Username + password sign-in; redirects by role/capability (`auth.js`) |
| `/activate.html` | Public | Invitation activation and password recovery |
| `/about.html` | Public | Product/about page |
| `/crew.html` | Unnamed or `reports.submit` | Shift notes submission, report confirmation, Head's Up display |
| `/manager.html` | `can_manage` | Shift report inbox, manager briefing, weekly overview, Head's Up edit dialog, management (manager list) |
| `/accounts.html` | Named account | Your access + store switch, change password / log out everywhere, people & permissions, business owner tools |
| `/production.html` | Named + `production.view` | Today (choose batches) → review deductions → confirm; recipe book; history |
| `/inventory.html` | Named + `inventory.view` | "Coming soon" placeholder only |

### Mobile routes

| Area | Routes |
| --- | --- |
| Auth | `sign-in`, `activate`, `index` (redirects to `/today`) |
| Tabs | `today`, `reports`, `inventory`, `production` (role `production` only), `store` (manager/owner), `accounts` |
| Heads Up | `heads-up` |
| Team | `team/index`, `team/[userId]`, `team/invite`, `team/assign`, `team/build`, `team/access` |
| Owner | `owner/index`, `owner/[userId]`, `owner/cutover` |
| Catalog | `catalog/index`, `catalog/[productId]`, `catalog/new`, `catalog/scan`, `catalog/packages/[productId]` |
| Shelves | `shelves/index`, `shelves/[shelfId]` |
| Counts | `counts/index`, `counts/[countId]`, `counts/[countId]/line/[lineId]`, `counts/[countId]/review`, `counts/history` |
| Stock | `stock/index`, `stock/[productId]` |
| Production | `production/index`, `production/run`, `production/review`, `production/recipes/index`, `production/recipes/[recipeId]`, `production/recipes/new`, `production/logs/index`, `production/logs/[logId]` |

## Paired views

These views exist on both platforms. The layouts differ, but the workflow is shared.

| Workflow | Browser | Mobile |
| --- | --- | --- |
| Sign in | `index.html` | `sign-in` |
| Activate invitation / reset password | `activate.html` | `activate` |
| Submit a shift report | `crew.html` (Shift Notes + Report Overview) | `reports` ("Write a report") |
| Read Head's Up | `crew.html`, `manager.html` | `today` (Heads Up card), `heads-up` |
| Edit Head's Up | `manager.html` (dialog) | `heads-up` (reached from `store`) |
| Shift report inbox with per-report briefing | `manager.html` (Inbox + Manager Briefing) | `reports` → Shift reports |
| Account profile, store switch, change password, sign out on every device | `accounts.html` sections 01–02 | `accounts` |
| Team list, edit store role/capabilities, remove access | `accounts.html` section 03 | `team/index`, `team/[userId]` |
| Invite a new person / reissue activation code | `accounts.html` section 03 | `team/invite`, `team/[userId]` |
| Add an existing account to the store | `accounts.html` section 03 | `team/assign` |
| Business delegation, ownership transfer, suspend/restore | `accounts.html` section 04 | `owner/index`, `owner/[userId]` |
| Record production (choose batches → review deductions → confirm) | `production.html` Today + Review | `production/run`, `production/review` |

### Partially paired

The feature exists on both platforms, but one side is less complete.

| Workflow | Browser | Mobile |
| --- | --- | --- |
| Recipe book | Read-only list of recipe cards | List, recipe detail, create and edit (`recipes.manage`) |
| Production history | List only | List, log detail, and reverse a confirmed log with a reason |
| Manager roster / last sign-in | Dedicated "Management" panel listing managers sorted by last sign-in | Last sign-in shown only on an individual team member's detail screen |
| Inventory | `inventory.html` exists but is a "Coming soon" placeholder | Full inventory workspace (see below) |

## Browser-only views

- **About page** (`about.html`).
- **Weekly Overview** (`manager.html`, `/api/weekly-overview`). Mobile has no weekly
  summary view.
- **Management panel** (`manager.html`): a standalone roster of manager accounts.
- **Single-page manager dashboard**: inbox, briefing, weekly overview, Head's Up, and
  management combined on one page.
- **Legacy store-code manager gate** (`manager.html` `#manager-auth-gate`). The
  markup remains, but `showLogin()` is never called, so it is unreachable.

## Mobile-only views

- **Today home** (`today`): greeting, current-store card, change-store shortcut,
  and role-based quick actions. The browser has no home page and redirects
  straight to a role workspace after sign-in.
- **Store hub** (`store`): entry point to Heads Up, Team members, Store access,
  Build team, and Owner tools.
- **Build team** (`team/build`) and **Store access** (`team/access`) summary screens.
- **Store sign-in cutover review** (`owner/cutover`).
- **Inventory hub** (`inventory`): Catalog, Open Shelves, Begin Count, Current Inventory.
- **Company catalog**: list, product detail, add product (`catalog.manage`).
- **Barcode scanning** (`catalog/scan`): camera or manual code lookup, create new
  item, or add a package to an existing item.
- **Packages & barcodes** (`catalog/packages/[productId]`): package options,
  combining items, using an item as a package of another.
- **Shelves**: shelf list, create shelf, shelf detail with product assignment.
- **Inventory counts**: start a store count, count session, per-location count
  entry (packages + loose, full containers + partial, measured total, zero),
  review/finalize, count history.
- **Current stock**: stock list and per-product stock detail with the last physical count.
- **Recipe detail and recipe editor** (`production/recipes/[recipeId]`,
  `production/recipes/new`).
- **Production log detail and reversal** (`production/logs/[logId]`).
- **Production reports with advisory forecast** (`reports` → Production reports,
  `ForecastPanel` in `apps/mobile/src/reports/ProductionReports.tsx`).

## Gaps by platform

### Views the browser is missing (present on mobile)

1. Today home dashboard
2. Store hub, Build team, Store access screens
3. Owner store sign-in cutover review
4. Inventory hub (the browser page is a placeholder)
5. Company catalog list, product detail, add product
6. Barcode scan / code lookup
7. Packages & barcodes management, including combining items
8. Shelves list and shelf detail / product assignment
9. Inventory counts: start, count session, count entry, review/finalize, history
10. Current stock list and product stock detail
11. Recipe detail, create recipe, edit recipe
12. Production log detail and log reversal
13. Production reports inbox and advisory production forecast

### Views mobile is missing (present on browser)

1. Weekly Overview
2. Standalone Management roster (manager accounts by last sign-in)
3. About page

## Navigation and access differences

- **Landing:** browser sign-in redirects by role/capability: production →
  `production.html`, `reports.view` → `manager.html`, `reports.submit` →
  `crew.html`, otherwise `accounts.html`. Mobile always lands on `today`.
- **Production entry:** the browser serves `production.html` to any named account
  with `production.view`. Mobile shows the Production tab only for the
  `production` role; other roles with `production.view` reach it from a Today
  quick action.
- **Store tab:** mobile shows Store only to managers and owners. The browser has
  no equivalent page, and its team/owner tools live inside `accounts.html`.
- **Workspace restoration:** mobile restores the last screen and drafts per
  account/store (`apps/mobile/src/restoration/`). Browser production keeps a
  local draft only for the production run.

## Documentation requiring attention

Each in-scope document (`docs/*.md`, `docs/NATIVE_APP_ROADMAP.md`,
`docs/workstreams/*`, `docs/prompts/*`, `docs/parallel/*`) was compared against
the baseline code. The documents below have roughly half or more of their content
deprecated, already implemented, or no longer in scope.

### Core documents

| Document | Approx. stale | Reason |
| --- | --- | --- |
| `docs/HANDOFF.md` | ~75% | Most of the file is explicitly a "historical planning baseline". It still says FastAPI, inventory, forecasting and an app shell are "planned, not implemented", describes a superseded "mobile web first" direction, and says "Begin F0". All of these are contradicted by `backend/shiftly/` and `apps/mobile/`. |
| `docs/IMPLEMENTATION_HANDOFF.md` | ~90% | Self-described historical pre-integration baseline (migrations 001–011, `python server.py` only, "no FastAPI"). The "known foundation work" list has since been delivered. |
| `docs/TASKS.md` | ~65% | Says "I1 onward remain planned", but catalog (I1), shelves (I2, partial), movements/balances (I3, partial), counts (I4), recipes (S1, partial) and N1 are implemented. The "Next bounded task" (first shelf, then counts) is complete. |
| `docs/NATIVE_APP_ROADMAP.md` | ~60% | Phase 1 is still labeled "underway". Phase 2 parity, the phase 3 catalog/counts work, barcode capture, local restoration, Heads Up and production are implemented. It still calls Forecast "planned next", but the mobile forecast panel exists. Weekly Overview remains the only open parity item. |
| `docs/PRODUCT.md` | ~50% | "Current inventory functionality is not implemented" and "shared crew sign-in during enrollment" are both outdated: inventory exists on mobile and shared login was retired. The "manager window will offer two distinct spaces" model does not match either client. The first-native-slice boundaries are already exceeded. |

### Workstreams (completed delivery records)

Each of these records describes work that is already implemented and merged. Some
remain useful as dated evidence or behavior contracts, but their content describes
completed work rather than current or upcoming scope.

| Document | Reason |
| --- | --- |
| `docs/workstreams/account-settings-and-store-hub.md` | Self-marked "Implemented and locally verified"; `accounts` and `store` screens exist. |
| `docs/workstreams/architecture-bloat-audit-2026-09-23.md` | Snapshot audit whose recommendations (separate inventory API/service, feature vs. session errors) were applied; line references describe the original snapshot. |
| `docs/workstreams/browser-theme-2026-09-26.md` | Theme alignment is implemented in `styles.css` and the browser pages. |
| `docs/workstreams/codex-accounts-permissions.md` | Backend lane handoff; the "required peer changes" were completed in the integration lane. |
| `docs/workstreams/codex-f1-report-services.md` | States "no FastAPI app… legacy server remains the runtime entry point", which was superseded once FastAPI parity merged. |
| `docs/workstreams/codex-foundation.md` | F0 worker-recovery handoff; merged. |
| `docs/workstreams/codex-integration-runtime.md` | Round 3 runtime handoff; merged. |
| `docs/workstreams/copilot-accounts-permissions.md` | Accounts & Access integration handoff; merged. |
| `docs/workstreams/copilot-f1-api-foundation.md` | "Development-only FastAPI factory and health routes"; FastAPI now serves all routes. |
| `docs/workstreams/copilot-fastapi-integration.md` | FastAPI parity handoff; merged. |
| `docs/workstreams/copilot-foundation.md` | F0 contract/browser-test handoff; merged. |
| `docs/workstreams/focused-verification.md` | Verification evidence for PR #7-era gates that have since closed. |
| `docs/workstreams/individual-accounts-release-2026-09-24.md` | Individual-account release decision; implemented. |
| `docs/workstreams/inventory-counts.md` | Self-marked "Status: implemented". |
| `docs/workstreams/inventory-foundation-and-shared-catalog.md` | Describes the implemented catalog/shelf slice; its "next approved slice" (counts) is also implemented. |
| `docs/workstreams/inventory-packages.md` | Package options and mixed counts; implemented and verified per the document itself. |
| `docs/workstreams/production-and-assisted-inventory.md` | Of the four approved capabilities, production, barcode-assisted catalog and advisory forecasting are implemented. Only shelf-photo counting and scale capture remain deferred. |
| `docs/workstreams/react-native-foundation.md` | Native foundation handoff; its "next delivery gates" have been delivered. |
| `docs/workstreams/store-production-forecast.md` | Self-marked "Implemented and locally verified on 2026-10-01". |

### Prompts and parallel rounds (completed assignments)

| Document | Reason |
| --- | --- |
| `docs/prompts/CODEX_FOUNDATION.md` | Agent prompt for F0 worker recovery; delivered and merged. |
| `docs/prompts/COPILOT_FOUNDATION.md` | Agent prompt for F0 contracts/browser CI; delivered and merged. |
| `docs/prompts/CODEX_INTEGRATION_RUNTIME.md` | Agent prompt for Round 3 services/runtime; delivered and merged. |
| `docs/prompts/COPILOT_FASTAPI_INTEGRATION.md` | Agent prompt for Round 3 FastAPI parity; delivered and merged. |
| `docs/parallel/ROUND_01.md` | Still reads "assignments prepared; implementation has not started", but both lanes merged. |
| `docs/parallel/ROUND_03.md` | Self-described historical assignment text; both lanes merged through PR #7. |

### Local-only documents (untracked in this checkout, absent from `origin/main`)

| Document | Reason |
| --- | --- |
| `docs/parallel/ROUND_02.md` | Reads "work has not started", but both Round 2 lanes merged in PRs #3 and #4. |
| `docs/prompts/CODEX_F1_REPORT_SERVICES.md` | Agent prompt for F1 report-service extraction; delivered (`backend/shiftly/reports/`). |
| `docs/prompts/COPILOT_F1_API_FOUNDATION.md` | Agent prompt for the F1 FastAPI foundation; delivered and since expanded to full parity. |

`docs/AGENTS.md` (also local-only) is a model-workflow process guide rather than
a description of the code, so it was not scored against the codebase.

### Reviewed, below the threshold

These were reviewed and are not flagged. Each contains some outdated content
(well under half).

- `docs/API.md`: the "Proposed broader inventory API" (`/api/v1/stores/...`)
  section was superseded by the implemented mobile inventory routes. The document
  also does not describe the implemented counts, stock, package, barcode,
  production or forecast endpoints.
- `docs/INVENTORY.md`: catalog, shelves, standard containers and counts are now
  implemented, but most of the specification (pars, camera counts, sales
  insights, receiving) is still future scope. The "Manager → Inventory" browser
  entry point does not exist; the browser page is a placeholder.
- `docs/workstreams/camera-and-invoice-readiness.md`: still forward-looking and in scope.
- `docs/workstreams/engineering-adoption.md`: the most recent workstream (PR #21);
  it matches the code.
- `docs/ARCHITECTURE.md`, `docs/DATABASE.md` (migrations 001–024 match),
  `docs/DEPLOYMENT.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/SECURITY.md`,
  `docs/TESTING.md`: current.
