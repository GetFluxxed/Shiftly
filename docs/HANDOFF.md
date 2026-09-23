# Shiftly handoff

Updated: 2026-09-22.

**Current client direction:** The user selected a React Native phone/tablet app.
Follow [NATIVE_APP_ROADMAP.md](NATIVE_APP_ROADMAP.md) and
[the mobile development guide](../apps/mobile/README.md). The native foundation
starts from published Accounts & Access integration `7ecb61d` (PR #10 over PR #9).
Earlier mobile-web-first statements below are historical and superseded. The
existing browser app remains available; native device/distribution readiness and
hosted production cutover require separate evidence.

## Current implementation and readiness

Main at `e01e84e` includes merged PRs #1–#7: worker recovery, contract/browser
coverage, report/identity/store services, FastAPI routes, bounded resources,
coordinated migrations and a standalone worker. Its hosted CI passed.

The focused verification follow-up adds the complete contract matrix and recovery
rehearsal, and fixes the request/routing regressions those checks found. Read
[focused verification evidence](workstreams/focused-verification.md) for tested
commits, counts, commands and gate status.

- Gate D technical checks: verified in the focused-verification branch.
- Gate D closeout: review and merge that branch with green CI.
- Gate P: open. Hosted staging, process supervision, backup policy, required
  merge-check administration and approved production cutover remain separate.
- `render.yaml` still uses the legacy server. No production deployment occurred.

After the follow-up merges, start A1/A2 from current main: Operations/Inventory
navigation and explicit inventory actors/permissions. Then implement I1 catalog,
units, packs and weight profiles. Manual inventory precedes camera counting.
Preserve the old uncommitted reports worktree; do not use it as the new baseline.

The remaining sections record the historical planning baseline, not current status.

## Baseline

- Application: Shiftly; repository folder: Shift-Observer.
- Assessed implementation: `main` at `53fdd36`.
- Recent security/cache fixes are committed. Last verified suite: 78 passing
  tests; CI succeeded for that commit.
- Current runtime: modular Python files, the existing HTTP server, PostgreSQL,
  HTML/CSS/JS client, and an in-process briefing worker.
- FastAPI, inventory, camera analysis, partial-weight tracking, sales forecasting,
  receiving, and an installable app shell are planned, not implemented.

## Current direction

The user confirmed **installable mobile web first, native later**. Add a
separate Inventory workspace reachable from the manager window. Its core scope
includes shelves, pars, running stock, camera-assisted counts, explicitly
calibrated partial weights, and shortage insights. Barcode/SKU invoice receiving
is the stretch goal.

Read in this order:

1. [Implementation plan](IMPLEMENTATION_PLAN.md)
2. [Inventory specification](INVENTORY.md)
3. [Architecture](ARCHITECTURE.md)
4. [Work packages](TASKS.md)
5. [API contracts](API.md), [database](DATABASE.md), [security](SECURITY.md),
   [testing](TESTING.md), and [deployment](DEPLOYMENT.md)

## Preserved parallel work

The `codex/reports-module` worktree is based on `b289865` and has uncommitted
changes. Preserve it. Compare and selectively port useful work onto current
main through the F0 package; its structure is not automatically the target.

## Immediate task and known gaps

Begin F0: current-contract capture and worker recovery. A reviewed failure path
allows the worker to exit if recording a job failure also fails. Current health
checks do not establish worker progress. Then introduce FastAPI through F1.

The first paired assignments and integration protocol are in
[Round 1](parallel/ROUND_01.md), with reusable prompts for
[Codex](prompts/CODEX_FOUNDATION.md) and
[GitHub Copilot](prompts/COPILOT_FOUNDATION.md). They are prepared instructions;
neither implementation has been launched by this planning update.

Staging/restore evidence, durable independent workers, browser CI, shared limits
for multiple API processes, and inventory-specific authorization remain work
items. The plan revision changed documentation only; it did not implement these
features or alter production configuration.
