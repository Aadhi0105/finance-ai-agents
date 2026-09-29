# Agent 2: first live observation integration

Agent 2 can now fetch annual statements for an explicit watchlist independently
of its triage model. `--data-source yfinance` selects real observations;
`--live` still selects the paid triage model. Neither switch implies the other.
No missing provider result is replaced with fixtures.

## Stadler profile and issuer reconciliation

`watchlists/stadler-annual.json` defines three **illustrative analyst policies**, not
Stadler's contractual covenants. It requires CHF annual consolidated data and
issuer reconciliation. Limits are configurable examples, not investment or credit
recommendations. A profile claiming contractual status is refused: a verified
financing definition and reviewed implementation are still required.

The reference `references/monitoring/SRAIL.SW-2025-12-31.json` records selected
figures from [Stadler's 2025 annual report](https://www.stadlerrail.com/api/docs/x/518f589306/annual-report_2025_en.pdf),
printed pages 182–184 and 215, along with the PDF SHA-256. CHF-thousand amounts
were converted to base CHF. Tolerance is CHF 1,000, the filing's display unit.

| Metric | Reviewed calculation (CHF thousands) | Result | Example policy |
| --- | --- | --- | --- |
| Current ratio | 4,236,715 / 4,428,274 | 0.956742 | At least 1.0 |
| Operating interest coverage | 160,571 / (42,097 + 281) | 3.789018 | At least 3.0 |
| Net debt / operating EBITDA proxy | (433,906 + 505,737 − 664,190) / (160,571 + 117,880) | 0.989233 | At most 3.5 |

Interest includes finance-lease interest, but excludes bank charges and guarantee
costs. EBITDA is an accounting proxy rather than contractual adjusted EBITDA.
Current assets include work in progress and compensation claims. A low current
ratio alone does not establish financial distress or a financing covenant breach.

Two actual provider fetches on 29 September 2026 used the 31 December 2025 period.
The first created three baseline observations, including a current-ratio policy
breach. The second recognized duplicate observations instead of appending history.
No model call was needed: the existing baseline/unchanged-alert policy suppresses
new exception triage. Inspect full state to see the retained policy breach.

## Run it

From the repository, using the configured Python environment:

```bash
python monitor.py --once --data-source yfinance \
  --watchlist watchlists/stadler-annual.json \
  --db state/stadler-live.duckdb

python monitor.py --state --db state/stadler-live.duckdb
```

Repeat the first command to check for a newer annual period. Add `--live` to
request real-model triage if new exceptions are surfaced. Without it, triage is
scripted but the observations remain live. A saved cycle can be replayed with
`--catchup N` and the same data-source, watchlist and database arguments, without
another provider request or model call. Catch-up numbers count monitoring runs;
they do not request historical provider periods.

The initial integration supports live observations through --once and --catchup.
Live --run/--loop/--cron configuration is deliberately refused rather than silently
running fixture observations. No schedule or notification destination is installed.

## Data, state and failure contracts

- One bounded subprocess fetch per unique ticker, outside the database lock;
  each fetch times out after 60 seconds. There is no implicit source fallback.
- The latest annual income period anchors every required field. Other statement
  periods are not substituted. Missing fields, nonpositive denominators, future
  dates, unknown currency/units and expired reporting periods are unavailable.
- A profile sets its maximum reporting-period age. Stadler's example uses 550 days.
  This is a configurable annual-data policy, not proof that the latest interim
  report has been included. Annual-only ingestion intentionally ignores interim
  and trailing-twelve-month data. Publication dates remain unavailable.
- Each cycle saves all attempts, including failures and duplicate fetch evidence.
  New observations retain provider labels, raw inputs, retrieval timestamp,
  formula numerator/denominator, profile hash and issuer-comparison evidence.
- Stadler's reviewed profile refuses mismatched fields or periods without a new
  reviewed issuer reference. References apply per ticker, period and currency;
  the FY2025 comparison is never inherited by a later year. Unreviewed custom
  profiles must explicitly opt out of required reconciliation and remain labelled
  unreviewed in their evidence.
- Live and fixture databases cannot be mixed. Existing legacy state is treated as
  fixture data; live mode requires a separate database. Definitions, currencies,
  tickers, thresholds and formula revisions form the live series identity. A
  changed identity on an existing item triggers the existing persistent review hold.
- Provider failures preserve current state, record review_required coverage and
  produce CLI exit 3. Successful duplicate coverage advances the ledger without
  adding another observation. Paid-triage failure remains exit 2.
- All rows, evidence, review holds, source binding and cycle results commit in one
  transaction. Concurrent refreshes can result in a duplicate cycle, not a second
  copy of the observation. Failed cycles do not bind a fresh database's source.

The existing acceptance guide describes the prior fixture-only milestone. This
integration expands observation ingestion for the explicit supported profile;
it does not add correction approval/backfill, triage retry, notifications,
distributed operations or contractual-covenant interpretation.

## Verification

On 29 September 2026, **519 regression tests passed**, including 29 live-input
contract and integration cases. They cover period alignment, independent issuer
ratio calculations, source/currency/unit mismatches, stale/future periods, missing
or invalid inputs, duplicate refresh, replay without fetching, database separation,
provider failure, definition review holds, transactional source binding, source
labels in triage, and review exit status. Real baseline and duplicate-refresh cycle
records are retained locally in `output/agent2-live-validation/` alongside the
provider snapshot, issuer PDF and comparison reference. These outputs are ignored
by Git; the reviewed reference, watchlist, tests and implementation are versioned.
