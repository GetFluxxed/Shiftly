# Shiftly product direction

Reviewed against source revision `df53f98` on 2026-10-21. This document records
intended users, goals, platform commitments, success criteria and exclusions.
Delivery order and status live in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md);
per-platform screens live in [WORKFLOWS.md](WORKFLOWS.md).

## Purpose

Shiftly is a store-scoped operations system for a small multi-store food business.
It keeps shift handoffs, the ingredient catalog, physical stock, daily production
and advisory production planning in one authoritative PostgreSQL record. People
review and confirm every stock-changing action; AI output and client state never
change stock by themselves.

## Intended users

| Role | Primary needs |
| --- | --- |
| Business owner | Company catalog, recipes, every store, team and ownership administration, final review authority |
| Delegated administrator | Business administration explicitly delegated by an owner, limited to granted stores and capabilities |
| Store manager | One store: shift reports and briefings, Heads Up, counts and approval, recipes, production review, forecasts, permitted team invitations |
| Production staff | One store: record daily production against recipes and view inventory; no shift reports or store administration |
| Crew | One store: submit shift reports and read Heads Up; optional inventory viewing and count entry when granted |

All staff use individual, invitation-activated accounts. Role and capability
details are in [SECURITY.md](SECURITY.md#roles-and-capabilities).

## Current goals

1. Put a store's real catalog, package definitions, recipes and opening stock into
   Shiftly and keep them trustworthy through reviewed counts and confirmed
   production.
2. Make daily work fast on phones and tablets: shift reports, Heads Up, counts,
   production recording and their review.
3. Give managers and owners explainable, advisory production suggestions based on
   the store's own recorded data, clearly separated from confirmed stock.
4. Reduce manual counting and receiving effort later through reviewed shelf-photo
   proposals and invoice receiving, without weakening stock integrity.
5. Remain operable, recoverable and transferable by a human maintainer, following
   [ENGINEERING.md](../ENGINEERING.md).

## Platform commitments

- **Native app (primary).** React Native/Expo phone and tablet app in `apps/mobile`.
  New staff workflows, including all inventory work, are built natively. A separate
  React browser rewrite is not part of the current scope.
- **Browser (compatibility surface).** The existing HTML pages remain supported for
  sign-in, activation, crew reporting, the manager dashboard (including Weekly
  Overview), Accounts & Access, and production recording. Supported browser flows
  must keep working while they exist. Whether the browser gains further
  workflows, or loses existing ones after native parity, is an
  [open decision](IMPLEMENTATION_PLAN.md#open-owner-decisions). A feature existing
  on only one platform is not, by itself, a parity requirement.
- **Shared rules.** Both clients use the same server-side accounts, permissions,
  services and data. Neither client is an authority for access or stock.

## Product rules

- Distinguish physical observations, book stock and estimates. Unknown stock is
  not zero; an uncounted line is not an explicit zero.
- Human review precedes every stock change. Drafts, previews, scans, photos and
  forecasts never post stock.
- Open containers and sealed packages are never counted twice. A repeat count
  reconciles stock rather than adding the whole count again.
- Production deducts each ingredient at recipe quantity × confirmed batches ×
  1.01. The owner chose this fixed 1% allowance on 2026-09-29, replacing an earlier
  proposed ±1% measured tolerance. The deduction is an estimate, not a weighed
  measurement.
- Forecasts analyze the store's own supplied records for each request. They do not
  train or fine-tune a model on reports, recipes or photos.
- Corrections append history; posted records are not silently edited or deleted.
- Manual counting, production and (later) receiving remain usable when AI or the
  camera is unavailable.

## Success criteria

| Area | Observable outcome |
| --- | --- |
| Data foundation | Every in-scope ingredient has one catalog identity, correct base unit, package definitions and barcodes; every active flavor has a reviewed recipe; a real opening count is posted |
| Daily operation | A pilot store records shift reports, counts and production for an agreed period with no unexplained stock discrepancy attributable to the software |
| Integrity | No duplicate posting, cross-store data exposure or unreviewed stock change in pilot evidence |
| Forecasts | Advisory suggestions are measured against actual production; quality targets are an [open decision](IMPLEMENTATION_PLAN.md#open-owner-decisions) |
| Operations | A maintainer can deploy, monitor, back up and restore the hosted system using repository documentation alone |
| Assisted inventory | Shelf-photo and invoice features meet the gates in the [camera and invoice plan](workstreams/camera-and-invoice-readiness.md) before staff use |

## Explicit exclusions

These are outside the current product scope unless the owner explicitly changes it:

- Public signup, shared crew credentials and password-only manager access
  (retired on 2026-09-24 and not to be restored for compatibility).
- Unattended camera stock posting, inferring partial weight or hidden stock from
  a photo, and automatic invoice posting from extracted text.
- Automatic purchasing or ordering.
- Training or fine-tuning a model on store records as a prerequisite for any feature.
- A separate React browser rewrite.
- Offline stock posting until a server idempotency/conflict design is approved
  (local draft restoration exists and is not offline submission).

Connected-scale capture is **deferred**, not excluded: it waits for a chosen
scale model and protocol.

## Approved future capabilities

Approved but not yet scheduled ahead of the [roadmap](IMPLEMENTATION_PLAN.md#roadmap):
par targets and below-par views; supplier lead times; sales-based usage estimates
and shortage insights; store-listing deactivation and shelf deletion; an
area/rack/shelf/bin location hierarchy; waste, transfer and manual adjustment
movements. CSV import/export and copyable shelf templates are recorded as possible
later conveniences, not commitments. Their rules are in
[INVENTORY.md](INVENTORY.md#future-inventory-rules).
