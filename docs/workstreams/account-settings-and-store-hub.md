# Account settings and Store workspace

Requested 2026-09-26. Implemented and locally verified; follow-up physical-device
review is pending. Publication and CI results are tracked in the pull request.

## Accepted layout

- Account shows personal identity and a compact settings grid. Open one panel at
  a time for store selection/details, effective permissions, sign-in security or
  sign-out. Sign-out first displays **Sign Out** and **Cancel Sign Out**; only the
  affirmative action ends the session. Password change and sign-out everywhere
  remain available under security.
- The tab order is Today, Reports, Inventory, Store, Account. Store remains
  visible to managers and owners only; Account is last. Its four Store tiles are
  Build Your Team, View Team Members, Store Access and Owner Workspace. The owner
  action stays unavailable to managers. These are navigation changes, not grants.
- Team building contains the existing invitation and existing-account actions.
  The member screen has a searchable dropdown and one selected member's details,
  with permitted editing reachable from that selection.
- Team members are ordered by their most recent recorded sign-in/activation at
  the selected store. Never-signed-in people follow, with stable username/ID ties.
  Session refresh, token rotation and other-store activity do not change this date.

## Boundaries

Keep crew/managers assigned to one store. Store switching remains available only
to authorized owners/admins. Invitations still create baseline crew; managers
require their existing delegated invitation capability and cannot promote or edit
memberships. Server-provided role choices and `canEdit` remain authoritative.
Admins retain their team administration link in Account settings and a Build
Your Team action in that area, including invitation and existing-account access
when their server-provided role choices permit it. Meanwhile,
the Store tab follows the requested manager/owner visibility rule. Direct Store
navigation also checks role; backend permissions remain independently enforced.

Reuse the inventory tile pattern as a small shared native component without
changing the accepted Inventory appearance or destinations. Reuse account services,
session invalidation, sensitive-form cleanup and native transport. The roster gains
nullable `lastSignInAt` from existing store-scoped audit events; no migration or
new permission is required. Do not seed or modify demo inventory during verification.

## Work packages and verification

The lead owns design, the shared grid/navigation, roster metadata, integration and
review. Separate Sol tasks implement Account settings and Store/team UI in
disjoint files. Verification covers sign-out/cancel, staff store-switch denial,
manager/owner tab visibility and direct-route denial, dropdown order and null
timestamps, selected-member editing, store isolation, and phone/tablet layout.
Run native checks and focused account/API/rendered journeys on disposable data;
physical-device acceptance is separately performed through Expo Go.


## Delivery evidence — 2026-09-26

- Native type-check and all 79 existing native tests passed. Final iOS and
  Android exports passed after the UI adjustments.
- The 67 focused roster, lifecycle and native API checks passed on disposable
  PostgreSQL. Roster coverage includes selected-store isolation, activation,
  stable ordering, never-signed-in accounts and excluding token refresh activity.
- All 11 account screen journeys passed: invitation activation, common login,
  manager store-switch restrictions, sign-out/cancel, four role-based Store tab
  cases, member ordering/search/editing, owner switching/permissions, and the
  administrator's retained team-building route. A public-screen remount issue in
  the expanded test renderer and an under-granted administrator fixture were
  corrected; no authorization rule was relaxed to pass these checks.
- Browser previews of actual native components with bundled fonts/icons checked
  Account and owner/manager Store grids at 320, 375, 390, 768 and 1024 pixel widths.
  Store tiles fit each tested viewport. Account settings fit from 375 pixels;
  the 320×568 preview scrolls vertically to preserve readable identity details.
  There is no horizontal overflow. The existing Inventory grid retained its
  layout, all five destinations and keyboard access at six viewport sizes.
- The local demo API was restarted without seeding or migrating its database.
  Owner and manager roster smoke checks passed; the manager retained one store.
  The live Expo iOS development bundle contains the new screens. Expo, the API and
  the existing worker remain running locally. The disposable test database was
  removed after verification.

These browser previews use navigation/platform adapters; native exports establish
bundle correctness. Neither substitutes for the user's Expo Go device review.
Earlier CI results do not verify this revision; consult the pull request checks
for the published commit.


## Navigation correction — 2026-09-26

Device feedback identified two causes: administration Back buttons followed global
navigation history, and Today/Account used React Navigation's default tab button
while explicit-href tabs used Expo Router's Link/Pressable button. The latter mixed
two native rendering paths in the same bar.

- Team and owner administration now use an explicit Back to Store destination for
  managers/owners, independent of earlier Home or Store Access visits. Admins keep
  an explicit Back to Account destination because they do not have the Store tab.
- Today and Account now declare their destinations just like the other visible
  tabs. No per-tab position offsets were added. Store precedes Account; existing
  role/capability visibility and the wide-screen sidebar remain unchanged.
- Sol inspected the installed tab implementation and staged the tab correction;
  the lead reviewed/integrated it and corrected return navigation. The rendered
  account fixture now retains history so regression checks exercise the formerly
  problematic Back path, rather than always pretending no history exists.
- Native type-check and 79 native checks passed. All 13 rendered account journeys
  passed against disposable PostgreSQL, including Store returns after earlier
  sibling-page visits, administrator fallback, tab order and role visibility.
  iOS/Android exports passed. The running Expo iOS bundle contains the fixes.

Reload Expo Go for device confirmation of tab alignment. This correction does
not change account data or permissions.
