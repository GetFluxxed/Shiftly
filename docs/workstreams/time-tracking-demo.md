# Time Tracking — local demo and account-linked delivery

## Objective and scope

Add **Time Tracking** directly beneath **Owner tools** on Today and inside the
owner workspace. The current deliverable is an owner-operated demo using the
shared React Native screen on phones, tablets, and the browser renderer. Crew
names require no accounts. The confirmed presets are **3 hours 30 minutes** and
**5 hours 30 minutes**, independent for each clocked-in member.

Use the existing cocoa/cream/rose theme and inventory-style name-entry modal.
Keep one Add member action, one clock action per person, and two timer controls.
Renaming, recent shift history, and confirmed removal belong in the member modal.

## Implemented behavior and boundaries

- An empty roster accepts up to 20 named demo members. Normalized duplicate names
  and empty names are rejected. Removing a member requires a named confirmation
  and warns when an active shift will be discarded.
- Clock in starts one shift; clock out saves its end time and stops both timers.
  A member retains the most recent 10 shifts. Times use local device timestamps;
  elapsed time and countdowns are calculated from those timestamps, including
  after backgrounding or reopening. This is not a payroll time authority.
- Timer activation requires an active shift. Tapping an active/completed timer
  opens a reset dialog; repeated activation does not silently restart it.
  Completion is visible in the app. No system notification is sent.
- Demo state uses the existing private workspace checkpoint, scoped to the
  current account/business/store/access context. It clears on sign-out or a
  changed scope and expires after seven days without an update. It is not server
  data, shared across devices, or an account roster. Native persistence uses the
  existing SecureStore adapter; the browser test adapter uses browser storage.
- The bounded demo model has a strict restore validator and a 40,000-character
  entry limit. Only its checkpoint key gets the needed nested-data depth. The
  existing 60,000-character whole-workspace limit and failure notice still apply.
  The display tick does not write checkpoints; mutations flush them explicitly.
- Owner visibility and route guards use the current session. No backend routes,
  permissions, database migrations, or notification dependencies are introduced.

## Account-linked physical app follow-up

The demo must remain labeled until these capabilities ship. Named demo records
must never automatically become authoritative attendance or account identities.

1. Link crew through existing account/store memberships and server capability
   policy. Owners select eligible accounts; a crew member can view only their
   own timers unless granted management authority. Scope checks run inside every
   protected write, and inactive memberships cannot receive timers.
2. Store shifts and timer assignments in PostgreSQL with server UTC timestamps,
   one open shift per account/store, idempotent commands, concurrency controls,
   and auditable corrections. Preserve original events and distinguish manager
   assignments from crew acknowledgments. The existing demo model is not this
   service contract or a replacement for it.
3. Add explicit device notification consent and authenticated push-token
   registration. Associate each device with its account, support revocation and
   token rotation, and avoid private information in notification payloads.
4. Schedule delivery in a durable server job when an owner assigns/changes a
   timer. Cancel obsolete jobs on reset/clock-out and deduplicate deliveries.
   Timers remain accurate in-app if permission is denied or delivery fails;
   device OS policies cannot guarantee push timing.
5. Verify two physical devices/accounts, locked/background delivery, token
   rotation, denied permission, reconnect, clock-out cancellation, sign-out,
   store/membership changes, and server authorization boundaries before claiming
   full app/push functionality. Signing, credentials, and deployment are separate.

## Acceptance and verification

Required: front-page placement, owner-only navigation, modal add/rename/remove,
independent presets, clock-in/out history, refresh restoration, elapsed time
across background time, visible completion, validation feedback within dialogs,
storage failures without duplicate mutations, and phone/tablet layouts.

Run `pnpm --dir apps/mobile check`, native exports, and the focused rendered
journeys in `tests/time_tracking/`. Native bundle exports and browser rendering
are local evidence; they do not establish physical-device or deployed readiness.

Local verification on 2026-10-29 passed TypeScript checking, all 217 mobile unit
tests, six new Chromium time-tracking journeys and four existing Expo navigation
journeys, and final iOS/Android bundle exports. Visual review covered 390-pixel
phone and 1024-pixel tablet layouts; the feature preview also loaded actual bundled
fonts and icons. An independent code review found no actionable demo-scope defects.
These checks used the existing pinned dependencies and direct compiler/test/Expo
commands because the local package-manager wrapper rejected a shared dependency
symlink; no packages or lockfiles were changed. No physical-device run, account
delivery, push delivery, CI run, merge, or deployment was performed for this change.

## Expo Go test delivery — 2026-10-29

After the owner requested mobile testing in the existing Expo Go app, feature
commit `9dcc381` was fast-forwarded into the clean checkout already serving Metro.
The existing Expo Go SDK 58 server on port 8081 now serves the updated app. The
existing LAN mobile API on port 4175 and the app's public API origin were retained;
no backend restart, migration, account change, or storage namespace change was
needed. Verification fetched the current iOS development bundle over the LAN and
confirmed Time Tracking, both timer durations, its persistence key, and the existing
API origin. The mobile account-status endpoint returned HTTP 200 over the LAN.

Open the existing Shiftly project in Expo Go and reload, or scan the current Expo
LAN URL from the development machine on the same Wi-Fi. The Mac and both local
services must remain running. This is local Expo Go delivery, not a Render
deployment, EAS release, or signed build. The feature commit has not been pushed;
physical-phone acceptance and remote CI remain unverified.
