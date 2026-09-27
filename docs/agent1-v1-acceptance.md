# Agent 1 v1 acceptance and operating boundary

Agent 1 v1 is an auditable, analyst-reviewed financial-evidence prototype.
Completion means supported inputs produce traceable calculations and reports,
and unsupported or insufficient evidence produces an explicit refusal or review
status. It does not mean every ticker receives an approved valuation.

## Supported scope

- Listed operating-company equities, with annual income, cash-flow and balance-sheet
  inputs in declared base currency units and aligned periods.
- Reporting and quote currencies must match. No automatic FX, pence-to-pounds,
  ADR ratio or share-class conversion. The market-cap consistency screen cannot
  prove ordinary-share equivalence; the analyst must verify it before using a value.
- Generic enterprise DCF applies only to positive reconstructed FCFF. Known
  Financial Services/Financials and Real Estate sectors, and known non-EQUITY
  instrument types, are refused by DCF. Ratios and historical evidence can still
  be retained. This conservative scope excludes banks, insurers, funds and property
  businesses from generic valuation; it does not provide their alternative models.
- Provider classification can be missing or wrong. It is saved for inspection and
  live financial data always warns that classification and share basis need review.
  Absence of an exclusion is not a suitability certificate.
- Negative earnings suppress P/E; non-positive operating profit suppresses EV/EBIT.
  Non-positive FCFF refuses DCF. Missing consensus may use historical comparison;
  history is not relabelled as an analyst forecast.
- Peer screening is descriptive. Business comparability, different fiscal periods
  and small samples remain analyst responsibilities.
- Only Python-rendered named numerical evidence is published. Unsupported prose
  is withheld, including apparently sourced model text and recommendations.

ASML FY2025 selected fields are independently reconciled against its US GAAP filing.
This is a period-specific reviewed reference, not automatic issuer verification
for all companies. See [issuer reconciliation](agent1-issuer-and-claims.md).

## Analyst review procedure

1. Read the execution status and validation banner. `completed` means the tool/model
   loop finished; it does not mean the evidence passed. Exit 3 and `report_REVIEW.html`
   require review. Missing calculations and explicit refusals are not zero values.
2. Check the listing, sector, ordinary-share basis, units, annual statement periods
   and accounting basis against issuer disclosures. Reconcile material inputs;
   do not copy ASML's adjustment into another issuer or period.
3. Verify quote observation time and estimate publication time from dated sources.
   Retrieval time does not establish freshness. If unavailable, leave unresolved.
4. Reconcile the current share count to its dated source and relevant share class.
   Year-end shares and weighted-average EPS denominators are different concepts.
5. Review the operating cash-flow reconstruction, tax and working-capital proxies,
   D&A, capex, debt/cash bridge and excluded non-operating assets. Set and justify
   growth, discount rate, terminal growth, horizon and scenario weights; these are
   assumptions, not estimated probabilities or an issuer-certified fair value.
6. Check peers and comparison dates, chart exclusions and omitted charts. Inspect
   the retained audit draft if needed, but independently source any qualitative claim.
7. Rebuild with `python run.py --rebuild <model.json>` to recheck stored evidence.
   Rebuild does not update market data or approve a human override. Use a fresh run
   for refreshed inputs. There is no manual approval switch: retain unresolved
   warnings and keep any human sign-off separate from machine validation.

## Closure verification

The bounded matrix combines live observations with deterministic failure cases.
Live providers cannot reliably supply a chosen missing-data condition on demand;
controlled missing-consensus tests and the complete offline history-fallback run
establish that branch without claiming that a live company lacked coverage.

Verified on **27 September 2026**, Python 3.11.9: **402 tests passed**.
The new tests cover sector/instrument refusals, negative earnings/FCFF, missing
provider consensus, classification retention and rejected-request recovery.

| Case | Observed outcome | Acceptance |
| --- | --- | --- |
| AAPL, live | 6 turns, 8 calls; grounded note; zero validation failures | Supported workflow completed; remaining quality warnings retained |
| RIVN, final live | 4 turns, 8 calls; negative net income; P/E unavailable; DCF explicitly refused for negative FCFF; grounded remaining evidence | Unsupported valuation refused; 11 gate failures retain review status |
| BRK-B, live | 5 turns, 8 calls; Financial Services classification; generic DCF explicitly refused; grounded remaining evidence | Sector boundary enforced; 7 gate failures retain review status |
| ASML.AS, complete offline | Consensus unavailable; usable own-history fallback; zero validation failures | Missing-consensus branch completed; illustrative data remains review-only |
| ASML.AS, prior live/filing review | 14 issuer checks, 19 grounded claims, zero validation failures | See [issuer review](agent1-issuer-and-claims.md) |

Every new run emitted a review report and five chart files; unavailable valuation
or peer charts can be labelled placeholders, not five successful analyses.
The complete live matrix had consensus available for all three issuers; no claim
is made that live missing-consensus behavior was observed.

The first RIVN run revealed a recovery defect: after correct DCF/peer refusals,
the model attempted forbidden peer-subject requests, and their errors replaced
valid RIVN financial evidence. Rejected ticker-mismatch requests now remain in
call history without mutating subject results; failed refreshes for the actual
subject still invalidate dependent calculations. The regression test covers both.
The first failed run is retained, and the final live rerun retained subject data
and published grounded evidence alongside the explicit valuation refusal.

All five new saved reports (including the initial RIVN run) rebuilt without changing
analysis, execution, call history, chart inputs or original drafts. HTML checks
verified the financial-evidence notice and absence of an approved report. AAPL's
valuation and index charts were visually inspected. Full browser layout inspection
was unavailable because browser policy blocked the local file URL; no browser
visual sign-off is claimed. Existing report-generation tests also pass.

Local evidence is under `output/agent1-closure`, `output/agent1-closure-final`
and `output/agent1-closure-offline`. A compact non-secret observation summary is
committed at `references/acceptance/agent1-v1-2026-09-27.json`; raw conversations,
logs and market snapshots remain in ignored local output. These observations do
not guarantee future model/provider behavior.

**Sign-off: Agent 1 v1 is functionally complete within the supported scope above.**
The remaining warnings and unsupported methods are explicit operating boundaries,
not waived checks. Full browser visual QA remains unverified; this does not change
the calculation, publication-control or refusal acceptance results.

## Accepted limitations and future work

Sourced qualitative claim retrieval/review, sector-specific valuation, automatic
FX/ADR conversion, issuer-wide filing normalization, a full operating-driver model,
company-specific WACC estimation and calibrated scenario probabilities are outside
v1. No profitability or investment-return prediction is certified. Live model and
provider responses remain variable; repeat checks when dependencies or models change.

Agent 2, the showcase and platform-wide audit have separate acceptance scopes.
