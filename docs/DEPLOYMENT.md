# Operating and deploying Shiftly

Reviewed against source revision `df53f98` on 2026-10-21. Current source and
feature support are in [README](../README.md). This runbook covers operation
without private assistant state. Derek confirmed ownership of GitHub,
Render/PostgreSQL, Expo and the AI-provider accounts on 2026-10-11. No separate
hosted staging environment is confirmed. Repository configuration and local
recovery evidence do not establish what is currently deployed in Render.

## Hosted environment observations

Dated observations, not verified facts. Re-check before relying on them.

| Date | Observation | Source |
| --- | --- | --- |
| 2026-10-21 | Hosted service runs the **legacy browser runtime** (`python server.py`) on a **free** Render web service | Owner-reported for this review; consistent with `render.yaml` |
| 2026-10-21 | Hosted database is a **paid PostgreSQL 18** instance | Owner-reported; `render.yaml` still declares `plan: free` with no version |
| 2026-10-21 | The deployed Git revision is not recorded | No deployment record in the repository |
| 2026-10-21 | No hosted environment serves `/api/mobile`; no staging environment exists | `render.yaml`; owner confirmation of no staging on 2026-10-11 |

Local development, CI and the rehearsals use PostgreSQL 16 (`docker-compose.yml`,
`deploy/compose.integration.yml`, `.github/workflows/ci.yml`).

## Configuration drift and compatibility checks

Resolve or explicitly accept each item before a hosted pilot (roadmap item 3 in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md#roadmap)):

- **Database version.** The hosted database (owner-reported PostgreSQL 18) differs
  from the PostgreSQL 16 used by CI and rehearsals. Before relying on it:
  - run the migrations and the release/account rehearsals against PostgreSQL 18,
    or pin the hosted version;
  - use `pg_dump`/`pg_restore` clients at least as new as the server.
- **Database plan.** `render.yaml` declares `plan: free` for `shiftly-db`, while the
  hosted database is reported as paid. Align the manifest with the actual resource
  before applying it, so a sync cannot change the database.
- **Runtime.** The manifest starts `python server.py` without `SHIFTLY_WORKER_MODE`,
  so it runs in the legacy **embedded** mode:
  - it applies migrations at web startup;
  - it runs only the briefing worker in-process.

  Forecast jobs queued by browser production confirmation are therefore not
  processed, and the native API is unavailable. Moving to the supported topology
  (FastAPI + separate worker + explicit migration) is a reviewed cutover, not a
  manifest edit.
- **Web plan.** The free web service tier's sleep/resource limits have not been
  evaluated for staff use. Confirm its current limits before a pilot.
- **Retired setting.** `ADMIN_SIGNUP_KEY` remains in the manifest but no longer
  enables signup. Remove it in a reviewed configuration change.

## Supported processes and reproducible installation

Use Python 3.12.15 and install `requirements.lock` for production;
`requirements-dev.lock` includes the same runtime pins plus verification tools.
The [lock verification and refresh procedure](TESTING.md#dependency-locks) applies
to both. Render's checked-in build command installs the production lock, but its
entry point remains the browser server (`python server.py`). This is not a mobile
API deployment. Changing dependency configuration does not switch the runtime.

The modern runtime uses one FastAPI process and one separately supervised worker.
The worker handles report briefings and production forecasts. Export configuration
into **each** process through the operator's shell or hosting secret manager.
The migration and worker commands deliberately do not load `.env`; do not depend
on the API's compatibility `.env` loader to configure other processes.

```sh
python -m pip install -r requirements.lock
python -m pip check
python -m backend.shiftly.runtime.migrate
```

After migration, start these in separate terminals/supervisors with the same
intended database and provider configuration:

```sh
SHIFTLY_WORKER_MODE=external WEB_CONCURRENCY=1 python -m uvicorn \
  backend.shiftly.app:create_app --factory --host 127.0.0.1 --port 4174 --workers 1
```

```sh
SHIFTLY_WORKER_MODE=external WEB_CONCURRENCY=1 python -m backend.shiftly.jobs.worker
```

Use the host/port assigned by the deployment platform behind HTTPS. Local phone
access needs the API bound to the local network and the Expo API origin set for
that network; see [mobile setup](../apps/mobile/README.md). Development stays on
the LAN. Do not use a private `/tmp` launcher as a maintenance prerequisite.

| Configuration | Purpose and owner action |
| --- | --- |
| `DATABASE_URL` | Explicit target database for API, worker and migration. Keep in the operator/hosting secret store. |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Backend-only provider credential/model. An empty key disables forecast availability and report AI cannot complete. Changing a model requires separate evaluation. |
| `SHIFTLY_WORKER_MODE=external`, `WEB_CONCURRENCY=1` | Required modern topology. Multi-process API scaling needs a shared admission-limit design first. |
| `SECURE_COOKIES=true` | HTTPS browser sessions; use false only for local HTTP. Native uses opaque bearer sessions. |
| `DB_POOL_*`, `DB_*_TIMEOUT*`, `SHUTDOWN_TIMEOUT`, `WORKER_STALE_SECONDS` | Bounded resources and failure handling; defaults and validation live in `config.py` and runtime settings. Tune from measurements. |
| `ADMIN_SIGNUP_KEY` | Historical operator configuration; it does not reopen public signup or create owners in the current release. |
| `EXPO_PUBLIC_API_URL` | Public API origin only, in ignored mobile `.env.local`; never put database/provider credentials here. |

Resource defaults (validated by the runtime settings; invalid, non-finite or
non-positive values fail before any database activity):

| Setting | Default | Meaning |
| --- | --- | --- |
| `WEB_CONCURRENCY` | 1 | Any other value is rejected by the modern composition |
| `DB_POOL_MAX_SIZE` | 4 | Pooled connections per resource-owning process |
| `DB_POOL_TIMEOUT` | 3 s | Pool checkout and dedicated-capacity wait |
| `DB_CONNECT_TIMEOUT` | 5 s | libpq connection timeout |
| `DB_STATEMENT_TIMEOUT_MS` | 10000 | Server-side statement timeout |
| `DB_LOCK_TIMEOUT_MS` | 2000 | Query and migration lock wait |
| `DB_IDLE_TRANSACTION_TIMEOUT_MS` | 30000 | Idle-transaction timeout |
| `SHUTDOWN_TIMEOUT` | 5 s | Worker join deadline and pool-close wait |
| `WORKER_STALE_SECONDS` | 60 | Maximum age of worker activity before health degrades |
| `SHIFTLY_WORKER_MODE` | `embedded` | Legacy server only; use `external` alongside the separate worker |

At defaults, budget up to six connections for the API, five for the worker and a
temporary migration connection.

**Worker rules**

- The separate worker holds a database session lock, so a second worker fails to
  start. If that connection is lost, the worker exits for supervisor restart.
- On SIGINT/SIGTERM it stops polling and waits a bounded time. A provider call still
  blocked after that exits nonzero and leaves its claim for lease recovery. Set the
  supervisor's termination grace accordingly.
- Never run the legacy embedded worker and the separate worker against the same
  queue. To run the legacy browser server beside the separate worker, start it with
  `SHIFTLY_WORKER_MODE=external python server.py`. That mode checks the schema
  instead of migrating and reads the shared worker health.

**Health**

- `/api/health` reports database readiness (200/503).
- `/api/health/worker` returns 200 only for a recently polling or processing
  worker. It reports state, ages, completed-job count, consecutive errors, queue
  depth and oldest queued age.
- Only the worker writes these observations. Stale, stopped or missing workers
  degrade the status rather than appearing healthy.

## Accounts and operator procedures

A fresh developer can create an empty local demo using the guarded
[demo setup procedure](../apps/mobile/README.md#create-a-fresh-local-demo).
That command is not a production enrollment tool. Existing workspaces use a
single-use invitation from an authorized issuer; elevated roles are assigned after
activation.

For explicit ownership mapping or account recovery, use
`python -m backend.shiftly.runtime.accounts_admin --help`. The commands use the
explicitly exported `DATABASE_URL` and do not load `.env`:

```sh
python -m backend.shiftly.runtime.accounts_admin bootstrap --manifest mapping.json
python -m backend.shiftly.runtime.accounts_admin bootstrap --manifest mapping.json --apply
python -m backend.shiftly.runtime.accounts_admin recovery --user-id 42 --reason 'Verified operator recovery'
python -m backend.shiftly.runtime.accounts_admin recovery --user-id 42 --reason 'Verified operator recovery' --apply --reveal-token
```

**Running the commands**

- Both default to a dry run.
- Applying recovery prints a one-time reset secret for supervised delivery. Keep it
  out of shared logs.
- The mapping manifest uses independently verified IDs, never guesses. Synthetic
  example:

```json
{"reason":"Synthetic rehearsal only","businesses":[{"id":700,"name":"Example business","owner_user_ids":[42]}],"stores":[{"store_id":12,"business_id":700,"accounts_enabled":false}]}
```

**What bootstrap requires and refuses**

- Owners must already be active, verified accounts.
- Bootstrap rejects conflicting business identity or ownership, reassignment,
  inactive stores, and disabling an already enabled store. It updates dependent
  membership and invitation scope in one transaction.
- Set `accounts_enabled: true` only for reviewed enrollment.
- Shared-crew cutover is a separate owner operation, done after individuals enroll.
- The command neither creates the first production identity nor guesses ownership.
  An initial production identity remains an explicitly reviewed operator procedure.

**Before applying to real data**

- Take and test a backup, rehearse with representative data and review the dry run.
- Never re-enable shared credentials, run a pre-account adapter against an enabled
  store, or remove account/audit data with a down migration.

Catalog editors maintain company products/packages in the catalog; authorized
staff assign store shelves. Recipe editors save versioned recipes. Counters save
and submit observations; approvers post counts. Production staff review and
confirm batches before the exact recipe amount plus 1% is deducted. Managers
publish Heads Up and administer only permitted team access. Stored edits are
published by their existing Save/Submit/Confirm actions, not a code deployment.
The [security contract](SECURITY.md) describes scope and the
[database guide](DATABASE.md) locates authoritative records and history.

## Service ownership and exit register

Derek is the accountable owner for the services below. No secondary operator is
confirmed. Store credentials and recovery codes in an owner-controlled password
manager, not this document. Before release, confirm account access, billing alerts,
recovery methods and a designated backup operator. Dollar budgets and retention
commitments require Derek's decision; none are assumed from a free-plan manifest.

| Dependency/service | Concrete purpose and data | Failure handling / replacement route |
| --- | --- | --- |
| GitHub | Git source, reviews, CI configuration and test evidence. Owner: Derek. | Keep an authorized local clone and mirror all branches/tags; source is ordinary Git. Preserve needed issues/release evidence separately. Reproduce CI with documented local commands. |
| Render | Hosts the checked-in browser deployment and managed PostgreSQL binding. Owner: Derek. Live service settings need inspection before changes. | Run the same Python commands on another supervised host; transfer configuration through the secret manager. Restore PostgreSQL separately; validate HTTPS, worker supervision and access before directing traffic. |
| PostgreSQL / psycopg | Authoritative accounts, catalog, recipes, counts, movements, reports, jobs and audit. Owner/data access custodian: Derek. | Standard SQL migrations and `pg_dump`/`pg_restore`; restore rehearsal below. No ORM or proprietary data format is required. Preserve history, IDs and sequence state. |
| OpenAI API | Report quality checks, briefings, weekly summaries and advisory production forecasts. Owner: Derek. | Stored records remain in PostgreSQL. Briefing jobs retry with limits; forecast failures remain visible. Report submission quality gating still depends on the provider. Replacement is through runtime/forecast provider adapters with schema and behavior evaluation; changing credentials alone is not a model migration plan. |
| Expo / React Native | Native development, camera/barcode and device integration. Expo account owner: Derek. Signed distribution is a separate gate. | App source, package manifest and frozen lockfile are local. Preserve signing/account access under Derek's control. A future build-service change requires native build/device verification; Expo Go is development delivery, not the release artifact. |
| FastAPI / Uvicorn / Python | API adapters and one-process runtime. Maintenance: project maintainer under Derek. | Source-controlled service boundaries and standard ASGI; keep runtime pins and migration compatibility when replacing infrastructure. |
| pnpm / Node / Playwright / pytest | Reproducible mobile tooling and automated checks. Maintenance: project maintainer under Derek. | Lockfiles, scripts and CI specify requirements. These tools do not own production data; retain failure evidence as access-controlled artifacts. |

Before a material dependency addition/update, record purpose, maintainer/maintenance
status, license compatibility, security exposure, operational cost and exit effort
in the change's pull request and, for a new service, in the register above.
Existing dependencies are retained; adoption is not a claim that every transitive
license or current advisory has been independently audited. That review is an
[accepted deviation](IMPLEMENTATION_PLAN.md#accepted-legacy-deviations).

## Backup, export and restore

PostgreSQL backup is the lossless export for existing app data. There is no
user-facing CSV exporter or image store. No shelf photos or invoices are stored,
because those workflows are not implemented. Protect database archives as
private data: they include employee records, credentials and tokens. Keep them
outside Git and restrict/encrypt their storage through the operator's approved
backup system.

**Before any live release:** Derek must confirm automated backup frequency,
retention, destination, access, acceptable data-loss window and recovery time.
Record a real restore date/result and alert owner. These settings are currently
unverified; local rehearsals do not provision or monitor hosted backups. Take a
separate pre-release archive even when automated backups exist.

Use `pg_dump`/`pg_restore` clients whose major version is at least the server's
(PostgreSQL 16 locally; the hosted database is reported as 18). Configure
`shiftly_source` and `shiftly_restore` as private libpq services in an operator-owned
service file, with credentials supplied through a protected password file/secret
manager. The restore service must identify a **new, empty, separate** database.
Service names below deliberately avoid placing passwords in command arguments.

```sh
psql 'service=shiftly_source' -c 'SELECT current_database(), inet_server_addr();'
psql 'service=shiftly_restore' -c 'SELECT current_database(), inet_server_addr();'
umask 077
backup_path="${TMPDIR:-/tmp}/shiftly-pre-release-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner --no-privileges \
  --dbname='service=shiftly_source' --file="$backup_path"
pg_restore --list "$backup_path" > "$backup_path.contents"
pg_restore --exit-on-error --single-transaction --no-owner --no-privileges \
  --dbname='service=shiftly_restore' "$backup_path"
```

Listing an archive only verifies readability; **restoring and checking it** proves
more. Compare migration versions, durable row counts, relationships, sequences,
stock totals, recipe revisions and audit records. Start the candidate API/worker
against the restored database with isolated configuration; confirm named login,
store scope, reporting, count history and worker recovery. Do not connect a test
worker or provider to the live queue. Transfer the archive to the approved private
backup destination; temporary files are not the retention strategy.

The automated [release and account rehearsals](TESTING.md#release-rehearsal-backup-prerequisites)
perform restore comparisons on synthetic disposable data. They are not commands
to run against the live source/restore services above.

## Hosted staging and release gate

No staging service is currently confirmed by the owner. Create separately named
resources, database, provider limits and credentials only after Derek approves
hosting cost and access. Record the exact candidate commit and installed runtime
versions. Use synthetic data, or a separately authorized sanitized dataset.

1. Install the production lock in staging and run `pip check`; validate schema
   compatibility and take a tested pre-upgrade backup.
2. Stop staging writes/workers for the rehearsal; run the coordinated migration
   once, then start the one API process and separate worker. Do not edit applied
   migrations or run a worker from each API instance.
3. Check `/api/health`, `/api/health/worker`, process restart supervision and named
   login. Exercise store isolation, barcode lookup, a reviewed count, production
   confirmation and advisory forecast errors using staging-only records.
4. Rehearse worker termination/recovery, provider failure and restoration into a
   fresh database. Record IDs and outcomes, not tokens or employee notes.
5. Test rollback to the last **compatible** application revision while retaining
   the forward schema. A pre-account application that restores shared login is
   not an acceptable rollback. Inventory history and revocations must remain.
6. Derek reviews the evidence, backup/restore target and expected interruption,
   then authorizes production promotion. Apply the same verified configuration
   and repeat post-release checks. Keep the previous compatible artifact available.

If rollback cannot read the forward schema, stop writes and use a reviewed forward
fix or restore plan. Restoring an old archive can discard newer writes; reconcile
that explicitly before switching databases. No destructive down-migration is part
of the default rollback procedure.

## Diagnosing ordinary failures

| Symptom | Check / corrective action |
| --- | --- |
| API will not start / schema not ready | Confirm the intended exported database and migration versions. Run coordinated migration only against the approved target; inspect sanitized startup errors. |
| API healthy, worker unhealthy | Check the separate worker process, matching database, singleton lock, schema and restart supervisor. API database health alone does not prove job progress. |
| Briefings/forecasts delayed | Inspect worker/queue status and sanitized error codes, key/model configuration, provider availability and bounded retries. Do not manually mark jobs completed or copy results across stores. |
| Mobile cannot connect | Verify Expo packager and API origin on the current LAN, API binding and firewall/network reachability. Native routes require FastAPI. |
| Activation fails | Confirm the invitation and browser/mobile point to the same database/environment, then check expiry/use/revocation. Create a new invitation in that environment when appropriate. |
| Count or edit conflict | Reload the authoritative version and review the draft. Never blindly replay an uncertain write or overwrite another user's work. |
| Permission/store changes | Reauthenticate/revalidate scope; do not fix access by editing client controls or bypassing server authorization. |

Keep logs free of raw credentials, provider headers, invitation links, unnecessary
notes and images. Report IDs, job IDs and stable error codes support diagnosis.
