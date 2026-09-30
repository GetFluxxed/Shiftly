# Shiftly native application roadmap

Updated: 2026-09-22. The user selected **a phone and tablet app with React Native**.
This supersedes the earlier mobile-web-first decision. React Native with Expo and
TypeScript is the primary new client in `apps/mobile`; the existing browser app
remains available during migration. A separate React browser rewrite is not part
of this phase.

The starting point is Accounts & Access integration `7ecb61d`, published in
[PR #10](https://github.com/GetFluxxed/Shiftly/pull/10), which builds on account
services [PR #9](https://github.com/GetFluxxed/Shiftly/pull/9). That integration's
588 passing tests and recovery rehearsals describe the starting backend/browser
baseline. They do not establish native device readiness.

**Inventory update — 2026-09-25:** The next approved native slice adds current
inventory, server-saved whole-store counts, review/finalization and history.
See [the inventory count contract](workstreams/inventory-counts.md). This includes
migration 017 and reuses existing count-entry and count-approval permissions.
Camera/scale automation, fully offline counting and forecasts remain later phases.

## Adopted architecture

| Layer | Responsibility |
| --- | --- |
| React Native + Expo + TypeScript | Native phone/tablet screens, navigation, accessible controls, device lifecycle and later camera/barcode integrations |
| FastAPI `/api/mobile` adapter | Explicit native request/response contract and opaque bearer authentication, delegated to shared services |
| Existing Python services | Accounts, store selection, roles/capabilities, reports, durable jobs and business rules |
| Existing PostgreSQL | Identities, memberships, sessions, reports, shared company catalog and store shelves; additive migration history through 015 |
| Existing browser client | Available reporting and full account administration while native workflows reach parity |
| Future private object storage | Authorized image evidence with store scope, retention and reviewed analysis; image bytes do not belong in account/session storage |

The frontend move does not require rewriting the backend, replacing PostgreSQL,
introducing an ORM, or duplicating permissions in TypeScript. React Native renders
native interfaces. Shared screen components and TypeScript contracts can support
future clients without committing to another browser rebuild now.

The native API returns the existing opaque database-backed account session token
to the app. The app sends it as `Authorization: Bearer <token>`; it is not a JWT
and introduces no new session database or migration. Browser cookie contracts
remain intact. Native requests must reject conflicting credentials instead of
choosing a more powerful identity.

Use Expo SecureStore for the token (iOS Keychain and Android protected storage),
with fetched account/report data in memory. The approved workspace restoration
contract below also permits encrypted local input drafts, separately from server
records. Passwords and invitation/recovery
codes must not enter URLs, logs, analytics, or ordinary persistent app storage.
Public Expo configuration may contain an API origin, never backend/database/AI
secrets. Release traffic requires HTTPS.

Every protected API request revalidates the server session and effective
permissions. Mutations retain transaction-level actor, membership and selected
store checks. Hiding a button is a usability feature, not authorization. On
session rejection, store changes or access changes, clear private screens and
drafts; on foregrounding, refresh the server context before enabling actions.
While active, recheck access every 60 seconds. An unchanged response preserves the
current screen and draft; changed actor, permissions or authorized stores invalidate
private pending responses and replace the workspace. SecureStore persistence does
not mean an account is still authorized. If device credential deletion fails, keep
the workspace locked and offer sign-out retry; never restore a discarded token.

## Delivery phases and acceptance

### 1. Native foundation and existing daily work — underway

Deliver the app shell and authenticated native API alongside the existing client:

- Individual username sign-in with an explicit store; invitation activation and
  independently issued account recovery codes.
- Current account, permissions and selected store; store switching, password
  changes, sign-out and sign-out across devices.
- A crew Today screen with Head's Up and shift report submission, attributed to
  the verified named actor.
- A manager report inbox with original notes, briefing status and available
  briefings, restricted to authorized stores and labeled with each report's store.
- Initial read-only team view for authorized accounts, expanded with native
  administration in phase 2. The browser Accounts & Access screen remains available.
- Inventory visible only with `inventory.view`; phase 3 now provides the first
  catalog/shelf slice. Quantities and camera results remain future work.

**Acceptance:** TypeScript and JavaScript bundle checks pass; API tests exercise
successful workflows plus absent/expired/revoked tokens, store boundaries,
permission denial and mixed credentials. Existing browser contracts continue to
pass. Device validation must separately demonstrate launch, sign-in, report
submission, keyboard behavior, store changes and session invalidation on the
agreed iPhone/Android phone and tablet matrix.

The local environment can run API tests, TypeScript checks and Expo bundling. It
does not currently have Xcode or the Android SDK. A successful bundle is not a
simulator, physical-device, signed-build or app-store release result. Record the
checks actually run in the delivery handoff.

### 2. Complete account and operations parity

Implemented native Team and Owner screens for invitations/reissue, existing-user
membership assignment, scoped role/capability editing and revocation/restoration,
business delegation, authorized suspension/restore, ownership transfer and
shared-login cutover. Native form choices come from the existing Python account
policy; mutations continue through the shared lifecycle services. Ownership
transfer clears the native credential, and sensitive codes leave memory when the
screen loses focus or the app backgrounds.

Manager Head's Up editing and Weekly Overview remain to be implemented where
absent from phase 1. Native device acceptance below remains a release requirement.

Local managers must never inherit business-owner authority or global recovery
powers through the client. Destructive access changes need clear effects and
confirmation. Recovery remains a separately issued operator workflow.

**Acceptance:** Reuse the account lifecycle/service checks and add native screen
flows for each authorized role and denial path. Verify background/foreground,
device restart, logout on another device, selected-store changes, form validation,
screen-reader labels, text scaling, keyboard navigation and accessible touch
targets. Test tablet portrait/landscape layouts without stretched phone forms.

### 3. Catalog, SKUs and trusted manual inventory

**First slice implemented, 2026-09-23:** see the [shared company catalog](workstreams/inventory-foundation-and-shared-catalog.md).
One editable company catalog, store listings and named shelves with product
assignments are available. Add/edit/archive/restore products centrally; shelf
removal is local. Rendered phone/tablet journeys and native bundles are verified;
physical-device acceptance remains a separate gate. The broader quantity and
conversion workflow below remains planned.

Build catalog items, SKU/barcode mappings, pack/base units, weight/tare profiles,
locations and pars first. Then add movement history, balances, receipts, counts,
approval and corrections using the rules in [INVENTORY.md](INVENTORY.md).
Prioritize native count entry and manager review screens around real pilot items.

Add migrations after the existing 001–015 history; rehearse fresh databases,
upgrades and restoration. Never alter already released migration history to
accommodate a frontend change. Catalog, counts and stock commands must retain
store scope, named actors and server-authorized capabilities.

**Acceptance:** Units and conversions are unambiguous; duplicate commands cannot
post stock twice; counts reconcile instead of adding the whole quantity; concurrent
updates surface conflicts; history survives corrections and configuration edits.
The manual workflow works when AI and camera capture are unavailable.

### 4. Barcode capture, private photos and reviewed assistance

Add native camera/barcode capture and manual fallback after the relevant catalog
or count service is ready. A barcode maps to a known item and unit; scanning alone
does not approve a receipt. Validate uploaded media and attach it to the verified
store, location, actor and count session. Add private storage, access checks,
retention/deletion, interrupted-upload recovery and durable analysis jobs.

Photo analysis produces proposed item matches and quantities with uncertainty;
people review and approve them through inventory services. Images do not prove
hidden quantities or remaining weights in open containers. Build an approved,
representative evaluation set before selecting an AI provider or a training
approach. Dataset creation, inference, evaluation and model training are separate
work packages. No model or fine-tuning availability is assumed by this roadmap.

**Acceptance:** Real devices handle permission denial, retakes, poor connectivity,
overlapping images and unknown barcodes. Store isolation applies to image URLs
and jobs. Measured accuracy, correction effort, latency and cost meet agreed pilot
thresholds before assistance is enabled beyond the pilot.

### 5. Offline resilience and release readiness

Local UI/draft restoration is now implemented under the contract below. Introduce
an offline outbox only after server idempotency and conflict/version checks exist
for the affected commands. Recheck
identity, selected store and permissions on reconnect before replaying. Keep
pending work clearly distinct from accepted server records; clear or isolate
private drafts after account changes. Do not silently resubmit an ambiguous report
or stock change after a timeout.

Prepare signed development/release builds, separate staging configuration,
distribution accounts, privacy declarations, crash diagnostics without private
content, upgrade compatibility and rollback procedures. Finish tablet layouts,
accessibility and real-device performance work before claiming native release
readiness. Existing hosted runtime, backup and production cutover requirements
remain applicable.

**Acceptance:** Device evidence covers interrupted writes, process termination,
expired and remotely revoked sessions, upgrades, restore/reinstall behavior,
camera permissions and constrained connectivity. Review and distribution are
separate from committing the native foundation; no production backend cutover or
store publication is implied by this phase's code changes.

## Heads Up store announcements — 2026-09-29

The manager Store hub replaces Store Access with Heads Up. Managers can create
or edit the store's current announcement in a native screen and return directly
to Store. Crew and managers see the read-only announcement above Your Workspace on
Today, with an accessible refresh icon in its top-right corner. Editing is
available from Store. Today shortcuts use the same two-column action tiles as
Inventory and Store: reports, inventory, team management and account, subject
to existing access. Crew can also open the read-only announcement route. Owners
and administrators do not see or fetch Heads Up,
including when opening its native route directly. Owners retain Store Access.

This is the same single, store-scoped message used by the browser. Native
`GET /api/mobile/heads-up` and `POST /api/mobile/heads-up` reuse the store service
and existing table. The shared service enforces manager/crew reads and
manager-only writes for individual accounts through both browser transports and
native bearer sessions. Report permissions alone cannot give owners or
administrators access. No schema migration or new account capability is needed.
This is an in-app announcement, not an operating-system push notification.

Native writes require the current `expectedStoreId`; the transaction rechecks
the session, selected store and manager role, then saves the message and account
audit together. Messages accept at most 1,000 characters and use the existing
whitespace normalization. A store still has one current message; this release
does not add an announcement feed, history, scheduling or concurrent-edit
versioning. Browser and native changes become visible on refresh or re-entry.

The editor exposes loading, empty, error, saving and unsaved-change states.
Cancelled drafts are discarded. The subsequent workspace restoration revision
retains unfinished edits across navigation/backgrounding against the latest
message baseline. Failed saves preserve the current form; an uncertain save asks the manager to refresh before retrying and is never
automatically replayed. Existing session invalidation hides private content after
an account, role or store change.

Locally verified: native TypeScript checking and 79 unit checks; iOS and Android
exports; seven focused API/policy cases (including both browser transports),
nine existing announcement/report regressions, six rendered Heads Up journeys
and thirteen existing rendered account journeys. Rendered review covered a
390-pixel phone and 1024-pixel tablet, manager create/edit/cancel and return to
Store, read-only crew Today, owner/admin direct-route denial with no announcement
request, and failed-save draft preservation/cleanup. Three initial rendered
failures were outdated test selectors; the corrected journeys passed without
application changes. Tests used isolated schemas in a disposable database.

The subsequent Today layout revision passed native type checking, the 79 native
unit checks, and all six rendered Heads Up journeys. Phone/tablet review confirmed
the read-only notice, icon refresh, workspace order and matching shortcut grid.

The existing local demo API was restarted without seeding or migrating its data;
Expo serves the updated iPhone bundle. Physical-device acceptance, CI verification,
commit/push and deployment have not been performed for this change.

## Main constraints

- Native delivery changes the first client priority, not the dependency order of
  inventory, media and stock approval services.
- The native adapter requires the FastAPI runtime; the existing production
  startup still uses the legacy server until a separately verified cutover.
- Roles returned by the API describe current access; the server remains the
  authority after backgrounding, revocation, recovery and store changes.
- Scope the first release around daily crew/manager work. Full owner workflows,
  offline posting and AI inventory assistance have their own acceptance gates.
- Expo bundling and browser viewport tests cannot substitute for native-device
  verification or a signed release.

Run instructions are in [apps/mobile/README.md](../apps/mobile/README.md). Framework
references: [React application guidance](https://react.dev/learn/creating-a-react-app),
[Expo project setup](https://docs.expo.dev/get-started/create-a-project/) and
[Expo SecureStore](https://docs.expo.dev/versions/latest/sdk/securestore/).

## Workspace restoration — 2026-09-29

The app now checkpoints approved navigation, display preferences and input drafts
locally. Minimizing still locks private screens and invalidates pending responses;
foregrounding revalidates the server account before loading the last screen and
its input state. A process restart follows the same gate. Explicit launch links
keep their own destination and access-denied/activation behavior.

| Area | Restored | Deliberately transient |
| --- | --- | --- |
| All signed-in screens | Last allowed route, safe record IDs, contextual return destination, scroll offset | API responses, request tasks, server errors, confirmation dialogs |
| Catalog and shelves | Searches, filters, page cursor, product/new-shelf/shelf-name drafts, assignment picker | Automatic create, assign, remove or archive actions |
| Current inventory and counts | Searches, shelf selection, count date, unsaved full/partial measurements and units | Stock changes and count submission/finalization |
| Reports | Inbox/composer choice, selected report ID, list length, shift and unsent notes | Fetched report bodies and briefings |
| Heads Up | Unfinished manager message against the last fetched message baseline | Automatic publication |
| Team, Owner and Account | Team selector/search, owner search, permissions/store panel | Passwords, invitation/recovery codes, role/grant/reason edits, ownership transfer and sign-out confirmations |

Product and shelf edit drafts match the latest server version. Count-entry drafts
match the saved line version, count state and captured measurement configuration;
another line's edit does not discard them. A changed baseline uses current server
values. Save/Submit is still explicit; Cancel/Discard removes the local draft.
Report sends checkpoint an unconfirmed marker before the request. A lost response
or interrupted send remains blocked from resubmission until the person checks
the inbox/manager and explicitly acknowledges it. No request is replayed.

Checkpoint storage uses the existing Expo SecureStore, scoped to API origin and
verified user/business/store/role/capabilities/authorized stores. Sign-out and
changed account/store/access clear the workspace. No read is exposed while locked.
Storage has a schema version, a seven-day expiry and bounded size/entry count.
Small Unicode-safe chunks and a commit-last manifest prevent incomplete writes
from replacing a usable checkpoint; an error is visible in the app. Local storage
is a recovery convenience, not the authoritative inventory or report database.

The checkpoint is updated shortly after input and flushed on backgrounding; an OS
termination can interrupt the last in-flight write. Restoring uses the last complete
checkpoint and still requires valid sign-in and a connection to verify access.
This implements screen/draft continuity, not offline access, an offline outbox,
server autosave, background processing or cross-device draft synchronization.

Local verification passed: TypeScript checking, 97 native unit tests, and 36
rendered inventory/account/report/Heads Up journeys against disposable PostgreSQL.
The rendered checks include warm/cold recovery, scroll after content reload, stale
record drafts, exact partial units, scope changes, secret exclusion, lost report
responses and a store change while checkpointing. iOS and Android exports passed;
the local Expo bundle was checked for restoration code. No schema or backend
change was needed. Physical-device app-switcher, force-close, keyboard and scroll
acceptance remains separate; no hosted deployment is claimed.


## Production workspace — 2026-09-29

The native recipe/production slice is implemented and locally verified. Managers
and owners open Production from Today; staff assigned the separate Production
role receive its own bottom tab, with no Reports or Store access. Recipe setup
uses the shelf-style compact ingredient cards and add/remove controls. Daily
flavors support repeated batches, a stock-use review and explicit confirmation.
Each ingredient deduction is the recipe amount × batches × 1.01.

Restoration now also includes recipe drafts, daily flavor/batch selections,
production list searches/cursors and safe recipe/log destinations. Pending recipe
and production writes retain their original request identity; uncertain results
freeze the payload until recovery or exact retry. Account/store/access changes
clear private state. Production history remains server-authoritative.

Type checking, 103 native tests, four rendered production journeys and iOS/Android
exports passed. The database-backed service, account and browser checks and backup
recovery are recorded in the [production contract](workstreams/production-and-assisted-inventory.md).
The local demo schema and API were refreshed after a verified backup without
changing existing data. Physical-device acceptance and CI remain separate.
Camera suggestions, hardware scale capture and Forecast are planned next slices;
this milestone does not enable them.
