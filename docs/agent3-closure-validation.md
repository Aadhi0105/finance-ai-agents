# Agent 3 closure validation — issuer dates and retained prices

Validated on 2026-10-03 (India time), Python 3.11.9. The full deterministic suite
passed **736 tests**, including 10 closure regressions. This is bounded execution
acceptance, not completion of every Agent 3 capability or approval of an investment
forecast. The source plans are explicitly `validation_only: true`.

## Findings

Fresh ASML provider-date assembly succeeded with 12 events. The earlier Batch 2
ASML failure did not reproduce. Its original raw price inputs were not retained,
so the historical root cause remains undetermined. Current runs retain inputs;
assembly exclusions now additionally record the originating function and line,
without exception text, local variables or file paths.

The provider's latest ASML timestamp mapped to **2026-07-14** in Amsterdam, whereas
[ASML's Q2 2026 release](https://investor.asml.com/news-releases/news-release-details/q2-2026-financial-results)
is dated **July 15**. Provider timestamps therefore remain unverified. The baseline
is preserved rather than silently rewritten. The source-backed run selects five
other releases with explicit issuer-distributed publication times.

ASML's exceptional October 2024 event is deliberately excluded from the checked
set: its [issuer statement](https://www.asml.com/en/news/press-releases/2024/statement-relating-to-early-publication-of-our-q3-2024-results)
confirms early publication on October 15 rather than the planned October 16.
The first-publication time was not established here; a scheduled date is not a
substitute for the actual disclosure date.

## Issuer source checks

Every row links to its issuer-distributed release in the committed JSON plans:
[ASML](../fixtures/agent3_closure/asml-as-source-plan.json) and
[NVIDIA](../fixtures/agent3_closure/nvda-source-plan.json). Source timestamps use
Eastern Time converted with IANA timezones, including daylight-saving offsets.
Investor-call times are not used as announcement times.

| Listing | Release dates | Local release time | Expected event anchor |
|---|---|---|---|
| ASML.AS | 2025-01-29, 2025-04-16, 2025-07-16, 2025-10-15, 2026-01-28 | 07:00 Europe/Amsterdam | Same trading day |
| NVDA | 2024-08-28, 2024-11-20, 2025-02-26, 2025-05-28, 2025-08-27 | 16:20 America/New_York | Following trading day |

Both live runs assembled all five selected events with no rejected event records.
The ASML/AEX and NVIDIA/S&P 500 comparisons use provider Close with
`auto_adjust=False` on both legs. This checks compatible price-return computation;
it does not independently audit corporate actions or benchmark suitability.

`date_status` and `benchmark_status` are `source_checked`, design remains
`unverified`, and comparability is `validation_only`. A separate publication gate
rejects validation-only plans even if all other statistical conditions pass.
Automated source checking is never represented as human research approval.

## Acceptance results

| Check | Result |
|---|---|
| ASML fresh provider-date run | 12 events; held; old failure not reproduced |
| ASML issuer-date run | 5 events; 5 generated controls; held |
| NVIDIA issuer-date run | 5 events; 5 generated controls; held |
| Source timestamp/session/expected anchors | All 10 issuer events matched |
| Raw prices → 250 estimation returns and 3 event returns | All 20 event/control windows matched |
| Independent NumPy least-squares alpha, beta and CAR | All 20 windows matched |
| Local vs actual MCP statistics subprocess | Exact equality for both retained datasets |
| Offline bundle replay | Both matched; no provider/model calls |
| Held HTML export | No historical-quantile distribution published |
| Positive/null, timeout/failure, recovery and replay contracts | Deterministic regression suite; synthetic evidence, not live inference |
| ASML and NVIDIA current news | Both returned zero usable articles; live populated-feed acceptance not passed |
| Real FinBERT | Not run: optional torch/transformers absent; no model accuracy claim |

Repeated events from one issuer do not meet independent-event inference requirements.
Generated controls are not issuer-confirmed non-event dates. Calendar flags,
benchmark suitability, sampling and controls still require review. Descriptive CARs
are not recommendations or predictive results.

A subsequent bounded NVIDIA news diagnostic found HTTP **404**, a JSON object with
only `message`, and no `tickerStream`. The installed yfinance `get_news` method
converted that missing stream into `[]`. Thus these empty results are not evidence
that no news exists. A working populated provider response remains a follow-up;
this batch does not introduce an unvalidated provider fallback.

## Retained local evidence

Artifacts are ignored under `output/agent3-closure-validation/`; these identifiers
locate this machine's saved evidence, not portable files included in Git:

- Provider baseline: `baseline/f6b7e8967e6f4a79a30a97624f13fbc0/`
- ASML source dates: `asml-issuer/aa5e7fcbc2c349c8be2f3aeca78b6be0/`
- NVIDIA source dates: `nvda-issuer/e37a88e1e9ee499583792c80d8c9a631/`
- Independent verification: `asml-acceptance.json`, `nvda-acceptance.json`
- Replay and held HTML: `asml-replay.json`, `nvda-replay.json`,
  `asml-report.html`, `nvda-report.html`
- ASML empty-news run: `news-asml/103b4b25d93a484d877631466fe7a78f/`
- NVIDIA empty-news run: `news-nvda/363b30c319a046ae968a36dc1c49e318/`

Bundles record the base Git commit **and** hashes of the working Python sources;
live checks preceded the final closure commit. Replay compares retained values,
not current provider data or a guarantee of issuer-source authenticity.

## Reproduce

From the repository, using its Python environment:

```bash
python -m agent3.run_live ASML.AS issuer_date_validation --peers \
  --study-plan fixtures/agent3_closure/asml-as-source-plan.json \
  --db output/closure-asml.duckdb --output-dir output/closure-asml --timeout 180
python -m agent3.run_live NVDA issuer_date_validation --peers \
  --study-plan fixtures/agent3_closure/nvda-source-plan.json \
  --db output/closure-nvda.duckdb --output-dir output/closure-nvda --timeout 180
python -m scripts.check_agent3_closure <saved-bundle.json> --mcp --output <new-acceptance.json>
python -m agent3.bundles <saved-bundle.json> --output <new-replay.json> --html <new-report.html>
pytest -q
```

A held live run exits **3**, by design. Explicit empty `--peers` means target-only;
these checks require no model-proposed universe or paid LLM. New live runs may differ
or lack enough history. The independent verifier requires a validation-only source
plan with expected anchors; it is not a general eligibility approver. It checks the
retained provider prices, not an independent second price vendor.

## Remaining closure work

Restore/verify a populated live news source and review its actual classifications.
If real FinBERT is desired, install the optional runtime, pin a model revision and
validate real inference separately. An approved independent-issuer study remains
necessary before any publishable inferential result; these convenience samples do
not supply that approval. The unreproduced old ASML exception remains historical
uncertainty rather than a claimed root-cause fix.
