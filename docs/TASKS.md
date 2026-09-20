# Task backlog baseline

## Phase 1 status

- Baseline repo verification: complete
- Core docs: in progress
- Regression tests: complete for the initial flow
- CI: complete for the initial baseline

## Ordered backlog

### 1. Baseline and contract capture
- document current routes, auth assumptions, and database schema
- confirm startup requirements and deployment assumptions
- record repository risks and compatibility constraints

### 2. Regression protection
- add integration tests for auth, report flow, and queue processing
- keep AI calls mocked at the service boundary
- use disposable Postgres for all tests

### 3. CI guardrails
- run pytest on pull requests
- run Postgres-backed job validation in CI
- keep secrets out of the repo and away from test fixtures

### 4. Deployment and operations readiness
- prepare staging config and runbook
- document backup and restore steps
- record rollout and rollback checks separately

### 5. Small extraction work
- move configuration loading into a dedicated boundary
- preserve python server.py startup behavior
- keep route contracts unchanged while extracting logic

## Future work queue

- tenant-aware identity evolution
- modular backend separation
- inventory foundations
- queue/worker split
- mobile/client API work

## Ownership note

This backlog is intentionally scoped and should be reviewed in smaller PRs with explicit acceptance criteria and compatibility checks before larger architecture work begins.
