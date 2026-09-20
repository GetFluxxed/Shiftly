# Round 1: Codex and GitHub Copilot coordination

Status: assignments prepared; implementation has not started.
Plan: [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md).

## Goal and boundary

Complete the worker-recovery and contract-capture portions of F0 and introduce
the browser/CI coverage portion of F3. This round does not complete every F0/F3
or Phase 0 requirement. FastAPI implementation begins only after the two results
are integrated and the foundation's remaining gates are reviewed.

The product direction remains installable mobile web first, native later;
Inventory is a separate manager workspace. Core inventory includes partial
weights; barcode/SKU invoice receiving remains the stretch goal.

## Common starting point

Both assignments start from the same planning commit, not the old
`codex/reports-module` worktree. After fetching origin, resolve and record:

```sh
git log -1 --format=%H origin/main -- docs/parallel/ROUND_01.md
```

This round's coordinator keeps this file unchanged until both assignments finish,
so it identifies the same base even after the first feature branch merges.
Create a separate branch and checkout/worktree for each agent at that commit.
If the proposed branch/worktree already exists, inspect it and preserve its work;
do not reset, delete, force-checkout or recreate it over existing changes.

For a cloud Copilot checkout, its isolated task checkout satisfies the worktree
requirement. If the platform chooses a branch name, record that distinct branch
in the handoff; otherwise use the names below.

## Exclusive ownership for this round

| Owner | Branch | Editable paths |
| --- | --- | --- |
| Codex | `codex/f0-worker-recovery` | `reporting.py`; worker startup/status integration in `server.py`; `tests/test_worker_recovery.py`; optional `migrations/012_briefing_job_recovery.sql`; `docs/workstreams/codex-foundation.md` |
| GitHub Copilot | `codex/f0-contract-browser-tests` | New files under `tests/contracts/` and `tests/browser/`; `.github/workflows/`; `requirements.txt`; new `requirements-dev.txt`, `requirements.lock`, `requirements-dev.lock`; new `scripts/run_browser_tests.py`; `docs/workstreams/copilot-foundation.md` |
| Coordinator, after integration | No concurrent implementation branch | Shared plan/backlog/handoff documents; existing test fixtures and other existing tests; any scope changes |

Everything not explicitly assigned is read-only. In particular, neither agent
edits `tests/conftest.py`, existing regression test files, current UI assets,
`routes.py`, `auth.py`, `security.py`, `database.py`, `config.py`, `render.yaml`, or
the other agent's files. Neither begins `backend/`, FastAPI, inventory tables,
camera functionality, the app shell, or sales/receiving implementations this round.

Codex is the only migration writer this round. Use 012 only if durable recovery
needs it; first verify that the number is still free. If it is already occupied,
report the collision rather than editing or renaming somebody else's migration.
Do not rewrite migrations 001–011. No new runtime dependency is needed for the
Codex lane; request an ownership change if evidence shows otherwise.

## Contracts between the lanes

- Preserve current endpoint paths, authentication, cookies, security headers,
  response statuses and stable response fields. Worker monitoring may be
  additive; the existing `/api/health` contract must remain compatible.
- Preserve the callable report/job APIs used by existing tests. Worker timing
  and recovery internals may change; Copilot's HTTP/browser tests must assert
  externally visible behavior rather than internal polling cadence.
- Copilot must not weaken assertions to conceal a backend defect. Record a
  minimal reproduction in its handoff and request a scoped fix from the owner.
- Shared fixtures are read-only. Lane-specific fixtures belong under each
  owner's new tests; use the existing disposable database mechanism.
- Use distinct disposable databases/containers and random local HTTP ports.
  Never run tests against the application's `.env` database or production data.
  Stub external AI and other paid/network services at test boundaries.
- Check changed-file ownership before every commit and before opening a PR.
  Unrelated local edits stay untouched and out of the commit.

## Escalation and integration

If a required change falls outside the allowlist, record the exact path, reason,
and proposed contract in the owning workstream handoff and report it. Continue
independent in-scope work. The coordinator resolves ownership before either
agent edits the shared file; agents do not silently expand their assignments.

Each agent commits only its work, pushes only its feature branch, and opens a
draft PR if available. If PR tooling is unavailable, provide the pushed branch
and compare URL. Neither merges, pushes to main, deploys, rewrites shared
history, or sends work to the other agent.

Suggested integration order:

1. Review Codex's worker changes against the baseline and existing tests.
2. The coordinator merges Codex only after its checks pass.
3. Copilot merges updated `origin/main` into its own branch without force-pushing,
   preserves both sets of changes, and runs the combined suite plus browser CI.
   A conflict in an unowned file goes to the coordinator instead of being guessed.
4. Review and merge Copilot after combined checks pass.
5. Update shared documentation and remaining F0/F3 status together. Allocate a
   new round for F1 rather than letting either agent drift into FastAPI work.

Agents may prepare independent draft PRs simultaneously. Integration and changes
to shared interfaces remain sequential. These ownership boundaries prevent
overlapping edits; the combined checks address behavioral interactions.

## Prompts

- [Codex worker-recovery prompt](../prompts/CODEX_FOUNDATION.md)
- [GitHub Copilot contract/browser prompt](../prompts/COPILOT_FOUNDATION.md)
