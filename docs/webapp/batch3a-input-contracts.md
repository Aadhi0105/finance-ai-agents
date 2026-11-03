# Webapp Batch 3A — data onboarding and workspace contracts

**2 November 2026 · Design complete.** This specifies Batch 3B–3D.
[3B.1 implements the private saved-input backend](batch3b1-data-onboarding.md),
and [3B.2 adds fresh-close execution and recovery](batch3b2-fresh-close.md).
[3C implements browser onboarding](batch3c-browser-onboarding.md). Broader final
acceptance remains 3D work. This design document itself adds no runtime capability or financial approval.

[Package envelope](data-onboarding/input-package.schema.json) ·
[Acceptance matrix](data-onboarding/acceptance-matrix.md) ·
[Example and verification notes](data-onboarding/README.md).

## Purpose and simple examples

The next product step is to let an analyst deliberately add a supported local
dataset, understand whether it is usable, and select its exact version for work.
An imported input, a completed calculation, a delivered report and an approved
financial conclusion have separate identities and states.

For example, an analyst has an existing research `model.json`. Keystone should
preserve the submitted package, check the supported model format, identify the
company/listing and dates, and show any permission or evidence holds. If eligible,
the analyst can request an offline rebuild into a new native report. This does
not fetch newer statements, rerun the model conversation, or authenticate the
file's author. A saved Yahoo result remains subject to its source-use restrictions.

A second example is a fictional EUR budget and actuals panel. After validating
its account tree, complete annual budget and closed YTD actuals, a separate close
profile can calculate a new close. That differs from displaying an already saved
close. The same path can later accept authorised company inputs, but the user has
not yet supplied the real-company dataset needed for Agent 4 production acceptance.

## Baseline before 3B.1

| Workflow | Existing saved source | What the Batch 2 worker does |
| --- | --- | --- |
| Research | `agent1.model/2`, stored as `model.json` | Revalidates and rebuilds a private copy; does not gather inputs or repeat tool calls |
| Monitoring | Recognised unversioned `snapshot.json` | Renders a saved export; does not ingest observations, advance a cycle or decide corrections |
| Past events | `agent3.run_bundle/1` | Recomputes retained deterministic stages and compares them with saved output |
| Company news | `agent3.run_bundle/1` | Replays retained inputs/scores; does not retrieve news or run a new scoring model |
| Financial close | Saved `agent4.close/1` bundle | Renders a frozen close; does not load budget/actuals into accounting state |

The catalogue is explicitly `keystone.synthetic-workspace`. Source adapters,
native projection, frontend checks and labels assume synthetic evidence. The
report JSON schema already lists other classifications, but that alone does not
implement support for them. Existing checks must not be relaxed to accept an
uploaded file merely because it declares `fixture` or `synthetic`.

Relevant implementation: [catalogue](../../keystone/workspace/catalog.py),
[closed job profiles](../../keystone/workspace/job_contract.py),
[saved worker](../../keystone/workspace/saved_job.py),
[source adapters](../../keystone/workspace/report_views/sources.py) and
[native projection](../../keystone/workspace/report_views/common.py).

## Scope decisions for Batch 3

| Decision | Specification |
| --- | --- |
| Operating model | One local operator, one server-selected workspace at a time. Workspace selection is not tenant isolation or a user permission system. |
| First transfer format | One UTF-8 JSON package with a closed metadata envelope and one typed JSON payload. No archive extraction, uploaded HTML, executables, database files, spreadsheets or arbitrary filesystem paths. |
| First backend slice | Import and validate the five existing saved-evidence families. Generate reports from their retained evidence through explicit offline jobs. |
| Next backend slice | Add a separately versioned raw Agent 4 close-request profile with isolated accounting state and its own acceptance cases. It cannot reuse the saved-close rendering profile. |
| Other fresh input adapters | Raw statement/price kits for Agent 1, observation ingestion for Agent 2, raw event-price assembly and fresh news scoring need separate contracts/adapters. They are not implied by importing saved evidence. |
| Real saved evidence | Local processing may be enabled only for supported formats with applicable source-use evidence and classification-aware private readers. Real data is never relabelled synthetic to use Batch 2. |
| Live access | No provider fetch, URL retrieval, paid model call, external sharing or background scheduling in Batch 3. |
| Versions | Original input bytes and accepted versions are immutable. Corrections produce new versions; no silent replacement or automatic switch to the newest input. |
| Browser authority | The browser supplies data and references. The server owns storage locations, eligibility, permission decisions, profile selection, limits and result identity. |
| Existing workspaces | Continue serving existing v1/v2 synthetic catalogues unchanged. Create a separate onboarding workspace; no automatic in-place conversion or moved job-ledger adoption. |

This order is deliberate: accepting an existing export is a bounded extension;
accepting arbitrary raw finance data is a new analytical interface. UI capability
labels must name the actual action, such as **Rebuild saved research** or
**Calculate financial close**, rather than presenting both as a fresh research run.

## Workspace, company, dataset and version

| Record | Identity and meaning |
| --- | --- |
| Workspace | Server-generated stable ID and private root chosen by the operator at startup. Display name is editable metadata; paths are not browser inputs. |
| Entity | Workspace-local stable company ID and display name. Listing/ticker is separate, optional for internal FP&A. Matching a company name does not merge issuers, securities or share classes. |
| Dataset | A logical series of inputs for one entity and one supported format, with a server-generated ID. A company can have several datasets. |
| Dataset version | Immutable package, parsed payload, declarations, effective source classification, validation receipt, permission references and hashes. New local ID; upstream run IDs remain declared provenance. |
| Import attempt | A durable receipt for one transfer/validation request, including rejection or interruption. It is not a financial execution job. |
| Job | An explicit action bound to one accepted dataset version and its exact fingerprints. |
| Report | A separate registered output with dataset/version and job lineage; never a fabricated bootstrap report used to make an input runnable. |

Dataset identity includes format and entity. A different issuer, listing, currency
or materially different definition requires an explicit new dataset or reviewed
mapping; file names do not decide identity. An old input remains selectable only
when its current eligibility and policy permit use. Opening a report never
changes the selected input or refreshes a source.

The initial workspace registry is a local SQLite ledger plus immutable files,
not Firebase, a cloud database or an uploaded DuckDB file. Agent 2/4 engine state
keeps its own financial transaction semantics. Do not use a generic dataset row
as a replacement for their accounting/monitoring databases.

3B.1 clarifies entity scope: an explicit group can own a monitoring watchlist or
event peer set, with bounded declared members. Research/news still bind a company
and listing, and saved close binds the exact accounting entity. This does not merge
companies or establish peer comparability.

## Package envelope and provenance

The envelope schema is [version 1](data-onboarding/input-package.schema.json),
now used as the outer validator in 3B.1. It is not a permission grant. It checks
the outer structure and workflow/format pairing. Each payload additionally needs
the bounded semantic validator described below; an arbitrary object passing the
envelope is not an accepted dataset.

| Field | Meaning |
| --- | --- |
| `schema_version`, `kind` | Exactly `1` and `keystone.input-package`; unknown versions are refused. |
| `workflow`, `payload_format` | Closed, matching registry values; never a module, command, script or tool name. |
| `dataset.title`, `entity_id` | Readable title and existing workspace entity selected during preflight. |
| `dataset.upstream_id` | Optional source run/version label; untrusted provenance, not a local key. |
| `dataset.supersedes_version_id` | Optional explicit prior version of the same dataset. No effect on engine corrections or already saved reports. |
| `sources` | One or more named source declarations: category, provider/owner label, reference, observation/publication/retrieval dates, currency, units and permission-record reference. |
| `payload` | Exactly one JSON object in the selected family; never a link that the server follows. |

Date fields are timezone-aware instants or canonical calendar dates as specified
in the schema. Unknown values are `null`; omission is not a reason to substitute
upload time. Source declarations are an index, not a replacement for the payload's
per-observation provenance. Multiple dates/currencies remain attached to their
original series. A disagreement between envelope, payload and server entity
binding is refused, rather than silently reconciled.

Record three different fingerprints: original package bytes, canonical parsed
payload and canonical effective contract/validation receipt. The new
`keystone-input-json/1` canonical form uses Python `json.dumps` with sorted keys,
`separators=(',', ':')`, `ensure_ascii=False`, `allow_nan=False`, UTF-8 encoding
and no trailing newline or Unicode normalisation. Record the supported Python
runtime; reject duplicate fields/non-finite numbers before canonicalisation.
Existing agent-specific bundle/request digests keep their own algorithms and
must not be replaced with this new fingerprint. A byte change and a semantic
change can therefore be distinguished. Retain parser/adapter versions,
producer code identity, processing time and exact references used by the job.
Neither a hash nor a declared source URL establishes authenticity.

### Source-use and classification decisions

Reuse the inventory categories `synthetic`, `public_provider`, `issuer` and
`confidential`; unknown category is an unresolved declaration, not synthetic.
Native display maps these to `synthetic`, `provider`, `issuer` and `internal`.
Different categories produce `mixed`; incomplete classification produces
`unknown`. Derived output preserves all contributors and their restrictions.

`permission_record_id` is a reference to an operator-managed local record, not a
browser assertion that permission is reviewed. The record must bind the relevant
owner/provider, dataset or approved content scope, intended use, evidence
reference/fingerprint, review date and any expiry. It distinguishes:

- local retention, local deterministic processing and local backup;
- transfer to an external model; and
- sharing/display to other people or redistribution.

For this batch, retention and local processing must be permitted for the intended
use. Model transfer and external sharing stay disabled even if a source record
permits them. Backup inclusion needs its own permitted scope; unresolved backup
rights create a coverage hold rather than silently omitting data from a claimed
complete backup. Source-owner evidence is required for confidential company data.

Preflight stores bounded protected control metadata and checks the referenced
policy **before accepting/storing the payload**. Invalid-policy refusals retain
safe reason codes rather than submitted source content. A missing, expired, conflicting
or denied record refuses upload. The server rechecks policy at validation, job
claim and delivery. A later hold blocks new processing and unauthorised access;
retention/expiry resolution remains an explicit operator action, not automatic
deletion or an assertion that indefinite retention is allowed.

Self-authored synthetic examples need an explicit local operator provenance record;
known repository fixtures may bind to their recorded hashes. A caller-supplied
`data_kind: synthetic` or `meta.data_source: fixture` cannot provide this evidence.
Local operator records are attestations, not authenticated enterprise approvals.
The existing Yahoo enquiry and unresolved rights are not changed by import.

## Per-workflow payload contracts

| Workflow | `payload_format` | Required meaning and validation |
| --- | --- | --- |
| Research | `agent1.model/2` | Version-2 sidecar: `meta`, `analysis`, execution evidence and retained chart inputs where present. Listing/mode/source identities must agree; keep configuration, tool evidence, unavailable fields and original holds. Rebuild validates supported claims in a copy; it does not recompute every analytical tool from raw financial statements. |
| Monitoring | `agent2.snapshot/legacy-1` | Explicit wrapper name for the currently unversioned export, not a new claim about its producer. Requires `run`, `current`, `reviews`, `decisions`, `cycles`, `attempts`, `unreadable_audits`, `exported_at` and supported `data_mode`. Selected cycle identity, effective-state basis and correction links must agree. Empty `run: null` can be retained as an empty snapshot, but is not a runnable selected-cycle profile. |
| Past events | `agent3.events-bundle/1` | Version-1 `agent3.run_bundle`, terminal record, matching attempt ID, retained-input fingerprint, bundle hash, provenance and an event-shaped request/result. Full replay inputs are needed for execution eligibility; incomplete terminal evidence can be retained with a hold. Never interpret the uploaded event list as verified release timing. |
| Company news | `agent3.news-bundle/1` | Same version-1 bundle family, explicitly news-shaped. Preserve cutoff, aliases, input stories, exclusion/dedup evidence, text scope and saved score coverage. Replay reuses saved scores; it never loads model weights or fetches article URLs. |
| Saved close | `agent4.close/1` | Frozen close bundle with matching request/run identity, request digest, hierarchy/report and lineage. Verify report/source agreement using current Agent 4 checks. Preserve budget approval as a caller assertion; do not infer permission or financial sign-off. |
| New close request — second slice | `agent4.close-request/1` | Payload uses the current `agent4.close.execute_close` request fields; its package tag versions this boundary. Require entity, run ID, close period, cadence, budget, actuals and account tree. Validate against isolated state before committing a new calculation. |

The importer adds strict top-level family recognition and resource bounds around
legacy formats; legacy audit dictionaries stay inert data. It must enumerate the
supported producer shapes and consumed fields rather than forwarding arbitrary
objects into a renderer. Optional legacy omissions become named review holds
only when the corresponding existing engine supports that omission. Unsupported
versions, malformed identifiers, cross-workflow bundles and ambiguous shapes fail.

### Financial rules carried forward

- **Research:** base reporting-currency amounts; explicit price units and quote
  currency; aligned statement periods; missing is not zero. No implicit FX, ADR,
  share-class or minor-unit conversion. Preserve DCF assumptions, peer exclusions,
  historical/consensus distinctions and qualitative claim holds. Use the existing
  [financial contract](../agent1-financial-contract.md).
- **Monitoring:** distinguish cycle number from financial reporting period; retain
  metric definition, threshold, allowed direction, units, dates and original/effective
  history separately. Uploaded decisions do not approve a new correction or prove
  reviewer identity. Snapshot import cannot append observations to a live database.
- **Events:** daily market-model inputs retain 250 estimation observations and a
  three-observation event window where that method is used. Keep date alignment,
  the estimation gap, benchmark/return basis, release/session/timezone evidence,
  comparability, sampling/control and multiple-testing holds. Recompute with the
  existing engine; dates missing under a supported legacy shape remain limitations,
  not invented confirmations. CAR remains a historical diagnostic.
- **News:** publication, retrieval and cutoff are separate. Keep original text
  scope, aliases, relevance and cluster membership. Missing/failed scores are not
  neutral; diagnostic tone is not a return forecast or a licensed article archive.
- **Close:** request rows are exact integer `amount_cents` values, not EUR major-unit
  floats. EUR only, supported calendar month/quarter/year ends, unique line/period
  keys, explicit signs and stable account IDs. Require a full-year budget and
  complete effective closed-YTD actuals for every leaf; a delta is usable only
  with its exact retained predecessor state. No future actuals, currency/cadence
  mixing, silent zero fill or bypass of source-version/freshness rules. Financial
  tree tool inputs using major-unit amounts are a different interface.

For a new close, `budget.approved: true` remains an explicit required assertion,
not independently verified approval. An uploaded `supersedes` value has effect
only after the existing engine validates the correct current close in the bound
accounting workspace. Dataset supersession alone never mutates accounting heads.

## Validation, limits and failure behaviour

Proposed initial limits are conservative implementation requirements, not measured
capacity claims. Increasing them later requires repeatable capacity evidence.

| Boundary | Initial design limit |
| --- | --- |
| Package | One JSON object, UTF-8, no compression; 20,000,000 bytes including envelope |
| JSON parser | Maximum depth 64 and 1,000,000 values; reject duplicate keys, non-finite values, invalid encoding and unsupported top-level fields |
| Records | At most 50,000 combined tabular rows per package; existing tighter engine limits still apply (for example 1,000 event cases) |
| Text | At most 100,000 characters per retained text field and 2,000,000 combined text characters; smaller legacy field limits remain in force |
| Source declarations | 1–20 per package; bounded labels/references as in the envelope schema |
| Admission | At most five unresolved transfers and one active validator per workspace |
| Time | 60 seconds per transfer and 60 seconds for supervised validation; explicit job processing limit remains at most 600 seconds |
| Retained inputs | 100 datasets, 200 accepted versions, 200,000,000 aggregate input bytes per workspace |
| Reports/jobs | Existing 100-report/100,000,000-byte catalogue bounds and 20-pending/1,000-retained-job bounds continue until separately revised |

Count both original and derived input copies, staging reservations and retained
failed payloads against input capacity; do not count only canonical payload size.
Reject insufficient capacity without deleting old evidence. Parsing/validation
needs bounded supervised work; streaming size checks occur before full parsing.
No request may increase its own limits. File names are display metadata only;
new storage members use fixed server-generated names and never follow links.

Validation layers are: transport/access → policy and capacity → strict envelope →
typed payload → identity/financial semantics → eligibility. Structural failure
refuses acceptance. Missing optional evidence can yield **Accepted · review
required**, with explicit reasons. This status never clears a source-rights hold
or makes an unsupported profile runnable.

User errors identify a safe field/row and an actionable reason, such as
“Actuals row 8 requires an integer amount in cents.” They do not echo raw records,
server paths, audit conversation text, access tokens or stack traces.

## Import lifecycle, identity and recovery

Proposed import states are `reserved`, `receiving`, `validating`, `accepted`,
`rejected`, `interrupted` and `delivery_failed`. Only an accepted ledger entry
with verified immutable files can supply an execution source. Eligibility is a
separate current decision: supported format/profile, valid permission scope,
matched fingerprints and adequate retained inputs.

1. **Preflight:** validate the workspace/entity, declared format/source policy,
   expected package byte length/hash and a client-generated request key. Reserve
   capacity and save a durable import identity without reading a financial payload.
2. **Transfer:** use that identity and the same request key. Enforce size, time and
   byte fingerprint while receiving. The 3B.1 receiver holds one bounded package
   in memory and checks its actual content/contract before private staging, so a
   caller's payload-hash assertion alone cannot authorise retaining different bytes.
3. **Validate:** supervised offline validation reads only that file and registered
   local policy references. It writes a receipt and canonical payload copy. It
   does not call external URLs, trust supplied paths or dispatch a financial job.
4. **Accept:** flush all files, promote the immutable version directory, then
   transactionally record acceptance and its event. File promotion and SQLite
   commit are distinct boundaries; the ledger controls visibility. A prepared
   orphan directory is not automatically an accepted input.
5. **Use:** the analyst explicitly selects the accepted version and action.
   Creating/importing data never automatically starts processing.

Repeating the same request key with the exact descriptor/package retrieves the
same attempt. A changed body conflicts. Identical content submitted with a new
key within the same dataset and effective contract returns the existing version
with a new attempt receipt; it does not duplicate data or manufacture history.
Different provenance, entity binding or contract produces a distinct version.
Do not deduplicate confidential content across workspaces or disclose its presence.

On a lost acknowledgement, inspect the existing attempt and resend only that
identity. Incomplete/unpermitted receiving bytes are discarded from bounded memory;
the control receipt remains. Fully received authorised bytes can remain in private
staging after later interruption or semantic refusal, and are never eligible
without acceptance. A permitted transfer retry uses a new bounded staging member and
rechecks the entire file; byte-range append/resume is outside the first contract.
Explicit bounded recovery can verify/promote an already complete
prepared version once; it does not repeat financial processing. Missing/changed
proof is refused. Quarantined failures and incomplete staging remain outside all
catalogue/download routes. No automatic retention deletion is introduced.

Accepted versions cannot be edited, overwritten or deleted through the import
API. Dataset supersession records a relationship and reason; original jobs and
reports stay bound to the earlier version. Revocation/permission changes produce
append-only eligibility events, not edits to original source bytes.

## Private storage and access

The existing read-only report routes have no per-request token requirement. That
is acceptable only for the present explicit synthetic scope. **Non-synthetic
onboarding cannot be enabled until the private workspace read boundary exists.**

The proposed onboarding workspace stores a version-1 workspace descriptor,
entity/dataset/import ledger, immutable version directories, private staging,
operator permission records, report catalogue and job-control directory under one
operator-selected private root. Directories use `0700` and files `0600`; symlinks,
special files, overlapping roots and arbitrary supplied paths are refused.
Private data must be in an ignored operator directory before the first write.
The literal future root name and ignore rule are implementation work, not an
instruction to create files in the repository now.

Only the built application shell/static assets and bounded non-sensitive access
capabilities may be served before connection. All workspace/entity/dataset/import
metadata, reports, source files and job reads/writes require the current local
token, exact local origin and loopback host. No cataloguing of private names or
counts before access. Tokens stay in memory; reload/clear/restart requires
reconnection. This remains a local access capability, not enterprise authentication.

Private downloads use authenticated fetches with checked bytes and temporary local
download objects; direct unprotected file/image/HTML URLs are not a workaround.
Imported HTML is refused. Generated original HTML is offered as a download, not
an active document on the application origin. Text remains escaped; source URLs
are inert references until a deliberate external link action. Any offered link
must pass a scheme/credential check: HTTP(S) only, no embedded credentials or
executable schemes; uncertain/private references remain plain text. Do not retrieve
remote images, articles, styles, links or model resources during import/reading.

## Execution, schema compatibility and storage protection

The proposed onboarding catalogue is a separately recognised **version 3**, with
workspace identity, per-run classification and dataset-version origin. Old
synthetic v1/v2 catalogues and job-request v1 remain strictly supported; a client
must refuse unknown versions. No change to the financial payload schemas is
implied by this catalogue version.

Native source adapters and frontend validators/labels need explicit new versions
for permitted non-synthetic sources. Report schema v1 already has classification
values; reuse it only if its structure and evidence bindings remain sufficient.
Any new required fields need a new report schema, with paired backend/client
acceptance. Do not edit only the visible synthetic banner or blindly reuse
`check_source` for real data. References and permission/classification decisions
must be traceable from a generated report to its effective input receipt.

Add a **job-request v2** with a tagged source reference for an accepted dataset
version (dataset ID, version ID and effective contract fingerprint). The server
resolves its payload/receipt and pins all relevant hashes, permission revision,
entity identity and profile version. `source_run_id` in v1 keeps its existing
meaning. Never place a dataset ID into a run-ID field or accept browser commands.
Claim-time and delivery-time checks preserve the 2B/2D stale-source and recovery
rules. All Batch 3 jobs remain offline, paid-model disabled and financially unapproved.

The new close-request profile additionally binds a workspace/entity accounting
state generation. It runs the existing atomic close transaction under the existing
mutator/worker controls, and records the committed run before report delivery.
Unknown outcomes require checking that committed identity; no blind recalculation
or automatic requeue. Uploaded monitoring snapshots never enter this state path.

Backup inventory must explicitly cover the descriptor, entity/dataset/import
ledger, accepted originals/canonical payloads/validation and policy evidence,
registered reports, jobs/operation receipts and applicable Agent 4 accounting state.
Maintain a separate declared inventory for retained staging/failure evidence.
Exclude rotating tokens, credentials and environment files. Capture SQLite and
DuckDB under quiescence with the existing maintenance controls; do not copy an
active database or assume an unlisted WAL is unnecessary.

Restore into a fresh private destination. Verify identities, all hashes, receipt
links, effective permission holds and source bindings; rotate tokens and never
auto-run restored queued work. A local snapshot/restore rehearsal does not resolve
the deferred independent encrypted backup or clean-machine recovery dependencies.
The new storage contract must be accepted before claiming existing backup tooling
fully covers onboarding data.

## Proposed interface and backend handoff

These route boundaries were proposed in 3A. See the
[implemented 3B.1 contracts and commands](batch3b1-data-onboarding.md#api-contract)
and the [3C browser/inspection guide](batch3c-browser-onboarding.md) for the current protected interface:

| Capability | Proposed boundary |
| --- | --- |
| Capabilities | Before connection, fixed supported versions/formats and configured limits only; remaining capacity and workspace-specific actions require access |
| Entity/dataset management | Protected bounded create/list; server-generated IDs; no browser-selected disk paths |
| Preflight | `POST /api/imports` with metadata, source-policy references, expected size/hash and request key |
| Transfer | `PUT /api/imports/{id}/package`, bounded JSON bytes; only a matching reserved/explicitly retryable attempt |
| Inspect | Protected import receipt/list and dataset-version list/detail; safe errors and opaque pagination |
| Execute | Protected existing jobs namespace with explicit v2 dataset-version source; no run on upload |
| Operator recovery | Explicit local delivery/acceptance recovery, absent from the browser until separately designed |

The preflight descriptor and uploaded envelope must agree exactly on workspace
binding, entity, format, dataset/provenance declarations and expected package hash.
Server-generated fields and effective permission/eligibility are never accepted
from the upload. Default serving remains read-only; admission, import and worker
capabilities need separate explicit opt-ins. Enabling imports must not enable
execution, paid/live access or private reads without a connection.

The 3C page flow is **choose entity/dataset → choose supported file → inspect
validation and provenance → select accepted version → start the named action →
open its report**. Show rejected, held, interrupted and duplicate outcomes plainly.
Retain request identity through ambiguous responses and guard late navigation as
in 2C/2D. Do not display an enabled action for an unimplemented adapter.

## Implementation order and completion criteria

| Part | Deliverable and completion boundary |
| --- | --- |
| **3A — this design** | Current-code map, explicit format/financial contracts, envelope design, permission/privacy boundary, storage/version/recovery rules and pending acceptance matrix. Documentation/schema checks only. |
| **3B.1 — backend foundation** | Implemented: private workspace/ledger, permission preflight, bounded ingestion, immutable versions, strict saved-source validators, protected private reads, classification-aware projection and v2 job bindings for the five saved families. See the [verification record](batch3b1-data-onboarding.md#verification-and-repeatable-engineering-rehearsal). |
| **3B.2 — fresh close input** | Implemented: shared source validation without a canonical close on upload, isolated accounting state and predecessor pins, fixed fresh-close profile, atomic attribution and delivery-only recovery, exact-cent/correction/permission/isolation/restore tests. See the [backend guide](batch3b2-fresh-close.md). |
| **3C — interface** | Implemented: protected connection, company/dataset/import pages, read-only package inspection, validation/provenance panels, exact version/action selection, protected native readers/downloads and classification labels. See the [implementation and verification guide](batch3c-browser-onboarding.md). |
| **3D — acceptance** | Execute the [matrix](data-onboarding/acceptance-matrix.md): five saved families plus fresh close, all negative boundaries, browser-to-report/restore tests and preservation of prior evidence. |

3B.1 must not claim fresh analysis for the snapshot/replay families. 3B.2 must not
claim company acceptance using only fictional data. A family is enabled only when
its relevant rows pass; other families stay visibly unavailable. These two backend
slices refine Batch 3, not the earlier estimate of five remaining product batches.

Part 3A changes no production acceptance gates. Source permissions, independent
protection, clean-machine recovery, human financial/news/interpretation review,
physical accessibility/actual print acceptance, and authorised Agent 4 company
data retain their recorded status. No service purchase, external submission or
private-data transfer is authorised by this specification.
