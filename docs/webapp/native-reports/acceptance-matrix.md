# Native report acceptance matrix

Updated 31 October 2026 · implementation and remaining acceptance criteria.

**Part 1:** specification, outlines, schema and examples are reviewable design
artifacts. **Part 2A backend checks and bounded Agent 1/event/news browser checks are
recorded below, including [Part 2C charts](part2c-charts.md) and
[Parts 3A events](part3a-events.md), [3B news](part3b-news.md) and
[3C validation](part3c-validation.md). Wider physical-device,
cross-agent and human reader acceptance remains pending.**
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
| Native screens, interactive charts, print and reader acceptance | Agent 1 implemented in Parts 2B/2C and events/news in Parts 3A/3B; monitoring/close and wider acceptance pending |

The broader rows below intentionally remain pending where they require browser
review or additional workflow cases beyond this bounded synthetic data layer.

## Common native report implementation

Part 2B.1 supplies the shared native Agent 1 summary/key-figure screen.
[Part 2B.2](part2b2-research.md) adds supporting sections and numerical tables.
Cross-agent, physical-device and human interpretation rows remain pending where their wider
scope is not yet implemented. See [the reader evidence](part2b1-reader.md).

| Part 2B.1 check | Result |
| --- | --- |
| Agent 1 summary/key figures render inside the shell with no report iframe | Browser verified |
| Exact values, periods and sources remain accessible beside compact labels | Frontend formatting/source checks and browser source inspection passed |
| Execution, evidence restrictions, approval and snapshot consistency remain separate | Browser verified; false approval also enforced at the client boundary |
| Legacy, unsupported, removed and changed-evidence states do not retain trusted figures | Frontend tests and actual local browser probes passed |
| Evidence downloads agree with the loaded inventory; failed reads invalidate the reader | SHA-256/size tests and actual browser download/refusal/recovery passed |
| Keyboard source return and 320px/390px layouts retain access to the result | Browser verified; no outer horizontal overflow in inspected states |
| Agent 1 supporting sections and numerical tables | Implemented in Part 2B.2; browser layout/navigation reviewed |
| Interactive Agent 1 charts | Implemented in Part 2C; bounded browser checks below |

| Part 2B.2 check | Result |
| --- | --- |
| Performance, valuation, peers, market context, consensus and external research have native sections | Browser verified against complete registered synthetic workspace |
| Bridge eligibility, net-cash sign, peer dates/quote currency and analyst counts preserve saved meaning | 12 new backend cases passed; full Python suite 1,081 passed |
| Old research adapter 1.0.0 remains valid; fresh projection adds 1.1.0 detail | Compatibility tests and actual old/new workspace reads passed |
| Market tables retain null gaps, actual zero values and all dates | Frontend tests; browser 25-row pagination and point-level source inspection passed |
| Local review links, source return and mobile Go preserve navigation/focus | Browser verified; 320px/390px outer page does not overflow |
| Populated and unavailable consensus remain distinct from DCF and broker research | Default browser plus separate controlled synthetic case verified: EUR 650.00/share, 12 analysts, unknown horizon |
| Human interpretation acceptance | Remains a separate review |

| Part 2C check | Result |
| --- | --- |
| All eight Agent 1 charts use saved numerical series, with exact tables and sources | Implemented; browser inspected, zero report iframes/raster images |
| Null gaps, actual zero, signed bars, flat/single points, large close decimal amounts and date spacing | 13 new frontend cases passed; 51 frontend tests total |
| Pointer selection and keyboard arrows/Home/End expose exact values; Escape dismisses floating label | Browser checked; source/table values agree and focus returns |
| Diagnostic scenarios/peers stay discrete; restricted equity/peer results are not plotted | Default and separate controlled withheld browser cases passed |
| Legend filters retain table data and financial state | Browser checked; all-hidden explanation also implemented |
| Research adapter 1.0.0 and 1.1.0; 390px/320px layouts | Browser checked; eight graphs in both versions, no outer overflow in inspected states |
| 5,000 points per series and 20,000 aggregate points retained; 20,001 refused | Automated parser/geometry checks passed; maximum-payload browser timing remains pending |
| Touch and screen-reader user acceptance | Touch pointer-down/native range controls implemented; physical-device/screen-reader sessions pending |
| Native backend and frontend production checks | 83 workspace/backend tests, 51 frontend tests, TypeScript and build passed |

| Part 3A check | Result |
| --- | --- |
| Summary, sample/basis, historical observations, interpretation, review and evidence are native sections | Desktop browser verified; one SVG CAR chart and no primary report iframe/raster image |
| Case dates/basis, peer roles, exclusions and original findings retain their sources | 13 new backend cases passed, including repeated issuers, missing CAR, count/spread inconsistency and unknown checks |
| Ten cases do not override other failed study checks; invalid/unavailable p-values stay withheld | Controlled backend cases passed; genuine saved zero remains a diagnostic value |
| Wrong workflow, source, adapter, approval, visibility, units, references or populated path refused | 24 new frontend boundary cases passed; full frontend suite 75 passed |
| Exact selected CAR/source values, keyboard Home/End and source-return focus agree | Browser verified; explicit zero baseline/axis label retained |
| Event adapters 1.0.0/1.1.0 and Agent 1/news routing remain compatible | Automated compatibility and actual browser checks passed; old events explain missing metadata, Agent 1 retains eight graphs, news remains its separate existing reader |
| 390px/320px layout, section Go focus and source details | Browser verified; no outer overflow in inspected states, case table scroll contained, viewport override reset |
| Changed bundle refuses graphs/downloads; restored bytes recover | Disposable-workspace browser check passed; main/source workspaces each retain all 31 file hashes |
| Event download completion and saved-file hash | Open: page reported verified download, but browser event did not return a file; security policy blocked internal Downloads inspection. Automated size/hash boundary tests pass |
| Full Python and frontend build checks | 1,094 Python tests, 75 frontend tests, TypeScript and production build passed; no new dependencies |
| Verified event-relative path, human interpretation, physical touch/screen reader, broad print/export | Not completed by Part 3A; eligible path projection itself remains unimplemented |

| Part 3B check | Result |
| --- | --- |
| News summary, retained cards, coverage/exclusions, tone, review and evidence render natively | Browser checked; no primary report iframe/raster image; published tone stays withheld |
| Saved cutoff, timestamp/scope distinctions, relevance, cluster members, exclusions and scorer metadata retained | 18 added backend tests passed; default browser text/source inspection passed |
| Empty input, recorded empty response, no relevance, failed retrieval and inconsistent counts remain distinct | Controlled backend and frontend cases passed; no claim of live-source acceptance |
| Diagnostic zero does not become neutral; invalid scores/aggregates stay missing/withheld | Backend/frontend cases passed; default 0.3/−0.3 source inspection and 0.0 daily diagnostic remain separate from null published tone |
| Coverage and story-tone graphs use saved values, exact tables and keyboard/source controls | Browser checked; fixed −1/+1 score scale, explicit zero baseline, Home/End and source-return focus |
| Search/clear affects only retained cards | Browser checked; unmatched-filter state distinct, stored counts/publication unchanged |
| News 1.0.0/1.1.0 compatibility | Backend/frontend tests and browser passed; older news has no invented graphs or metadata |
| 390px/320px sections, Go focus, source details and contained table scrolling | Browser checked; no outer overflow in inspected states; viewport override reset |
| Changed bundle refuses cards, graphs and downloads; exact restoration recovers | Disposable-workspace browser check passed; source/main workspace hashes unchanged |
| Complete automated regression | 1,112 Python tests, 105 frontend tests, TypeScript and production build passed; no new dependencies |
| Wider acceptance | Human interpretation, physical touch/screen reader, broad print/export, maximum-payload browser timing and saved-download completion remain open; real-source published-tone acceptance is outside this synthetic reader |

| Part 3C check | Result |
| --- | --- |
| Early terminal news attempt without an analytical result is distinct from an empty feed | News 1.2.0 implemented; failed/unavailable/refused backend cases and actual unavailable browser case passed; completed/held missing-result states refused |
| Existing news 1.0.0/1.1.0 recipes remain valid | Prior-version delivery/reprojection and frontend fixture checks passed; no original recipe or saved artifact rewritten |
| Complete reading copy retains all measures, chart/table rows, restrictions and source references | Ten new frontend cases; actual forty-row copy retained all stories despite a one-card filter; no collapsed review details or pagination in the copy |
| News pagination and return focus preserve reading context | Browser checked; page 2 announces rows 11–20 and focuses the new page; copy return retains headline filter and focus |
| Empty, irrelevant, no-result failure, scorer failure, duplicate/excluded and limited-language/text cases | Actual controlled browser cases passed; failed/scorer-unavailable output did not become zero/neutral; headline/body markup remained text |
| Ten-case count and repeated/missing event values preserve restrictions | Browser checked; ten-case diagnostic test stays held; repeated issuer count seven, missing CAR unavailable, mean withheld, event path withheld |
| Large controlled reports retain every observation | Browser: 2,000 repeated event bars and two complete 2,000-row case tables; 600 news representatives and complete 600-row story/score tables; observed local ready times about 0.75–1.34s including tool/HTTP overhead, not an SLA |
| Primary/copy 390px and 320px layouts | Browser checked; no outer overflow in inspected states; labelled plot/table scroll areas, viewport override reset |
| Fresh evidence validation before reading/printing | Browser pre-print tamper case refused before the dialog, removed stale figures/copy and focused error; exact restoration recovered |
| Other-agent routes and reading-copy cleanup | Browser checked: Agent 1 retains eight graphs; Agents 2/4 retain existing reader tabs; leaving a copy removes its body/print mode |
| Source and acceptance workspace remain unchanged | Before/after hashes: 31 source files and 71 acceptance files unchanged; disposable copy restored exactly |
| Full automated checks | 1,118 Python tests, 115 frontend tests, TypeScript and production build passed; no new dependencies |
| Print/PDF and wider user acceptance | Complete copy and print stylesheet implemented; print paused DOM automation, automated tab closed without submitting a print job. Actual PDF pagination/reconciliation, physical printing, physical-device/screen-reader and human interpretation acceptance remain open |

| ID | Criterion | Verification required | Status |
| --- | --- | --- | --- |
| NATIVE-01 | Primary reports render as native components within Keystone | Inspect all five workflow pages; no primary report iframe or raw HTML injection | Pending |
| NATIVE-02 | Every figure preserves source value, unit, period and allowed display state | Adapter reconciliation against saved evidence, including invalid/missing cases | Pending |
| NATIVE-03 | Execution, evidence gate, integrity and financial approval remain distinct | Gate-mapping tests and visual review; financial approval stays false | Pending |
| NATIVE-04 | Warning grouping preserves all original findings and their impacts | Compare source checks to grouped reasons; inspect local and report-level notices | Pending |
| NATIVE-05 | Main summaries use only explicitly supported templates/references | Grounding and unsupported-prose refusal checks; no hidden model publication path | Pending |
| NATIVE-06 | Every chart uses supplied numerical data, with matching exact tables | Reconcile axes/points/tooltips/table values and chart-specific restrictions | Agent 1, event-case bars and news coverage/diagnostics implemented/browser checked; verified event paths and monitoring/close pending |
| NATIVE-07 | Pointer, keyboard and touch expose equivalent information | Browser input checks; visible focus; readable labels; colour-independent meaning | Agent 1/event/news selection and keyboard checked; physical touch, screen-reader and wider cross-agent acceptance pending |
| NATIVE-08 | Narrow layouts preserve the report and evidence | Review at 320px and 390px widths; outer page stays within viewport; table scrolling contained | Agent 1/event/news sections and source detail checked; monitoring/close pending |
| NATIVE-09 | Invalid, oversized, unsupported and missing views have truthful load states | Error-response and browser tests; no partial/stale verified view or path leakage | Pending |
| NATIVE-10 | Opening a report does not mutate evidence or trigger execution/network acquisition | Before/after hashes; provider/model calls blocked; no mutation endpoints added | Pending |
| NATIVE-11 | Old supported/unsupported saved records are handled explicitly | Compatibility cases; no guessing from arbitrary JSON or source HTML | Pending |
| NATIVE-12 | Source/view versions cannot be mixed | Tamper/version/concurrent-delivery checks; registration published last | Pending |
| NATIVE-13 | Print/export and original downloads preserve values and restrictions | Inspect print output and download hashes; original report sandbox remains in force | Agent 3 complete-copy content and pre-print integrity checks passed in 3C; actual PDF/physical-print and saved-download completion, other workflows pending |
| NATIVE-14 | Bounded payloads render without freezing or silently dropping content | Largest allowed fixture and over-limit refusal; documented aggregate bounds | Agent 1 data/geometry bounds and Agent 3 2,000-case/600-story browser samples checked; oversized QA details refused before catalogue publication; exhaustive maximum-payload/cross-agent timing pending |

## Workflow implementation

| ID | Criterion | Verification required | Status |
| --- | --- | --- | --- |
| A1-01 | Performance, valuation, peers and market context are readable sections | Original eligible fields represented or explicitly unavailable; no invented business background | Part 2B.2 implemented; browser reviewed, human interpretation pending |
| A1-02 | Keystone assessment, external consensus and external research are distinguishable | Correct attribution/availability; no broker ratings or reports invented | Native attribution implemented; automated boundary and default browser checks passed |
| A1-03 | Unavailable consensus does not become a forecast or DCF target | Current ASML fixture plus a separate controlled populated-consensus fixture | Default/controlled browser and data tests passed for bounded synthetic scope |
| A1-04 | Price/benchmark and derived charts preserve existing financial definitions | Exact date alignment, SMA windows, volatility annualisation and drawdown parity | Part 2C uses existing backend series; parity tests and bounded source/table/browser checks passed |
| A1-05 | Valuation assumptions, eligibility and peer restrictions remain visible | Missing bridge, excluded sector, small peer set, incompatible period/currency cases | Part 2B.2 data gates and default browser checks passed; broader reader cases pending |
| A3A-01 | Event diagnostics are understandable without raw gate codes | Reader explains sample, abnormal return, window and major review requirements | Part 3A implemented and browser inspected; human interpretation acceptance pending |
| A3A-02 | Historical observations do not become predicted returns | Held, inference-unavailable and repeated/overlapping-event cases | Part 3A bounded source/refusal tests and default browser passed; broader reader acceptance pending |
| A3A-03 | A dated/session path requires verified alignment | Current fixture withholds path; a separate eligible timing fixture supplies actual observations | Withholding/refusal implemented and checked; eligible path projection and its acceptance remain unimplemented |
| A3A-04 | Sample minimum does not imply automatic approval | Cases that meet count but fail timing/comparability/dependence/control checks | Controlled backend plus 3C ten-case browser example with count check passed and other restrictions held; human acceptance pending |
| A3B-01 | Coverage, relevance, clusters and text scope remain distinct | Valid-empty, retrieval-failed, excluded, duplicate and truncated/language-limited cases | 3B automated cases plus 3C empty/irrelevant/early-failed/mixed browser cases passed; broader human acceptance pending |
| A3B-02 | Withheld tone does not become neutral, zero or a trade signal | Current null published level and 0.0 diagnostic score; separate eligible/unsupported scorer cases | 3B boundaries and 3C no-result/scorer-unavailable/zero browser cases passed; eligible real-source published tone and human acceptance remain separate |
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
