# Deployment baseline

## Verified runtime, pending hosted cutover — 2026-09-21

FastAPI and a separate worker are implemented and verified on disposable local
PostgreSQL. Run the migration command once before starting either process:

```sh
python -m backend.shiftly.runtime.migrate
python -m uvicorn backend.shiftly.app:create_app --factory --host 127.0.0.1 --port 4174 --workers 1
python -m backend.shiftly.jobs.worker
```

Run API and worker under separate supervisors, with `SHIFTLY_WORKER_MODE=external`
and `WEB_CONCURRENCY=1`. The migration command serializes concurrent attempts;
neither new process applies migrations during startup. Legacy rollback preserves
the forward-compatible schema and can also use external worker mode.

The focused rehearsal demonstrates an upgrade from migrations 001–012, a real
worker kill and lease recovery, database connection loss/reconnect, legacy reads
with existing sessions, and archive restoration with API login. It uses two fresh
disposable databases and temporarily disables connections to its source database.
Follow [TESTING.md](TESTING.md); never use application databases for this runner.

This is local recovery evidence. Actual hosted staging, supervision, backup policy,
required merge-check configuration and an approved production cutover are still
Gate P. The existing `render.yaml` remains unchanged.

## Current deployment configuration

The project ships with a Render config in [render.yaml](../render.yaml). It currently defines:
- one web service
- a managed Postgres database
- a Python runtime
- a DATABASE_URL environment binding
- startup command: python server.py
- health check path: /api/health

## Local startup checklist

1. Copy .env.example to .env and set actual secrets
2. Start Postgres locally via docker compose up -d postgres
3. Ensure DATABASE_URL matches the local database port (55432)
4. Install dependencies with python3 -m pip install -r requirements.txt
5. Start the app with python3 server.py
6. Verify /api/health responds successfully

## Staging and production guidance

The wider roadmap expects a separate staging configuration before any deployment-affecting production change. The current repo is not yet split into separate staging and production deployment manifests.

## Recovery and backup expectations

- Keep Postgres backups outside of source control
- Rehearse restore flow before production deployment
- Validate application startup after restoring a database snapshot
- Capture last-known-good migration version and deployment commit

## Migration 010 rollout

Startup applies migration 010 in a transaction before accepting requests. It
builds the store-scoped report-hash constraint and a legacy-report index, then
drops the old global constraint. Existing data is preserved. Adding these
constraints can lock the reports table while the indexes are built; allow for
this during rollout on a large database.

An application rollback can retain migration 010. Do not restore the old global
unique constraint after different stores have submitted identical reports:
those are valid records under the new schema. Recover through a tested backup
or a forward migration if a schema change is needed.

## Request limits and weekly cache

Migration 011 adds the weekly overview cache during normal startup. Generation
uses a nonblocking PostgreSQL session lock per store and at most two dedicated
connections per Python process. Connections use autocommit so no transaction
stays open during an AI request; closing the connection releases its lock.
Busy requests return HTTP 202, and the manager page retries up to ten times at
three-second intervals before asking the user to refresh.

Login reservations count in-flight checks together with recent failures, up to
ten per client address and normalized store code in fifteen minutes. Successful
logins release their reservation without adding a failure. This counter and the
weekly concurrency cap are process-local, matching the current single-process
startup. Multiple server processes or replicas would need a shared login budget
and a deployment-wide generation cap.

## Required deployment decisions before rollout

- confirm environment variables are supplied securely by the hosting platform
- verify AI key configuration and startup behavior in staging
- test the health endpoint and key user flows before production promotion
- keep the existing browser app working while introducing modular changes

## Remaining hosted runtime and inventory deployment

The new runtime is verified locally; hosted cutover and inventory deployment
remain future work. Production startup and `render.yaml` are unchanged.

- Run FastAPI behind an ASGI server with bounded database resources, and start
  durable workers separately. Coordinate migrations once before either begins
  processing traffic; do not launch a job worker in every API lifespan.
- Introduce separate staging resources, a tested restore procedure, contract
  and browser smoke tests, and a documented transport cutover/rollback.
- Provide private object storage and lifecycle rules for inventory evidence;
  define upload/processing limits and per-store AI budgets.
- Serve the installable mobile web app over HTTPS. Apply camera permissions to
  capture pages and test the asset-only service-worker cache/update policy.
- Use store feature flags for catalog, manual inventory, camera proposals,
  sales insights and stretch receiving. Enable each after its acceptance gate.
- Monitor error rates, pool usage, worker heartbeat, oldest queued job, media
  failures, provider usage, count conflicts and forecast input freshness.
- Log IDs and operational outcomes without secrets or unnecessary raw employee
  notes/images. Rehearse provider outage, worker restart and failed import paths.
- Keep current reports available during inventory rollout and use compatible
  migrations so a UI/API rollback preserves posted stock history and evidence.
## FastAPI integration rehearsal status

The FastAPI app remains development-only. Production continues to start
`server.py`; no deployment entry point or Render configuration is changed by
this integration branch. Run the local FastAPI adapter with:

```sh
python3 scripts/run_api_dev.py
```

The adapter now composes the shared identity/report/store services, including
Accounts & Access. Named identity, protected pages, account lifecycle and reporting
are verified through both transports. Independent workers, migration coordination
and disposable release/account recovery rehearsals are included in validation.
These local/CI results do not establish hosted staging or production readiness.

Account rollout requires additive migration 014 and an explicitly reviewed
store/business/owner mapping. The bootstrap command defaults to dry-run; this
integration does not assign real owners or activate production stores. Follow the
[backend rollout and rollback procedure](workstreams/codex-accounts-permissions.md#migration-operator-mapping-and-recovery).
Enable individual access only after staging verification and deliberate enrollment;
shared-crew cutover is a separate owner action. A rollback must retain revocations
and account policy, rather than returning to an older permissive adapter.
