# Agent 1: financial correctness contract

Batch 1 covers ingestion, ratios, scenario DCF, annual trends, peer screening,
and consensus. Publication gates and narrative grounding are covered by
[Batch 2](agent1-evidence-validation.md). CLI completion states and report
lifecycle hardening remain separate work.

## Data and provenance

Financial amounts are in **base reporting-currency units**, not thousands or
millions. Prices carry quote currency and unit metadata. Each financial result
identifies its annual period and each component statement's period. The Yahoo
adapter selects the latest income-statement period and reads cash flow and debt/
cash only from that same period. Missing matches remain missing; it never borrows
another statement's latest column. These are provider period labels, which can
differ from the issuer's actual closing date (e.g. Yahoo labels Apple's FY2025
September 30; Apple reports September 27).

Retrieval timestamps are UTC. Unknown price/estimate publication dates remain
null; retrieval time is not represented as publication time. `fast_info` does
not expose an exact price timestamp, so its `as_of` remains null and the separate
`info` quote timestamp is explicitly labelled. Fixture retrieval timestamps are
null and the source is explicitly illustrative. Fixture dates and currencies
are declared assumptions, not assertions of audited data.

Zero is a real observation. Missing/non-finite provider values become null, and
alias lookup can try another field without replacing a valid zero. Analytical
inputs reject non-finite values, incompatible currencies/units, and explicitly
mismatched statement periods. Arithmetic overflow returns an error rather than
JSON Infinity/NaN. No implicit FX, minor currency-unit, or ADR conversion occurs.
When market cap, price, and shares are all present, a discrepancy greater than
5% between market cap and price × shares blocks the calculation for reconciliation.
This is a consistency screen, not proof that ADR/share classes are comparable.

## Cash flow and DCF

`FCFF = EBIT × (1 − tax rate) + D&A − capital expenditure − change in working capital`

- Capex is normalized to a non-negative outflow magnitude before analysis.
- Working capital uses **balance-change convention**: positive means cash
  absorption; negative means release. Yahoo's `Change In Working Capital` is
  a signed operating cash-flow contribution, so ingestion negates it. Both raw
  and normalized values are recorded. This aggregate can include non-current
  operating assets/liabilities; the output explicitly identifies that proxy.
- EBIT is used consistently for DCF and EV/EBIT. If Yahoo lacks EBIT but provides
  operating income, the proxy is explicitly labelled. A legitimate zero EBIT
  never triggers the fallback.
- An explicit tax-rate override must be finite in [0,1]. Otherwise an effective
  rate is used only with positive pretax income and a ratio in [0,1]. There is
  no silent 50% cap. A default 25% rate and missing-WC assumption of zero are
  returned as warnings. Tax losses do not automatically imply a tax benefit.
- Non-positive FCFF is outside this positive-cash-flow growth model's applicability.
- WACC is an analyst-supplied discount-rate assumption, **not an estimated WACC**.
  It must be positive and exceed terminal growth. Horizon is an integer 1–30
  (booleans rejected). Growth rates must be finite and greater than −100%,
  including bear/base/bull adjustments. Scenario weights must be finite,
  non-negative, contain all three scenarios, and sum to one.
- Year 1 uses the scenario's initial growth. With multiple forecast years,
  growth fades linearly to terminal growth in the final forecast year. With
  one forecast year, initial growth applies once, then terminal growth applies
  in the perpetuity. Cash flows use end-of-year discounting.
- Both debt and cash are required to bridge enterprise value to equity. Missing
  shares or price suppress the corresponding per-share/upside calculation.
  Genuine zero values remain zero. Negative residual equity is preserved as a
  distress diagnostic; negative share-price targets and weighted upside are
  withheld when any scenario has negative equity.
- Arithmetic uses full precision; displayed valuations are rounded afterwards.
  Scenario weights are analyst assumptions, not estimated probabilities.

### Working-capital verification

On 2026-09-25 the public Yahoo/yfinance AAPL annual statement reported FY2025
`Change In Working Capital = −25,000` (USD millions). Apple's issuer statement
provides the underlying operating-asset/liability adjustments:
`−6,682 −347 +1,400 −9,197 +902 −11,076 = −25,000`.
The cash-flow reconciliation is:
`112,010 +11,698 +12,863 −89 −25,000 = 111,482`.
Thus the provider number is a cash outflow contribution, and the FCFF contract
must subtract a normalized positive 25,000. The tests exercise this conversion
through the actual adapter and separately test cash release.

Sources: [Apple FY2025 financial statements](https://www.apple.com/newsroom/pdfs/fy2025-q4/FY25_Q4_Consolidated_Financial_Statements.pdf),
[Yahoo AAPL cash flow](https://finance.yahoo.com/quote/AAPL/cash-flow/),
[Damodaran: working capital in valuation](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/noncashwc.htm).
This verifies the adapter sign; it does not establish that the provider aggregate
is a company-specific normalized operating working-capital forecast.

## Ratios, history, peers, and consensus

Margins require positive revenue but can legitimately be below −100%. P/E and
EV/EBIT require positive earnings/EBIT. EV includes debt minus cash. YoY growth
requires comparable annual periods (350–380 days allows 52/53-week calendars).

Historical ingestion preserves exact dates, excludes duplicate-year/stub
observations, and computes CAGR on the latest consecutive sequence with positive
finite revenue. Empty oldest provider columns do not invalidate usable recent
years. Insufficient history has `available=false`, no CAGR, and an explicit reason.
`cagr_years` identifies the exact observations used. Growth-versus-history is
expressed in **percentage points**, not relative percent.

Peer screening preserves raw evidence, dates, exclusions and provider failures.
Each peer's market cap and earnings must use the same currency; different peers
may use different currencies because each P/E is dimensionless. Fiscal-period
differences and fewer than five usable peers are warnings. Two usable peers are
the minimum for the existing screening statistic. Median/MAD is primary, with
mean/standard-deviation fallback. If all peers are identical, the standardized
outlier verdict is **indeterminate**, with explicit deviation from the median;
it is not a statistical all-clear. Peer selection and business comparability
remain analyst responsibilities, and the metric uses annual earnings, not TTM.

Consensus is available only with a usable price target or current/forward
revenue/EPS estimate. A current price is not consensus. Non-finite estimates,
non-positive revenue/targets, and estimates explicitly backed by zero analysts
are excluded. Negative EPS estimates remain valid. Coverage is recorded where
available; missing coverage and publication dates are not invented. Historical
or arbitrary period labels do not make forward consensus available.

## Verification

Run `python -m pytest` after installing `requirements.txt` and
`requirements-dev.txt`. The regression suite includes independent one- and
two-year DCF benchmarks, weighted valuation, zero/distressed equity, malformed
inputs, currency/period mismatch, provider normalization, flat peers, partial
consensus, and history boundaries. Provider tests are deterministic doubles;
CI does not call Yahoo or a paid model. Controlled public-data checks were also
performed for ASML.AS and AAPL. Those live observations are not pinned forecasts
or recommendations.
