# Agent 4 — controlled end-to-end closure acceptance

**Acceptance date: 5 October 2026. Status: passed for the bounded offline v1 workflow.**
This is a simulated 2026 EUR financial year, including a simulated December close;
it is not a real company's accounts or an observed future financial outcome.
No production-engine changes were required by this validation batch.

## Reproduce

```bash
python scripts/check_agent4_closure.py
AGENT_STATS_VIA_MCP=1 python scripts/check_agent4_closure.py
python -m pytest tests/test_agent4_closure_acceptance.py
```

Each run creates a fresh isolated database and artifacts under
`output/agent4-closure/`. An optional `--output-dir` must name a new directory;
existing data is never overwritten. `acceptance.json` records results, counters and
report paths; `parity.json` retains the financial evidence for cross-backend comparison.
The recovered HTML folder contains all 14 financial closes and their original JSON.
The history-gap case has its own database and report.

The source ledger and authored answer key are checked in at
`fixtures/agent4/closure/control-ledger.json`. Expected accounting is validated with
direct integer sums/subtraction. Expected projection points use an explicit assumption
schedule and exact rational arithmetic, without calling production roll-up, forecast,
persistence or formatting functions to generate the expected answers. Negative tests
deliberately corrupt answer-key values and confirm the verifier refuses them.

Projection agreement tests the implementation of declared assumptions. It does **not**
establish that those assumptions are economically accurate or that an 80% range has
80% empirical coverage. The persistence labels are provisional rule outputs, not
confirmed causes. The answer key's expected assumption schedule is specified in the
verifier, not chosen by reading the engine's observed classifications.

## Controlled sequence and results

The original plan is €1,000 sales and €600 costs per month. Twelve prior-year
observations supply a small alternating variance baseline. March sales include a
single €300 spike. Sales from May onwards are €1,100 per month. In July, February
sales are restated upward by €50, then the August–December sales plan is revised to
€1,150 per month. Costs remain €600 per month throughout.

| Control | Independent expected result | Outcome |
| --- | --- | --- |
| Original annual profit budget | €4,800 | Matched |
| March close profit / variance | €700 / +€300 | Matched |
| March normalized profit landing | €1,500 YTD + €3,600 remaining plan = €5,100 | Matched; provisional ONE_OFF, reversion unconfirmed |
| June persistence | Two consecutive substantial positive observations | AMBIGUOUS as expected |
| July profit landing | Round(€3,400 × €4,800 / €2,800) = €5,828.57 | Matched; provisional STRUCTURAL rule |
| July after February restatement | €3,450 YTD; landing €5,914.29 | Matched; unchanged observations retained |
| Revised annual profit budget | €5,550 | Matched; original plan retained |
| July after re-budget | Round(€3,450 × €5,550 / €2,800) = €6,838.39 | Matched; revised phasing explicitly selected |
| Simulated year-end sales / costs | €13,150 / €7,200 | Matched |
| Simulated year-end profit | €5,950 | Matched exactly |
| Closed-year target / outcome | €5,550 / hit | Deterministic 100%, zero remaining horizon |

All 12 monthly closes, plus the July restatement and July re-budget, have independent
checks for close profit, selected close budget, YTD profit, annual budget and projected
profit landing. Current variance appears exactly once in the analysis history. Root
headline amounts match the saved accounting controls. Eligible ranges contain their
landing; probabilities remain in [0,1] with their uncalibrated-model disclosures.
At year-end the range collapses to [€5,950, €5,950].

Forecast trajectories can change as provisional persistence classifications change.
For example, a two-observation pattern is ambiguous while a longer pattern can meet
the structural rule. Passing this sequence does not make those labels calibrated
estimates or resolve the economic assumptions behind carrying a variance forward.

## Refusal, versioning and recovery controls

- April first arrives without the cost observation. The close is refused, leaving
  financial versions unchanged. Retrying the same run/version labels with complete
  data succeeds; the failed and successful attempts remain in the attempt log.
- Every original January–July request is replayed. No financial rows or versions are
  duplicated; attempt records still capture the replay.
- A June close submitted after July is refused as stale. The late February figure
  is instead incorporated as an explicit correction of the current July close.
  This tests ordering policy, not a wall-clock delivery deadline or scheduler.
- The February sales-only restatement retains the unaffected cost observation and
  all other periods. The effective snapshot identifies sales from `restatement-feb`
  and costs from `actual-02`; the original February report still shows €400 profit.
- A formal new budget version changes future phasing. Old saved reports keep the
  original budget; all saved bundle fingerprints remain unchanged across later closes.
- JSON and HTML exports are deliberately pointed at a file where a directory is
  required. Both fail and record failed receipts while the December close remains
  committed. After closing and reopening the database, both exports recover. A
  repeated JSON delivery reproduces identical bytes and does not alter financial state.
- An auxiliary prior-history gap excludes July 2025. The gap remains explicit;
  persistence becomes UNKNOWN, and the forecast range/probability are withheld.

The primary sequence ends with **2 budget versions, 13 actuals versions, 14 forecast
versions and 14 saved closes**. The auxiliary gap case is separate and is not included
in those counters. Financial immutability here means the supported store/replay APIs;
local hashes are not authenticated protection against replacing the database itself.

## Verification evidence

- **930 repository tests passed**, including four new closure-acceptance cases.
- After strengthening the oracle to check every monthly projection, the four focused
  tests and complete local acceptance sequence passed again.
- Local and MCP execution matched exactly for **15 evidence snapshots**: all 14 closes
  and the gap case. Compared fields were request, bound hierarchy, complete report and
  source panels. Database timestamps, paths and code-identity metadata were excluded.
  The final expanded local oracle also matched that same MCP evidence.
- Browser review followed the recovered year-end report through the July restatement
  and original February report. All 14 history links were present. The visible source
  basis and year-end amounts matched the saved controls; no console errors appeared.
- Browser viewport overrides requested 1280×900 and 390×844; the in-app browser actually
  measured **984×692** and **300px width**, respectively, in this session. The narrow
  page width also measured 300px, with no page-level horizontal overflow. These are
  the measured review sizes, not claims of exact requested-device emulation.

Local evidence is retained in `output/agent4-closure/` (not committed). The final
local oracle run is `acceptance-g946bu9q/run/`; browser-reviewed recovered artifacts
are from the equivalent `acceptance-ggn4s9dy/run/`. Captures are
`year-end-desktop.jpg` and `year-end-narrow.jpg`.

## Completion statement and remaining boundaries

Agent 4 has passed bounded v1 acceptance for **offline, deterministic EUR,
calendar-year amount-based closes**, with approved-budget assertions, effective
restatements, provisional diagnostics, disclosed forecasts, saved evidence, HTML
reports and recovery. This supports using that specific completion statement rather
than claiming universal FP&A or unattended production readiness.

The broader unit-based decomposition library has its separate batch tests; this
amount-ledger acceptance does not validate a real ERP price/volume/mix feed.
No authorized internal-company dataset was supplied, so real-company validation is
still unverified. Public issuer filings cannot replace a confidential phased budget.
Forecast calibration/backtesting, external source authentication, ERP integration,
interactive approvals, fiscal calendars, multi-currency handling and scheduling are
separate work. They are not implied by this acceptance result.
