# October 31, 2026 iPhone counting pilot

Updated 2026-10-24. The goal is a functional, installable iPhone release candidate
for the general manager's October 31 physical count. Eight calendar days remain at
the start of this workstream. The date is a target for a bounded internal pilot,
not a guarantee of App Store or TestFlight review.

## Frozen pilot scope

The pilot includes individual-account sign-in and server-authorized roles, the
shared catalog and barcode/manual capture, the temporary Saved scans inbox, and
the existing whole-store count workflow. The manager prepares the count online,
records observations through the restricted offline workspace, reconnects to sync,
and completes review/posting online.

Shelf-photo counting, AI inventory recognition, offline catalog mutation, offline
review/posting and unrelated production expansion remain outside the count pilot.
On October 25 the owner additionally authorized manager/owner invoice photo intake
and reviewed incoming previews. This bounded local preview is documented in
[invoice previews](invoice-receiving-preview.md); it does not complete the count
pilot’s signing, hosted or device gates. A barcode capture, invoice proposal or
saved draft never changes stock.

## Interface consistency before October 31

Keep the existing cocoa/rose palette, typography and bottom navigation. Refine
existing native screens so the same action has the same label, placement and
interaction. This is presentation work within the pilot; it does not expand the
feature scope or replace signing, connectivity and count-integrity gates.

1. **Inventory first:** use compact aligned tables for catalog/current stock,
   compact rows for shelf contents, and the established count list with entry
   sheets. Preserve searchable SKUs in the catalog and a separate Change action.
   Keep exact quantities readable, including original pound-labelled containers.
2. **Recipes and production:** align list density, section headings, edit sheets,
   primary actions and confirmation placement while preserving recipe scaling,
   Variegato and production-posting behavior.
3. **Today, Reports, Store and Account:** align page spacing, workspace tiles,
   headings, action priority, empty/error states and settings. Retain role-specific
   access and existing supported destinations.
4. **Final walkthrough:** check immediate back destinations, search/filter
   persistence, visible save/cancel actions, loading/sync feedback, 44-point touch
   targets, long names and enlarged text on the pilot iPhone. Review phone/tablet
   layouts and use the same labels for the same operation across views.

The catalog table is the first implementation in this pass. It preserves the
existing measurement editor, scan-result cards, alphabetical search, status
filters, pagination and permission checks. Local TypeScript/mobile checks passed;
eight focused rendered journeys passed against disposable data. The table was
checked from 320 to 1440 pixels, with phone/tablet previews reviewed. Enlarged
native text and final physical-device acceptance remain part of the walkthrough.
Later screens remain pending individual review; the entire app is not yet
declared visually verified.

## Expo Go compatibility — October 24

The owner's Expo Go now supports SDK 58; the project and running development
server were still on SDK 57. Upgrade the complete supported set to Expo 58.0.19,
React Native 0.88.0 and React 19.3.0, including camera, router, SecureStore and
Metro. Preserve the API origin, encrypted storage keys and database. No data
migration or app reinstall is part of this upgrade.

React Native's strict public instance types replace component ref types; remove
the obsolete status-bar color prop and retain the existing focused/unfocused tab
palette. The browser journey harness selects Expo's public `expo-source` export
so its TypeScript-only declarations do not become invalid runtime imports. No
assertions, account checks or storage behavior are bypassed.

The pinned package manager added exact release-age exceptions for the newly
published official Expo dependencies selected by its compatibility check. Their
lockfile integrity and the general package-age policy remain in force; review
these exceptions during the next dependency maintenance pass.

Local evidence: Expo Doctor passes all 20 checks, the dependency compatibility
check is clean, frozen-lockfile installation succeeds, TypeScript and all 199
mobile tests pass, and 22 focused rendered journeys pass against disposable
PostgreSQL. Both native bundle exports pass. The restarted local server advertises
SDK 58 and serves the iOS development bundle successfully. These checks do not
establish physical iPhone acceptance, signing, CI or deployment. Reopen the app
on the owner's phone and verify a saved count, saved scan, real camera capture,
modal dismissal and immediate back navigation before accepting device behavior.

## SDK 58 navigation follow-up — October 25

Physical testing exposed a navigation regression after the upgrade: opening a
section could return immediately to Today. SDK 58 interprets a tab's `href: null`
as an unavailable destination and redirects it to the first available tab. The
catalog, shelves, count, stock, team, owner and announcement sections previously
used this option only to omit their bottom-bar buttons. Production also used it
for managers/owners despite their permitted shortcut on Today.

Keep those destinations declared and hide only their tab buttons and item space.
Retain `href: null` for tabs unavailable to the account. Existing screen/API
permissions, restoration scope, saved drafts and inventory data remain unchanged.
This preserves the current routes and bottom-bar design without moving all route
files during a compatibility fix.

The earlier rendered journeys replace the router with a test adapter and therefore
cannot establish SDK router behavior. The new `test_rendered_router.py` uses the
installed Expo router, actual tab layout, session/workspace controllers, root
redirect, Today and Reports screens, with fixture accounts and read-only report
responses. Other destination content is stubbed to isolate route behavior.

Local evidence: the pre-fix layout reproduced the catalog returning to Today.
The fixed layout passes three real-router browser journeys covering nested
sections, the owner Production shortcut, tab order, role restrictions, Reports
loading/refresh and cold restoration of a saved catalog page. TypeScript and 199
mobile unit tests pass; the local Expo server serves the updated SDK 58 iOS bundle.
Reports stayed open in the baseline route check too, so the specific reported
Reports reset has not been reproduced locally. A full Expo Go reload and physical
iPhone confirmation remain pending; these checks do not establish CI, deployment
or signed-build acceptance.

## Distribution decision and prerequisites

The preferred deadline route is an Expo/EAS internal-distribution iOS release
candidate using ad hoc provisioning. It embeds the JavaScript bundle, installs
from a controlled link, and must launch without Metro. The general manager's exact
iPhone must be registered before the build; adding another device requires another
provisioned build. Protect the internal build link and share it only with the
pilot participants.

This route is blocked until the owner confirms an active Apple Developer Program
membership, signing authority, an Expo account/project, a unique bundle identifier,
and the general manager's device identifier. Do not invent account, team, app or
bundle identifiers. TestFlight may be used instead, but internal testers must be
App Store Connect users and external testing can require Beta App Review. Neither
Apple processing nor review completion by October 31 is guaranteed.

No `eas.json`, bundle identifier, paid build, submission, provisioning action,
public exposure or hosted deployment is authorized merely by this document.

## Backend and production-data gate

The release candidate must embed only a stable HTTPS API origin. It must reach the
supported FastAPI `/api/mobile` routes. The checked-in Render configuration starts
the legacy `python server.py` browser runtime, which does not serve those routes
and is therefore insufficient for this pilot.

Before promotion, record the exact application revision and runtime versions;
retain and restore-test a database backup; apply migrations explicitly; run one
supervised FastAPI process; and provide a separately supervised worker when
AI-backed reports or forecasts are enabled. Verify health, restart behavior and a
compatible rollback artifact. Never point the demo initializer at the intended
hosted database or silently copy/reset demo inventory.

The general manager must use a named individual account mapped to the intended
business and store with only the necessary capabilities. Dry-run controlled
account mapping against independently verified IDs. Prove that another account or
store cannot read, prepare, upload or resolve the pilot's data before accepting the
hosted environment.

## Temporary Saved scans contract

An account with `inventory.view` and `catalog.manage` opens Saved scans while
online. Successful inbox restoration and explicit online preparation grant only
that origin, user, business and store a restricted
12-hour offline workspace. A partial preparation cannot advertise offline
readiness. Up to 100 encrypted local drafts may retain the raw barcode and proposed
name, unit and container amount. No photo is stored.

Offline capture does not call the server, create a product or package, change
stock, or schedule background upload. After reconnection, the original authorized
account reviews each draft online. A fresh server lookup must handle an existing
product, reserved alias or archived record before offering an explicit new-product
or package action. Each resulting mutation uses the normal server authorization
and conflict behavior.

Sign-out locks the queue but preserves pending drafts for recovery. Only the same
account under the same service origin, business and store may resume or resolve
them after signing in again. Until a draft is resolved online, it has no server
backup. Storage failure cannot report a successful save.

The Saved scans inbox is the temporary part. Remove it only after permanent
offline catalog synchronization and review have shipped and all existing drafts
have been migrated or safely drained. Do not retire the installed app, offline
count queue, account isolation or permission enforcement with it.

## Acceptance checklist

- [ ] Owner confirms active Apple Developer membership, signing authority, Expo
  ownership, a unique bundle identifier, distribution path and registered GM
  device. Evidence pending.
- [x] Saved scans source passes local mobile checks, rendered offline journeys
  and iOS/Android bundle export. See the evidence ledger below.
- [ ] The committed release candidate passes exact-revision CI. CI evidence is
  pending; local exports do not establish a signed release candidate.
- [ ] A signed internal/release binary installs on the GM iPhone, launches after a
  force-quit in airplane mode without Metro, and recovers encrypted state. Build
  and physical-device evidence are pending.
- [ ] Camera permission, real barcode scanning and manual fallback work on that
  iPhone. Physical-device evidence is pending.
- [ ] While online, the GM signs in to the intended store, prepares Saved scans
  and the complete open count, then verifies both offline grants are ready.
- [ ] Offline, the GM cold-launches, saves representative raw scans and count
  observations including an explicit zero, backgrounds/reopens, and sees only the
  restricted authorized workspace.
- [ ] Reconnected with the app foregrounded, every count observation syncs or
  presents an explicit conflict; review/posting remains unavailable until clear.
  Every saved scan receives a fresh lookup and explicit resolution.
- [ ] Sign-out, account/store changes, expiry and remote revocation lock private
  state; only the original account/scope can recover pending drafts. Another store
  cannot observe or mutate them.
- [ ] The HTTPS FastAPI deployment, database backup/restore, migration, account
  mapping, worker requirement, health checks and compatible rollback are verified
  for the exact candidate revision. Hosted evidence is pending.
- [ ] The posted count produces the expected store-scoped balances and immutable
  history without any Saved scan changing stock directly.

## Working delivery sequence

These dates depend on signing access and a stable supported backend; a missed
prerequisite reduces rehearsal time and must not be hidden by declaring source
completion a release.

| Target | Deliverable |
| --- | --- |
| October 23–24 | Refine the catalog table; exercise Saved scans and counts on the owner's iPhone; confirm Apple/Expo ownership and the GM device; finish catalog data needed for the count |
| October 24–26 | Continue the bounded interface consistency pass; configure the signed internal release and stable HTTPS FastAPI environment; rehearse database/account mapping and recovery |
| October 27–28 | Install on the GM's exact iPhone; rehearse offline cold launch, capture, count, reconnection and conflicts in the storage area |
| October 29–30 | Fix rehearsal blockers; freeze the candidate, verify its CI and reinstall/retest that exact build |
| October 31 | Assisted GM count with reviewed posting, known recovery steps and the previous working build available |

## Evidence ledger

| Stage | State on 2026-10-23 |
| --- | --- |
| Settled scope and acceptance contract | Documented here |
| Temporary Saved scans implementation | Implemented; no backend or schema change |
| Focused local checks | TypeScript and all 199 mobile tests passed |
| Rendered offline journeys | All 5 saved-scan and 3 existing offline-count journeys passed together against disposable PostgreSQL; no live inventory writes |
| iOS/Android bundle export | Passed for both platforms; this is not a signed binary or device acceptance |
| Exact-revision CI | Pending |
| Active Apple membership/signing ownership | Pending owner answer |
| Bundle identifier and EAS build configuration | Not created; pending ownership decision |
| Signed installable iPhone build | Pending |
| GM physical-device and airplane-mode acceptance | Pending |
| Stable HTTPS FastAPI `/api/mobile` deployment | Pending; current checked-in Render runtime is legacy |
| Production account/data mapping and isolation | Pending |
| Backup, migration, health and rollback rehearsal | Pending |

Official distribution references: [Expo internal distribution](https://docs.expo.dev/build/internal-distribution/),
[Expo iOS submission prerequisites](https://docs.expo.dev/submit/ios/),
[Apple registered-device distribution](https://developer.apple.com/documentation/xcode/distributing-your-app-to-registered-devices),
and [Apple TestFlight overview](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/).
