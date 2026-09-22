# Accounts & Access backend handoff

Date: 2026-09-22. Branch: `codex/accounts-permissions-services`.
Base: `9a31a930ebf6fa305e8919d1ff398177666b3577`.

This implements the Codex backend lane of A2a and A2b/A1: named accounts,
scoped policy, lifecycle, migration, controlled bootstrap and legacy HTTP
adapters. FastAPI account adapters, screens and combined named-account browser
verification remain Copilot dependencies. Existing FastAPI regression coverage
does not establish named-account parity. This branch is not production cutover.

## Policy and compatibility

The server selects credentials by store code, normalized username and password.
Migration 014 copies each legacy manager by its unique manager ID, preserving
the original password salt/hash and an explicit `legacy_manager_id`. Username
normalization uses NFKC, collapsed whitespace and database lowercase. Collisions
fail the migration transaction; operators must reconcile identity explicitly.
Historical employee names never create accounts. No business or owner is inferred.

| Role | Effective authority in an enabled, mapped store |
| --- | --- |
| Owner | All capabilities in the owned business; appoint owners/admins and transfer ownership. |
| Admin | Intersection of explicit business delegation and explicit store grants. May appoint managers only within that delegation. |
| Manager | Local reporting/operational capabilities; crew administration only with `memberships.manage`. No automatic shared catalog editing. |
| Crew | `reports.submit` by default; optional view/count/draft/proposal grants only. No approval, posting, adjustment or administration. |

Exact capability names (use these strings in the adapter/UI):
`reports.submit`, `reports.view`, `reports.manage`, `inventory.view`,
`counts.submit`, `counts.approve`, `receipts.draft`, `receipts.post`,
`stock.adjust`, `configuration.manage`, `catalog.propose`, `catalog.manage`,
`memberships.manage`.

Manager defaults are all capabilities above except `catalog.manage` and
`memberships.manage`. A manager can additionally receive `catalog.manage`
through an explicit active business-admin delegation; that does not give the
manager owner/admin account-management authority. Store manager grants themselves
cannot contain `catalog.manage`. Crew's optional grants are `inventory.view`,
`counts.submit`, `receipts.draft`, `catalog.propose` and `reports.submit`.
Unmapped or account-disabled stores expose only reporting capabilities.

Self-escalation and removing/suspending the last active owner are denied.
Local revocation preserves the user's other stores. Global suspension requires
ownership of every target scope, including historical/revoked scopes; an
unassigned scope fails closed. Managers/admins cannot reset a global password
based on local crew authority. Recovery issuance is operator-only, after separate
identity verification; it has no HTTP endpoint.

One request resolves one principal. Invalid named cookies never fall back,
including supplied empty, malformed or duplicate named cookies. The service
signature is `identity.resolve_principal(account_token=None, manager_token='',
crew_token='')`: only `None` means no named cookie. Adapters must preserve that
distinction instead of using a missing/empty default of `''`. The legacy
`security.named_account_token(handler)` helper implements it.
Named plus shared-crew cookies are rejected. Named plus legacy-manager cookies
are accepted only for the same explicitly mapped person and selected store.
Two valid legacy cookie types are rejected as ambiguous; one valid legacy cookie
with an expired legacy peer retains the existing compatibility behavior. Logout
may always clear/revoke the supplied cookies. New sign-in explicitly replaces
old credentials. Shared sessions receive no new account/inventory authority.

Password changes/recovery update the mapped legacy credential and revoke both
session types. Store cutover disables shared crew login and revokes its sessions.
The old add-manager API is denied even with the operator key once a store is
mapped or account-enabled. Controlled legacy signup/add-manager for unassigned
compatibility stores remains available and creates an explicit account mapping.

## Service contract

Import `AccountsService` from `backend.shiftly.identity.accounts`, or use the
already-composed `services.accounts` / `services.identity.accounts`.
Construction performs no I/O. Constructor:
`AccountsService(connect, stores=None, *, admission=None, token_factory=...,
password_hasher=..., session_ttl=28800)`.

Public methods below own their transactions unless a connection is explicitly
supplied. `token` means the raw named cookie; never accept an actor/user ID as
authentication. IDs are positive integers, not numeric strings or booleans.

```python
login(store_code, username, password, *, client_key)
login_payload(fields, *, client_key)
resolve_actor(token, *, connection=None, capability=None, store_id=None)
require(token, capability, *, connection, store_id=None)
authorized_stores(token, *, capability=None, connection=None)
switch_store(token, store_id)
logout(token)
logout_all(token)
roster(token, *, store_id=None)
invite(token, *, username, display_name='', role='crew', capabilities=(),
       store_id=None, expires_in=86400, reason='')
reissue_invitation(token, *, user_id, expires_in=86400, store_id=None, reason='')
activate_invitation(invitation_token, password, *, client_key)
set_membership(token, *, user_id, role, capabilities=(), active=True,
               store_id=None, reason='')
set_business_membership(token, *, user_id, role, capabilities=(),
                        active=True, reason='')
transfer_ownership(token, *, user_id, reason='')
suspend_user(token, *, user_id, suspended=True, reason='')
change_password(token, *, current_password, new_password)
issue_password_reset(*, user_id, reason, expires_in=3600)  # operator only
reset_password(reset_token, password, *, client_key)
cutover_store(token, *, store_id=None, reason='')
```

`resolve_actor` validates the session's original selected store before checking
an optional target store. Revocation at that original store cannot be bypassed
by requesting another store. `require` acquires the policy transaction lock;
the caller must retain that transaction through its associated privileged write.
Never treat a previously resolved actor as permanent authority.

`AccountActor` is frozen. Its `.as_dict()` response contains `userId`, `username`,
`displayName`, `storeId`, `businessId`, authoritative `role`, sorted `capabilities`
and `provenance: "named"`. It also has internal `legacy_manager_id` and
`credential_version`. `authorized_stores` returns actor dictionaries plus
`storeName` (the identifier key is `storeId`, not `id`). Owners see owned-business
stores; other users require their own store membership.

Login, activation and store switching return `SessionResult(role="account",
token=..., response=..., ttl=...)`. The JSON response contains `authenticated`,
`actor`, `storeName` and a legacy `role` projection (`crew` or `manager`). The
actor's role/capabilities are authoritative. Raw session tokens are excluded
from the response JSON and object's representation. Switching rotates/revokes
the previous selected-store token. Default TTL is eight hours.

Roster returns `{storeId, members: [...]}` with each member's `userId`, `username`,
`displayName`, `accountState`, `role`, `membershipState`, `capabilities`. These are
stored membership grants, not the policy-expanded effective capabilities. Roster
is store-membership based; it is not a global people directory or an enumeration
of owners without a local membership.

Invitation/reissue return `{userId, invitationId, token, expiresIn}`. Operator
recovery returns `{userId, resetId, token, expiresIn}`. Their representations
redact tokens, but deliberate JSON serialization reveals the one-time delivery
secret: never log these results or put secrets in query strings. Invitations
expire within 60 seconds–7 days; resets within 60 seconds–1 day. Redemption is
single-use and checks current authority. New passwords require 8–1024 characters.
Email is optional and this module sends no messages.

Password operations return `{changed: true, reauthenticationRequired: true}`;
logout operations return `{authenticated: false}`. Membership changes return
target IDs, role and active state (store changes also return grants); transfer
returns `{businessId, ownerUserId}`; suspension `{userId, state}`; cutover
`{storeId, sharedCrewEnabled: false}`.

`IdentityError.code` maps to HTTP status: `invalid` 400, `unauthenticated` 401,
`forbidden` 403, `not_found` 404, `conflict` 409, `limited` 429,
`unavailable` 503. HTTP errors are `{"error": "safe message"}`. Account-route
database failures return a generic 503 without database details.

All policy mutations, session issuance/revocation and privileged writes use the
same schema-scoped PostgreSQL advisory transaction lock. This serializes them
across processes, including last-owner races. Audit writes commit atomically with
mutations and retain actor, subject, business/store, action, reason and safe
details. Raw passwords/tokens are not recorded. This deliberately simple lock
serializes writes within a schema; measure contention before scaling. Existing
in-memory admission budgets still require one API process (separate worker is
supported). Login, activation and reset redemption use shared admission control.

## Legacy HTTP contract and Copilot integration

`routes.account_route` implements these routes under `/api/accounts/`:

| Method/path suffix | Body / result |
| --- | --- |
| GET `status` | Named `{authenticated, actor, stores}`; legacy `{authenticated:false, reauthenticationRequired:true}`. |
| GET `team` | Roster for selected store; requires team authority. |
| POST `login` | `storeCode`, `username`, `password`; sets named cookie. |
| POST `activate` | `token`, `password`; sets named cookie. |
| POST `reset-password` | `token`, `password`; consumes operator-issued reset and clears cookies. |
| POST `logout` / `logout-all` | Logout needs no body; logout-all accepts `{}` and requires named principal. |
| POST `switch-store` | `storeId`; rotates cookie. |
| POST `invitations` | `username`, optional `displayName`, `role`, `capabilities`, `storeId`, `expiresIn`, `reason`. |
| POST `invitations/reissue` | `userId`, optional `storeId`, `expiresIn`, `reason`. |
| POST `memberships` | `userId`, `role`, optional `capabilities`, `active`, `storeId`, `reason`. |
| POST `business-memberships` | `userId`, `role`, optional `capabilities`, `active`, `reason`; selected business. |
| POST `transfer-ownership` | `userId`, optional `reason`; clears caller cookies. |
| POST `suspend` | `userId`, optional `suspended`, `reason`. |
| POST `password` | `currentPassword`, `newPassword`; clears cookies. |
| POST `cutover` | Optional `storeId`, `reason`. |

Cookie name is **`shiftly_account_session`**, HttpOnly, Path=/, SameSite=Strict,
Secure controlled by existing secure-cookie setting. Named login expires both
legacy cookies. Clear all three on logout/password changes. Account responses
are `Cache-Control: no-store`. Mutation bodies must be JSON objects, bounded to
20 KB. Reject cross-site Fetch Metadata and a supplied Origin not matching Host.
Use tokens only in request bodies or HttpOnly cookies, never URL parameters.

Required peer changes (not implemented in this backend lane):

1. `backend/shiftly/api/compat.py`: add the account namespace above using
   `context.services.accounts`; update cookie helpers for the third cookie.
   Resolve all three cookies with `services.identity.resolve_principal(...)`
   across status, old/new report and account routes. Update
   `backend/shiftly/core/dependencies.py` to preserve named-cookie presence and
   reject duplicate/empty/malformed named values. Do not retain old cookie
   precedence or turn `result.role == "account"` into a crew cookie.
2. `backend/shiftly/api/compat.py`: named report submission calls
   `services.submission.submit(store_id, fields, actor_token=token,
   accounts=services.accounts)`. Legacy submission passes `legacy_credentials`
   containing actual manager/crew tokens. Authorization is rechecked after the
   quality gate in the report/job insertion transaction. Named report reads use
   `services.reports.list_for_actor(token, services.accounts)`, not a fake legacy
   manager ID. Heads-up writes pass the same named or legacy credential arguments
   to `services.stores.save_heads_up`. Preserve existing reporting response shapes.
3. `backend/shiftly/app.py` and `backend/shiftly/api/static.py`: resolve the same
   principal for protected pages; accounts needs named login, inventory additionally
   needs `inventory.view`. Legacy server already protects `accounts.html` and
   `inventory.html` and allowlists `accounts.js`, `inventory.js`, `activate.html`,
   `activate.js`. Missing files stay 404. Do not expose unavailable stock actions.
4. Root browser assets: add store + username + password selection, invitation
   activation, account/team/store-selection screens and permission-aware controls.
   Drive permissions from `actor.capabilities`, never the legacy JSON `role`.
5. `tests/contract/`, `tests/browser/`, CI/rehearsal integration: verify identical
   named-account behavior through both transports, including every mixed-cookie
   case, named crew reporting and new managers without legacy IDs. Keep features
   gated until these adapters/screens and their combined tests are complete.

The existing `/api/auth/status` response remains compatible for old sessions;
named sessions additionally expose `actor` and remain authenticated even without
report permissions. Existing historical report display names/text, job processing,
deduplication and scoped report response shapes are preserved. New named reports
persist a server-derived `reports.actor_user_id`; historical rows remain NULL.
Legacy inboxes retain access across permitted store memberships, but exclude
inactive stores/businesses and suspended/revoked account access.

## Migration, operator mapping and recovery

Migration `014_accounts_access.sql` is additive; 001–013 are unchanged. It adds
businesses, users, business/store memberships, named sessions, invitations,
resets and audit; stores gain business/enrollment/shared-crew flags; reports gain
nullable actor. Constraints and deferred scope triggers prevent mismatched/null
business assignments. Fresh installs and 013 upgrades use the normal transactional
runner. The manager backfill is in that transaction; assess real table sizes
before rollout and use a separate resumable process if volume requires it.

Use explicit disposable `DATABASE_URL` and the existing runtime settings; these
commands do not load the application's `.env`:

```sh
python -m backend.shiftly.runtime.migrate
python -m backend.shiftly.runtime.accounts_admin bootstrap --manifest mapping.json
python -m backend.shiftly.runtime.accounts_admin bootstrap --manifest mapping.json --apply
python -m backend.shiftly.runtime.accounts_admin recovery --user-id 42 --reason 'Verified operator recovery'
python -m backend.shiftly.runtime.accounts_admin recovery --user-id 42 --reason 'Verified operator recovery' --apply --reveal-token
```

Bootstrap/recovery default to dry-run. Applying recovery intentionally prints the
one-time secret for supervised delivery. It must not be captured in shared logs.
Example mapping uses synthetic IDs; replace all IDs with independently verified
values, not guesses:

```json
{"reason":"Synthetic rehearsal only","businesses":[{"id":700,"name":"Example business","owner_user_ids":[42]}],"stores":[{"store_id":12,"business_id":700,"accounts_enabled":false}]}
```

Owners must already be active verified accounts. Bootstrap rejects conflicting
business identity/ownership, reassignment, inactive stores, and disabling an
already-enabled boundary. It updates dependent membership/invitation scope in
one transaction. Set `accounts_enabled:true` only for reviewed enrollment; this
grants the mapped role's operational policy. Shared crew cutover is a separate
owner operation after individuals have enrolled. No real mapping was applied.

Before rollout, take and test a backup, rehearse migration with representative
data, reconcile any normalized-name conflicts, apply 014, then review the dry-run
mapping. FastAPI integration and combined verification are prerequisites to
activation. Keep additive schema/history on application rollback. Never run a
pre-account permissive adapter against an activated store, re-enable shared
credentials automatically, or remove audit/account data with a down migration.
Recovery rollback means a tested compatible build/restore, preserving revocations;
the transport rehearsal is the current branch's legacy transport, not old code.

## Verification and commit record

Baseline at the exact base: **357 passed in 70.33s** with disposable PostgreSQL 16,
mocked AI and both existing transports/browser cases. Final verification and
commit SHAs are recorded below after the checkpoint is committed.

Independent account recovery rehearsal (`python -m
backend.shiftly.runtime.accounts_rehearsal --create-databases`) passed in 1.73s.
It used explicit `ACCOUNTS_REHEARSAL_DATABASE_URL` and
`ACCOUNTS_REHEARSAL_RESTORE_DATABASE_URL`, plus optional
`ACCOUNTS_REHEARSAL_SOURCE_CONTAINER` / `ACCOUNTS_REHEARSAL_RESTORE_CONTAINER`.
Targets must be distinct local disposable database names beginning
`shiftly_accounts_rehearsal` / `shiftly_accounts_restore`; newly created databases
are removed in finally. No application `.env` or paid provider calls are used.

This is a real pg_dump/pg_restore rehearsal: exact equality of 20 durable tables,
7 sequences, 33 foreign keys, 25 checks, 3 scope triggers and 2 functions. It
verifies 013 historical values, mapping dry-run/apply, named report actors,
credentials/revocations, scope isolation, suspension, shared-crew cutover and
restored reads/writes, activation and replay denial. The independently run
existing release rehearsal additionally covers API/worker restart, worker crash,
database outage and transport rollback; it passed in 5.96s with a real 63,816-byte
archive and exact 20-table, 7-sequence, 33-FK restore comparison. Both sets of
temporary rehearsal databases were removed.

Two minimal shared-file adaptations are isolated in an integration commit:
`tests/test_report_duplicates.py` and `tests/test_weekly_overview.py` still compare
every original historical field and additionally require a NULL actor after
upgrade. `scripts/rehearse_release.py::verify_upgrade` still requires all original
rows/fields, sequence states and FK definitions to survive, while allowing
additive schema. Post-restore equality remains complete. Nine direct regression
tests reject removed/changed rows, fields, sequences and FKs; none of the old
checks is skipped or weakened to permit data changes.

Owned implementation paths: `backend/shiftly/identity/{accounts,accounts_core,
accounts_policy,accounts_lifecycle,principal,repository,service}.py`,
`backend/shiftly/runtime/{composition,accounts_admin,accounts_rehearsal}.py`,
`backend/shiftly/{reports,stores}/{repository,service}.py`, `auth.py`, `routes.py`,
`server.py`, `security.py`, `store_service.py`, `reporting.py`, migration 014,
`tests/accounts_services/`, and `tests/runtime_services/test_migrations_status.py`.
No dependencies, worker semantics, production settings or peer UI/FastAPI files
were changed. No inventory/catalog tables, media pipeline or training were added.
