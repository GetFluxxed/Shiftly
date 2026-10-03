# Camera and invoice readiness plan

Decision date: 2026-10-01. This is the ordered path from today's catalog and
package work to a reviewed shelf-photo prototype, then to invoice receiving. It
is a planning contract, not evidence that the unfinished work is verified, a
promise that camera work will begin by a particular time, or a legal/compliance
approval.

The existing camera feature scans barcodes for catalog lookup and creation. It
does not count shelves, save shelf photos, receive invoices or call an AI
provider. Production currently deducts the exact recipe quantity multiplied by
confirmed batches and `1.01`; camera and receiving work must preserve that stock
history and its version checks.

## Delivery order and ownership

Work proceeds in this order. A later stage may be designed or explored while an
earlier one is finishing, but it cannot be called staff-ready until its gate is
met.

| Stage | Owner | Observable exit evidence |
| --- | --- | --- |
| 1. Catalog and package setup | Lead/team implement; store owner or designated catalog manager supplies real product/package facts | Every in-scope ingredient has one stable catalog identity, base unit, active store listing, shelf assignment where applicable, and versioned package/case definitions with explicit barcode mappings. Mixed-count calculations for sealed cases, loose full packages and net partial weight pass preservation, conversion, stale-version, package-breakdown and duplicate-package-ID tests. Migrations `021`–`022` and their implementation are not treated as verified until the lead records review, migration rehearsal and applicable CI/device evidence. |
| 2. Recipes | Store owner/production lead supplies and signs off real recipes; team validates behavior | Every active production flavor has a reviewed current recipe, explicit yield and complete ingredient mappings. A test production preview agrees with the recipe and the `× batches × 1.01` rule, and missing/archived ingredient conflicts are resolved. |
| 3. Opening stock | Authorized counter enters; authorized approver posts | A real whole-store count covers every required product/location, distinguishes uncounted from zero, includes package/partial breakdowns, and is approved. Current inventory and immutable movement history agree after posting; no quantity is invented from catalog/package metadata. |
| 4. Current issues and release hygiene | Team diagnoses/fixes; lead reviews | Open catalog/package/count/recipe/production defects are triaged with owner and severity; blocking items are fixed and regression evidence is recorded. Physical-device barcode, permission, background/return and relevant mixed-count journeys pass on the intended pilot devices. |
| 5. Security, permissions and recovery review | Lead/security reviewer; owner supplies operating facts | The read-only review below has findings and dispositions, the permission matrix is verified server-side, backup/restore and job-recovery rehearsals pass, and no release-blocking high-severity finding remains. This records evidence; it does not claim security is complete. |
| 6. Privacy and operating policy readiness | Company/data owner and attorney decide; team supplies accurate data-flow facts | Jurisdiction and company facts are answered, notices and policies match actual collection/providers/retention, an attorney reviews them before release, and staff acknowledge the operating procedure. This is a readiness gate, not legal advice or immunity. |
| 7. Shelf-photo prototype | Team implements; trained reviewers evaluate | A limited, non-posting prototype runs on representative labeled shelf photos and produces reviewed proposals only. It meets the prototype gate below. |
| 8. Staff camera pilot | Owner authorizes named stores/users after evidence review | Pilot accuracy, correction effort, latency, cost, privacy, device and recovery thresholds are agreed from real examples and met; all observations still require normal count review/approval. |
| 9. Invoice receiving | Deferred until stored catalog/package/stock facts are ready; team implements and finance/operations validates | The separate receiving gate below passes. Invoice extraction never posts stock by itself. |

### Timeboxed path toward a camera prototype

The user hopes to begin camera work tonight. Use a bounded readiness checkpoint
instead of treating that hope as a deadline:

1. Timebox a first checkpoint to inventory the real ingredient/package/recipe and
   opening-count gaps, name owners, and classify blockers. The checkpoint may end
   with a go or no-go decision; it does not waive missing data.
2. If stages 1–4 have recorded evidence and stages 5–6 have no issue that makes
   even a private prototype unsafe, start the narrow prototype: capture/upload,
   private storage, durable analysis job, typed proposal, and review UI. Keep it
   limited to test data or a named internal store and prohibit stock posting.
3. If those conditions are not met, spend the session closing the highest-value
   prerequisite and prepare a fixture-driven adapter/evaluation harness that uses
   no paid provider calls. Do not label scaffolding as a working camera count.

## Readiness checklist before shelf-photo work

### Catalog, packages, recipes and balances

- [ ] Use owner-reviewed combining for items with no count, balance or recipe history. If either record has history, retain both and schedule a reviewed historical reconciliation; do not simply sum possibly overlapping counts or rewrite recipe revisions.
- [ ] Resolve every ingredient to one company product; preserve aliases and
  leading zeros, and keep variable supplier shipment labels separate from stable
  manufacturer/internal identities.
- [ ] Record package net amount, unit, case contents and barcode per package
  option from a label, invoice, supplier specification or authorized operator.
  Record the source; do not infer case composition or partial weight from a photo.
- [ ] Prove case, loose-package and partial-weight inputs normalize exactly to the
  product base unit. Show that boxes inside a counted case are excluded from the loose-box count; a manual count cannot independently detect someone entering the same physical contents twice.
- [ ] Review all active recipes and their ingredient/product mappings. Exercise a
  preview showing recipe amount, 1% allowance and total deduction separately.
- [ ] Post the real opening count through the existing draft → review → posted
  workflow. Reconcile any unknown stock before production or receipt testing.
- [ ] Record device and CI evidence separately. The lead must review and publish
  the package/mixed-count evidence before the stage becomes complete.

### Permission matrix to implement and test

The server remains authoritative. Camera OS consent only permits the device to
capture an image; it never grants Shiftly staff authority. There is no public
role signup. Owners control role/capability assignments, and every action is
limited to authorized company/store scope.

| Action | Required authority | Scope and rule |
| --- | --- | --- |
| View catalog, packages, stock or proposals | `inventory.view` | Authorized company and selected store only; private media needs separate signed/authorized retrieval. |
| Manage company products/packages/barcodes | `catalog.manage` | Company catalog only; preserve referenced history and require versions. |
| Enter/save counts or correct camera proposals | `counts.submit` | Selected authorized store and open count only; cannot approve. |
| Review/post counts | `counts.approve` | Selected authorized store; recheck baselines and permission in the posting transaction. |
| Manage recipes | `recipes.manage` | Company recipes; no implied stock or store authority. |
| Confirm production | `production.submit` | Selected authorized store; exact recipe revision and existing `1.01` rule. |
| Upload shelf/invoice photo | Proposed: `counts.submit` for a count photo; existing `receipts.draft` for invoice drafts | Reuse existing capability policy unless the review identifies a real need for a narrower capture grant. Selected authorized store only; request OS camera permission just in time and use a system file/photo picker without unnecessary broad library access. |
| Review/edit invoice extraction | Existing `receipts.draft` (workflow still to be implemented) | Selected authorized store; proposal state only. |
| Confirm/post invoice receipt | Existing `receipts.post` (workflow still to be implemented) | Selected authorized store; fresh authority check in the atomic receipt transaction. Keep separable from upload/edit. |
| Create unresolved product/package during receiving | `catalog.manage` plus `receipts.draft` | Otherwise save/request an authorized resolution; never elevate the uploader. |

Test owner, manager/production/crew, deliberately delegated and revoked users;
wrong business/store IDs; store switching; delayed responses; background/session
restoration; and authorization revoked between upload, review and confirmation.

### Read-only security and recovery gate

Review actual code, configuration and deployed infrastructure without changing
production data. Record evidence, severity, owner and disposition for:

- tenant/company/store isolation across products, packages, counts, recipes,
  production, media, jobs, extracted lines, receipts and audit/history;
- private object storage, opaque object keys, expiring signed access, and fresh
  authorization on every media read; no public bucket or guessable permanent URL;
- decoded file-type verification, byte and pixel/decompression limits,
  orientation normalization, unnecessary EXIF/location removal, and malware or
  malformed-file handling for image/PDF uploads;
- server-side secrets, least-privilege service credentials, rotation process and
  logs/errors that exclude credentials and private document/image content;
- durable job ownership, bounded retries/backoff, timeouts, terminal failures,
  duplicate work, lost response recovery, cancellation and operational alerts;
- append-only audit evidence for actor, store, source, model/schema version,
  human corrections, confirmation and later reversal/correction;
- opaque session restoration, expiry/revocation, selected-store revalidation and
  private-state clearing after identity/scope changes;
- tested backup, restore and recovery objectives covering media metadata, receipt
  ledger, stock balances and audit records;
- vendor/subprocessor terms, data location/retention/deletion, incident notice,
  access controls and contract ownership.

FTC guidance supports collecting only what is needed, retaining it only while
there is a legitimate need, restricting access by role, and setting/verifying
provider security expectations in writing. These are planning inputs, not a
certification of compliance.

## Privacy and operating policy readiness

Before drafting final policies, the company/data owner must answer:

- legal company name, operator/contact, product owner and data controller/owner;
- countries and U.S. states where the company, stores, staff and customers are
  located; intended age groups; whether employee images/data may be captured;
- whether invoices can contain customer names, addresses, account, payment, tax
  or other sensitive fields, and which fields can be cropped/redacted before use;
- every hosting, storage, analytics, crash-reporting and AI processor, their
  contracts, data regions, retention, deletion, training/opt-in settings and
  subprocessors;
- exact original/derived-image, extracted-text, job-log and audit retention, who
  can delete each, legal/operational holds, and what backups retain;
- support/privacy request channels, identity verification, deletion/correction
  process, incident contacts and record owner;
- whether any information is sold, shared for cross-context behavioral
  advertising, or used for tracking; do not assume an answer from the app code.

Have qualified counsel decide which laws and employee/consumer notices apply.
California may be relevant, but must not be assumed from repository location or
the current team. The California Privacy Protection Agency says covered
businesses provide notice at or before collection, describe categories,
purposes, sale/sharing and intended retention, maintain a privacy policy, and may
need employee-specific notices. Counsel should confirm applicability and final
wording before any staff pilot or public release.

The privacy policy outline should cover: scope and entities; data categories and
sources; shelf/invoice images and extracted fields; purposes; legal basis where
applicable; stores/AI and other processors; sale/sharing/tracking facts; retention
and deletion; security summary without promises; role-based access; rights and
request/appeal methods; international transfers if any; children; changes,
effective date and contact. Publish only verified facts. Do not say uploads are
never retained or never used for model training unless the chosen endpoint,
account settings, contract and app storage all establish that statement.

At capture/upload, show a concise notice explaining what will be photographed,
the inventory/receiving purpose, that a named AI processor may analyze it, who
inside the company can access it, retention/deletion, and a link to the current
privacy policy. Let the user cancel, retake or choose a file where supported.
Apple separately requires a camera purpose string and user authorization for
camera access; denial needs a usable recovery/manual path.

The operating policy outline should cover: authorized capture locations and
avoidance/redaction of people/payment or unrelated documents; device custody;
store selection; image quality and retakes; human review of every proposal;
unknown/occluded/open-package handling; overlapping-photo prevention; partial
and damaged deliveries; separation of duties; corrections/reversals; incident
reporting; retention/deletion; periodic access review; model/schema change
evaluation; and training/acknowledgment records.

## Shelf-photo prototype and release gates

### Technical design

Use the existing server-side provider plumbing, but add separate vision job
schemas, prompts, adapters, evaluation sets, retry policy and configuration. The
repository default is currently `gpt-4o-mini` through the Responses API. Before selecting a camera model, verify the configured model’s current image-input and structured-output support, availability, retention and price in the official model documentation. The official vision guide supports image input by URL, base64 data or file ID. It also documents that vision can make
incorrect descriptions and has spatial/rotation/small-text limitations. Therefore:

- begin by evaluating the same configured image-capable model for both shelf and
  invoice jobs; keep the two model settings independently configurable and reuse
  a model only if each evaluation passes;
- use strict Structured Outputs/JSON Schema for typed proposals, then validate
  every ID, unit, quantity and scope against Shiftly data; schema adherence is not
  factual accuracy or authorization;
- do not fine-tune first, change API credentials, make paid evaluation calls or
  enable production traffic as part of this plan;
- treat text inside photos as untrusted data, never as system/developer
  instructions, tool calls, IDs, permission claims or approval commands;
- extraction creates proposals only. It cannot post a count, adjustment, receipt,
  product, package or price.

OpenAI's current data-control documentation says API data is not used to train
models unless the customer opts in, while default abuse-monitoring logs may retain
customer content for up to 30 days and endpoint/application-state behavior varies.
Verify the actual organization/project settings and endpoint before writing the
notice. Set request storage deliberately and record the result of that review.

### Gate A — private prototype go/no-go

Go only when stages 1–4 have evidence; a representative, labeled fixture set and
expected answers exist; capture purpose/consent and private media handling are
defined; prompt injection and malformed uploads are tested; and the prototype is
technically unable to post stock. A fixture-only adapter/harness may precede this
gate. Stop if catalog/package identities are ambiguous or media can cross stores.

### Gate B — named staff pilot go/no-go

Go only after Gate A plus lead security review, applicable privacy/employee notice
and counsel review, physical-device capture/denial/background tests, durable-job
recovery, agreed accuracy/error/correction-effort/latency/cost thresholds, and a
trained reviewer operating procedure. Limit stores and named users; keep manual
counting available. Stop or roll back on wrong-tenant media, unauthorized access,
unreviewed stock effects or unexplained duplicate/zero proposals.

### Gate C — public release go/no-go

Go only after pilot evidence meets thresholds over an agreed sample/time period;
high-severity findings are closed; incident, deletion and recovery procedures are
tested; vendor contracts and disclosures match actual behavior; policies/notices
are published and versioned; support ownership exists; and the exact release
revision passes CI, device and deployment checks. No gate guarantees immunity,
perfect security or counting accuracy.

## Deferred invoice-photo receiving

Invoice receiving starts only after the catalog, package conversions, opening
stock and store-scoped movement ledger hold the information needed to interpret a
delivery. It is a separate **Inventory → Receive invoice** grid tile and workflow:

1. An authorized user takes a photo or selects/uploads an image/PDF. The server
   validates and stores it privately, strips unnecessary metadata where
   appropriate, creates a durable extraction job and returns proposal status.
2. Extraction produces bounded fields and candidate lines. It may propose supplier,
   invoice number/date, product text, barcode/SKU, package/count and quantity, but
   it never posts stock. Pricing/tax/total extraction is optional and is not
   required to receive stock.
3. Match only against the authorized company's existing products, aliases and
   versioned package options using bounded candidates. Never let invoice text
   select a store, grant authority or issue instructions.
4. An unresolved line may create a new product/package inline only for a user who
   independently has `catalog.manage`; otherwise preserve the proposal and request
   resolution by an authorized catalog manager.
5. Start all lines unchecked. For each delivered line the reviewer explicitly
   confirms received/not received and enters actual received quantity and unit,
   including partial, missing or damaged quantities. Ordered/extracted quantity is
   evidence, not the received quantity.
6. Show a final review of resolved mappings, conversions, exclusions, damage and
   stock deltas. Recheck store, capabilities, versions and duplicates on Confirm.
7. Confirm atomically writes one idempotent receipt and immutable receipt movements,
   updates balances, and links source evidence/audit. A failure writes no stock.
   Corrections are append-only linked reversals/replacements, never edits to posted
   movements.

Duplicate safety uses a receipt attempt/request fingerprint plus bounded business
keys such as normalized supplier + invoice number + store, file hash, and stable
source/line identifiers. Duplicates create a review conflict, not silent posting.
Do not impose a single global invoice-number uniqueness rule: suppliers reuse
numbers, corrected documents exist, and legitimate partial/back-order deliveries
can reference the same invoice. A later delivery records its own receipt/delivery
identity and only its actually received quantities; it links the prior invoice
without being blocked or double-posted.

Invoice pilot evidence must cover multi-page/rotated/poor images; duplicate file
and re-photographed document; reused invoice numbers across suppliers/stores;
partial and split deliveries; missing/damaged lines; price-only/irrelevant lines;
unknown package/product and authorization handoff; catalog changes during review;
lost confirmation responses/concurrency; wrong-store access; corrections;
provider outage; and exact movement/balance reconciliation. Paid provider evaluations are outside this package implementation; define their fixture set and spend limit when starting camera development.

## Sources checked for this plan

- OpenAI, [Images and vision](https://developers.openai.com/api/docs/guides/images-vision): image-input mechanisms, model/detail support and documented accuracy/spatial/text limitations.
- OpenAI, [Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs): JSON Schema-constrained output and explicit edge-case handling.
- OpenAI, [Data controls in the OpenAI platform](https://developers.openai.com/api/docs/guides/your-data): training defaults, abuse-monitoring retention, endpoint application state and retention-control caveats.
- Apple, [NSCameraUsageDescription](https://developer.apple.com/documentation/BundleResources/Information-Property-List/NSCameraUsageDescription): required camera purpose description.
- California Privacy Protection Agency, [What General Notices Are Required by the CCPA?](https://cppa.ca.gov/pdf/general_notices.pdf): notice-at-collection and privacy-policy checklist, including employee coverage caveat.
- California Attorney General, [Making Your Privacy Practices Public](https://oag.ca.gov/sites/all/files/agweb/pdfs/cybersecurity/making_your_privacy_practices_public.pdf): CalOPPA policy scope/content guidance. Applicability requires counsel.
- Federal Trade Commission, [Start with Security](https://www.ftc.gov/business-guidance/resources/start-security-guide-business): data minimization/retention, least-privilege access, authentication, testing and provider oversight guidance.

