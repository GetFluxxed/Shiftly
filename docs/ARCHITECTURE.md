# Architecture baseline

## Current state

The repo currently implements a modularity gap rather than a modular app. The application is organized as a single Python server that handles:

- HTTP routes
- authentication and session validation
- PostgreSQL queries
- AI call orchestration
- background briefing job processing
- static file serving

This structure is easy to operate, but it couples transport, business logic, persistence, and worker behavior in one file.

## Observed boundaries

### Persistence
- PostgreSQL via psycopg
- Migrations under migrations/*.sql
- Database initialization happens at startup in initialize_database()

### HTTP layer
- ThreadingHTTPServer + ShiftlyHandler
- Routing is handled inside do_GET and do_POST

### AI/report processing
- validate_report() calls OpenAI for quality gate checks.
- call_openai() wraps the OpenAI Responses API.
- worker_loop() polls briefing_jobs and processes queued report briefings.

### Session model
- manager_sessions and crew_sessions store expiration metadata.
- Store membership is used to authorize manager access to store-scoped views.

## Target direction

The handoff brief describes a modular monolith path, with business logic extracted gradually around:

- configuration
- database access
- security/auth services
- reports and AI services
- worker entry point
- future mobile/API clients

## Recommended minimal extraction sequence

1. Configuration loading
2. Database access helpers
3. Session and access checks
4. Report validation and queue logic
5. Briefing worker entry point
6. Route adapters

This sequence preserves behavior and allows testing between each boundary.
