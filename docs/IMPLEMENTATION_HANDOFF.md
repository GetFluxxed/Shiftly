# Implementation baseline and transition handoff

Updated: 2026-09-20. This file records the starting implementation.
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) defines the new delivery plan.

## Assessed checkout

The current main baseline is `53fdd36`. Its recent fixes include isolated
database tests, manager crew access, bounded weekly generation, cache validation,
explicit weekly coverage, and atomic login reservations. The last verified
suite passed 78 tests and the associated CI run succeeded.

The previous description of a single-file app with no tests or CI is obsolete.

## Existing boundaries

| File or area | Current responsibility |
| --- | --- |
| config.py | Environment/settings loading |
| database.py | PostgreSQL connection creation |
| auth.py | Manager session and store membership resolution |
| security.py | Request helpers, hashing and rate limits |
| store_service.py | Store lookup, crew access, managers and Head's Up reads |
| reporting.py | Reports, queue, AI provider, worker and weekly cache |
| routes.py | Authentication and write-route workflows; still coupled to server globals |
| server.py | HTTP dispatch, responses, static files, startup migrations and worker thread |
| migrations/ | Applied schema sequence 001–011 |
| tests/ | Isolated PostgreSQL and deterministic regression coverage |
| .github/workflows/ci.yml | Python/PostgreSQL test job |
| render.yaml | Current web/database deployment description |

## Preserve during migration

Keep original report notes, completed briefings, job history, accounts, hashed
sessions, memberships, Head's Up data and migration records. Existing browser
paths, cookies and API behavior require compatibility tests before FastAPI
becomes the production entry point.

The current startup is still `python server.py`. No new FastAPI, object storage,
sales provider or native-client dependency is implemented by the planning update.

## Known foundation work

- Remove route-to-server dependencies and separate domain services from HTTP.
- Reproduce and fix worker termination when failure recording also fails.
- Add independently supervised workers, bounded retries and progress monitoring.
- Add consistent input/error contracts, pagination and future API versioning.
- Establish staging and demonstrated backup/restore/cutover procedures.
- Extend CI with browser coverage, dependency reproducibility and checks.
- Replace process-local admission limits before adding multiple API replicas.
- Establish verified inventory actors, permissions and auditable stock posting.

## Development continuity

Preserve the older uncommitted `codex/reports-module` worktree based on
`b289865`. Review its useful service extractions individually against current
main. Do not restore its older baseline or discard its edits.

Use the ordered packages in [TASKS.md](TASKS.md). Inventory discovery can proceed
in parallel with foundation work; stock writes must wait for the authorization,
unit conversion, ledger and reconciliation rules in [INVENTORY.md](INVENTORY.md).

## Planning references

- [Product direction](PRODUCT.md)
- [FastAPI and client architecture](ARCHITECTURE.md)
- [Current and proposed API contracts](API.md)
- [Schema baseline and planned ownership](DATABASE.md)
- [Security and permissions](SECURITY.md)
- [Testing](TESTING.md)
- [Deployment](DEPLOYMENT.md)
