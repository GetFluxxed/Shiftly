# Engineering standards adoption — 2026-10-11

> **Archived record.** Dated decisions and evidence as of its own revision; not current
> guidance. See the [archive index](README.md) and the maintained documents it links.

## Accepted scope and baseline

Derek requested adoption of the supplied engineering guide and all three work
packages: current documentation, reproducible/independent operation, and targeted
legacy cleanup. [ENGINEERING.md](../../ENGINEERING.md) preserves the supplied
version 0.1 policy; its status line records adoption and Markdown spacing is
normalized without changing the policy text. [AGENTS.md](../../AGENTS.md)
retains project-specific rules and explicitly reserves consequential decisions for
the human owner. Both coding assistants are directed to those files.

The starting checkout was `604683d` on `codex/inventory-package-options`, with a
clean working tree. [PR #20](https://github.com/GetFluxxed/Shiftly/pull/20) previously
passed [CI](https://github.com/GetFluxxed/Shiftly/actions/runs/37155120186) for that
revision. This is historical evidence, not a CI result for these new edits.
No live database, inventory, recipe, account, hosted configuration or public
release is changed by this adoption pass.

## Work package 1 — Current baseline and documentation

The README is the entry point for current supported behavior and repository
locations. Architecture, database, security, implementation plan, mobile setup,
deployment and testing documents describe the same source state: migrations
001–024, native inventory/packages/counts, versioned recipes/production, store
forecasts and barcode scanning. Shared logins and public signup are retired.
Photo counting and invoice receiving remain planned.

Historical workstream documents retain dated evidence, rather than being rewritten
to claim those features existed earlier. Current documents link to the applicable
contracts. Catalog/package metadata does not create stock; counts and production
retain their current transaction and history rules.

Acceptance: a maintainer can locate current capabilities, their owning modules,
data rules, commands and verification boundaries without this conversation.

## Work package 2 — Reproducibility and independent operation

- Production's complete runtime closure is pinned in `requirements.lock`.
  Development includes those same pins plus test tools. Render installs that
  production lock; Render and CI select Python 3.12.15. Existing pinned package
  versions were retained; previously implicit dependencies now have explicit pins.
- A metadata-based verifier rejects missing/incompatible runtime dependencies,
  duplicate pins, dropped extras, development packages in the runtime closure,
  and disagreement between installed versions and the lock. CI runs it with
  `pip check`; no additional dependency-management service is introduced.
- Derek confirmed ownership of GitHub, Render/PostgreSQL, Expo and the provider
  account. [Deployment operations](../DEPLOYMENT.md) records purpose, data,
  configuration, failure diagnosis, backup/restore, exit routes and release gates.
- The local demo initializer requires an explicit loopback `DEMO_DATABASE_URL`
  with a `shiftly_demo_` database name, port and user. It refuses existing
  businesses/stores/accounts under the account policy lock, uses a hidden
  interactive password prompt, and creates one synthetic owner/store atomically.
  It seeds no inventory, products or recipes. This command is not an HTTP route
  and does not change production enrollment.
- The initializer closes an observed first-boot gap: the existing operator mapping
  command expects existing identities, so migration alone did not give a new
  developer an interactive workspace. Production first-owner provisioning remains
  a separate explicit operator procedure; local demo setup is not a workaround.

Acceptance: fresh locked installs succeed; a new local maintainer can migrate,
initialize, start and authenticate; failure/repeat/concurrent initialization cannot
leave or overwrite a workspace; isolated recovery restores durable records.

## Work package 3 — Targeted legacy cleanup

The actual reporting provider transport now belongs to
`backend/shiftly/runtime/provider.py`. Durable briefing claim, fencing, completion,
failure and retry/loop behavior belong to `backend/shiftly/jobs/reporting.py`.
The modern worker imports that package directly. Root `reporting.py` remains the
compatibility facade for the browser adapter and older test seams; it no longer
owns the extracted implementation.

This fixes the direction of the dependency identified in the earlier bloat audit.
It does not introduce a queue framework, microservice, new provider, schema change,
stock rule or authorization change. The extracted code uses readable control flow.
Unrelated inventory/production formatting is not mixed into this behavior-preserving
move. Tests execute modern worker startup while forbidding root reporting imports,
and preserve root logger replacement, sanitized errors and terminal provider setup
failures. Existing lease/retry/recovery characterization remains in force.

Acceptance: modern runtime no longer reaches through the legacy reporting facade;
existing supported facade calls, result contracts, lease fencing, failures and
recovery still work.

## Seven-pillar assessment after the changes

| Pillar | Concrete evidence / remaining boundary |
| --- | --- |
| Necessary simplicity | Existing architecture retained; one targeted extraction and one constrained development setup command, no framework rewrite. |
| Controlled dependencies | Full runtime pins shared by deploy/CI, clean-install and closure checks; material service purposes and exit routes recorded. Existing license/advisory inventory is an outstanding review, not a claim of certification. |
| Human readability | Current entry documents, conventional extracted control flow and focused regression checks. Other compressed code is a touch-area cleanup target, not an automatic rewrite backlog. |
| Clear boundaries | Package-owned provider and jobs; legacy facade preserved. Existing inventory transaction/permission boundaries unchanged. |
| Independent operation | Reproducible startup, fresh demo, diagnostics and restore runbooks; no required private assistant launcher. Hosted access/recovery verification is separate. |
| Evidence | Focused regression checks, exact install checks and disposable recovery below. No physical-device, paid-provider or hosted test claim. |
| Ownership and exit | Confirmed accountable owner, standard Git/PostgreSQL artifacts, documented vendor replacement paths. Secondary operator and hosted backup commitments remain owner decisions. |

## Retained gaps and release gates

These are visible limitations, not declarations that all legacy code is compliant.
Derek owns their disposition; a maintainer performs the technical work. Routine
feature work follows the adopted standards immediately. Revisit these items at
release planning or when the relevant subsystem changes.

| Item | Impact | Disposition / closure evidence |
| --- | --- | --- |
| No confirmed hosted staging | Local success cannot establish platform supervision, network permissions or recovery. | Hosted release gate: authorize resources/cost, exercise the documented staging/rollback/restore flow, record actual evidence. No new service was provisioned. |
| Backup schedule, retention, recovery targets and secondary operator unconfirmed | Recovery expectations and account continuity are not yet an operating commitment. | Before live rollout, Derek assigns targets/access and verifies an actual hosted restore and alert route. Local archive rehearsals are supporting evidence only. |
| Initial production owner creation is still an explicit operator task | An empty production database cannot self-enroll an owner. | Keep public signup closed. Use a separately reviewed, verified operator procedure; the new local demo tool cannot target hosted databases. |
| Legacy browser adapter and its test globals remain | Compatibility code still has import-time settings and broader test fixtures. | Retain while browser compatibility is supported. Narrow fixtures or retire adapter only in scoped work with contract tests; new modules use package boundaries. |
| Schema-wide policy lock and broad legacy roster reads | Potential contention as staff/history grows; no current load outage measured. | Measure query/lock latency with representative store sizes before changing locks; preserve concurrent revocation checks. |
| Full existing dependency license/advisory review | Pinning alone does not prove security or distribution rights. | Review material dependencies before release and each consequential update; track findings, owner and remediation. No vulnerability-free claim. |
| Signed device builds, accessibility/device acceptance and real-model evaluation | Browser tests and exports do not prove device or forecast quality. | Apply existing native and camera readiness gates with actual devices and approved sample data/cost. |

## Verification record

Verified locally on 2026-10-11 after integration:

| Check | Result / scope |
| --- | --- |
| Fresh production and development installs | Passed in clean official Python 3.12.15 containers, including `pip check`; development also passed the lock verifier and its regression tests. Existing runtime pins were preserved. |
| Integrated backend regressions | **310 passed** in a fresh locked Python 3.14.7 environment against disposable PostgreSQL 16. Covered API foundation, contracts, identities, runtime/provider/worker behavior, reporting, duplicate reports, weekly summaries, dependency locks and release rehearsal tests. The new demo setup tests cover login, refusal, concurrent calls, rollback and hidden-password safeguards. |
| Real release recovery rehearsal | Passed fresh/upgrade/repeat/concurrent migration, API plus independent worker, terminated-worker lease recovery, database outage/reconnect, legacy rollback and actual archive restore. Compared **44 tables, 8 sequences and 90 foreign keys**; verified restored counts, stock movements, recipe revisions, production/reversals, measurements and report access. |
| Real account recovery rehearsal | Passed historical upgrade preservation, explicit ownership mapping, activation, resets/session revocation, store scope, suspension and replay denial after actual restore. Compared **44 tables, 8 sequences, 90 foreign keys, 102 checks, 19 triggers and 10 functions**. An initial invocation was safely refused because its disposable database name did not meet the runner's required pattern; the corrected explicit targets passed. |
| Documentation and code review | Current documents checked against implementation; relative links/anchors, policy-source preservation, Python compilation and whitespace checks reviewed before handoff. Provider/worker cleanup, dependency changes and demo safeguards received separate agent review plus lead integration review. |

With an explicit disposable `TEST_DATABASE_URL` and the locked development
environment, reproduce the integrated suite from the repository root:

```sh
python -m pytest -q tests/api_foundation tests/contracts tests/identity_services \
  tests/runtime_services tests/test_worker_recovery.py tests/report_services \
  tests/test_report_duplicates.py tests/test_weekly_overview.py \
  tests/test_dependency_locks.py tests/release_rehearsal
```

Use [TESTING.md](../TESTING.md) for setup and both two-database rehearsal commands. The rehearsals used newly created,
explicitly named Docker resources; account rehearsal databases were removed by
the runner, and the two rehearsal containers were removed after verification. No live
app or local demo database was used as a fixture.

The integration suites and recovery rehearsals ran on host Python 3.14.7; clean
installation and dependency closure were separately checked on the pinned release
Python 3.12.15. Full release-version CI remains required for the published revision.
No new CI run, commit, push, hosted deployment, physical-device check or paid model
request was performed. Native/browser UI suites were not rerun because this pass
did not change their implementation. Local results do not close the hosted release
gates above or establish forecast accuracy, accessibility or complete security.
