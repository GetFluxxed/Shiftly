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
with transient account/report data in memory. Passwords and invitation/recovery
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

Introduce explicit saved drafts and an offline outbox only after server
idempotency and conflict/version checks exist for the affected commands. Recheck
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
