# Fresh local research — implementation acceptance matrix

**3 November 2026 · Frozen 4A.2 design checkpoint.**
The Pending status column below records the original design checkpoint, not a
current runtime verdict. [4B](../batch4b-local-research.md) records initial
implementation evidence; [4D](../batch4d-workflow-acceptance.md) records subsequent
count-bound, fault/recovery and browser acceptance and the remaining coverage
limits. A demonstration does not automatically pass every variant in these rows.
[4A.2 specification](../batch4a2-fresh-analysis-contracts.md) ·
[Financial semantics](financial-semantics.md) ·
[Execution/recovery](execution-and-recovery.md).

Freeze expected outcomes before running the implementation. Design-schema checks
and example arithmetic are recorded separately in the [pack guide](README.md);
they do not pass any row below. Each row gates its corresponding 4B capability;
4D adds broader cross-workflow acceptance. Use new isolated synthetic workspaces
and scoped synthetic permission records, no existing provider downloads.

Evidence: **S** strict parser/schema/semantic cases; **F** independent financial
oracles and actual shared-function parity; **J** protected API/worker/durable job;
**N** native projection/source/export parity; **B** visible browser and keyboard/
mobile review; **R** fault injection and quiesced local snapshot/restore;
**W** existing Python/frontend/build regressions. Test fault controls are not
production API features. Capture exact input, plan, code/lock, job and result
hashes and measured bytes/time; do not report credentials or real private data.

| ID | Fixture or trigger | Required observable outcome | Evidence | Status |
| --- | --- | --- | --- | --- |
| FR-01 | Current v1/v2 requests, schema-1 input families, old recipes/catalogues | Read/rebuild/close behaviour and bytes unchanged; new format explicitly refused by old readers; unknown versions refused by new code | S, W | Pending |
| FR-02 | New format advertised but handler/recipe/profile missing | No enabled new-analysis action; no partial enum-only feature activation | J, B | Pending |
| FR-03 | Complete fictional package | Accept one immutable version with correct entity/classification, minimum summary eligible, section readiness; no job/calculation during import | S, J | Pending |
| FR-04 | No revenue, or neither operating nor attributable net income | Reject minimum; preserve valid zero revenue/negative profit in separate valid cases | S, F | Pending |
| FR-05 | Numeric JSON value, bool, exponent/separator/NaN string, negative zero, out-of-bound scale/sign | Refuse without coercion; present zero stays sourced and distinct from missing | S | Pending |
| FR-06 | Null without reason, present value without source, unresolved/unused/duplicate source, forged source category | Refuse; no classification downgrade or guessed source | S, J | Pending |
| FR-07 | Wrong entity/MIC/share class/currency/unit, ADR, unsupported company or conflicting simultaneous first listing-scope pins | Reject full package including optional-group contradictions; first scope pinned atomically across datasets; equal names never merge entities | S, J | Pending |
| FR-08 | Quarter/stub/overlap/duplicate closing year/unsorted/future dates | Reject; no silent annualisation, reordering, period borrowing or dropped row | S | Pending |
| FR-09 | Three valid years versus two/gapped/nonpositive sequence | Current YoY only for comparable pair; CAGR requires latest positive consecutive suffix ≥3; exact included/excluded dates recorded | S, F, N | Pending |
| FR-10 | Missing optional income or historical observation | Keep supported figures; individual unavailable reason; null chart gap and exact table, no interpolation | F, N, B | Pending |
| FR-11 | Old statements; unknown publication/retrieval times | Dated observations with stale/unknown-date review; upload timestamp never substitutes | S, N, B | Pending |
| FR-12 | Quote absent/stale/future/mismatched; cap reconciliation at and beyond 5% | Absent unavailable, age >7 held, future/basis/reconciliation conflict rejected; exact Decimal boundary checked | S, F, N | Pending |
| FR-13 | Positive, zero, negative earnings/operating income; missing cash/debt/claims | Independent P/E and EV/operating-income outcomes; nonpositive denominator not applicable; bridge holds retained | F, N | Pending |
| FR-14 | Summary-only request | Null valuation/review accepted; no DCF call, no missing-required-DCF failure, excluded scope visible, report review-required | J, F, N, B | Pending |
| FR-15 | Missing/unreviewed DCF parameters, invalid horizon/rates, wrong weights/deltas | Refuse invalid request; no default fill or weight normalisation; effective scenario growth bounds checked | S, J, F | Pending |
| FR-16 | Changed version/contract/parameter/tax after acknowledgement | Review digests invalidated and confirmation reset; server rejects stale review; checkbox cannot grant rights | S, J, B | Pending |
| FR-17 | Effective tax valid/negative pretax/out-of-range; explicit rate zero/one | Independent FCFF; unsuitable effective tax holds DCF; explicit bounds valid; no default 25% | F, N | Pending |
| FR-18 | Working-capital absorption/release/missing and capex sign | Correct FCFF sign; missing dNWC held, never zero; mistyped convention rejected; no provider-specific transformation | F, S | Pending |
| FR-19 | Full one-year benchmark in design examples plus independent two-year case | Match independently calculated EV, equity, per-share, weights, gap and terminal concentration within recorded engine precision; year-1 and fade semantics checked | F, N | Pending |
| FR-20 | Nonpositive FCFF; unknown/nonzero equity claims; missing debt/cash | DCF not applicable or held with exact reason; current summary survives; no EV per share or false equity target | F, N, B | Pending |
| FR-21 | Missing/stale shares/price; negative residual equity and genuine zero equity | Eligible equity totals retained; per-share/gap holds correct; negative equity diagnostic; zero never treated missing | F, N | Pending |
| FR-22 | Large accepted decimals and near-boundary rate gap | Checked conversion/finite output; overflow refuses calculation safely; no NaN/Infinity/extra precision in JSON/view/export | F, S, N | Pending |
| FR-23 | Raw peers/history/consensus/broker fields; thesis/HTML/code fields | Unknown input groups refused; separate unavailable report sections; no provider, interpreter or uploaded HTML execution | S, J, N | Pending |
| FR-24 | No/denied/expired/mismatched policy before transfer and after acceptance | Refuse retention/claim/registration/delivery as applicable; no browser permission override; audit evidence preserved | J, R | Pending |
| FR-25 | Wrong token/origin/Host, HEAD/download and disconnected/reloaded browser | No private records before connection; safe errors, no secrets/paths; late responses cannot repopulate cleared state | J, B, W | Pending |
| FR-26 | Same request key with same/changed plan, lost response, repeated click | Same request returns one original job; changed request conflicts; retained key/reconnect finds original; no automatic new-key retry | J, B | Pending |
| FR-27 | Claim input/receipt/entity/policy/eligibility change; concurrent workspaces | Exact binding rechecked; one attempt or source_changed with zero calculation; no cross-workspace writes | J, R | Pending |
| FR-28 | Network/model/provider/fixture-acquisition hooks instrumented | Exactly zero external requests/model calls/downloads, no fixture fallback or fabricated LLM turns; effective limits recorded zero | J, F, W | Pending |
| FR-29 | Timeout, package/request/result cap, slow transfer, exhausted retained capacity, disk full | Safe bounded refusal/failure; reservations count stage+delivery; prior evidence intact; no truncation/deletion | S, J, R | Pending |
| FR-30 | Crash before copy, during computation, before proof and after promotion | No partial visible result; original attempt preserved; incomplete outcome unknown/failed; complete proof discoverable without second calculation | J, R | Pending |
| FR-31 | Complete proof with failed catalogue delivery; repeat recovery; corrupt proof | Exact saved result delivered once with zero math/render rerun; corruption/rights change refused; no automatic worker retry | J, R | Pending |
| FR-32 | New analytical source/recipe alongside old research | Exact source-family dispatch, input-to-result-to-view reconciliation, plan/producer lineage; old recipe replays remain unchanged | N, W | Pending |
| FR-33 | Mutated metric, derivation pointer, series point, inventory, duplicate ID, input-readiness claim or scope gate | Reject receipt/result/native registration/delivery; no numeric value or completed-analysis claim merely because shape validates; no dangling references | S, N, R | Pending |
| FR-34 | Browser full/summary/missing-cash/stale-quote reports | Embedded native interface with interactive numerical graphs and exact tables; visible holds/periods/classification, readable grouped review items, keyboard/touch/mobile supported | B, N | Pending |
| FR-35 | Originals/download/reading/print copy | Same retained figures, assumptions and holds; no second dataset or image-only report; no missing review items from paging/filtering | N, B | Pending |
| FR-36 | Snapshot, fresh-folder restore, restored queue/recovery | Complete new-record inventory, hashes/links correct, new token, queues held, explicit permission/code release, original unchanged | R, J | Pending |
| FR-37 | Backup permission pending/denied; missing/unlisted snapshot members | Refused/incomplete protection stated; no silent exclusions or device-loss claim; no external transfer | R | Pending |
| FR-38 | Entire new path with current engineering regressions | Actual protected HTTP/import/job/native/download/restart run plus full Python/interface/build checks; measured volume/time and zero external calls | J, N, B, R, W | Pending |
| FR-39 | Technical success presented as completion | Review-required job/report, approval always false, no invented analyst recommendation/source authenticity or live LLM claim; production dependencies unchanged | N, B, W | Pending |

Human interpretation of a real-company report, source-use authorisation,
independent backup, encryption/key recovery, clean-machine recovery and authorised
Agent 4 company data are separate release dependencies. This matrix's synthetic
engineering acceptance cannot close them. Actual PDF/physical print acceptance
is also separate from the reading/print-copy content check.
