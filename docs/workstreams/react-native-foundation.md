# React Native foundation handoff

Date: 2026-09-22. Branch: `codex/react-native-foundation`.

Worktree: `/Users/getfluxxed/projects/Shiftly-codex-react-native`.

The user chose a phone and tablet app as the first client priority. This starts
that migration on the completed Accounts & Access integration, commit
`7ecb61d5b39cf9c9a72e3248cb30f6d004830bad` from draft PR #10. The earlier Accounts,
Copilot UI and reports worktrees are preserved. This foundation is local
development work; it does not merge the previous PRs or change production.

## Delivered

`apps/mobile` contains a React Native, Expo Router and TypeScript application,
with a committed pnpm lockfile and Expo-compatible dependency versions. The
native bundle targets iOS and Android. React Native Web is a development-only
renderer for visual inspection, not a new production browser client.

The UI provides individual sign-in, activation and recovery redemption, Today,
crew report submission, a manager inbox with store labels and report details,
account/profile access, store switching, password change, local/global sign-out,
and an authorized read-only team roster. Inventory is an honest permission-gated
empty state. Phone navigation and report details adapt to tablet sidebar and
column layouts. Buttons, safe areas, keyboard-aware forms and text scaling are
part of the foundation, with device validation still required.

FastAPI adds `/api/mobile/accounts/*`, `/api/mobile/reports`, and read-only
`/api/mobile/heads-up`. The adapter uses the existing account/report services,
database and opaque hashed sessions. Native sign-in returns a token to the
device's secure storage; browser endpoints retain HttpOnly cookies. Duplicate,
malformed or mixed browser/native credentials fail closed. Native protected
writes require a matching `expectedStoreId`, and the service rechecks authority
inside the write transaction. Native reports include authorized store IDs/names;
existing web report payloads remain unchanged. Named compatibility accounts with
`businessId: null` retain their permitted reporting access.

Tokens stay outside React state and are scoped to the configured API origin.
The client omits cookies, refuses redirect forwarding, requires HTTPS in release
configuration and never automatically replays a write. Passwords, codes, drafts
and rosters are not persisted. Leaving a form clears sensitive fields; background
events hide private screens. Epoch checks discard responses from a prior session
or store. Foregrounding and an active-app check every 60 seconds revalidate access;
unchanged access preserves the current draft, while changed authorized stores or
capabilities reset private views. Server-side authority applies to every request.

Failed secure-storage cleanup cannot restore the discarded token during the
current app process. The app keeps an explicit retry path and does not claim
sign-out completed if device removal failed. Interrupted issuance, concurrent
logout/login and pending cleanup have regression coverage. OS storage failures,
process termination and reinstall behavior remain part of the device test gate.

## Verification

- Complete Python/service/contract/browser suite: **614 passed in 187.22s**,
  including 26 new native API cases. All existing browser assertions remain.
- Mobile client/session suite: **40 passed**, including deferred network/storage
  races, compatibility accounts, revocation and changed-store access.
- TypeScript checks, dependency peer checks and iOS/Android bundle exports passed.
- Six fixture-driven visual checks at phone and tablet sizes had no rendering
  errors or horizontal overflow. The preview renders the actual native screen
  components with a temporary React Native Web harness and synthetic data.
  Three final Today checks also confirm the primary action fits above phone
  navigation; icon imports include only the font used by these screens.
- Real accounts migration/archive restore passed in **1.79s**, comparing 20 tables,
  7 sequences, 33 foreign keys, 25 checks, 3 triggers and 2 functions.
- Real release recovery passed in **5.92s**, including fresh/upgrade/concurrent
  migrations, separate API/worker, worker termination/fencing, database outage,
  legacy rollback and restored login/reports. All rehearsal databases were removed.
  The owned disposable test container was removed after verification.
- CI now includes the mobile type/session checks and both native bundle exports,
  alongside the existing backend and recovery jobs. Hosted CI has not run for
  this local foundation branch.

Local evidence: `/private/tmp/shiftly-native-full.xml`,
`/private/tmp/shiftly-native-export.log`,
`/private/tmp/shiftly-native-accounts-rehearsal.log`,
`/private/tmp/shiftly-native-release-rehearsal.log`, and
`/private/tmp/shiftly-native-visual-proof/results.json` with labeled screenshots.

## Next delivery gates

Run this app against a development FastAPI instance using
[the mobile runbook](../../apps/mobile/README.md). The production startup remains
the legacy server; it does not expose the new native namespace. No real owner
mapping, production data, live AI calls, migrations, deployment configuration,
Apple/Google app identifiers or distribution accounts were changed for this work.

Xcode and the Android SDK are absent on this host. The exports are JavaScript and
asset bundles, not signed native binaries. Simulator/physical-device launch,
secure storage, native navigation, keyboard, accessibility, lifecycle, camera and
distribution checks are not claimed by the local results.

Follow [the adopted native roadmap](../NATIVE_APP_ROADMAP.md): finish native account
administration and operations parity; build catalog/SKUs and trusted manual
inventory; add barcode/photo storage and reviewed assistance; then implement
offline posting with idempotency and complete release preparation. This work
does not claim the entire browser application has been migrated.
