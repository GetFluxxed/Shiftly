# Invoice review and incoming preview

Decision and source implementation: October 25, 2026. The owner requested a sixth
Today tile for invoice handling and an Incoming tile under Inventory, and explicitly
selected managers/owners and photo reading. This brings a bounded preview forward
from the earlier camera plan. It does not authorize automated stock posting.

## User flow and scope

Managers and owners with `inventory.view`, `receipts.draft` and `receipts.post`
can create a manual invoice draft or take one invoice photo. Crew, Production and
administrators do not gain this surface. Company catalog creation retains its
existing `catalog.manage` policy; a manager can keep an unmatched line for an owner.

An explicit Read invoice action uploads the photo to the configured AI provider.
The result is a proposal: a reviewer applies it, corrects quantities and units,
selects the catalog product/package and checks each received line. Save persists
the reviewed draft. Close retains read-only history and removes it from Incoming.
Neither action changes current inventory. A received checkbox refers to the whole
line; partial receipt quantities remain future work.

Incoming shows expected open-invoice quantities, the received subset and proposed
current-plus-incoming totals. Current stock uses live balances, including later
production deductions. Unknown stock remains N/A. A newer posted count requires
explicit review because it may already include the shipment. Archived/merged
products or changed base units/package amounts require affected lines to be
unmatched/rematched; unsafe quantities are excluded rather than reinterpreted.
Active company products can be matched before store listing or shelf assignment.

Only the native app and modern FastAPI runtime receive this feature. Browser
receiving, PDF/library/multi-page upload, invoice totals/prices, stock posting,
receipt reversals and offline image upload are not part of this implementation.
Manual draft edits use the existing private workspace checkpoint. Photo capture
and extraction require connectivity; this does not solve Expo Go delivery offline.

## Implementation and integrity

`inventory/receiving` owns services, SQL, exact decimal validation and photo jobs;
its FastAPI routers are transport adapters. Migrations 028 and 029 are additive.
Every mutation rechecks selected-store authority inside its transaction, including
idempotent replay. Version checks reject concurrent edits. Supplier plus invoice
number detects duplicates among active drafts when both fields are present.
Closed history is immutable. This is not final duplicate-receipt protection.

Catalog/package facts are snapshotted under row locks; store writes use the existing
inventory advisory lock. Conversion uses decimal strings and exact arithmetic,
including pound-to-kilogram conversion. Drafts do not touch stock balances or
movements. No AI result can create a product, mark received or post inventory.

## Private photos, provider and dependency

The server accepts one JPEG/PNG image up to 5 MiB and 20 megapixels, normalizes
orientation, strips metadata and re-encodes to JPEG with a maximum 4096-pixel edge.
It never fetches a supplied image URL. Photos are private database bytes with no
public download route. The separately supervised worker processes durable leased
jobs, checks current issuer authority and invoice version, records model/schema
provenance and validates a bounded structured response. The queued model is pinned
through execution. Repeated uploads reuse the recorded request; retries are bounded
at three attempts and new photos at ten per store per day.

Raw image bytes are removed after successful/terminal processing; expiry is 24 hours
and cleanup runs in the worker. An unavailable worker delays expiry cleanup. Drafts,
proposals and audit/provenance remain. Backups may retain images under their separate
operator policy; live deletion is not a promise of deletion from backups or provider
systems. Upload copy discloses provider transmission. Public privacy/operating
policies, actual provider retention terms and hosted controls remain release work.

The existing `OPENAI_API_KEY` and `OPENAI_MODEL` configure the Responses image
adapter, with `store: false`, a 30-second timeout and bounded output. No key means
photo reading is unavailable while manual entry works. Models must accept image
input; changing models needs evaluation. Per-store limits bound requests, not dollar
cost; Derek still owns billing alerts and cost limits. No paid provider call is made
by the automated tests. The image adapter can be replaced without changing drafts
or stock rules, subject to equivalent schema/security evaluation.

Pillow 13.0.0 is the one added runtime dependency, maintained by the Pillow project
under MIT-CMU, for decoded-type/pixel validation and metadata-removing re-encoding.
It adds no Python runtime dependencies. Image decoding is the new untrusted-input
exposure; size/pixel bounds, format restriction and locked updates limit it. Replacing
Pillow requires equivalent sanitization and malformed-image tests, not a database
migration. Fresh runtime and development lock installs and `pip check` passed on
Python 3.12.14; the lock verifier passed. Linux x86_64 CPython 3.12 wheel resolution
passed using manylinux_2_28; this is resolution evidence, not a hosted execution test.

Reference APIs: [Expo Camera](https://docs.expo.dev/versions/latest/sdk/camera/)
and [OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create).

## Verification and acceptance

Focused service checks cover exact projections without stock mutation, roles and
store scope, duplicate/replayed requests, concurrent edits, changed catalog/package
facts, decimal/cursor bounds and a real 027-to-028 preservation upgrade. Photo checks
use deterministic providers and cover image sanitization/limits, malicious output,
revocation, quotas, stale versions, leases and retry identity. Separate process tests
exercise photo completion, model provenance, image removal and shutdown recovery.

Mobile rendered tests use a mocked camera/provider and cannot establish physical
capture quality, permission behavior or background lifecycle on an iPhone. Before
staff reliance, test a representative invoice end to end, match packages, confirm
received items, compare Incoming to current stock, lose/recover connectivity and
verify stock remains unchanged. Record physical, CI and hosted evidence separately.

### Local evidence — October 25, 2026

- The owner chose manual invoice testing first. The local demo has no AI-provider
  key; list/editor photo actions are disabled and the direct camera route also
  explains availability. No provider request was made.
- The integrated receiving/photo/worker/resource pass completed with 77 passing
  tests. After adding the runtime availability detail, the receiving suite passed
  all 22 tests. These used an explicitly configured disposable PostgreSQL database.
- Mobile TypeScript and all 206 native behavior tests passed. Ten rendered invoice
  journeys and four real Expo Router checks passed, including manual entry through
  Incoming, package selection, close, uncertain retry, rebase followed by editing,
  role-based entry and disabled-provider camera access. Camera/provider fixtures
  remain simulated. Compact layouts were visually checked at 390-pixel width.
- A private local backup was restored into a separate disposable database before
  applying migrations 028/029. Row fingerprints for 26 existing catalog, inventory,
  production and account tables matched before/after. A fresh backup preceded the
  live local migration; the same original-table preservation check passed.
- Both migrations are applied to the local demo. API and separate worker health
  checks passed after restart; Expo Go remains the local mobile test route. The
  current iOS development bundle compiled successfully.

This is local implementation/verification evidence. It does not establish CI,
hosted deployment, a signed iPhone build, physical invoice quality or provider
accuracy. Current stock remains unchanged by invoice draft/received/close actions.
