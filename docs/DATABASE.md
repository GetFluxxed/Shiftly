# Database baseline

Baseline: `e01e84e`. The inventory additions at the end are planned; only the
existing schema and migrations listed below are currently implemented.

## Current schema overview

The app uses PostgreSQL and runs SQL migrations in order. The new runtime uses
`python -m backend.shiftly.runtime.migrate` as a coordinated release command;
FastAPI and the standalone worker require the schema to be ready at startup.
The legacy entry point retains its compatibility migration wrapper.

### Core tables
- reports
- briefing_jobs
- briefings
- stores
- manager_users
- store_memberships
- manager_sessions
- crew_sessions
- store_heads_up
- weekly_overview_cache
- schema_migrations
- briefing_job_recovery
- runtime_worker_status

### Key relationships
- reports belong to a store
- briefing_jobs reference a report
- briefings reference a report
- manager_users are linked to stores through store_memberships
- sessions are associated with a store or manager user depending on role

### Notable constraints
- reports are keyed by UUID
- report_hash is unique per store and employee+shift+notes combination
- briefing_jobs are unique per report
- store access codes are hashed and unique
- session expiry is enforced with NOW() checks

## Existing migrations

The migration sequence currently includes:
- 001_initial_schema.sql
- 002_manager_sessions.sql
- 003_remove_image_submission.sql
- 004_multi_tenant_access.sql
- 005_crew_sessions.sql
- 006_manager_credentials.sql
- 007_allow_username_managers.sql
- 008_store_heads_up.sql
- 009_manager_last_sign_in.sql
- 010_store_scoped_report_hash.sql
- 011_weekly_overview_cache.sql
- 012_briefing_job_recovery.sql
- 013_runtime_operations.sql

Migration 010 replaces the original global report-hash uniqueness constraint
with uniqueness on `(store_id, report_hash)`. Identical reports at different
stores are allowed; duplicates within the same store are rejected atomically,
including simultaneous submissions. Legacy reports with no store retain their
own unique-hash index. Existing report hashes, IDs, jobs and briefings are
preserved.

Migration 011 adds one cached weekly overview per store without changing
historical reports. Cache fingerprints include the complete reports supplied to
the model, the total seven-day report count, model, prompt and input limits.
Invalid provider responses are never cached, and invalid existing cache entries
are regenerated.

Weekly overviews include the newest complete reports that fit both limits:
50 reports and 20,000 input characters. The response distinguishes the total
`reportCount` from `includedReportCount` and sets `truncated` when reports are
omitted. The manager page explicitly labels partial coverage. No report is
cut off mid-entry.

## Data governance note

The current design stores the original employee notes and saves the AI-generated briefing separately. This helps preserve the source report while allowing the generated summary to evolve separately.

## Future migration guidance

Additive schema changes only. Preserve historical records, avoid rewriting applied migrations, and validate backfills before cutover.

## Planned inventory schema boundaries

The detailed model and invariants are in [INVENTORY.md](INVENTORY.md). Add these
groups incrementally in their implementation phases, not as one speculative
migration:

- Store items, decimal base units, versioned pack/weight/tare conversions, and
  internal SKU versus supplier/barcode mappings.
- Store-owned shelf/location hierarchy, assignments, par history and optional
  shelf targets.
- Append-only stock movement events and transactionally maintained balance
  projections, with linked reversals and paired transfers.
- Count sessions, coverage, baseline versions, camera/manual observations,
  open-container measurements and approval records.
- Private media metadata, durable analysis jobs and versioned provider results.
- Deduplicated sales batches, line-item/recipe mappings and forecast snapshots.
- Invoice/receipt lines, scan events, discrepancies and unique posting references.

Enforce store ownership across relationships, unit compatibility and replay
uniqueness. Posting a count or receipt must not partially update its movement
history and current balance. Historical records preserve the conversion and
configuration versions that produced them; archive referenced catalog entries.

Separate observed physical stock, book balances and sales projections. A photo
is not a receipt, and a forecast is not a confirmed stock movement. Repeated
uploads, approval retries and invoice imports must not duplicate quantities.

Retain migrations 001–011 unchanged. Coordinate new migration numbers across
worktrees. During FastAPI deployment work, introduce a serialized migration
entry point and test upgrade, repeat startup, compatible rollback and forward
recovery against disposable PostgreSQL and staging copies.
