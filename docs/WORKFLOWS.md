# Workflows: browser and mobile

Reviewed against source revision `df53f98` on 2026-10-21. This document maps each
user workflow to the browser and native clients, who can reach it, and where the
two clients intentionally or currently differ. It describes source behavior only;
deployment and device status are in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md#status-matrix).

- **Browser:** root HTML/JS pages served by FastAPI (`backend/shiftly/api/static.py`)
  and by the legacy `server.py`. Page access is decided server-side in
  `backend/shiftly/app.py` (`_default_page_access_provider`) and `server.py`.
- **Mobile:** Expo Router routes in `apps/mobile/app/`, screens in
  `apps/mobile/src/`. Tab visibility is in `apps/mobile/app/(app)/_layout.tsx`.
  The native API (`/api/mobile`) exists only on the FastAPI runtime.
- Hidden buttons and tabs are usability features. The server rechecks every
  capability; see [SECURITY.md](SECURITY.md#roles-and-capabilities).

A workflow missing from one client is recorded here as a fact. It is a parity
requirement only where the [implementation plan](IMPLEMENTATION_PLAN.md) says so.

## Entry and navigation

| Aspect | Browser | Mobile |
| --- | --- | --- |
| Sign-in | `/` username + password | `sign-in` username + password |
| Activation / password recovery | `/activate.html` (token in URL fragment or typed) | `activate` (code typed) |
| Landing after sign-in | Production role → `production.html`; `reports.view` → `manager.html`; `reports.submit` → `crew.html`; `production.view` → `production.html`; otherwise `accounts.html` | Always `today` |
| Navigation model | Separate pages linked from each page's menu | Tabs: Today, Reports, Inventory, Production, Store, Account (each shown only when allowed); feature stacks open from tiles |
| Public pages | `/about.html` product page | None |

### Mobile tab visibility

Feature Back controls return to the immediate page that opened them. This includes
cross-section links such as Owner tools → Team or Time Tracking and Incoming →
Invoices. Direct links use a feature's canonical parent; Production Review returns
to the production run. Completed production opens its log with Production History
as the return destination. At a top-level tab, native Back returns to Today.

Android system Back and iOS stack Back use the same page action, including local
scanner steps, report details, settings panels, and pending-action guards. Modal
close handlers retain their existing unsaved-change checks. Return context is
bounded device UI state, revalidated during restoration, and grants no access.

| Tab | Shown to |
| --- | --- |
| Today | Everyone |
| Reports | `reports.submit` or `reports.view` (not Production role) |
| Inventory | `inventory.view` |
| Production | Production role only; other roles with `production.view` open it from a Today tile |
| Store | Managers and owners |
| Account | Everyone |

## Workflow matrix

Status: **Both** = available on both clients; **Mobile only** / **Browser only**;
**Partial** = both clients have the workflow, but one exposes less.

| Workflow | Browser | Mobile | Who (server-enforced) | Status |
| --- | --- | --- | --- | --- |
| Submit a shift report | `crew.html` | Reports → Write a report | `reports.submit` | Both |
| Shift report inbox with AI briefing | `manager.html` Inbox + Briefing | Reports → Shift reports | `reports.view` | Both |
| Weekly Overview | `manager.html` | — | `reports.view` | Browser only |
| Manager roster with last sign-in | `manager.html` Management panel | Last sign-in on each member's detail screen | `reports.view` (browser); `memberships.manage` (mobile) | Partial |
| Read Heads Up | `crew.html`, `manager.html` | Today card, `heads-up` | Manager, crew, production roles | Both |
| Edit Heads Up | `manager.html` dialog | Store → Heads Up | Manager role only | Both |
| Account profile, password, sign out everywhere | `accounts.html` | Account | Any signed-in account | Both |
| Switch store | `accounts.html` | Account → Switch store; Today → Change store | Owner/admin with more than one authorized store | Both |
| Team list, edit role/permissions, remove access | `accounts.html` People & permissions | Store → Team members → member | `memberships.manage`; role limits in [SECURITY.md](SECURITY.md#roles-and-capabilities) | Both |
| Invite a new person / reissue code | `accounts.html` | Store → Build team → Invite; member → Reissue | `memberships.manage` | Both |
| Add an existing account to a store | `accounts.html` | Store → Build team → Add an existing account | Owner/admin with `memberships.manage` | Both |
| Business delegation, ownership transfer, suspend/restore | `accounts.html` Business access | Store/Today → Owner tools → member | Owner | Both |
| Store sign-in cutover review | — | Owner tools → Review store sign-in | Owner | Mobile only |
| Store hub and access summary | — | Store; Store → Store access | Managers and owners | Mobile only |
| Record production: choose batches → review → confirm | `production.html` Today + Review | Production → Record today's production → Review | `production.submit` | Both |
| Recipe book | `production.html` Recipes (read-only list) | Recipe list and detail | `production.view` | Partial |
| Create or edit a recipe | — (API supports it; page does not) | Production → New recipe; recipe → Edit recipe | `recipes.manage` | Mobile only |
| Production history | `production.html` History (list) | History list and log detail | `production.view` | Partial |
| Reverse a production log | — (API supports it; page does not) | Log detail → Reverse | `production.manage` | Mobile only |
| Production reports and advisory forecast | — | Reports → Production reports | `forecasts.view` + `reports.view` + `production.view` + `inventory.view` | Mobile only |
| Inventory hub | `inventory.html` "coming soon" placeholder | Inventory | `inventory.view` | Mobile only |
| Company catalog: list, detail, add/edit, archive/restore | — | Inventory → Catalog | View: `inventory.view`; change: `catalog.manage` | Mobile only |
| Barcode lookup and scan-to-catalog | — | Catalog → Scan product | Lookup: `inventory.view`; create: `catalog.manage` | Mobile only |
| Packages & barcodes; correct a product's counting unit | — | Product → Packages & barcodes / Change | `catalog.manage` | Mobile only |
| Combine a duplicate catalog item | — | Packages & barcodes → Combine items | Owner | Mobile only |
| Shelves: create, rename, assign products | — | Inventory → Open Shelves | View: `inventory.view`; change: `configuration.manage` | Mobile only |
| Count inventory: start, enter, review | — | Inventory → Begin Count | `counts.submit` | Mobile only |
| Post, reopen or cancel a count | — | Count → review | `counts.approve` | Mobile only |
| Current stock and product stock detail; count history | — | Inventory → Current Inventory | `inventory.view` | Mobile only |

Heads Up is store staff communication. Owners and administrators can neither read
nor edit it on either client (`backend/shiftly/stores/repository.py`).

## Time Tracking device demo

Owners open Today → Owner tools → Time Tracking in the native app. Names need no
accounts; the roster, shift history and timer timestamps stay in the existing
account/store-scoped device checkpoint. This is a local demo, with no browser
compatibility-page equivalent, account-linked delivery or push notifications.

Tap a member name to open details. The modal has the original independent 3:30
and 5:30 timers plus a separate **Breaks** section with **10 min** and **30 min**
controls. Each break has its own countdown and reset confirmation. Breaks require
clock-in, continue while the modal is closed or the app is backgrounded, and stop
at clock-out. A new shift starts with fresh timers. Starting or resetting a break
does not pause other timers or deduct time from shift totals. Existing saved
rosters remain valid; the optional break state is added only when used.

Above three members the roster uses compact rows; up to three it shows expanded
timer cards. Break controls stay inside the member modal in both layouts. Names,
shift history and confirmed removal are managed through the same modal.

## Partial implementations

- **Browser inventory:** `inventory.html` is reachable with `inventory.view` but
  shows only a placeholder. No browser inventory workflow exists.
- **Browser production:** the page records production and lists recipes and
  history. The browser `/api/production` routes also accept recipe creation/edits
  and reversal, but no browser screen exposes them.
- **Manager roster:** the browser panel lists managers by last sign-in. Mobile
  shows a selected member's last sign-in inside team administration and orders the
  team list by recent sign-in.
- **Weekly Overview:** browser only. Adding it to the native Reports area is an
  approved parity item (see the [roadmap](IMPLEMENTATION_PLAN.md#roadmap)).
- **Camera:** native barcode scanning only. The browser-rendered test harness uses
  manual code entry; there is no browser camera workflow.

## Intentional platform differences

- **Inventory and recipe authoring are native-first.** Accepted direction: build
  inventory screens natively; do not redirect them to the browser or start a
  separate React web rewrite. Whether the browser placeholder should gain
  workflows or be removed is an [open decision](IMPLEMENTATION_PLAN.md#open-owner-decisions).
- **Production staff** get a dedicated Production tab on mobile and land on
  `production.html` in the browser. They have no Reports, Store or Heads Up editing
  on either client.
- **Admins** have no Store tab; they reach team administration from Account →
  Team administration.
- **Device features:** native-only SecureStore sessions, workspace restoration and
  the barcode camera. Browser sessions are HttpOnly cookies.
- **Workspace restoration** (mobile) keeps the last screen and unsaved input on the
  device for up to seven days. It is not offline submission; Save, Submit and
  Confirm still require the server. Browser production keeps only its current
  draft in `sessionStorage`.
- **Runtime:** browser pages also run on the legacy `server.py`; the native app
  requires the FastAPI runtime. Hosted availability is tracked in
  [DEPLOYMENT.md](DEPLOYMENT.md#hosted-environment-observations).
