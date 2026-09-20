# Testing baseline

## Local validation

This repo is prepared for a lightweight integration baseline using a disposable local PostgreSQL instance.

1. Start Postgres locally with docker compose up -d postgres
2. Ensure the .env file points at localhost:55432
3. Run pytest -q

## CI coverage goal

The initial tests cover:
- manager signup and session creation
- crew authentication and report submission
- report queue processing and job completion

## Safety rules

- Use disposable local data only.
- Never copy production secrets or data into tests.
- Do not mock the database layer for the integration baseline.
- Keep AI behavior deterministic via monkeypatching at the service boundary.
