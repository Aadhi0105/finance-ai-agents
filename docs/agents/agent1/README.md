# Agent 1 · Company research and valuation

[Project guide](../../../README.md) · [Agent 2](../agent2/README.md) · [Agent 3](../agent3/README.md) · [Agent 4](../agent4/README.md)

## Contents

- [What is this agent?](#what-is-this-agent)
- [Why this agent?](#why-this-agent)
- [What does it do?](#what-does-it-do)
- [Simple example: researching a manufacturer](#simple-example-researching-a-manufacturer)
- [When should you use it?](#when-should-you-use-it)
- [Getting started](#getting-started)
- [Modes and configuration](#modes-and-configuration)
- [Calculations and evidence controls](#calculations-and-evidence-controls)
- [Outputs and analyst review](#outputs-and-analyst-review)
- [Recovery and exit codes](#recovery-and-exit-codes)
- [Validation and implementation](#validation-and-implementation)

## What is this agent?

Agent 1 builds a financial-evidence report for a listed company. It brings together
statements, prices, historical performance, selected peers, and explicit valuation
assumptions so an analyst can inspect them in one place.

It helps answer: **How is the business performing, how does it compare with the
chosen peers, and what value follows from the stated cash-flow assumptions?** It
is a research aid, not an automatic investment recommendation or a replacement
for reading the issuer's filings.

## Why this agent?

A manual research pass involves collecting statements, aligning periods and
currencies, computing ratios, checking peers, building a valuation, and writing
up the results. Small inconsistencies can propagate into an apparently polished
report: a missing cash balance can distort equity value, or an unsuitable earnings
denominator can produce a misleading multiple.

This agent makes those assumptions and gaps explicit. It saves the underlying
evidence and execution record, computes figures in Python, and withholds report
claims that cannot be tied to supported evidence. The benefit is a repeatable,
inspectable research starting point.

## What does it do?

1. Gather company financials, prices, and available estimates.
2. Normalise financial inputs and check period, unit, ticker, and currency contracts.
3. Compute eligible ratios, trends, cash-flow valuation, and peer diagnostics.
4. Let the live model select tools and propose a research draft within the workflow.
5. Validate numerical and qualitative claims against retained evidence.
6. Save a machine-readable record, charts, and a standard or review-required HTML report.

Missing consensus can lead to a historical-trend analysis. Historical results stay
labelled as history; they do not become analyst forecasts. Without explicit live
peers the model selects peers, but neither selection path proves comparability.

## Simple example: researching a manufacturer

**Illustrative numbers, not an issuer result.** Suppose revenue increases from
€900 million to €1 billion and operating profit is €120 million. Python can show
11.1% revenue growth and a 12% operating margin. The analyst can then compare the
margin and eligible valuation multiples with selected manufacturers.

Next, the cash-flow model applies explicit growth, discount-rate, and terminal
assumptions. Its output is conditional on those assumptions. If debt is known
but cash is missing, the agent cannot complete the enterprise-to-equity bridge
by assuming cash is zero. If reconstructed free cash flow is unsuitable for the
generic DCF, it withholds that valuation instead.

The analyst receives the figures, assumptions, excluded evidence, and review
reasons. This helps identify what to investigate: for example, whether a margin
change is durable. The arithmetic alone does not establish its business cause,
and unsupported model explanations are not published as fact.

## When should you use it?

Use it for an initial, evidence-backed review of a listed operating company with
usable annual statements and compatible quote/reporting currencies. Check the
actual listing and provider coverage before relying on a ticker.

The generic enterprise DCF excludes financial-services/financials, real-estate,
and non-equity cases. Negative or zero denominators can make individual multiples
unavailable. There is no automatic FX, pence conversion, ADR ratio, or share-class
reconciliation. The DCF is a two-stage scaffold, not a complete three-statement
operating model. A report may still retain useful history when valuation is held.

## Getting started

Install the [shared prerequisites](../../../README.md#install-and-configure).
Run from the repository root:

```bash
python run.py --offline ASML.AS --output output/readme-agent1
```

Offline mode forces fixtures, uses the scripted model, and does not load `.env`.
It needs no API key or provider connection. The default command `python run.py`
also selects offline ASML.AS. An illustrative run normally exits **3** and creates
a review report; inspect the printed output path.

For live research, configure `ANTHROPIC_API_KEY` locally first. This command makes
provider requests and paid model calls:

```bash
python run.py --live ASML.AS --peers ASM.AS BESI.AS LRCX   --output output/asml-research --trace
```

These peers demonstrate syntax; independently assess business mix, accounting,
periods, and valuation comparability. `--peers` is live-only and enforces the
requested set at dispatch. Omit it to allow model selection.

## Modes and configuration

| Option | Behaviour |
| --- | --- |
| `--offline TICKER` | Bundled fixtures; use a ticker actually available in `fixtures/` |
| `--live TICKER` | Live model and yfinance data; missing credentials fail explicitly |
| `--rebuild MODEL_JSON` | Revalidate and render saved evidence without provider/model calls |
| `--peers TICKER ...` | Explicit live peer universe |
| `--output PATH` | Root directory for a new run |
| `--trace` | Print tool/execution progress |
| `AGENT_MODEL` | Override the configured Anthropic text/tool-use model |

The three modes are mutually exclusive. Prefer explicit modes in scripts. Live
credentials may be loaded from the local `.env`; never add that file to Git.

## Calculations and evidence controls

| Area | Method and important boundary |
| --- | --- |
| Statements | Explicit units, currency, periods, finite inputs, provider working-capital normalisation |
| Ratios | Margins, growth and eligible multiples; nonpositive earnings/operating-profit denominators are suppressed where required |
| Enterprise value | Market capitalisation plus debt minus cash; missing sides of the bridge are not silently zero |
| DCF | Reconstructed FCFF, two-stage fade, bear/base/bull scenarios; invalid discount/terminal assumptions refused |
| Peers | Robust median/MAD diagnostics; small samples and economic comparability remain analyst concerns |
| Trends | Own-company historical evidence; excluded observations and internal gaps remain visible |
| Published note | Named numerical evidence rendered by Python; unsupported numerical or qualitative prose withheld |

The live draft can receive at most one numerical-grounding correction request.
Rejected revisions fall back to labelled evidence statements, with unsupported
interpretation withheld. The original model text and audit evidence remain saved.
Passing a calculation check does not prove the provider input matches a filing.
See the separate issuer checks below.

## Outputs and analyst review

Each run has a unique directory containing:

| Artifact | How to use it |
| --- | --- |
| `model.json` | Evidence, configuration, conversation/tool history, provenance, execution and validation status |
| `report.html` or `report_REVIEW.html` | Readable analysis; the review variant is explicitly restricted |
| `charts/` | Up to five chart families, with unavailable/failed content labelled rather than silently invented |

Charts cover price/index, moving averages, volatility/drawdown, peer multiples,
and valuation where eligible. Inspect periods and excluded observations; a chart
that ends early is not evidence of continuous coverage.

Before relying on a report, review listing/currency, statement dates, source
quality, cash-flow reconstruction, peer suitability, valuation assumptions, and
all withheld sections. Any quality warning requires review. There is no manual
switch that turns inadequate evidence into an approved report.

## Recovery and exit codes

Replace the placeholder with the exact saved file printed by the run:

```bash
python run.py --rebuild /path/to/model.json --output output/rebuilt-research
```

Rebuild uses saved evidence and current validation/rendering code. It does not
refetch data or resume a model conversation. Revalidation, age-sensitive checks,
and renderer changes mean this is not a byte-identical historical reproduction.
Legacy records without explicit completion evidence remain review-required.

| Exit | Meaning | Action |
| --- | --- | --- |
| 0 | Completed, approved evidence and successful artifacts | Inspect report assumptions and scope |
| 1 | Execution/artifact failure, including chart failure | Inspect saved execution record and filesystem error |
| 2 | Invalid CLI usage | Correct arguments |
| 3 | Completed with artifacts; financial review required | Read review reasons; do not treat as a clean publication |
| 4 | Incomplete execution without artifact failure | Inspect the checkpoint and missing evidence |
| 130 | Interrupted | Inspect saved state before starting another attempt |

| Symptom | Next step |
| --- | --- |
| Missing API key | Configure local credentials and select live mode explicitly |
| Company or peer data unavailable | Verify listing/provider coverage; do not substitute another listing silently |
| DCF withheld | Inspect FCFF, sector eligibility, currency, and bridge completeness |
| No consensus | Use labelled historical context; do not relabel it as estimates |
| Report marked REVIEW | Read the evidence reasons; fixing layout alone cannot clear financial holds |
| Saved analysis but broken chart delivery | Preserve `model.json`, resolve output access, then rebuild |

## Validation and implementation

Bounded acceptance covers offline runs, selected live companies, financial edge
cases, explicit peers, report failure paths, and saved-evidence rebuilding. Selected
ASML FY2025 filing checks validate particular inputs, not all issuers or periods.
Comprehensive Agent 1 browser acceptance remains unverified in the v1 record.

- [Financial contracts and model limits](../../agent1-financial-contract.md)
- [Numerical evidence validation](../../agent1-evidence-validation.md)
- [Execution, checkpoints and reporting](../../agent1-execution-reporting.md)
- [Verification record](../../agent1-verification.md)
- [Issuer reconciliation and qualitative claims](../../agent1-issuer-and-claims.md)
- [Bounded v1 acceptance and review procedure](../../agent1-v1-acceptance.md)

Implementation starts at `run.py`; `agent/` owns the loop/models, `tools/data.py`
and `tools/analytical.py` own research inputs/calculations, `validation/` owns
publication controls, and `composer.py` produces artifacts. Run the repository
regression suite using the [project testing instructions](../../../README.md#validation-and-current-scope).
