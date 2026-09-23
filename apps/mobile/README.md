# Shiftly mobile

Native phone and tablet client built with React Native, Expo and TypeScript.
It uses the existing Python/FastAPI services and PostgreSQL account system. The
existing browser application remains available while native workflows expand.
See the [native roadmap](../../docs/NATIVE_APP_ROADMAP.md) for phase boundaries and
release acceptance.

## Current slice

Individual sign-in, activation/recovery, store selection, account/password and
sign-out controls, crew report entry and Head's Up, manager report reading,
native Team screens for invitations/reissue, existing-account assignment and
store permissions/removal/restoration, plus an Owner workspace for business
delegation, suspension/restoration, ownership transfer and shared-crew cutover.
Inventory now includes a shared company product/SKU catalog with add, edit,
archive and restore, plus named store shelves and assignment/removal of existing
products. Owners or delegated catalog administrators manage shared products;
store configuration permission controls shelf changes. Catalog products now
include an editable full-container amount, exact gram/kilogram equivalents and
A–Z catalog ordering. New unit choices are each, grams and kilograms. Quantities, camera capture
and offline posting remain later phases. This is a development foundation; bundling is not a
claim of physical-device or store-release verification.

The [inventory foundation and shared catalog](../../docs/workstreams/inventory-foundation-and-shared-catalog.md)
documents this implemented slice and its verification. API paths stay under `/api/mobile`; feature code supplies
uncertain-write guidance. Machine-readable errors distinguish form conflicts from
session/store invalidation, with conservative fallback for older responses.

## Requirements

- Node.js 22.13+ (22.x) or 24.3+ (24.x), matching the selected React Native
  dependency requirements, and the pinned `pnpm@11.19.0` package manager.
- Expo Go on a compatible phone/tablet for initial development, or separately
  installed iOS/Android simulator tooling.
- The Shiftly **FastAPI** server reachable from the device, a migrated development
  PostgreSQL database and a named account with a store membership. Shared crew
  passwords are browser enrollment compatibility, not native account credentials.

Dependencies are pinned in `package.json` and `pnpm-lock.yaml`. Use the committed
lockfile; do not independently upgrade React or React Native outside the selected
Expo SDK's supported dependency set.

## Run the API

From the repository root, install the Python dependencies and configure a private
`.env` with your development database as described in the root README. Apply
migrations before starting the API and worker:

```sh
python -m backend.shiftly.runtime.migrate
SHIFTLY_WORKER_MODE=external python -m uvicorn backend.shiftly.app:create_app \
  --factory --host 0.0.0.0 --port 4174 --workers 1
```

In a separate terminal with the same backend environment:

```sh
SHIFTLY_WORKER_MODE=external python -m backend.shiftly.jobs.worker
```

The mobile routes are available only through FastAPI. `python server.py` retains
the browser/legacy runtime and does not serve `/api/mobile`. Report quality checks
and briefing generation use the configured backend AI provider; automated API
tests mock it. Do not put AI keys or database credentials in the Expo environment.

Use the existing account enrollment/operator process for a development named
account. A fresh database does not imply an owner, and the mobile app does not
create businesses or grant itself ownership.

## Run the app

From this directory:

```sh
pnpm install --frozen-lockfile
cp .env.example .env.local
```

Set `EXPO_PUBLIC_API_URL` in `.env.local` to the API **origin**, without `/api/mobile`:

```dotenv
EXPO_PUBLIC_API_URL=http://127.0.0.1:4174
```

Then start Expo:

```sh
pnpm start
```

Use the development computer's private LAN address for a physical phone/tablet;
`127.0.0.1` on the phone refers to the phone itself. Both devices must have network
access to the API. An Android emulator commonly reaches its host through
`http://10.0.2.2:4174`; choose the address appropriate to your emulator/network.
Restart Expo after changing configuration. A Metro/Expo tunnel exposes the
JavaScript development server, not automatically your Python API.

Development configuration permits loopback/private-LAN HTTP. Platform cleartext
network policies can still block it; use a reachable HTTPS development endpoint
or an explicitly configured development build. Release configuration requires
HTTPS. `EXPO_PUBLIC_*` values are embedded in the client and are public, so only
place the non-secret API origin here.

With simulator tools installed, `pnpm ios` or `pnpm android` starts Expo for that
platform. These scripts do not create a signed distribution build. The current
local environment has no Xcode/Android SDK, so native simulator/device validation
must be recorded separately on a suitable host.

## Checks

```sh
pnpm typecheck
pnpm test
pnpm export:native
```

The export command generates the iOS and Android JavaScript/assets bundle. It does
not compile or sign a native binary. TypeScript and unit/API checks do not replace
real-device tests of keyboard, safe areas, accessibility, tablet layout, lifecycle,
secure storage, network interruptions or remotely revoked access.

The backend test suite continues to require an explicitly disposable
`TEST_DATABASE_URL`; see [TESTING.md](../../docs/TESTING.md). Keep the existing
browser/transport suite alongside native adapter checks.

## Session and data behavior

The app authenticates through `/api/mobile/accounts/*`. Login, activation and
store switching return an opaque `sessionToken` plus `expiresIn` (seconds). The
current session lifetime is eight hours; this foundation has no refresh token,
so expiry requires sign-in again. Store only the
session token in Expo SecureStore and send it as a bearer token. No JWT, browser
cookie sharing or second identity store is introduced. The server rejects mixed
browser/native credentials and validates the session and current permissions on
protected requests.

Protected writes carry the rendered `expectedStoreId`; store switching rotates
the token. After a rejected session or changed account/store context, private
content and drafts must be cleared. Foreground refresh rechecks access before
enabling actions. While the app remains active, access is checked every 60 seconds;
unchanged access preserves the screen/draft, while changed permissions or authorized
stores replace the workspace and invalidate older responses. A network failure
during that check pauses private access until the server can verify it again.
The manager inbox can include multiple authorized stores and
must label each report's store; a selected store is not a grant of access to every
report. Failed or uncertain writes must not be silently queued/replayed: offline
outbox support requires future server idempotency and conflict handling.

Invitation/recovery codes are entered explicitly. Do not persist them, passwords,
report bodies or account rosters in ordinary device storage, links or diagnostics.
SecureStore is local credential protection; expiry, suspension and revocation are
enforced by the backend. If sign-out cannot delete the saved device credential,
the app stays locked and retries cleanup rather than reopening that session.
A failed cleanup must be completed before treating the device as signed out; the
message directs the user to reconnect and retry before closing the app.

## Native account administration

Open **Account → Manage team** to invite someone, add an existing account by their
Account ID (visible on their own Account screen), or change a store membership.
Owners can also choose existing people from their business when adding store
access. Invited people activate their own account and choose their own password.
Activation codes appear only on the issuing screen, expire after 24 hours, and
are discarded on navigation/backgrounding; they are never put in routes or storage.
Reissuing invalidates the earlier code. Editing a pending membership invalidates
its invitation, so reissue after saving if that membership remains active.

Open **Today → Owner workspace** or **Account → Owner workspace** for business
roles, account suspension/restoration, ownership transfer, and store sign-in
cutover. Administrator permissions require matching store grants and active
business delegation. An ownership transfer ends the current owner's business
sessions and clears the native credential. Global suspension is offered only
when the owner has authority across the target's complete account history.

`GET /api/mobile/accounts/management` returns selected-store members, form choices
derived from Python policy, and eligible row actions. Only owners receive the
business directory and owner controls. These choices are presentation hints:
every write still uses the existing service's transaction-level authorization.
The original browser/native roster response remains unchanged. No migration or
second permission model was added.

Account changes require explicit confirmation showing scope and effects. Unknown
network outcomes are never replayed automatically: refresh the team or sign in
again before retrying, and reissue an activation code if its delivery was lost.

Before a release, exercise the actual iPhone/Android screens for keyboard and
text scaling, back navigation, backgrounding while an invitation code is visible,
manager denial, store switches during edits, and transfer/sign-out cleanup.
Bundle and automated service checks do not replace those device checks.

## Visual theme

The native client uses a cocoa, cream and rose theme inspired by
[baciodilatte.us](https://baciodilatte.us/): cocoa `#6B4124`, rose `#F08183`,
cream `#FBF6EE`, and pale blush selections. Shared tokens live in
`src/ui/theme.ts`; use semantic colors for all new screens. Error and success
messages keep separate colors and icons. The checked normal-text/background
pairs exceed 4.5:1 contrast, including secondary text on the cream surfaces.

Newsreader headings and Work Sans body/controls are bundled from the pinned
open-source Expo Google Fonts packages; loading works in Expo Go. The shared
`Typography` component selects actual bundled weights and uses native fallbacks
while fonts load or if loading fails. Fonts are not fetched from a third-party
font service while the app runs. Layout review used the real screen components
in a temporary browser renderer at 390-pixel phone and 1024-pixel tablet widths;
this is not a substitute for final native device accessibility/keyboard checks.
