# Webapp Batch 4A.1 — fresh-analysis scope and user journey

**3 November 2026 · Product design and isolated interaction preview.**
This follows [3D](batch3d-onboarding-acceptance.md). It defines the next workflow's
purpose, first supported scope and observable behaviour. It does not enable new
financial processing, import formats, provider access or model calls.

## Split of Batch 4A

| Part | Deliverable | Completion boundary |
| --- | --- | --- |
| **4A.1 — this part** | Current capability map, chosen first use case, scope and exclusions, conceptual input groups, user journey, section-level holds, output expectations, interactive fictional preview and 4A.2 handoff | Reviewable product decisions and browser-checked preview; no processing contract or financial acceptance claim |
| **[4A.2 — specified](batch4a2-fresh-analysis-contracts.md)** | Exact input/output schemas and versions, provenance/permission rules, financial dependency map, execution and recovery design, compatibility plan and acceptance matrix | Design contracts and examples checked; all 39 runtime acceptance rows pending implementation in 4B/later acceptance |

The later sequence is **4B: Agent 1 implementation → 4C: separate monitoring,
events and news slices → 4D: newly enabled workflow acceptance**. These labels
describe the proposed product sequence, distinct from the earlier Production v1
five-batch programme. Agent 4's supported new-close calculation already exists.

## 1. What problem this solves

Today an analyst can add a supported saved research `model.json`, select its
accepted version and rebuild its retained findings into a native report. They
cannot yet supply a new structured financial kit through the webapp and ask it
to calculate a new Agent 1 analysis from those observations.

The next capability answers: **What do these supplied company financials show,
and which comparisons or conditional valuations can their evidence support?**

“New analysis” means new calculations and a new evidence-linked result from a
selected accepted input. It does not mean newly retrieved market data, independent
source verification, a model-written investment thesis or an investment decision.
Observation dates remain separate from upload, processing and report dates.

## 2. Current versus proposed capability

| Workflow | Current web capability | Proposed extension |
| --- | --- | --- |
| Agent 1 | Validate/import a saved model and rebuild saved research | Calculate from a new, supported local financial input kit; first implementation |
| Agent 2 | Import/render a monitoring snapshot | Accept new observations and evaluate a new monitoring cycle; later dedicated slice |
| Agent 3 events | Import/replay a retained event bundle | Assemble and analyse new supplied event/window evidence; later dedicated slice |
| Agent 3 news | Import/replay retained news/scoring evidence | Process new supplied news text and eligible scoring inputs; later dedicated slice |
| Agent 4 | Import saved closes; calculate supported EUR closes and corrections from new close requests | Preserve that existing workflow; additional company/fiscal/currency acceptance remains separately scoped |

A successful saved rebuild does not demonstrate these proposed new-input paths.
Buttons and help must name the action: **New company analysis**, **Rebuild saved
research**, **Evaluate new observations**, **Analyse supplied events**, or the
appropriate news action. Capability discovery must eventually distinguish them.

## 3. Recommended first supported use case

Start with one listed operating company, one explicitly identified ordinary-share
basis, annual statements and compatible **EUR** statement/quote units. EUR is the
deliberately narrow first web-input acceptance slice; existing agent CLI support
for other compatible currencies is not removed or reclassified.

The analyst supplies already structured local inputs and applicable operator
source-use evidence. Python performs the numerical work. The first new mode uses
a deterministic processing plan and evidence-linked observations; paid LLM tool
selection and free-form prose are not prerequisites for this slice.

The financial-summary path is useful on its own. Valuation is an explicit optional
scope, enabled only when its method and input requirements are met. Peer,
historical-market and external-estimate sections retain independent availability.
4A.2 must determine precisely which optional groups ship in the first 4B slice;
the preview does not promise every existing analytical tool at launch.

### Initial exclusions

Financial-services/real-estate generic DCFs, unsupported securities/share classes,
automatic ADR/FX/minor-unit conversions, quarterly/stub/mixed-period kits,
multi-company consolidation and unrestricted industry/issuer coverage need
separate support. This first flow does not parse arbitrary PDFs, spreadsheets,
uploaded HTML, executable files or database files. A local financial kit is a
future supported structured format, not an arbitrary object with a new label.

Live Yahoo/other provider retrieval, news collection, paid models, external
dictionary/model downloads, scheduling, enterprise authentication, financial
approval, external sharing and hosted deployment are outside this part. Source
rights, authorised real-company FP&A acceptance and independent recovery retain
their existing status. The external drive remains deferred by the user.

## 4. Conceptual input groups

These are business requirements, **not** a JSON schema or an accepted file format.
The exact fields, strict types, units, signs, dates and bounds belong in 4A.2.

| Group | Purpose | Missing/unsupported behaviour |
| --- | --- | --- |
| Identity and source scope | Workspace/company/listing, annual period, reporting currency/unit basis, source references/classification and permission evidence | Missing/ambiguous mandatory identity, basis or permission blocks acceptance/processing; a company name alone is insufficient |
| Current annual financial observations | Supported revenue, income and statement measures with their own dates and definitions | Required minimum usable observations must be defined in 4A.2; absence blocks a new analysis rather than producing an empty successful report |
| Prior financial observations | Comparable annual growth and historical trends | Missing prior/history values withhold the affected change/trend; do not invent observations or silently annualise |
| Cash-flow and equity bridge | Eligible FCFF basis, tax/sign conventions, cash/debt and compatible share inputs | Missing or unsuitable inputs withhold the affected valuation/bridge; missing cash is never zero |
| Explicit valuation assumptions | Chosen method, growth/discount/terminal inputs, horizon, scenarios and weights | Requested valuation needs validated parameters and explicit review; no company-specific WACC or probabilities inferred from defaults |
| Quote and price history | Dated quote-based multiples, model-value gap and historical market context | Require compatible quote/share/currency basis; missing or stale data withholds affected metrics; no current quote fabricated |
| Selected peer evidence | Explicit peer identities, dated fundamentals/quotes and comparability basis | No provider fallback or automatic peer selection; missing/insufficient evidence remains unavailable or a held diagnostic |
| External estimates | Attributable consensus, dates and coverage; broker documents are a distinct source type | No invented consensus or broker ratings; history and model valuation cannot substitute for them |

Missing optional data differs from contradictory or malformed data. A declared
currency, listing or period conflict must not be silently ignored to make a
section runnable. 4A.2 must specify whether each conflict rejects the package or
holds a clearly isolated section, with no hidden basis conversion.

## 5. Proposed user journey

1. **Choose the task.** Distinguish a new analysis from rebuilding a saved report.
   Select a registered company/listing and the intended annual question.
2. **Choose local evidence.** The future browser accepts only the format defined
   in 4A.2. Explain supported input groups and units before transfer. The existing
   operator-managed source-use records remain authoritative.
3. **Inspect and accept the input.** Show identity, observation dates, declared
   scope, validation results and section-level readiness. Explicit import creates
   a version only after actual validation; inspection/upload alone starts no job.
4. **Choose analytical scope and assumptions.** Financial summary, eligible
   valuation and other supported sections have explicit selections. Review any
   proposed defaults as assumptions; record the actual selected values. Changing
   the selected input or assumptions invalidates the earlier review selection.
5. **Confirm an exact request.** Show the input version, source dates, included and
   withheld sections, assumptions, local-processing mode and applicable limits.
   A separately confirmed request creates one durable job. 4A.2 specifies the
   binding, retry semantics and server rechecks; a UI checkbox cannot grant rights.
6. **Follow execution.** Preserve queued/running/failed/unknown/delivery-required
   distinctions. Preserve the request identity after a lost acknowledgement. No
   financial success is inferred from an HTTP response or an attempted process.
7. **Inspect a new report.** The native reader shows source classification, exact
   financial periods, newly calculated observations, assumptions, section holds,
   source tables and interactive retained numerical series. The original export
   remains a separately verified download.
8. **Revise deliberately.** Corrected supplied evidence becomes another immutable
   version and a separately confirmed analysis. It does not rewrite earlier
   inputs/results or automatically change the selected version. This does not
   inherit Agent 4's accounting correction semantics.

The isolated 4A.1 preview groups the middle steps into **Choose inputs → Check
readiness → Review assumptions → Preview result**. It ends before real import,
request admission or processing. The complete future journey above remains the
implementation requirement; the four visual steps are not an API design.

## 6. Readiness and outcome vocabulary

| Situation | Expected user experience |
| --- | --- |
| Identity/current annual-period basis missing | Block the proposed request; identify the missing mandatory group; no empty “completed” result |
| Local retention/processing permission unresolved | Block actual inspection/import/processing as required by the boundary; no browser permission grant |
| Unsupported business/security/method | Explain the initial supported scope; do not force the generic method |
| Cash missing, financial summary otherwise usable | Retain financial observations; withhold the equity valuation/bridge and explain why |
| Prior observation/history missing | Withhold dependent growth/trend; retain supported current-period observations |
| Market history/consensus absent | Mark those sections unavailable; retain eligible financial calculations |
| Valuation requested, assumptions unreviewed | Ask for explicit review or exclusion of valuation before confirmation; financial approval stays separate |
| Valid analysis with financial review outstanding | A delivered review-required report, with its checks and holds, is a legitimate result |
| Interruption or uncertain delivery | Inspect the original job and apply its defined recovery; starting another job is not recovery |

Exact status codes and distinctions between accepted-but-ineligible input and
refused input are left to 4A.2. The product words above must not be treated as
implemented backend states or as permission to relax current guards.

## 7. A simple, independent example

The fictional Northstar Components sample has FY2024 revenue of EUR 900 million,
FY2025 revenue of EUR 1 billion and FY2025 operating income of EUR 120 million.
Independent arithmetic gives approximately 11.1% revenue growth and a 12%
operating margin. Those are design examples, not issuer results or forecasts.

If cash is missing, financial observations may still be useful while the equity
bridge is held. If the company/current annual-period identity cannot be resolved,
the proposed request is blocked. If market history or consensus is absent, those
sections stay unavailable. The reviewer's question is what the supplied evidence
supports, not whether every visual card has a number.

The preview's 9% discount, 12% initial growth, 2.5% terminal growth and ten-year
horizon are illustrative layout values, not recommended investment assumptions.
No DCF output is fabricated from them. The complete assumption set and scenario
behaviour must be specified in 4A.2 and independently tested in implementation.

## 8. Report expectations

Reuse the native-reader structure: summary, key figures, financial performance,
eligible valuation/assumptions, peer diagnostics, dated market context, separate
consensus/broker availability, grouped review requirements, and evidence/method.
Keep source-linked exact numerical tables alongside interactive charts. Omit or
clearly hold unsupported content; no placeholder becomes a financial zero.

State that calculations were produced from supplied local evidence. Retain the
input version, processing plan/code identity, assumption choices and job/result
lineage. Imported assertions are not verified issuer facts. No buy/hold/sell
recommendations, unsupported qualitative business claims, fabricated model
conversation or authenticated financial-approval badge is introduced.

## 9. Repository implications for 4A.2

- [Agent 1 orchestration](../../run.py) currently distinguishes fixture-driven
  offline and provider/paid-model live modes. `--offline` is **not** a raw-kit
  runner: it selects fixtures. A new local input adapter and truthful execution
  provenance are needed; do not relabel supplied real inputs as fixtures.
- [Data tools](../../tools/data.py) select fixture/provider acquisition. Bind the
  new accepted kit without hidden provider fallback or synthetic history creation.
- Reuse the financial meaning and applicability guards in
  [financial contracts](../../tools/financial_contract.py),
  [analytical tools](../../tools/analytical.py) and
  [publication validation](../../validation/publication.py). The browser owns
  selection/presentation, while Python owns financial calculations and eligibility.
- [Private execution](../../keystone/workspace/onboarding/execution.py),
  [job contracts](../../keystone/workspace/job_contract.py) and existing
  [native report recipes](../../web/src/reports/report-data.ts) need an explicit
  compatibility plan. Do not impersonate a saved-model rebuild or an old adapter
  merely to make a new raw input executable.
- Extend the 3D storage, permission recheck, exact-version binding and recovery
  invariants. Source permission, execution readiness, source authenticity and
  financial review remain separate concepts.

## 10. Handoff to 4A.2

The [4A.2 specification](batch4a2-fresh-analysis-contracts.md) now resolves this
handoff. It includes annual summaries/history, optional dated quote comparisons
and explicit scenario DCF in the first implementation. Raw peer, market-history,
consensus and broker inputs remain separate extensions. The product preview below
is retained as the original 4A.1 walkthrough, not a live implementation of 4A.2.

The original handoff requirements were:

Define the strict kit schema/version, minimal required observations and optional
groups; metadata and sign/unit/date rules; listing/share/currency alignment;
per-source rights and classification; explicit analytical/assumption plan;
server-selected executor and version-bound request; result provenance/adapter
compatibility; resource limits/idempotency/recheck behaviour; interrupted-result
recovery/backup inventory; and a frozen expected-outcome acceptance matrix.

Resolve the first optional tools actually included in 4B, how meaningful partial
analysis is represented, and the native-view changes needed for a new execution
mode. Do not promise a general uploaded-file parser, live connector or AI-written
research note through these names. No API route, JSON schema, source permission
grant, migration or implementation flag is added by 4A.1.

## 11. Live design preview and verification

The [isolated preview](fresh-analysis-preview/index.html) uses fictional constants
and in-tab state, with no API requests, file uploads, token input, persistence or
job submission. Its content policy disables network connections and form actions.
All processing/registration statements are explicitly proposed or illustrative.
The real request button remains disabled. It is separate from the working
workspace and is not served by the production application router.

From the repository root, run:

```bash
.venv/bin/python -m http.server 8854 --bind 127.0.0.1 \
  --directory docs/webapp/fresh-analysis-preview
```

Open **http://127.0.0.1:8854/**. Stop that preview with Ctrl+C in its terminal.
Serve only this isolated public design directory, not the repository root.
The current working workspace remains separately available at its own address.

### Recorded verification

| Check | Result |
| --- | --- |
| JavaScript syntax | `node --check` passed |
| Local preview readiness | HTTP 200 on loopback port 8854 |
| Browser interaction review | **14 checks passed**, covering review gating, the labelled result layout with disabled request, keyboard selection of a fictional observation, missing-cash partial analysis, three blocking examples, missing optional market data, explicit summary-only selection, review reset after input changes, separate saved rebuild, clean reload and layout checks |
| Responsive layout | Inputs at 1,280 CSS pixels and assumption/blocked screens at 320 CSS pixels had no page-level horizontal overflow; temporary override reset |
| Scope isolation | Fictional constants and in-tab state only; no file/token input, no API integration, disabled request control; `connect-src 'none'` and `form-action 'none'` |
| Application code | Existing agent, API, import/job contracts, storage and production frontend files unchanged |

Ignored screenshots and the case-by-case record are under
`output/fresh-analysis-4a1-preview/`. Checks are for the **design interaction**,
not actual source permission, semantic input validation, financial calculations,
execution/recovery or new-runner acceptance. Production Python/frontend
regressions were not rerun for this documentation and isolated static preview;
no production implementation changed. Detailed engineering acceptance remains
4A.2 specification and 4B/4D implementation work.
