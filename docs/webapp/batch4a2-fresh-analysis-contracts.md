# Webapp Batch 4A.2 — fresh-analysis engineering specification

**3 November 2026 · Specification complete; runtime implementation pending.**
This was the 4A.2 design checkpoint. [4B](batch4b-local-research.md) now implements
the bounded local workflow and records its verification and execution-receipt
refinement. Broader final acceptance remains separately tracked.
This resolves the [4A.1 product scope](batch4a1-fresh-analysis-scope.md) into a
bounded Agent 1 implementation contract. It adds design schemas, fictional
examples and expected acceptance outcomes. It enables no importer, endpoint,
worker profile, financial calculation, source permission or release gate.

[Contract pack](fresh-analysis/README.md) ·
[Financial semantics](fresh-analysis/financial-semantics.md) ·
[Execution and recovery](fresh-analysis/execution-and-recovery.md) ·
[Acceptance matrix](fresh-analysis/acceptance-matrix.md).

## 1. Decisions for the first implementation

| Decision | Required behaviour in 4B |
| --- | --- |
| First subject | One registered listed nonfinancial operating company, consolidated annual statements, one ordinary-share class, EUR/base units |
| Acquisition | An explicit local structured financial kit; never provider retrieval or the offline fixture script |
| Required analysis | Current financial summary, eligible margins, annual revenue change and supplied annual history |
| Historical trend | A maximum of ten annual periods; revenue CAGR only over the latest consecutive positive sequence with at least three observations |
| Optional quote | One dated, compatible EUR snapshot for annual P/E, EV/operating-income and conditional model-value comparison |
| Optional valuation | Explicitly selected two-stage FCFF scenario DCF, complete reviewed parameters, no default tax or missing-working-capital substitution |
| Deferred groups | Raw price/benchmark histories, peer sets, analyst consensus, broker documents and qualitative thesis input; reject these unknown input groups, keep corresponding report sections visibly unavailable |
| Execution | A fixed server-owned local plan, zero provider/model requests, one durable attempt per admitted job |
| Result | A new `agent1.local-analysis/1` evidence record and separately registered native report; never a fabricated `agent1.model/2` run |
| Financial status | Delivered results are always review-required; no investment recommendation or authenticated financial sign-off |

Quote-based P/E is market capitalisation divided by attributable annual net
income. EV/operating-income uses the explicitly supplied operating-income basis.
It must not be renamed reported EBIT or treated as a contemporaneous TTM multiple.
Valuation scenario weights are analyst choices, not calibrated probabilities.

The first slice includes useful optional valuation without implementing every
existing Agent 1 data tool. The deferred groups need separate contracts and
acceptance before their upload or calculation becomes available. Existing saved
research can still display its retained peer, market and consensus evidence.

## 2. Contract identities and compatibility

| Boundary | New specification | Existing meaning preserved |
| --- | --- | --- |
| Upload envelope | `keystone.input-package`, schema **2**, workflow `research`, format `agent1.financial-kit/1` | Schema-1 envelopes retain their six existing saved/close formats |
| Financial payload | `keystone.financial-kit`, schema **1** | Not a saved model or a request to parse a filing |
| Preflight | Schema **2**, same descriptor fields as current preflight; metadata is exactly the new envelope minus `payload` | Preflight v1 unchanged; payload remains prohibited in preflight |
| Job request | Schema **3**, exact dataset-version source plus explicit `analysis_plan` and `assumption_review` | Request v1 saved-run and v2 imported-saved/fresh-close semantics unchanged |
| Immutable job record | Schema **4**, profile `calculate-local-research`, profile version **1** | Record v1/v2/v3 remain readable; v3 still means fresh close |
| Validation receipt | Schema **3**, validator `financial-kit/1.0.0`, with per-section input readiness, producer/payload identity and analytical execution `not_started` | Existing receipt v1/v2 are not reinterpreted; no invented source run |
| Analytical evidence | `keystone.local-research-result`, schema **1**, source family `agent1.local-analysis/1` | Existing `model.json` schema 2 and publication gate unchanged |
| Native recipe | Adapter `agent1-local-report`, version **1.0.0**, report-view schema **1** | Existing research recipes, including private 2.0.0, remain reproducible |
| Catalogue | Retain private catalogue schema **3** and existing `DatasetOrigin` fields | New recipe/profile dispatch is required; no in-place source migration |

The document schemas are prospective identifiers. Older software must refuse new
versions/formats explicitly. **Do not copy these schemas into runtime directories
or widen an enum alone to claim support.** Enable the format only with its
validator, executor, source policy, result verifier, native recipe, backup and
interface acceptance together. New code must still read existing catalogues and
jobs. Downgrading a workspace containing new records requires supported code or
restoring a compatible snapshot into another directory; never rewrite new records
to look old.

## 3. Import and provenance contract

The [package schema](fresh-analysis/financial-kit.schema.json) closes the entire
new envelope and financial payload. Dates, decimal strings and collection limits
are structural constraints; the [semantic rules](fresh-analysis/financial-semantics.md)
are equally mandatory. Passing JSON Schema is insufficient for acceptance.

The package declares a registered company, an explicit listing and unique source references.
Every non-null observation has a source ID and a nonempty filing/table/page
locator. Every null observation instead has a missing reason and null source
reference/locator. Source IDs resolve to the envelope; envelope and payload
identity, currency, source coverage and units must agree. The entity's ticker is
checked against its existing registration. Full MIC/share-class scope is a
declared, version-pinned basis under the first-acceptance rule in the financial
semantics, not a listing verified by an exchange registry. Unused/duplicate source
declarations are refused. A locator is inert text, never a local path to open,
code to execute, URL to fetch or proof that a filing was inspected.

Operator permission records remain external to the upload. Resolve every source
against the exact payload digest, entity, workspace, category, owner, evidence
and intended private personal evaluation. Require local retention and local
processing before financial bytes are retained or validated. The browser cannot
create or override these records. Recheck the current records before acceptance,
claim, result registration and delivery. Unknown classification/permission fails
closed; effective mixed classification includes every contributing source.

The first uploaded bytes are already structured observations; uploading them
does not upload the original filing. Record the asserted source and operator
evidence without claiming independent source authenticity. Publication/retrieval
times can be unknown with a review reason. Processing time never fills them.
Future financial observations or quote dates are refused; old valid observations
remain dated and subject to the freshness rules.

The strict minimum is a usable latest annual revenue observation and at least
one of operating income or attributable net income, plus mandatory identity and
period basis. Valid zero revenue is accepted; dependent margins/growth can be
unavailable. Negative profit remains a real observation. An empty analysis cannot
be accepted by providing only optional cash-flow inputs.

Import inspection returns existing outer states with a new validation receipt:
`eligible=true` means the minimum financial-summary path can execute. Individual
sections/metrics have their own readiness and reasons. This is not permission,
source verification, DCF suitability or financial approval. No calculation job
starts during preflight, transfer, semantic inspection or version acceptance.

## 4. Analysis plan and explicit review

The [request schema](fresh-analysis/analysis-request.schema.json) fixes summary
and annual trends on, and makes valuation either null or a complete parameter
object. Quote metrics are attempted only from eligible supplied observations;
the plan cannot select a network adapter, command, model or filesystem path.
Unsupported tasks/fields are refused rather than ignored.

A reviewed DCF plan includes horizon, discount rate, terminal growth, initial
growth, the fixed bear/base/bull growth deltas, three weights, a tax policy and
assumption rationale. There are no omitted-parameter defaults. `tax_basis` is
either an explicitly supplied rate or a valid effective rate; absent or unsuitable
effective tax inputs withhold valuation. Missing working capital is never zero.
The supported rate/horizon bounds and complete dependency graph are in the
financial semantics. Summary-only requests have null valuation and null review.

`assumption_review` binds the exact selected source reference and canonical plan
digests. It records an acknowledgement, not an authenticated person's approval.
Changing input version, contract fingerprint, tax treatment or any plan value
invalidates it. A server check recomputes both digests and validates readiness;
an arbitrary client hash or checkbox grants no capability. The UI must require
deliberate review and a separate confirmation before admission.

Confirmation shows exact version, financial periods, quote age, classification,
included/withheld/excluded sections and reasons, all valuation parameters and
local limits. Missing DCF evidence may leave a summary request usable: the
confirmation must name the hold; it cannot silently switch valuation off or
pretend a held section succeeded. Malformed assumptions block admission even if
the engine could otherwise skip their section.

## 5. Financial computation and report meaning

Python owns all arithmetic, applicability and source reconciliation. The new
adapter binds supplied inputs directly; it must not call `run_offline`, enable
`yfinance`, reuse provider-specific normalization, fabricate stub-model turns or
invoke peer acquisition. Shared mathematical functions can be reused through
explicit, source-free inputs. See the [function/dependency map](fresh-analysis/financial-semantics.md).

The existing publication gate requires prices, peers, consensus, DCF and
fixture/yfinance provenance for a complete research run. It is not an appropriate
acceptance gate for this new, deliberately narrower workflow. Add a separate
versioned local scope-aware validator that reconciles supplied inputs and exact
parameters. Preserve the old gate and its tests. The local validator can hold a
section without inventing missing tools, passing a fake source label or
upgrading a partial report to complete research.

The [result schema](fresh-analysis/local-result.schema.json) specifies a closed
evidence record with identity, exact plan, provenance, lineage, section outcomes,
typed metrics, numerical series, deterministic derivation references and checks.
Raw inputs, plan/review receipt, validation basis, calculation record and native
series must be retained under verified artifact inventory. Reports identify this
as **calculated from supplied local evidence**. Synthetic results remain labelled
fictional throughout the UI, chart tooltips, source tables, exports and print.

No result claims a live LLM run, analyst conversation, verified issuer fact,
broker target, market consensus, buy/hold/sell rating or source permission granted
by Keystone. `financial_approval` is always false. The gate is always
`review_required`; successful arithmetic cannot produce a financial approval.

### Independent fictional benchmark

Northstar Components has annual revenue EUR 800m/900m/1bn for FY2023/24/25,
FY2025 operating income EUR 120m, attributable net income EUR 75m, D&A EUR 20m,
capex EUR 25m and working-capital absorption EUR 5m. With an explicit tax rate
25%, FCFF is **EUR 80m**. A one-year horizon, discount rate 10%, terminal growth
2% and initial growth 10% produce conditional enterprise values **EUR
1.06bn/1.10bn/1.14bn** under the fixed scenario deltas. Debt EUR 200m and cash
EUR 100m give equity values EUR 960m/1bn/1.04bn. At 10m shares, the scenario
values are **EUR 96/100/104 per share**. Weights 25%/50%/25% yield EUR 100 per
share. Against a separately dated EUR 80 quote, the conditional model-value gap
is 25%, not a forecast return or recommendation.

The current revenue growth is 11.11% after existing four-decimal ratio rounding,
and operating margin is 12%. The three-observation revenue CAGR is about 11.8034%.
The two explicit one-year discounting terms are independently checked in the
design verifier; actual engine/adapter/report parity remains an implementation
acceptance requirement. None of these assumptions are company recommendations.

## 6. Execution, durability and recovery

The [execution specification](fresh-analysis/execution-and-recovery.md) defines
the request/record binding, fixed profile, resource ceilings, state transitions,
atomic result proof, delivery-only recovery and private backup inventory.
Reuse protected imports/jobs and exact-version binding. No new public data route,
operator-permission mutation, report approval, blind retry or browser-selected
executor is introduced. Retain the existing token/origin/private-read boundaries.

The immutable job contains the exact plan and review hashes; execution is still
a separate mutable receipt. A lost admission acknowledgement reuses the original
request key. A worker interruption never creates another automatic attempt.
Committed analytical evidence can be delivered after verification without
recalculation. Partial evidence stays hidden. Changed permission or source data
blocks use even when a prior process exited successfully.

Local snapshot/restore must include new input, request, proof and result records.
Restore into a new private destination, issue a new token, hold restored queued
work and recheck supported code and permissions before operator release. No claim
of independent protection or clean-machine recovery follows. The external drive
remains deferred.

## 7. Implementation order and acceptance

| 4B engineering slice | Deliverable and enabling condition |
| --- | --- |
| Foundation | Strict v2 package/preflight dispatch, financial-kit validator, source policy and per-section receipt; no action until the executable path exists |
| Calculation | Fixed local plan, reviewed valuation binding, source-free math, scope-aware gate, result/proof schema and crash-safe storage |
| Delivery | Explicit local recipe, reconciliation, native charts/tables, verified originals and delivery-only recovery; saved recipes unchanged |
| Interface | New-analysis task, supported-kit help, exact-version/plan review, separate confirmed request, partial/held results and access/retry safeguards |
| Bounded acceptance | All applicable [acceptance rows](fresh-analysis/acceptance-matrix.md) pass on isolated synthetic cases, including real loopback HTTP/browser, faults, restore and no-network counters |

These are implementation dependencies, not newly authorised parallel work or a
claim that 4B is already complete. 4C remains separately scoped new monitoring,
event and news processing. 4D provides the broader newly-enabled workflow
acceptance; each 4B capability must already pass its own enabling rows.

All matrix rows were **pending implementation** at this design checkpoint.
Structural examples and independent example arithmetic do not satisfy runtime
rows. Real-source rights, human interpretation, authorised company FP&A data,
independent backup, key recovery and clean-machine disaster recovery retain their
existing open/deferred status. There is no unresolved technical choice required
to start this bounded 4B implementation; expanding its scope needs a documented
contract and acceptance revision.

## 8. Design verification

Run the [design verifier](fresh-analysis/check_design.py) using the command in the
[contract-pack guide](fresh-analysis/README.md). It checks the four schemas,
fictional examples, selected malformed variants, sample references/hashes and
independent example arithmetic. It does not run a production importer or engine,
grant permissions, simulate crash durability or mark any runtime matrix row as
passed. The existing 4A.1 preview remains a historical product walkthrough; it
does not acquire upload/execution capability from this specification.
