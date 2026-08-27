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

- `estimate_factor_exposure` (factor regression)
- `estimate_factor_exposure` (factor regression)
- **No MCP** — correct for Agent 1 (MCP enters at the spine, after Agent 1).
- **No shorts / ownership tracking** — separate market-structure tool by design.

---

## Agent 2 — Monitoring / surveillance (in progress)

Agent 1 analysed one thing, once (stateless). **Agent 2 watches many things,
repeatedly, and its job is detecting *change*.** It loops over a configured
watchlist on a cadence, checks each item against its rules, compares to last
cycle's stored state, classifies what changed, and reports only the exceptions.

**Built so far (deterministic spine):**
- Fixture covenant watchlist with per-item thresholds (`fixtures/covenants.json`).
- `threshold_check` — deterministic breach test (`tools/covenant_checks.py`); stays local.
- Persistent DuckDB state store — current-state + append-only history, long/tidy
  panel shape (`state/store.py`).
- Change classification — NEW_BREACH / WIDENING / IMPROVING / RESOLVED / KNOWN_STABLE,
  with cold-start baseline suppression (`state/classify.py`).
- `run_cycle()` — the atom (`scheduler/cycle.py`), exception-based reporting.
- **Statistical checks** (`tools/statistical_checks.py`) — the discipline-carrying set:
  - `anomaly_significance_check` — robust modified z-score (median/MAD): is the
    latest value a significant outlier vs the item's own history? (**statistics**)
  - `drift_check` — OLS value~time with a t-test on the slope + prediction band
    and cycles-to-breach projection: is there a real trend? (**econometrics**)
  - `breach_probability` — first-passage (barrier-crossing) probability of
    breaching within a horizon, from the item's drift + volatility (**probability**)
  - Together they catch a drift toward breach *before* the hard threshold, and
    only flag movement *toward* breach (not toward safety). These three become the
    MCP spine (shared with Agent 3), local for now.

```bash
python monitor.py --reset    # fresh start
python monitor.py --once     # one cycle (the atom); cycle 1 = baseline
python monitor.py --run 10   # demo: drift is flagged cycles before the hard breach
python monitor.py --state    # on-demand full-state view
```

**Model triage** (`monitoring/triage.py`) — after the deterministic cycle detects,
the model triages the flags: groups by entity, and DECIDES whether to re-check
ambiguous ones (`recheck_flag`) before escalating. The re-check verdict is
computed deterministically (corroborated / corroborated_but_verify / isolated /
weak) — the model decides *whether* to call it, never computes it. Reuses the
Agent 1 tool-use loop (`agent/loop.py`, `agent/models.py`) — the shared spine.

```bash
python monitor.py --once          # cycle + stub triage of any exceptions
python monitor.py --once --live   # cycle + real-model triage (needs ANTHROPIC_API_KEY)
```

**Robustness** (`state/store.py`, `scheduler/cycle.py`):
- **Transactional writes** — a cycle computes everything first (read-before),
  then writes history + current-state in ONE transaction (write-after); a
  mid-cycle crash rolls back and leaves last-good state intact.
- **Idempotency** — `UNIQUE(item_id, data_ts)` + `ON CONFLICT DO NOTHING`; the
  same observation is never double-recorded (safe re-runs / catch-up).
- **Freshness gating** — an item is skipped when its data hasn't advanced (a
  quarterly covenant re-checked daily is skipped on stale days — cadence stays
  coherent with the data's true update frequency).
- **Skip-to-now catch-up** — after downtime, `--catchup ASOF` processes the
  latest directly (missed cycles not replayed) and surfaces the gap so a breach
  isn't misread as fresh.

```bash
python monitor.py --catchup 9   # data jumped to cycle 9 after downtime
```

**Next:** thin scheduler wrapper (cron over `--once`); then extract the three
shared checks (anomaly / drift / breach_probability) to a stdio MCP server.
