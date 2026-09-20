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

GitHub Actions runs the suite with Python 3.12 and a disposable PostgreSQL 16
service, supplying `TEST_DATABASE_URL` explicitly.

## Safety rules

- Use disposable local data only.
- Never copy production secrets or data into tests.
- Do not mock the database layer for the integration baseline.
- Keep AI behavior deterministic via monkeypatching at the service boundary.
