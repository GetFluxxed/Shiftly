# Testing

## Local validation

The integration suite requires a disposable PostgreSQL database. It reads only
`TEST_DATABASE_URL`; it never falls back to the application's `DATABASE_URL` or
the database in `.env`. Database tests fail with setup instructions when this
variable is missing.

Install the dependencies with `python3 -m pip install -r requirements.txt`, then
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
  python3 -m pytest -q
```

Each database test creates and removes its own randomly named schema. Its
connections use only that schema, with no fallback to `public`. The test role
must be able to create schemas. Tests do not truncate existing application
tables. The suite also resets process-level rate limits and worker signals and
blocks external AI calls unless a test supplies a deterministic response.

When finished, remove the disposable database:

```sh
docker stop shiftly-test-db
```

## Coverage

- Manager signup, login, session creation and revocation
- Crew authentication and manager access to crew reporting
- Malformed login requests and database health/startup failures
- Report queue processing and job completion
- Duplicate submissions within and across stores, including concurrent requests
- Transaction rollback when creating a report's background job fails
- Fresh schema setup and upgrades that preserve reports, jobs and briefings
- Test database isolation and refusal to use the application database implicitly
- Concurrent login reservations, failure-window expiry and successful-login recovery
- Weekly generation capacity, nonblocking store locks and cleanup after provider failures
- Weekly cache validation, complete-report coverage counts and source invalidation
- Weekly endpoint authorization, pending responses and migration 011 upgrades

GitHub Actions runs the suite with Python 3.12 and a disposable PostgreSQL 16
service, supplying `TEST_DATABASE_URL` explicitly.

The merged FastAPI foundation adds `tests/transport_parity/`. These checks run
the legacy HTTP server and the development FastAPI app against equivalent
disposable database state for health responses, public assets, protected-page
redirects, traversal denial, and security headers. They do not claim full
browser parity until the Codex identity/store/runtime service checkpoint is
published.

## Planned coverage for the next modules

These checks are future acceptance requirements from
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), not existing test claims.

| Area | Required evidence |
| --- | --- |
| FastAPI migration | Old/new transport contract parity, cookies, validation errors, security headers and browser flows |
| Worker reliability | Restart/lease recovery, nested failures, bounded retries, duplicate delivery and heartbeat alerts |
| Authorization | Named actor permissions, revocation, selected-store scope and nested cross-store object denial |
| Stock history | Balance rebuilds, atomic posting, transfers, reversals, idempotency and concurrent conflicts |
| Partial inventory | Full/tare weights, decimal conversion, invalid measurements, versioned profiles and the 7,000 g worked example |
| Camera counts | Duplicate/overlapping pictures, unknown items, hidden stock, incomplete coverage and reviewed proposals |
| Media | Invalid/oversized images, private retrieval, metadata handling, deletion and interrupted upload |
| Sales/forecasting | Import replay, refunds, recipe/yield mappings, stale inputs, unit consistency and no double usage deduction |
| Stretch receiving | Barcode pack mappings, legitimate repeat scans, duplicate network events, discrepancies and partial receipts |
| Mobile app | Real iPhone/Android capture, installation, permission denial, saved drafts, reconnect conflicts and shared-device logout |

Add persistent browser tests to CI during the foundation phase. Separate
deterministic provider mocks from controlled real-photo/forecast evaluations;
record pilot ground truth, quality thresholds, correction effort, latency and
cost before enabling automation broadly. Routine test runs must not incur AI
charges or access production images.

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
results are recorded in the integration handoff. This local check does not
complete the broader Round 3 parity, CI or production gates by itself.
