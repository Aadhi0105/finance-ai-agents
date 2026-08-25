# finance-ai-agents

Three finance/quant agents on one shared engine. This repo currently contains
**Agent 1 — Equity Research**, at its build skeleton: a hand-rolled agent loop
that calls deterministic Python tools, proven end-to-end.

> **Governing principle: the LLM never does the math.** Every number comes from a
> deterministic Python tool. The model decides *which* tool to call, *reads* the
> result, and *writes* the view. This is the difference between a system whose
> figures you can audit and a toy that invents them.

## What runs today

The loop drives five tools across two families, exercising all three disciplines
the build spec assigns Agent 1:

| Tool | Family | Discipline it carries |
|------|--------|-----------------------|
| `get_financials` | data | — |
| `get_prices` | data | — |
| `compute_ratios` | analytical | econometrics-lite (margins, growth, P/E, EV/EBIT) |
| `run_dcf` | analytical | **probability** — two-stage scenario-weighted (bear/base/bull) |
| `peer_outlier_check` | analytical | **statistics** — median/MAD robust outlier test (mean/z alongside) |

Every number is computed in Python; the model chooses which tool to call and
reads the result. Every DCF and peer assumption is returned in the tool output,
so a reviewer can audit exactly what drove each figure.

```bash
python run.py                # offline: scripted model + fixture data (prints the trace)
python run.py --live ASML.AS # live: model decides the sequence, data via yfinance
```

Live mode needs `pip install -r requirements.txt` and `ANTHROPIC_API_KEY` (loaded
from a gitignored `.env`).

**DCF v2:** the DCF uses real free cash flow (net income only as a logged
fallback), a two-stage model (growth fading linearly to terminal over a 10-year
horizon), and a net-debt bridge to equity value. Every assumption is returned in
the run output. It is not tuned to match market price — a defensible method can
still show a stock above or below its DCF intrinsic value.

## Layout (flat, per spec §3.2)

```
agent/       loop.py (orchestrator) · models.py (Stub/Anthropic) · state.py (working memory)
tools/       registry.py · data.py (fetchers) · analytical.py (computations)
validation/  gate.py — deterministic confidence gate (pass / flag-for-review)
fixtures/    offline sample data
output/      per-run artifacts (gitignored)
run.py       entry point
```

## The offline/live switch

| Piece  | Offline (this sandbox / CI)     | Live (your Mac)                       |
|--------|----------------------------------|----------------------------------------|
| Model  | `StubModel` (scripted turns)     | `AnthropicModel` (claude-sonnet-4-6)   |
| Data   | `fixtures/*.json`                | `yfinance` (`AGENT_DATA_SOURCE=yfinance`) |

Same loop, same tools, same tool-use protocol in both. Only the model and the
data source change.

## Skill / JD language this demonstrates

Financial modelling, valuation, corporate finance; agentic tool-use with
deterministic, auditable computation. Full mapping in the build spec.

## Not here yet (deliberate)

- `get_consensus` + its null-fallback branch — the first real *decision* fork,
  where the loop stops being a clean pipeline. Next checkpoint, built deliberately.
- `estimate_factor_exposure` (factor regression)
- `get_consensus` decision-branch
- `estimate_factor_exposure` (factor regression)
- **No MCP** — correct for Agent 1 (MCP enters at the spine, after Agent 1).
- **No shorts / ownership tracking** — separate market-structure tool by design.
