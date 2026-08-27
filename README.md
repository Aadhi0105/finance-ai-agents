# finance-ai-agents

A multi-agent platform for finance & markets analysis, built on one shared
analytical spine. Two agents run today — an **equity-research** agent that turns a
ticker into an auditable fundamental view, and a **covenant-monitoring** agent
that watches many items over time and detects change — with their shared
statistical tools exposed over an **MCP server**.

> **Governing principle: the LLM never does the math.** Every number — every DCF,
> regression, z-score, and probability — comes from deterministic Python. The
> model decides *which* tool to call, *reads* the result, and *writes* the
> narrative. It never computes in its head. For a finance audience this is the
> whole difference between a system whose figures you can audit and a toy that
> invents them.

This is a **platform, not a pipeline**: the agents are siblings on a shared
foundation, not stages in a chain. They have different triggers and cadences (one
is on-demand per ticker, the other is scheduled over a watchlist), and they share
tools and conventions rather than feeding one another.

---

## Quickstart

```bash
pip install -r requirements.txt
```

**Agent 1 — equity research** (single ticker -> report):

```bash
python run.py                 # offline: scripted model + fixture data, prints the full trace
python run.py --live ASML.AS  # live: the model decides the tool sequence, data via yfinance
```

Live mode needs `ANTHROPIC_API_KEY` (loaded from a gitignored `.env`). A run
writes `report.html`, `model.json`, and `charts/` to a per-run `output/` folder.

**Agent 2 — covenant monitoring** (watchlist -> change detection over cycles):

```bash
python monitor.py --reset      # fresh state
python monitor.py --run 10     # run 10 cycles; drift is flagged before the hard breach
python monitor.py --once       # one cycle, with model triage of any exceptions
python monitor.py --state      # on-demand full-state snapshot
python monitor.py --catchup 9  # skip-to-now after downtime, surfacing the gap
```

Run the same monitoring cycles with the statistical checks served over MCP
instead of in-process — the output is byte-identical:

```bash
AGENT_STATS_VIA_MCP=1 python monitor.py --run 10
```

---

## The shared spine

Four things are reused across every agent — this is what makes it one platform
rather than three scripts that happen to rhyme:

- **Data access** — prices and fundamentals via `yfinance` (EU *and* US tickers:
  `ASML.AS`, `SAP.DE`, `AAPL`, ...). Analysing a European name is a ticker choice,
  not a plumbing project.
- **Agent loop** — one *plan -> call tool -> observe -> decide -> repeat*
  controller, hand-rolled on the raw Anthropic tool-use API (no framework).
  Written once in `agent/loop.py`; Agent 2's triage reuses it.
- **Analytical tools** — the computations (DCF, robust peer stats, anomaly
  significance, drift, breach probability). Skill made callable. Built as local
  Python, and the shared ones are lifted to an MCP server once a second agent
  consumes them.
- **Validation / confidence layer** — scores outputs and gates low-confidence
  results to human review, rather than emitting them blindly.

---

## Agent 1 — Equity Research

Give it a ticker; it produces a defensible, auditable fundamental view — the draft
a junior analyst would produce, numerically grounded and self-flagging, not an
oracle. It is deliberately the *least* agentic of the platform: the loop is
constrained (the model picks tool order and optional tools, but the phases
*gather -> compute -> compare -> draft -> validate* stay scaffolded), because for
a research tool reliability beats flash.

**The tools** (`tools/data.py`, `tools/analytical.py`):

| Tool | Family | Discipline it carries |
|------|--------|-----------------------|
| `get_financials`, `get_prices` | data | — |
| `get_consensus` | data | analyst estimates *or null* -> the model falls back to history |
| `get_historical_trend` | data | the company's own multi-year trajectory (the fallback basis) |
| `compute_ratios` | analytical | margins, growth, P/E, EV/EBIT |
| `run_dcf` | analytical | **probability** — two-stage, scenario-weighted (bear/base/bull) |
| `peer_outlier_check` | analytical | **statistics** — robust median/MAD outlier test |

**The agentic moment:** `get_consensus` is designed to often return null (analyst
consensus is the one genuinely paywalled input). When it does, the model *decides*
to call `get_historical_trend` and anchor its view to the company's own history
instead — a real branch, visible in the trace, not a hidden fallback.

**Output — three artifacts per run:**

- `report.html` — the prose note (view, evidence, what-would-change-it) with five
  embedded charts: price vs. home index, price + moving averages, volatility &
  drawdown, the peer-multiple scatter (the statistics check, drawn), and the DCF
  football-field.
- `model.json` — every computed number behind the prose. The auditability piece:
  the report rebuilds byte-identically from it (`python run.py --rebuild <model.json>`).
- `charts/` — the five charts as standalone images.

A **validation gate** (`validation/gate.py`) scores each run on deterministic
checks (is FCF real or a fallback? is the filing stale? is a margin implausible?)
and either passes it or flags it for review — distinguishing a *data-quality
problem* (flag) from a *dramatic but legitimate finding* (pass with a note).

---

## Agent 2 — Covenant Monitoring / Surveillance

Agent 1 analyses one thing, once. **Agent 2 watches many things, repeatedly, and
its whole job is detecting *change*** — every component below is a consequence of
that. It loops over a watchlist on a cadence, checks each item, compares to last
cycle's stored state, classifies what changed, and reports only the exceptions.

**Detection is deterministic; the three disciplines each do one job**
(`tools/covenant_checks.py`, `tools/statistical_checks.py`):

- `threshold_check` — is the covenant crossed? (deterministic, stays local)
- `anomaly_significance_check` — **statistics**: is the latest value a significant
  outlier vs the item's own history? (robust modified z-score)
- `drift_check` — **econometrics**: is there a real trend? (OLS value~time, t-test
  on the slope, prediction band, and a cycles-to-breach projection)
- `breach_probability` — **probability**: chance of breaching within a horizon,
  from the series' own drift and volatility (first-passage barrier crossing)

Together these catch a covenant *drifting toward breach cycles before it actually
crosses* — the difference between a monitoring system and a threshold alarm.

**Persistent state** (`state/store.py`) — a DuckDB store with two layers over one
file: *current-state* (latest snapshot per item, doubling as the full-state view)
and *history* (append-only, every cycle) in long/tidy panel shape (`item x time`).
Change is classified against stored status — `NEW_BREACH / WIDENING / IMPROVING /
RESOLVED / KNOWN_STABLE` — with a cold-start baseline that suppresses first-cycle
alerts.

**Production-honest, not a toy** (`scheduler/cycle.py`, `scheduler/trigger.py`):

- **Transactional writes** — a cycle computes everything first, then writes
  history + current-state in one transaction; a mid-cycle crash rolls back and
  leaves last-good state intact.
- **Freshness gating** — an item is skipped when its data hasn't advanced, so a
  daily monitor over a quarterly covenant doesn't manufacture phantom cycles.
- **Skip-to-now catch-up** — after downtime, process the latest directly (missed
  cycles not replayed) and surface the gap so a breach isn't misread as fresh.
- **Idempotency** — a `(item_id, data_ts)` uniqueness key makes re-runs safe.
- **Thin scheduler** — an in-process loop or a cron line fires `run_cycle()`; all
  the sophistication is in the atom, none in the trigger. No Airflow/Celery/Kafka.

**Model triage** (`monitoring/triage.py`) — after deterministic detection, the
model triages the flags: it groups them by entity and *decides* whether to
re-check ambiguous ones before escalating. The re-check verdict itself
(`corroborated / corroborated_but_verify / isolated / weak`) is computed
deterministically — the model decides *whether* to call it, never computes it.
This layer reuses Agent 1's tool-use loop, the shared spine paying off.

---

## MCP — and why it enters exactly here

**MCP** (Model Context Protocol) is a standard for exposing tools so any
MCP-compatible client can discover and call them. Here it is used with **stdio**
transport (the server is a local subprocess).

The rule this project follows: **MCP earns its place only at a boundary** — a tool
with more than one consumer. A lone agent has no boundary, so wrapping its tools in
a server would be decoration.

- **Agent 1 uses no MCP** — nothing else consumes its tools.
- **Agent 2 is the second consumer** of the shared analytical checks, so its three
  statistical tools are lifted to an MCP server (`mcp_server/server.py`), and
  Agent 2 calls them as a client (`mcp_server/client.py`).

The discipline is in what *doesn't* move: only `anomaly_significance_check`,
`drift_check`, and `breach_probability` go on the server (they will be reused by a
future news-intelligence agent). `threshold_check`, the data-refresh tools, and
the state store stay local — they don't cross a boundary, and putting them on the
server would be the exact "MCP as decoration" mistake this design avoids.

The server *wraps* the existing functions rather than reimplementing them — one
source of truth — which is what makes the two paths provably identical. A full
10-cycle run produces a byte-identical result whether the checks run in-process or
over MCP (toggle with `AGENT_STATS_VIA_MCP=1`).

---

## The three disciplines — one job each

| Discipline | The question it answers | Its job |
|---|---|---|
| **Probability** | "How likely, and how big could the move be?" | Distributions: scenario weighting, tail/breach likelihood. |
| **Statistics** | "Is this signal real or noise?" | Significance testing, anomaly detection. What confidence scores are, underneath. |
| **Econometrics** | "What's the relationship, over time?" | Regression, trend / expected-range models. |

Each is *primary* in at least one place. Depth per agent (**P** primary · **S**
secondary · **L** light):

| | Agent 1 — Equity Research | Agent 2 — Monitoring |
|---|---|---|
| **Probability** | L — scenario-weighted valuation | S — breach probability, tail flags |
| **Statistics** | S — peer-outlier check | **P** — anomaly significance |
| **Econometrics** | S — trend / factor framing | S — drift regression |

---

## Repo layout

```
agent/       loop.py (orchestrator) . models.py (Stub/Anthropic) . state.py (working memory)
tools/       data.py, analytical.py        (Agent 1 tools)
             covenant_checks.py            (threshold_check — local)
             statistical_checks.py         (the 3 shared checks — lifted to MCP)
             registry.py
validation/  gate.py                       (Agent 1 confidence gate)
composer.py  Agent 1 report + charts + model.json sidecar
run.py       Agent 1 entry point

state/       store.py (DuckDB) . classify.py   (Agent 2 state + change classification)
scheduler/   cycle.py (run_cycle atom) . trigger.py (thin scheduler)
monitoring/  triage.py                    (Agent 2 model triage; reuses agent/loop.py)
mcp_server/  server.py (stdio MCP server) . client.py (persistent client shim)
monitor.py   Agent 2 entry point

fixtures/    offline sample data (equity fixtures + covenants watchlist)
```

The offline/live and local/MCP switches follow one pattern throughout — a scripted
`StubModel` + fixture data for deterministic offline runs, the real model +
`yfinance` when live, and local functions vs. the MCP server for the shared checks.

---

## Honest limitations

Stated plainly, because knowing a tool's limits is part of building it:

- **Agent 1's DCF is a deliberate scaffold**, not a full three-statement model — a
  two-stage fade with scenario weights on real FCF. It is defensible and
  auditable, not a valuation an equity desk would ship as-is.
- **The peer check is directional at small n.** With a handful of peers the robust
  z-score is sensitive to which peers the model picks; the tool flags its own
  method-sensitivity rather than hiding it.
- **The model picks its own peers live**, so peer sets aren't perfectly
  reproducible across runs — that's the agentic behaviour, with reproducibility as
  the trade-off.
- **Agent 2's fixture series are deliberately clean**, so drift t-stats and breach
  probabilities read high/sharp. Real, noisier covenant data would produce more
  graduated signals; the machinery is what's being demonstrated.

---

## Roadmap

The platform is designed for four sibling agents on the shared spine. Two are
built. Planned next:

- **Agent 3 — Market / News Intelligence** — sentiment-tagged news linked to price
  moves, with a flagship **event study** running all three disciplines in one
  pipeline (abnormal returns -> significance test -> forward scenario
  distribution). Built as an MCP client from the start, reusing the server Agent 2
  stood up.
- **Agent 4 — FP&A / Variance** — Agent 2's machinery pointed at internal
  budget-vs-actual data. Under consideration.

---

## Stack

Python 3.11+ . Anthropic API (hand-rolled tool-use loop) . yfinance . DuckDB .
matplotlib . MCP (stdio). Offline runs need no API key or network.
