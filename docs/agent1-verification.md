# Agent 1 verification — Batch 4

Scope: regression coverage, full fixture execution, controlled live-provider
observations, and an accurate account of what these checks establish. This is
Agent 1 remediation, not completion of the repository-wide audit or Agent 2.

## Acceptance coverage

| Contract / original failure | Executable evidence |
| --- | --- |
| Nonfinite inputs, negative shares, currency/unit mismatch, incompatible statement dates, preservation of zero | `test_agent1_financial_correctness.py`, `test_integrity.py` |
| Working-capital cash absorption/release and provider normalization | `test_agent1_financial_correctness.py` |
| Independent DCF arithmetic, net-debt bridge, scenario weights and per-share output | `test_agent1_verification.py::test_full_dcf_against_hand_calculated_benchmark`, `test_dcf.py` |
| One-year horizon, zero/negative equity, tax assumptions | `test_agent1_financial_correctness.py` |
| Degenerate peers, exclusions, consensus availability, historical periods | `test_agent1_financial_correctness.py`, `test_peers.py` |
| Missing/errored/stale evidence, dates and numerical reconciliation | `test_gate.py`, `test_agent1_evidence_integration.py` |
| Wrong metric, sign, currency, numeric prose and named evidence markers | `test_grounding.py`, `test_agent1_evidence_integration.py` |
| Invalid arguments, truncation, iteration cap, interruption, model/tool failure, checkpoint failure | `test_agent1_execution.py` |
| Immutable snapshots and invalidation after upstream refresh | `test_agent1_execution.py` |
| Chart acquisition/render failure, atomic writes, rebuild locking, stale report cleanup | `test_agent1_reporting.py` |
| Actual CLI in a different directory, hostile ambient live settings, no live imports, real PNGs, rebuild, cross-process numerical reproducibility | `test_agent1_verification.py` |
| A complete valid record publishes; damaged evidence revokes approval on rebuild | `test_agent1_verification.py::test_real_report_approval_is_revoked_after_evidence_damage` |
| Requested peer set enforced before fetching; unknown record version requires review; nonfinite chart history cannot corrupt saved analysis | `test_agent1_verification.py` |
| Real offline sidecar/report emission and shared-system regression coverage | `test_smoke.py`, full test suite |

The full-value DCF example is hand-calculated: FCFF 1,500; two-year forecast;
6%/10%/14% initial growth fading to 2%; 10% discount rate; enterprise values
19,875/20,625/21,375. After net debt 400 and 20 shares, values are
973.75/1,011.25/1,048.75. Weights 20%/50%/30% give 1,015 per share and 103%
upside to a 500 price. The test calls the public calculation, not its internal
valuation helper. This is synthetic arithmetic, not an investment recommendation.

The CLI acceptance test launches separate interpreters with different hash seeds
and forbids importing yfinance or Anthropic. It checks real JSON/HTML/PNG outputs
and compares financial results, chart inputs, and grounded notes. Timestamps,
run IDs, durations and environment-dependent image bytes are not claimed to be
identical. The old misleading sidecar smoke test now actually emits a sidecar.
Tests isolate fixture selection from the caller's environment.

## Controlled provider observations

On **2026-09-25 UTC** (2026-09-26 India time), bounded checks exercised the real
financials, prices, consensus, annual-trend and one-month-history adapters for
**AAPL** and **ASML.AS**. No Anthropic call or credential was used. All five
adapters returned data for both symbols; this establishes connectivity and the
observed payload contract, not provider accuracy or future availability.

| Observation | AAPL | ASML.AS |
| --- | --- | --- |
| Provider latest annual period label | 2025-09-30 | 2025-12-31 |
| Income/cash-flow/balance-sheet periods | Aligned | Aligned |
| Reporting and quote currencies | USD / USD | EUR / EUR |
| Price × shares vs market-cap contract | Passed | Passed |
| Usable analyst estimates and historical trend | Returned | Returned |
| Price observation timestamp | Unavailable | Unavailable |
| Consensus publication timestamp | Unavailable | Unavailable |

The working-capital normalization record preserves both the provider cash-flow
contribution and its negated balance-change input. These observations do **not**
independently reconcile the latest statements to issuer filings; see the prior
[financial-contract evidence and limitations](agent1-financial-contract.md).
A retrieval timestamp is not an observation/publication timestamp. The ordinary
publication gate still requires review for those missing dates and model defaults.

Local versions during these checks: yfinance 1.7.0, pandas 3.0.6, matplotlib
3.11.2, pytest 9.1.1. The diagnostic saves the actual evidence locally so future
runs can be compared. Provider data is intentionally not committed as permanent
truth or included in deterministic CI.

Reproduce an **opt-in network check** from the repository root:

```bash
python -m scripts.check_agent1_live --ticker AAPL --timeout 20 --output output/AAPL-provider-check.json
```

Each adapter gets a separate subprocess deadline. The diagnostic saves each
result atomically, labels missing data/timeouts, and does not print provider
stderr. Exit 1 means an unavailable/failed operation; exit 0 means every worker
returned a usable diagnostic, which may still say `review`. Neither exit approves
a valuation. This command is deliberately excluded from CI.

## Small defects found and corrected during verification

- A CLI-specified peer list was only a prompt instruction. Dispatch now rejects
  a changed or duplicated peer set before any peer-data request.
- Nonfinite chart-history data could fail strict JSON persistence after analysis
  completion. The acquisition boundary now validates the full payload first,
  records the failure, and preserves the existing analysis.
- A missing target P/E crashed annotation formatting. Unavailable peer evidence
  now renders an explicit placeholder; the financial gate still requires review.
- Unknown saved-record schema versions could be treated like current records.
  Publication now requires version 2; legacy/unknown versions require review.
- The unavailable DCF placeholder no longer claims that enterprise value was
  successfully computed when the DCF itself failed.

## Verification boundary and remaining limitations

Local result: **346 tests passed on Python 3.11.9**, including a complete suite
run with ambient `AGENT_DATA_SOURCE=yfinance` to exercise fixture isolation.
Run `python -m pytest -q` for deterministic regression and acceptance checks.
CI now declares Python 3.11 and 3.12 jobs; their remote results must be checked on
the Batch 4 PR. Local results do not establish that both CI environments passed.
No line-coverage percentage or exhaustive proof is claimed by the matrix above.

No paid live-model run was performed. Model behavior is tested with protocol
responses/doubles; full live research remains sensitive to model choice, provider
availability, missing fields and peer selection. Approval checks numerical and
execution evidence, not the economic truth of qualitative prose. There is no
company-specific WACC estimator, operating-driver forecast, automatic FX/ADR
conversion, calibrated scenario probabilities, or peer-implied price model.
Missing data and unsuitable DCF inputs still require review or refusal.

Batches 1–4 address the agreed Agent 1 remediation scope with these explicit
limits. The showcase, other agents and platform-wide integration still require
their scheduled audit phases; they are not certified by these tests.
