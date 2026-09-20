# Deployment baseline

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
