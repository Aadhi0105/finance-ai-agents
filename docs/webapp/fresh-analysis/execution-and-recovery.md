# Local research execution and recovery — profile 1

**Normative 4A.2 design; all new execution support remains pending.**
For current implementation and the analytical-proof execution receipt version 3
refinement, see [4B](../batch4b-local-research.md). The original proposal below
retains its design-checkpoint meaning.
[Specification](../batch4a2-fresh-analysis-contracts.md) ·
[Request schema](analysis-request.schema.json) · [Acceptance](acceptance-matrix.md).

## Protected interface and immutable binding

Reuse the existing protected private `/api/imports`, dataset-version, job,
report-view and registered-download namespaces. No endpoint described here is
newly enabled by this document. Import/admission/worker remain separate explicit
startup capabilities; capability discovery advertises the new format/action only
after the complete supported path is installed. No private names or remaining
capacity before connection. Keep token, origin, Host, cache and error controls.

Preflight v2 contains the same six fields as v1: `schema_version`, `dataset_id`,
`package_bytes`, `package_sha256`, `payload_sha256`, `metadata`. Metadata is the
complete financial-kit envelope with only `payload` removed, and has envelope
schema 2. Package hash is SHA-256 of the exact transferred bytes; payload hash
uses canonical UTF-8 JSON with sorted keys, compact separators, `ensure_ascii=False`
and `allow_nan=False`. Decimal strings remain strings. All new plan/source/request
digests use that same canonical encoding; do not reuse the old job serializer's
different Unicode default without a versioned compatibility dispatch.

The server accepts no file path, adapter name or executable profile from the
browser. Request v3 binds one dataset ID, version ID and contract hash; the
server resolves workspace/entity/payload/receipt/policy identities and requires
format `agent1.financial-kit/1`. The server selects `calculate-local-research/1`.
Plan fields, tax choice and assumption acknowledgement are immutable request
content. The reviewed source hash covers the complete source-reference object;
the reviewed plan hash covers the complete plan object. No opaque UI review
token is assumed to prove identity or consent by an authenticated analyst.

Immutable record schema 4 retains existing job/operation identity rules and
contains request v3, canonical request hash, complete existing `DatasetBinding`,
profile/version, plan/source-review fingerprints, UTC evaluation date and the
admission readiness/producer fingerprint. The source contract also binds the
first accepted listing-scope pin; later versions cannot replace it.
Live-data/paid-model flags are false,
financial approval false, effective external requests/output tokens zero.
Missing/malformed review or request fields refuse admission; review does not
relax source rights or make ineligible valuation evidence eligible.

The closed [validation receipt schema 3](validation-receipt.schema.json) is a
new family, not an inherited saved-execution assertion. It records producer,
payload hash, exact period, validator version, evaluation date, listing-scope pin
and input readiness. `validation_status=validated`, `analytical_execution=not_started`,
`upstream_id=null` and `eligible=true`: this accepted-receipt shape is only emitted
after the minimum summary input is satisfied. Rejections remain safe import
attempt receipts, not accepted versions. No `execution_status=completed` assertion
is produced during intake. No invented upstream run or accounting-state pin.

Exactly one readiness entry exists for each of the eight result sections:
summary `minimum_satisfied`; performance/evidence `inputs_present`; valuation
`requires_plan` or `inputs_missing` with reasons; four deferred groups
`unsupported`. Readiness is about input presence, never a promised calculation.
No FCFF/ratio/DCF/report is generated during import. Plan suitability and finer
metric holds are checked after explicit request selection and during execution.
Source conflicts reject the package; missing optional values leave input holds.
The receipt is hashed into the immutable version; it is not browser authority.
Recheck all binding/eligibility, never trust a field merely because it says true.

## Resource policy

| Resource | First local-research profile ceiling |
| --- | --- |
| Package/transfer | 1,000,000 bytes, UTF-8 uncompressed JSON; 60-second transfer and 60-second semantic validation; existing parser limits remain upper ceilings |
| Structure | One entity/listing, 1–10 annual periods, 1–20 sources, one optional quote; only schema-defined fields; duplicate JSON keys refused before schema checks |
| Strings/values | Schema bounds apply; 15 monetary integer digits and six decimal places; no arbitrary uploaded document/text body |
| Job request | 8,192 bytes for request v3 only; existing v1/v2 4,096-byte ceiling unchanged |
| Execution | One local worker/attempt, default 120 seconds, requested timeout 1–120 seconds; zero provider requests, model calls, output tokens or downloads |
| Result budget | Reserve 16,000,000 bytes per admitted local-research job for staged and delivered evidence; enforce accounting of both copies until delivery, never just the final file |
| Evidence/view | At most 40 registered artifacts; 2,000,000-byte analytical result, 8 MiB native view, all shared chart/table/evidence limits retained |
| Workspace ceilings | Existing 100 datasets, 200 input versions, 20 pending jobs, 1,000 retained jobs and 100 catalogue runs remain; current lower free-space/byte limits also apply |

All ceilings are proposed bounds to measure in 4B/4D, not demonstrated throughput.
Count accepted, staged, rejected-but-retained and pending-delivery bytes. Reserve
before accepting work, fail safely on disk full, and preserve prior evidence.
No silent truncation, thinning, dropped review items or automatic deletion.
Worker environment strips provider/model credentials and network adapter access;
environment flags alone do not establish zero requests. Tests must intercept
network/provider/model entry points and demonstrate zero calls. Neither local
MCP transport nor downloads are needed for this profile.

## Idempotency and failure states

Admission uses the existing bounded request-key header and workspace isolation.
Same key + identical canonical request returns the original job; same key +
different source/plan/review/timeout conflicts. Do not derive the key from company
name. Different keys are distinct deliberate requests, not automatic retry
recovery. Acknowledgement loss keeps the original key in tab memory and retrieves
the original job after reconnection. Reload clears credentials/private evidence;
it must not silently resend a remembered request or create another key.

Execution receipts keep existing schema-1 states and the zero/one attempt rule:

| State | Meaning / allowed next action |
| --- | --- |
| `queued` | No attempt yet; claim only after fresh rights/input/readiness checks; restored queues stay held |
| `running` | Attempt 1; stages may be shown without implying progress percentages or financial success |
| `source_changed` | Bound input/entity/policy/eligibility differs at claim or registration; no computation/delivery; inspect and deliberately submit a new reviewed request if appropriate |
| `failed` | Known failure before a complete result proof; preserve attempt/diagnostics; do not automatically retry |
| `outcome_unknown` | Interrupted worker with no verified outcome; inspect saved evidence; no second execution under this job |
| `delivery_failed` | Complete verified analytical result/proof exists but catalogue delivery failed; operator may request delivery-only recovery |
| `review_required` | Verified result registered and delivered with financial approval false; whole or individual sections may remain held |
| `completed` | Existing state remains valid for old profiles; never emitted for new local research as a substitute for required financial review |

An unclaimed revoked request is claimed once and stops as `source_changed`, with
no calculation. A changed source during processing prevents registration and
delivery. Completed private reads recheck current retention/processing policy
and registered hashes; revocation makes them unavailable without deleting their
audit history. Date-dependent analytical freshness is frozen at successful
registration and shown on later reads, not silently recalculated in a browser.

## Atomic result proof and delivery-only recovery

Unlike a close, this profile changes no shared accounting state. It still must
preserve the original attempt and avoid inventing success after interruption.

1. Verify and copy exact accepted input, validation, contract/entity and plan into
   the job's private input area. Recheck bound content and permission fingerprints.
2. Calculate into a new private staging directory; prepare the analytical result,
   source/plan evidence, retained numerical series and both report forms.
3. Independently reconcile metrics, scope, source pointers, plan and lineage.
   Inventory every artifact by hash/size. Reject extra/unlisted/special files.
4. Write `analysis-commit.json` containing schema version 1, job/request/input/
   plan/producer identities and the complete artifact inventory except itself
   and the final catalogue. Fsync files and directories; atomically promote the complete result
   directory. A partial staging directory is never a recoverable committed result.
5. Store the proof hash and prepared-result descriptor durably, then register the
   exact result once under `result-<job suffix>`. Existing catalogue contents
   remain intact on registration failure. Delivery verifies proof and current
   source/policy again; it does not run financial functions or regenerate HTML.

The proof is a local integrity/attempt commit, not an accounting or financial
approval. Its producer digest covers source files, dependency lock, versions,
new schemas, mathematical plan and adapter recipe. Build it after native
projection files are finalized and before final catalogue publication. The
catalogue then registers the proof's hash as an additional evidence artifact;
the proof is not a native projection source. Avoid circular hashes by excluding
the proof and final catalogue from its inventory. Document this ordering in code.
The existing prepared-result descriptor hashes the final catalogue/run and a
separate operation receipt. That receipt records request/plan/proof identities,
review-required operation status, effective zero external usage and completion
time; it is outside the proof inventory and is hashed into the durable descriptor.
Neither the primary result nor proof references the receipt/catalogue hash.
Result identity never
uses an upstream issuer/document ID as the local job/result ID.

On restart, queued work stays queued/held under restore policy. Interrupted
running attempts become `outcome_unknown` unless a complete promoted result and
valid proof can be found. An operator recovery command may verify that saved
proof, transition to delivery recovery and register it once. It must refuse missing,
mutated, mismatched, oversized or unsupported records. No browser automatic
recovery or delete/reset-lock instructions. With no complete proof, inspect and
submit a separately confirmed new request if needed; retain the failed original.
Repeated delivery recovery is idempotent and never changes financial results.

## Result, native reader and backup integration

Primary result evidence remains named `payload.json` in the private run layout,
but its declared source schema is `agent1.local-analysis/1`. Register exactly two
native projection sources as today: primary result and retained native series.
For this new profile, catalogue `source_run_id` is the primary result's
`result_id`, not an intake receipt's null upstream ID. The result's internal
`execution.status=completed` means the scoped deterministic plan finished;
the durable job and report remain review-required, including partial/held sections.
The input kit and exact plan/contract are additional registered audit artifacts;
primary-result lineage binds their hashes. Evidence pointers resolve against
registered result metrics/derivations, whose input pointers resolve into the
registered kit. The verifier checks both hops; labels alone do not establish a
derivation. Display original decimals alongside any recorded engine rounding.

Use private catalogue 3 with `input_origin.profile=calculate-local-research` and
no `accounting_origin`. Extend explicit source/recipe dispatch rather than the
current research model/2 branch. New native recipe `agent1-local-report/1.0.0`
reuses report-view schema 1, shared charts/tables/reading copy and source controls,
with separately allowlisted grounded local-summary templates. The original HTML
export is generated once from the same verified result and served as a checked
download; native content is not an HTML embed. Old recipes and saved models stay
byte-identical, and opening a report writes nothing.

Quiesced snapshots inventory all accepted kit bytes, v2 metadata, validation,
policy/evidence records where backup rights permit, first listing-scope pins,
job v4/request v3 records,
execution receipts, attempt inputs, result proofs, staged/delivered artifacts,
catalogue and schema/producer identities. Preserve the existing token/key
exclusion and new-token restore. No original external filing is backed up if it
was never ingested. Missing/denied/pending local-backup rights must block a
complete eligible snapshot or report an explicit incomplete/refused outcome;
never silently omit restricted bytes and claim a complete backup.

Restore to a fresh private folder, verify full inventory/links and preserve
original request/attempt/result identities. New credentials, no automatic worker
release, explicit current policy/code recheck, original source unchanged. Recovery
is tested locally with synthetic permission evidence. Independent destination,
encryption/key recovery and clean-machine recovery remain separate unresolved
release dependencies; no external transfer or drive preparation is authorised.
