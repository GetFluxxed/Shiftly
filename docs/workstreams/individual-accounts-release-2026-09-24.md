# Individual accounts for the release

Decision: Shiftly is still in development, with test accounts only. Public sign-in does not retain the shared crew or password-only manager model.

## Account model

- Everyone signs in using a unique username and personal password. Store codes and role selectors are absent from the sign-in screens.
- Crew and manager accounts have one active store membership. They cannot switch stores. An administrator removes the old membership before transferring a person to another store; their password remains their own.
- Administrators use explicit business delegation and matching store permissions. Owners retain business-wide authority. Only those roles can switch between authorized stores.
- Reports, including the owner/admin inbox, show the selected store. Switching stores reloads the account context and report list.
- Admins and owners change store roles and permissions after activation. A manager with an explicitly delegated invitation permission may invite baseline crew, but cannot edit memberships or promote anybody.
- No public manager, admin, owner, or workspace signup. Initial ownership is a controlled operator/bootstrap action. Further ownership and administration are assigned by an existing owner.

## Invitations

Both clients request a randomly generated invitation token from the server. Its hash, recipient, store, issuer, expiry, and state are saved on the server. The server grants a baseline crew account; privileged roles and additional permissions are rejected at invitation creation and before activation.

A link contains only the opaque secret in its URL fragment. It does not carry trusted role, permission, store, or username claims. Opening the link previews the bound username and store without accepting the invitation. The client removes the fragment from navigation/history and submits the token in a request body when the recipient chooses a password.

Activation rechecks current store access and the issuer's authority under the same database policy lock as account changes. It consumes the token and creates the account session in one transaction. Expired, revoked, replaced, or already-used tokens cannot activate an account. Reissuing creates a new token and never revives an old one.

The mobile result provides a share sheet and selectable link. In Expo Go it points to the current local development server, so the recipient needs network access to that server. Installed builds use the Shiftly app scheme. The browser provides a link to its activation page. Email delivery and production universal links are separate release infrastructure work; this change does not send messages automatically.

## Enforcement and existing test data

The original store leakage came from membership-wide report queries and account/session logic that allowed staff to retarget any assigned membership. Enforcement now lives in the shared account service, report repository, and request principal, with matching mobile controls. Browser and mobile clients use the same policy.

Shared and legacy cookies are rejected by public request authentication, even when an old database row remains valid. Both public login URLs use individual accounts. The old signup endpoints return an invitation-required response regardless of the old operator key.

No schema migration is required. Existing records are preserved. An account with conflicting active staff assignments is denied access until an administrator resolves them. Unaccepted older invitations containing elevated roles or additional grants cannot activate; an administrator must set the pending membership to baseline crew and reissue a new invitation.

The test manager is assigned to Market Street, as selected by the user. The owner retains both Market Street and Harbor. Catalog items, container measurements, shelves, and reports are preserved.

## Verification

Verification covers individual login, forbidden store switching and request retargeting, selected-store reports, permission tampering, single-use and concurrent activation, issuer revocation, replacement links, concurrent store assignments, permission-change session revocation, native account screens, and inventory regressions. Test fixtures now create individual accounts explicitly rather than using the retired public signup flow.

Local verification: 706 Python/backend and rendered-screen tests passed; 71 mobile tests passed; TypeScript checking and iOS/Android exports passed. The account backup/restore rehearsal passed. These checks were completed before the publishing pass; they were not rerun locally at the user’s request. The user confirmed that the updated account experience works on the iPhone through Expo Go. CI on the published revision is the release checkpoint.

## CI teardown correction

The two preceding failed main-branch runs (35934429601 and 35723163755) completed all test assertions but encountered PostgreSQL deadlocks while dropping browser-test schemas. The legacy browser server used daemon request threads, so closing the listener did not wait for pending database requests. The browser fixture now uses non-daemon request handlers, making server closure wait for their transactions before database cleanup. A regression test holds an actual database request open during shutdown and verifies that closure cannot finish until the request completes. No retry or relaxed assertion masks the race.
