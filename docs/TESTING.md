# Testing

## Local validation

The integration suite requires a disposable PostgreSQL database. It reads only
`TEST_DATABASE_URL`; it never falls back to the application's `DATABASE_URL` or
the database in `.env`. Database tests fail with setup instructions when this
variable is missing.

Install the dependencies with `python3 -m pip install -r requirements-dev.lock`
and `python3 -m playwright install chromium`, then
start a separate test database (port 55433 keeps it separate from the usual local
app database on 55432):

```sh
docker run --rm --name shiftly-test-db \
  -e POSTGRES_USER=shiftly_test \
  -e POSTGRES_PASSWORD=shiftly_test \
  -e POSTGRES_DB=shiftly_test \
  -p 127.0.0.1:55433:5432 \
  -d postgres:16-alpine
docker exec shiftly-test-db pg_isready -U shiftly_test -d shiftly_test
```

Once Postgres is ready, run:

```sh
TEST_DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55433/shiftly_test \
  python3 -m pytest -q --browser chromium
```

Attach the database variable to the **pytest process** each time. In
`TEST_DATABASE_URL=... python3 -m compileall ... && python3 -m pytest ...`, only
compilation receives that variable; pytest will correctly refuse to run database
tests. Run compilation separately, then use the explicit pytest command above.
Keep the fixture's refusal to fall back to an application database intact.

Each database test creates and removes its own randomly named schema. Its
connections use only that schema, with no fallback to `public`. The test role
must be able to create schemas. Tests do not truncate existing application
tables. The suite also resets process-level rate limits and worker signals and
blocks external AI calls unless a test supplies a deterministic response.

When finished, remove the disposable database:

```sh
docker stop shiftly-test-db
```

## Coverage and appropriate checks

The suite covers individual invitations/accounts and store scope; both browser
transports and native API contracts; report submission, durable workers and
weekly summaries; catalog/barcode/package conversions and measurement correction;
counts, exact stock/movement history; recipe revisions, production confirmation
and advisory forecast validation/recovery; native restoration, compact layouts,
permission loss, stale conflicts and uncertain writes. Retired public signup and
shared login are tested as denied, not supported user workflows.

Choose the checks affected by a change. Relevant commands from the root:

```sh
python scripts/verify_dependency_locks.py
python -m pip check
python -m compileall -q backend scripts reporting.py
pnpm --dir apps/mobile check
pnpm --dir apps/mobile export:native
```

The native commands require the locked mobile install described in the
[mobile README](../apps/mobile/README.md). Backend integration and rendered native
journeys use the explicit disposable `TEST_DATABASE_URL` above; rendered journeys
also need the mobile dependencies, Node and Playwright Chromium. Physical-device,
signed-build and real-provider evaluations remain separate release gates.

For the engineering adoption changes, the focused regression sets are:

```sh
TEST_DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55433/shiftly_test \
  python -m pytest -q tests/test_worker_recovery.py tests/runtime_services \
  tests/report_services tests/test_report_duplicates.py tests/test_weekly_overview.py \
  tests/test_dependency_locks.py
```

All provider calls in ordinary tests are deterministic or refused; tests must not
incur AI charges. The modern worker startup test explicitly forbids importing the
legacy root reporting module. Demo setup tests cover named owner login, zero stock,
repeat/concurrent refusal, transaction rollback and hidden-input failure handling.

CI uses Python 3.12.15/PostgreSQL 16 and installs the shared locked runtime. It runs
the complete Python/browser suite and native type/tests/exports, followed by two
recovery rehearsals. Release rehearsal covers upgrade/repeat/concurrent migration,
real worker termination and expired lease recovery, database outage/reconnect,
compatible legacy reads, and real archive restoration with login. Account rehearsal
starts at historical migration 013, upgrades through all current migrations and
verifies ownership, revocations, named actors and restoration of rows, sequences,
foreign keys, checks, triggers and functions. These are synthetic-data proofs,
not hosted production recovery evidence.

Camera counts, media upload/retention, invoice receipt posting and offline write
queues remain future acceptance work. Their permission, malformed-input,
idempotency, overlap/duplicate, accuracy and recovery criteria live in the
[camera and invoice readiness plan](workstreams/camera-and-invoice-readiness.md).
The stock and production tests prove their implemented rules, not physical usage
measurement or forecast accuracy.

## Dependency locks

Use a fresh virtual environment; a developer's global package set is not the
release input. CI and the Render manifest select Python 3.12.15. The production
lock contains exact direct **and transitive** runtime pins, including upstream
platform markers. The development lock includes it and adds test-only packages.
Input ranges in `requirements.txt` describe permitted updates, not deploy inputs.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.lock
python scripts/verify_dependency_locks.py
python -m pip check
```

The verifier reads installed package metadata, checks runtime dependency closure,
compatible versions/extras, duplicate pins and matching inputs, and rejects a
stale environment. It is a development tool using the already-pinned `packaging`
module; production needs only `requirements.lock` and `pip check`.

For a deliberate update:

1. State the requirement and check the dependency's compatibility, license,
   maintenance/security exposure, operational cost and replacement path. Change
   only the intended input ranges/pins; preserve unrelated tested versions.
2. Resolve in a clean Python 3.12 environment, using existing exact pins as
   constraints for packages not being updated. Review resolver metadata/results;
   do not overwrite the lock with a global `pip freeze`.
3. Put the complete runtime closure, including required extras and platform
   markers, in `requirements.lock`. Keep test/browser-only pins in
   `requirements-dev.lock`, which must include the runtime lock exactly once.
4. Create separate fresh runtime-only and development environments. Install their
   respective locks and run `pip check`; run the verifier in development. Inspect
   the runtime-only install for unexpected/unpinned packages. Resolve/install the
   target Linux/Python architecture as well as local development platforms.
5. Run the relevant application tests/builds and recovery checks, review the exact
   dependency diff, and record evidence before updating the deployment. A passing
   resolver is not evidence that authentication, stock or provider behavior works.

Do not upgrade Expo/React Native packages independently of their supported SDK
combination. Use the frozen pnpm lockfile, and evaluate device/build behavior for
native dependency changes. Locking and `pip check` are not vulnerability audits.

## Safety rules

- Use disposable local data only.
- Never copy production secrets or data into tests.
- Do not mock the database layer for the integration baseline.
- Keep AI behavior deterministic via monkeypatching at the service boundary.


## Release-rehearsal backup prerequisites

The local release runner uses a real PostgreSQL custom-format archive and
`pg_restore --exit-on-error --single-transaction`. It replaces the schema/data in
its **disposable restore target**. Never point either rehearsal URL at a live
application database. Use a fresh source database for each full run because the
runner creates a fixed synthetic workspace.

Install matching PostgreSQL `pg_dump` and `pg_restore` clients on PATH, or use the
clients already inside the two disposable PostgreSQL containers:

```sh
docker compose -p shiftly-rehearsal -f deploy/compose.integration.yml up -d --wait
export REHEARSAL_DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55436/shiftly_test
export REHEARSAL_RESTORE_DATABASE_URL=postgresql://shiftly_test:shiftly_test@127.0.0.1:55437/shiftly_restore
export REHEARSAL_SOURCE_CONTAINER="$(docker compose -p shiftly-rehearsal -f deploy/compose.integration.yml ps -q postgres)"
export REHEARSAL_RESTORE_CONTAINER="$(docker compose -p shiftly-rehearsal -f deploy/compose.integration.yml ps -q postgres-restore)"
DATABASE_URL='' OPENAI_API_KEY='' python3 scripts/rehearse_release.py
docker compose -p shiftly-rehearsal -f deploy/compose.integration.yml down -v
```

The container variables select `docker exec` clients connected to PostgreSQL
inside those containers on port 5432. The URL still supplies the database name,
user and password. Without these variables, native clients are required.
Missing tools, command failures and timeouts fail the rehearsal; there is no
application-row-copy substitute for a backup. Errors omit tool output and
connection strings. The two-transport health fixture supplies the same explicit
fake API-key setting to both servers and remains subject to the shared
fail-closed AI fixture.

`tests/release_rehearsal/test_backup_restore.py` covers missing prerequisites,
source/target reuse, failed/timed-out backup and restore, sanitized failures and
the container archive pipeline. The real archive/restore and restored API smoke
results are recorded in the focused verification handoff. Technical checks must
be reviewed and merged with green CI to close Gate D. The disposable rehearsal
does not establish hosted staging or production readiness.
