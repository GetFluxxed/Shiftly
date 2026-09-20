# Product baseline

## Product summary

Shiftly is a store-facing shift communication app for crew reports and manager review. Crew members submit shift updates; managers review report summaries, weekly overviews, and a current Head’s Up message.

## User flows

### Crew flow
- Sign in to a store using a shared crew code and password.
- Submit shift report with employee name, shift type, and notes.
- Report must pass a quality gate before it is accepted.
- Accepted reports are queued for AI briefing.
- Crew sees current store Head’s Up information.

### Manager flow
- Sign in to a manager account associated with a store membership.
- See reports from assigned stores.
- See briefing status and the corresponding saved summary.
- Trigger or review a weekly overview for the store.
- Publish and replace a store-level Head’s Up message.

## Current product scope

This checkout is intentionally limited to:
- crew reporting
- manager review
- AI-assisted briefing
- weekly overview
- store-level messaging

No inventory, mobile client, or camera counting module exists yet.

## Non-goals for the current phase

- No FastAPI cutover
- No full identity redesign
- No frontend replacement
- No inventory implementation
- No camera AI feature
- No production deployment migration in the same change set

## Phase 1 working constraints

- Preserve existing endpoint paths and response contracts.
- Keep the current browser flow working.
- Add tests before refactoring logic.
- Add documentation before architecture churn.
