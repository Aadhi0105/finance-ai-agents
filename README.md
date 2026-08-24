# finance-ai-agents

Three finance/quant agents on one shared engine. This repo currently contains
**Agent 1 — Equity Research**, at its build skeleton: a hand-rolled agent loop
that calls deterministic Python tools, proven end-to-end.

> **Governing principle: the LLM never does the math.** Every number comes from a
> deterministic Python tool. The model decides *which* tool to call, *reads* the
> result, and *writes* the view. This is the difference between a system whose
> figures you can audit and a toy that invents them.

## What runs today (skeleton)

The loop, wired end-to-end through **one** data tool and **one** analytical tool:

- `get_financials` (fetcher) → `compute_ratios` (computation) → written note.
- Runs **fully offline** with a scripted model and fixture data — no API key,
  no network — so the loop's mechanics are proven independently of the model.

```bash
python run.py                # offline: scripted model + fixture data (prints the trace)
python run.py --live ASML.AS # live: Claude Sonnet decides the sequence, data via yfinance
```

Live mode needs `pip install -r requirements.txt` and `ANTHROPIC_API_KEY`.

## Layout (flat, per spec §3.2)

```
agent/       loop.py (orchestrator) · models.py (Stub/Anthropic) · state.py (working memory)
tools/       registry.py · data.py (fetchers) · analytical.py (computations)
validation/  (confidence gate — next checkpoint)
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

- `get_prices`, `run_dcf`, `estimate_factor_exposure`, `peer_outlier_check`
- the 5-chart visual layer + `report.html` / `model.json` / `charts/`
- the validation/confidence gate
- **No MCP** — correct for Agent 1 (MCP enters at the spine, after Agent 1).
- **No shorts / ownership tracking** — separate market-structure tool by design.
