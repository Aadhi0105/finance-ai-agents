# Agent 1: issuer reconciliation and qualitative publication controls

This review uses ASML's 2025 US GAAP annual report, not its IFRS report. Source:
[ASML US GAAP annual report](https://ourbrand.asml.com/m/71076aaad607de4d/original/asml-2025-annual-report-based-on-us-gaap.pdf).
The reference stores the PDF SHA-256, printed page numbers, units, reviewed
figures and limitations. The report itself is not bundled into the repository.
The provider comparison uses the retained 2026-09-26 live snapshot and was also
checked against a fresh provider fetch during this work.

## Reconciliation

Amounts below are EUR millions unless labelled otherwise. These are historical
statement comparisons, not forecasts or investment recommendations.

| Field | Issuer / calculation | Provider snapshot | Finding |
| --- | ---: | ---: | --- |
| Revenue, p. 276 | 32,667.3 | 32,667.3 | Matches |
| Gross profit, p. 276 | 17,258.0 | 17,258.0 | Matches |
| Operating income, p. 276 | 11,301.4 | 11,301.4 | Matches |
| Provider EBIT, pp. 276, 299 | 11,406.1 pretax + 118.3 interest expense = 11,524.4 | 11,524.4 | Includes 223.0 interest income; not the operating basis |
| Net income, p. 276 | 9,609.4 | 9,609.4 | Matches; includes profit from equity-method investments |
| Pretax income / income-tax expense, p. 276 | 11,406.1 / 2,013.4 | Same | Matches; consolidated effective rate remains an operating-tax assumption |
| D&A, p. 281 | 1,025.9 | 1,025.9 | Matches; footnote includes some financing-related amortization |
| Capex, p. 281 | 1,573.6 PP&E + 57.6 intangibles = 1,631.2 | 1,631.2 | Matches cash purchases; not all investing cash outflows |
| Operating cash flow, p. 281 | 12,658.5 | 12,658.5 implied by provider FCF + capex | Reconciles |
| Provider FCF, p. 281 calculation | 12,658.5 − 1,631.2 = 11,027.3 | 11,027.3 | CFO-minus-capex, not automatically unlevered FCFF |
| Debt, p. 278 | 1,681.9 current + 2,709.0 noncurrent = 4,390.9 | 4,390.9 | Matches carrying amounts, not market value or principal maturities |
| Cash, p. 278 | 12,916.0 | 12,916.0 | Matches cash and cash equivalents; excludes short-term investments |
| Year-end issued/outstanding shares, p. 278 | 385,417,665 shares | 384,100,000 current provider shares | Different dates; **not reconciled** |
| EPS denominators, p. 276 | 388.5m basic / 388.9m diluted weighted-average shares | Current shares used by valuation | Different concepts; not interchangeable |

The cash-flow statement's operating-asset/liability contributions sum to the
provider's working-capital cash contribution:

`1,415.5 − 227.2 − 832.5 − 561.9 − 237.3 + 13.4 + 334.1 + 1,122.4 = 1,026.5`.

The 334.1 term is **current tax assets and liabilities**. Excluding it gives an
operating cash contribution of 692.4, or a normalized balance change of **−692.4**
for the FCFF formula. The original aggregate was not pure operating working
capital. The cash-flow reconciliation also holds:

`9,609.4 + (1,025.9 + 49.7 + 202.3 + 469.4 + 180.7 + 94.6) + 1,026.5 = 12,658.5`.

## Changes to calculation inputs

The live adapter now prefers operating income for the operating EBIT input,
retaining Yahoo's separate EBIT as `provider_ebit`. Missing operating income may
use provider EBIT only as an explicitly warned proxy. Legitimate zero operating
income stays zero. Existing synthetic fixtures are not silently rewritten.

The ASML FY2025 profile applies the current-tax adjustment only when ticker,
period and currency match and all reviewed scalar inputs and the working-capital
aggregate reconcile. Tolerance is EUR 100,000 in base units, reflecting the
filing's EUR 0.1m display precision. A mismatch preserves the observed data,
records failed comparisons and returns an error; the tax adjustment is withheld.
Future periods and other issuers do not inherit this adjustment. Their operating
working-capital split remains unverified and explicitly warned.

With the retained snapshot and the same tax-rate assumption, FCFF changes from
EUR 9,911.318m to **EUR 9,393.582m**:

`11,301.4 × (1 − 2,013.4 / 11,406.1) + 1,025.9 − 1,631.2 + 692.4`.

Holding the original default DCF assumptions and shares fixed, the calculated
scenario-weighted value changes from EUR 626.54 to EUR 594.97 per share. This is a
model-impact comparison, not an independently established fair value.

Remaining economic limitations are recorded alongside the reconciliation:
D&A includes financing-related amortization; the residual operating-asset/liability
aggregate still includes finance receivables and broad other assets; consolidated
effective tax is a proxy for operating tax; and debt-minus-cash is not a full
valuation of non-operating investments, associates or loans. Matching historical
numbers does not make a forecast or simplified valuation model issuer-verified.

## Qualitative claim control

There is no semantic truth-checker or issuer-document retrieval tool available
to the research model. A URL supplied by the model is not verification. Therefore
publication uses a strict **named-evidence-only** policy:

- Only standalone, available `[[claim:ID]]` markers become Python-rendered statements.
- Free-form prose, headings, company claims, market predictions and buy/sell/hold
  recommendations are withheld from the report, regardless of wording or citations.
- The exact original template and withheld lines stay in `model.json`; the model
  conversation is unchanged. Withheld content requires review.
- Numerical grounding is still assessed against the original draft. Withholding
  prose does not erase numerical failures or manufacture financial approval.
- The report displays a fixed explanation of the publication boundary and calls
  the section “Financial evidence.” Rebuilds apply the same policy to older records.
- Even a numerically approved report does not claim semantic verification of an
  investment thesis. The model selects evidence; it does not certify facts by
  writing them fluently.

This intentionally withholds unsourced interpretation rather than pretending
that deterministic keyword checks can verify it. Publishing sourced qualitative
facts would require a separate reviewed-source and claim-support interface; that
capability is not claimed here. Human analysts can inspect the audit draft and
independently verify it outside the approved evidence section.

## Reproducible evidence

- `references/issuer/ASML.AS-2025-12-31.json`: reviewed issuer figures, calculations,
  scope, pages and document digest.
- `references/issuer/ASML.AS-provider-2026-09-26.json`: retained provider inputs,
  observation limitations and source-run commit; no API credentials or model prose.
- `tests/test_agent1_issuer_claims.py`: statement identities, saved-input
  reconciliation, FCFF benchmark, mismatch refusal, period/currency isolation,
  operating-income selection, and prose/citation/rebuild controls.

Run `python -m pytest tests/test_agent1_issuer_claims.py -q` without a network or
API key. The tests exercise the retained provider observation against separately
transcribed issuer numbers; they do not download a changing filing during CI.

## Verification on 27 September 2026

- Full offline suite: **392 passed** on Python 3.11.
- Fresh live provider data: all **14 issuer reconciliation checks matched**.
- Complete live LLM research run: **4 model turns, 8 tool calls, 5 charts**;
  execution completed with **0 validation failures** and **19 grounded claims**.
- The model still supplied prose despite the marker-only instruction. Publication
  withheld **25 lines**, including unsupported competitive and market assertions;
  the original draft remains in the audit record. This verifies that enforcement
  does not depend on model obedience.
- Offline rebuild preserved analysis, execution, tool history, chart inputs and
  original draft; unsupported prose remained absent from the HTML.
- Final status remains **flag_for_review**, reflecting unknown observation dates,
  current-share comparability, FCFF proxies, valuation assumptions and peer limits.
  Completion is not financial approval or verification of qualitative claims.

Local live artifact (ignored by Git):
`output/agent1-issuer-claims/ASML.AS_20260927T062639.617631+0000_312e2a780a68/report_REVIEW.html`.
