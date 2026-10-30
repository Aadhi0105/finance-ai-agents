# Native report acceptance matrix

30 October 2026 · implementation and remaining acceptance criteria.

**Part 1:** specification, outlines, schema and examples are reviewable design
artifacts. **Part 2A backend checks are recorded below. Browser/reader rows remain pending.**
The earlier Batch 1 iframe/browser acceptance does not satisfy native-report rows.

## Part 1 design acceptance

| ID | Criterion | Evidence / status |
| --- | --- | --- |
| DESIGN-01 | All four agents have outlines; event and news workflows are distinct | [Page outlines](page-outlines.md), documented |
| DESIGN-02 | Shared reading order, narrative boundaries and chart rules are explicit | [Specification](report-specification.md), documented |
| DESIGN-03 | Values, units, periods, availability and source references have a structured format | [Data contract](report-data-contract.md) and schema, documented |
| DESIGN-04 | Five synthetic examples conform structurally | Draft 2020-12 schema plus date/URI format checks, locally validated |
| DESIGN-05 | Example identifiers, references, source pointers, hashes and numeric transforms agree | Local semantic/source verification, validated against the saved synthetic snapshots |
| DESIGN-06 | Invalid examples demonstrate refusal boundaries | Seven structural probes (available-null, withheld-number, wrong workflow, extra field, financial approval, invalid decimal, invalid integrity) plus two semantic probes (broken reference, altered source value), locally checked |
| DESIGN-07 | Examples do not claim a running native endpoint or approved real-company research | Explicit design-only/synthetic scope in this pack |

Design validation is a local check of these documents. It is not a new automated
runtime validator committed with the application, and it does not certify source
truth. User interpretation/design acceptance remains to be reviewed.

## Part 2A backend acceptance

Automated evidence: `tests/test_native_reports.py` and the existing workspace
regression tests. These checks establish saved-data delivery, not source truth.

| Criterion | Status / evidence |
| --- | --- |
| Catalogue v1 compatibility; explicit v2 registration and original HTML retained | Implemented; legacy/native reads and reprojection tests |
| All five workflows produce typed source-linked report views | Implemented; actual offline engine outputs, strict schema and reference checks |
| Source/value/prose/gate changes cannot bypass view validation with an updated view hash | Implemented; tamper tests including a previously validated workspace |
| Safe 404/409/503 errors; local GET/HEAD boundary | Implemented; version, missing, invalid, origin and mutation cases |
| Delivery performs no writes, network acquisition or financial/chart calculations | Implemented; before/after hashes and forbidden-call tests, including a cold validation cache |
| Existing chart definitions and exact cents conversion retained | Implemented; SMA, volatility, drawdown, common-date rebasing and exact close bridge parity |
| Original/effective monitoring state; consensus/valuation; withheld/diagnostic tone stay separate | Implemented; controlled saved-source variations |
| Partial projection never publishes a catalogue; source workspace unchanged | Implemented; interrupted adapter and fresh-destination tests |
| Native screens, hover/focus/touch charts, print and reader acceptance | Pending subsequent frontend work |

The broader rows below intentionally remain pending where they require browser
review or additional workflow cases beyond this bounded synthetic data layer.

## Common native report implementation

| ID | Criterion | Verification required | Status |
| --- | --- | --- | --- |
| NATIVE-01 | Primary reports render as native components within Keystone | Inspect all five workflow pages; no primary report iframe or raw HTML injection | Pending |
| NATIVE-02 | Every figure preserves source value, unit, period and allowed display state | Adapter reconciliation against saved evidence, including invalid/missing cases | Pending |
| NATIVE-03 | Execution, evidence gate, integrity and financial approval remain distinct | Gate-mapping tests and visual review; financial approval stays false | Pending |
| NATIVE-04 | Warning grouping preserves all original findings and their impacts | Compare source checks to grouped reasons; inspect local and report-level notices | Pending |
| NATIVE-05 | Main summaries use only explicitly supported templates/references | Grounding and unsupported-prose refusal checks; no hidden model publication path | Pending |
| NATIVE-06 | Every chart uses supplied numerical data, with matching exact tables | Reconcile axes/points/tooltips/table values and chart-specific restrictions | Pending |
| NATIVE-07 | Pointer, keyboard and touch expose equivalent information | Browser input checks; visible focus; readable labels; colour-independent meaning | Pending |
| NATIVE-08 | Narrow layouts preserve the report and evidence | Review at 320px and 390px widths; outer page stays within viewport; table scrolling contained | Pending |
| NATIVE-09 | Invalid, oversized, unsupported and missing views have truthful load states | Error-response and browser tests; no partial/stale verified view or path leakage | Pending |
| NATIVE-10 | Opening a report does not mutate evidence or trigger execution/network acquisition | Before/after hashes; provider/model calls blocked; no mutation endpoints added | Pending |
| NATIVE-11 | Old supported/unsupported saved records are handled explicitly | Compatibility cases; no guessing from arbitrary JSON or source HTML | Pending |
| NATIVE-12 | Source/view versions cannot be mixed | Tamper/version/concurrent-delivery checks; registration published last | Pending |
| NATIVE-13 | Print/export and original downloads preserve values and restrictions | Inspect print output and download hashes; original report sandbox remains in force | Pending |
| NATIVE-14 | Bounded payloads render without freezing or silently dropping content | Largest allowed fixture and over-limit refusal; documented aggregate bounds | Pending |

## Workflow implementation

| ID | Criterion | Verification required | Status |
| --- | --- | --- | --- |
| A1-01 | Performance, valuation, peers and market context are readable sections | Original eligible fields represented or explicitly unavailable; no invented business background | Pending |
| A1-02 | Keystone assessment, external consensus and external research are distinguishable | Correct attribution/availability; no broker ratings or reports invented | Pending |
| A1-03 | Unavailable consensus does not become a forecast or DCF target | Current ASML fixture plus a separate controlled populated-consensus fixture | Pending |
| A1-04 | Price/benchmark and derived charts preserve existing financial definitions | Exact date alignment, SMA windows, volatility annualisation and drawdown parity | Pending |
| A1-05 | Valuation assumptions, eligibility and peer restrictions remain visible | Missing bridge, excluded sector, small peer set, incompatible period/currency cases | Pending |
| A3A-01 | Event diagnostics are understandable without raw gate codes | Reader explains sample, abnormal return, window and major review requirements | Pending |
| A3A-02 | Historical observations do not become predicted returns | Held, inference-unavailable and repeated/overlapping-event cases | Pending |
| A3A-03 | A dated/session path requires verified alignment | Current fixture withholds path; a separate eligible timing fixture supplies actual observations | Pending |
| A3A-04 | Sample minimum does not imply automatic approval | Cases that meet count but fail timing/comparability/dependence/control checks | Pending |
| A3B-01 | Coverage, relevance, clusters and text scope remain distinct | Valid-empty, retrieval-failed, excluded, duplicate and truncated/language-limited cases | Pending |
| A3B-02 | Withheld tone does not become neutral, zero or a trade signal | Current null published level and 0.0 diagnostic score; separate eligible/unsupported scorer cases | Pending |
| A2-01 | Original cycle, ongoing breach and corrected effective state remain distinct | Baseline, new issue, no-new-data and pending/approved-correction saved cases | Pending |
| A2-02 | Observation history is actually retained, not inferred from cycles | Registered historical observations; missing history shows unavailable graph | Pending |
| A4-01 | Bridge amounts, start/end positions and favourability reconcile exactly | €60 → +€10 → −€5 → €65 fixture and an adverse/alternative-account case | Pending |
| A4-02 | Forecast basis and limitations do not inherit close approval | Different forecast period, null interval/probability and uncalibrated forecast cases | Pending |

## Reader acceptance

An analyst/reviewer must be able to answer the following in plain language, using
the page without interpreting logs. Record the answer and any confusing wording;
automated structural checks cannot substitute for this review.

| Report | Required reader answer | Status |
| --- | --- | --- |
| Agent 1 | What did saved performance show? Which valuation assumptions matter? Is external consensus actually available? | Pending |
| Agent 2 | Which item requires attention, under which policy and observation date? Is it an original or corrected view? | Pending |
| Agent 3 events | What historical sample was studied? What does the diagnostic mean represent? Why is inference held? | Pending |
| Agent 3 news | Which stories were retained? Is a published tone available? What do clustering/scorer limitations mean? | Pending |
| Agent 4 | How does the bridge reconcile? What is established by accounting, and what remains provisional in the forecast? | Pending |

This matrix does not reopen the deferred analyst interpretation trial or mark it
complete. Native report reader acceptance is a later, separately recorded check.
Real-data permissions, external backup, disaster recovery and deployment gates
remain governed by the existing production documents.
