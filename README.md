# finance-ai-agents

A multi-agent platform for finance & markets analysis, built on one shared
analytical spine. Four agents run today — an **equity-research** agent that turns a
ticker into an auditable fundamental view, a **covenant-monitoring** agent that
watches many items over time and detects change, a **market/news-intelligence**
agent that tests whether events move a stock and projects the next one, and an
**FP&A / variance** agent that explains why a P&L missed plan — with their shared
analytical tools exposed over an **MCP server**.

> **Governing principle: the LLM never does the math.** Every number — every DCF,
> regression, z-score, CAAR, and probability — comes from deterministic Python.
> The model decides *which* tool to call, *reads* the result, and *writes* the
> narrative. It never computes in its head. For a finance audience this is the
> whole difference between a system whose figures you can audit and a toy that
> invents them.

This is a **platform, not a pipeline**: the agents are siblings on a shared
foundation, not stages in a chain. They have different triggers and cadences — one
runs on-demand per ticker, one is scheduled over a watchlist, one reads an event
universe, one runs at month-end close — and they share tools and conventions
rather than feeding one another. The clearest proof they are one platform: a single
significance library is called by all four (covenant drift, event-study CAAR,
variance materiality, variance persistence), byte-identical whether in-process or
over the MCP server.

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

**Agent 3 — market / news intelligence** (event study + scenario, and a news brief):

```bash
# Track A (rigor): cross-ticker event study on real earnings dates + a forward scenario
python -m agent3.run_live ASML.AS semicap_earnings
python -m agent3.run_live ALO.PA european_rail

# Track B (breadth): current news -> sentiment signal
AGENT_SENTIMENT_SCORER=lm         python -m agent3.run_news ASML.AS   # real lexicon, offline
AGENT_SENTIMENT_SCORER=divergence python -m agent3.run_news ASML.AS   # FinBERT + lexicon cross-check
```

The event study also runs on fixtures with no network — see the per-agent
sections below.

**Agent 4 — FP&A / variance** (decompose a P&L, classify, reforecast, board pack):

```bash
python -c "
import json
from agent4.hierarchy import rollup
from agent4.output import board_pack
bp = board_pack(rollup(json.load(open('fixtures/pnl.json'))))
print('reconciliation passed:', bp['reconciliation']['passed'])
open('waterfall.svg','w').write(bp['waterfall_svg'])
"
```

This decomposes the P&L fixture, rolls it up with penny-reconciliation at every
node, runs the integrity-gated commentary, and writes the variance-waterfall SVG.
Fully offline, no network or ML dependencies.

---

## The shared spine

Four things are reused across every agent — this is what makes it one platform
rather than three scripts that happen to rhyme:

- **Data access** — prices, fundamentals, and earnings dates via `yfinance` (EU
  *and* US tickers: `ASML.AS`, `SAP.DE`, `AAPL`, ...). Analysing a European name
  is a ticker choice, not a plumbing project.
- **Agent loop** — one *plan -> call tool -> observe -> decide -> repeat*
  controller, hand-rolled on the raw Anthropic tool-use API (no framework).
  Written once in `agent/loop.py`; Agent 2's triage and Agent 3's orchestration
  reuse it.
- **Analytical tools** — the computations (DCF, robust peer stats, anomaly
  significance, drift, breach probability, event study). Built as local Python,
  and the shared ones are lifted to an MCP server once a second agent consumes
  them. A single significance library (`tools/significance.py`) underlies both the
  covenant drift test and the event study.
- **Validation / confidence layer** — scores outputs and gates low-confidence or
  untrustworthy results to human review, rather than emitting them blindly. Each
  agent has its own gate; the discipline is shared.

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

**Output — three artifacts per run:** `report.html` (the prose note with five
embedded charts: price vs. home index, price + moving averages, volatility &
drawdown, the peer-multiple scatter, and the DCF football-field), `model.json`
(every computed number behind the prose — the report rebuilds byte-identically
from it via `python run.py --rebuild <model.json>`), and `charts/`.

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
transactional writes (a mid-cycle crash rolls back to last-good state), freshness
gating (skip an item whose data hasn't advanced, so a daily monitor over a
quarterly covenant doesn't manufacture phantom cycles), skip-to-now catch-up after
downtime (with the gap surfaced), idempotent re-runs (`(item_id, data_ts)` key),
and a thin scheduler firing `run_cycle()`. No Airflow/Celery/Kafka — all the
sophistication is in the atom, none in the trigger.

**Model triage** (`monitoring/triage.py`) — after deterministic detection, the
model triages the flags: it groups them by entity and *decides* whether to
re-check ambiguous ones before escalating. The re-check verdict itself
(`corroborated / isolated / weak`) is computed deterministically — the model
decides *whether* to call it, never computes it. This reuses Agent 1's loop.

---

## Agent 3 — Market / News Intelligence

Agent 1 valued a company from its numbers; Agent 2 watched those numbers change.
**Agent 3 turns events and text into a tested, forward-looking view** — its motto
is *read -> prove -> project*. It reads what happened, proves whether it moved the
stock (statistically), and projects the next comparable event as a
probability-weighted range. It is the only agent with two primary disciplines
(econometrics *and* probability).

It runs on **two tracks that never contaminate each other:**

- **Track A — the rigor lane.** Scheduled, precisely-dated events (earnings). The
  home of the event study, because exact timing is what makes a clean measurement
  possible.
- **Track B — the breadth lane.** Unstructured news, sentiment-scored. Messier and
  current-only, so it powers a daily brief — never a rigorous claim. The firewall
  is absolute: Track B sentiment never feeds a Track-A tested result.

### Track A — the event study (the flagship)

`run_event_study` (`tools/event_study.py`) is a market-model event study, and it
is the owner's master's-thesis difference-in-differences relabelled: the abnormal
return is the treatment effect, the market model is the counterfactual, the
estimation window is the parallel-trend pre-period, and a placebo on non-event
dates is the falsification test. Deterministic Python throughout:

1. Fit a market model `R = a + b*R_market` by OLS on an event-free estimation
   window (`[-250,-30]`), per event.
2. Abnormal return over the event window (`[-1,+1]`), cumulated to CAR.
3. Average across N comparable, cross-ticker events -> **CAAR** (the step that
   gives statistical power; a single event is noise).
4. Significance via a one-sample t-test (the shared `tools/significance.py`) plus
   a non-parametric sign test, with an **always-on placebo** that must come up
   empty for the result to be believable.

Peers come from a **model-proposes-and-pins** flow (`agent3/peers.py`): give it one
ticker, the model proposes a comparable peer set, and that set is *pinned* into the
run so the result is reproducible — a `--peers` override forces a set, and the
validation gate is the backstop against a loose one. The live assembly
(`agent3/track_a_live.py`) pulls real earnings dates + prices, drops-and-reports
peers with unusable data (some Euronext names return earnings dates that predate
their price history — labeled and excluded honestly), and refuses the study if too
few events survive.

### Track A — the scenario engine ("project")

`agent3/scenario.py` bootstraps the event study's *realized* per-event CAR
distribution into a forward, probability-weighted range for the next comparable
catalyst (p25 / median / p75, P(positive), and a separate confidence interval on
the mean effect). It is **calibration, not prediction** — a re-expression of what
comparable events did — and it refuses when the evidence is too thin (below an N
floor) or reports an explicit **null** when the underlying effect isn't
significant, rather than dressing noise up as a forecast.

### Track B — the news funnel

`agent3/news_funnel.py` turns raw news into a per-entity-per-day signal through
deterministic stages: ingest (the publication timestamp is sacred — undated items
are dropped, so there is no look-ahead), dedup/cluster (the same wire story from
twenty outlets is *one* signal, collapsed by headline similarity — coverage volume
is tracked but never counted as signal strength), relevance filter, score, and
aggregate. The entity-day signal carries **level, dispersion, count, and
confidence** — so a consumer knows how much to trust it (news that disagrees with
itself lowers confidence).

Sentiment scoring (`agent3/sentiment.py`) is pluggable: a real **Loughran-McDonald
lexicon** (transparent, offline, `tools`-free), a real **FinBERT** transformer, and
a **divergence scorer** that runs both and turns their *disagreement* into a free
confidence signal — when a context-aware model and a rule-based lexicon contradict
each other on a headline, that is exactly when a human should look, and the funnel
flags it.

### Assembly

`agent3/orchestrator.py` ties it together: assemble events -> event study (via MCP)
-> scenario -> validation gate -> record the outcome to a catalyst-calendar DuckDB
store (`agent3/catalyst_state.py`), rendered as either a per-entity **brief** or a
cross-entity **scan**. The **validation gate** (`agent3/validation.py`) carries the
Agent-3-specific checks: *confound* (a significant CAAR that is really an
index-wide move, flagged when events cluster on too few dates), *thin data* (too
few events / peers), and *multiple testing* (a significant result that doesn't
survive a multiplicity adjustment when many event types were tested). A significant
result isn't emitted automatically — it has to survive the gate; an insignificant
one is an honest null and passes cleanly.

---

## Agent 4 — FP&A / Variance

Agent 1 valued, Agent 2 monitored, Agent 3 tested events — **Agent 4 explains why a
number missed plan.** Its signature act is variance *decomposition* (attribution),
not detection, which is why it reuses Agent 2's significance machinery but is not
Agent 2 retargeted. Its data is internal, so it runs on realistic synthetic-company
fixtures — the honest, standard way to portfolio FP&A.

Three governing properties, all mechanical:

**Reconciles to the penny.** Every amount is carried as **integer cents**, and the
driver variances sum *exactly* to the total — no floating-point dust. The
decomposition engine (`agent4/decomposition.py`) dispatches by line type (revenue ->
price x volume x mix; variable cost -> rate x efficiency; fixed cost -> spending),
names the convention it used (sequential by default), and surfaces the absorbed
joint price-volume term when it is material. Lines lacking unit data report total
variance and label the split "not computable" rather than fabricating one.

**Every subtotal ties, not just the bottom line.** The hierarchy roll-up
(`agent4/hierarchy.py`) decomposes at the leaves and aggregates up the P&L tree with
explicit add/subtract sign roles, verifying penny-reconciliation at *every node* or
failing loudly. Favourability is resolved by profit impact at each level — a cost
line coming in over budget shows a positive variance but is correctly tagged adverse.

**Triage like a controller, and project forward.** The materiality x significance
2x2 (`agent4/materiality.py`) crosses relative-and-absolute size against a statistical
break from the line's own variance history, surfacing the **early-warning** quadrant
(immaterial in euros but a real break from pattern) that naive threshold tools miss.
The reforecast engine (`agent4/reforecast.py`) projects the full-year landing with a
method ladder (run-rate / phasing-aware / time-series, naming which it used) and a
confidence band drawn from the line's own historical dispersion that widens with
horizon — headlined as **P(hit annual target)**, never a bare point. Persistence
classification (`agent4/persistence.py`) labels each variance one-off vs structural
from recurrence, sign-consistency, and significance — so a one-off spike isn't
extrapolated and a structural shift is.

**State is versioned; nothing is overwritten** (`agent4/state.py`): an immutable
budget (a re-budget writes a new version), append-only actuals (a restatement keeps
the original), and a reforecast versioned every close (so the forecast *walk* is
preserved) — the auditability signature at the state level.

**The commentary cannot fabricate a number.** The integrity gate
(`agent4/commentary.py`) enforces a three-tier claim taxonomy — *computed fact*
(reference-built from the engine, every figure reconciling against the registry),
*observation* (traces to a stored classification), and *business-cause hypothesis*
(always flagged "requires confirmation," never asserted). A hard reconciliation
check re-verifies every figure in the prose against the computed model.json and
**fails the run** on any fabricated or mismatched number — the prose analogue of
the penny-reconciling bridge. Output is a **board pack** or an **exception view**,
with the signature **variance waterfall** (`agent4/output.py`) as inline SVG:
budget -> favourable/adverse steps -> actual, residual explicit, always tying.

---

## MCP — and why it enters exactly here

**MCP** (Model Context Protocol) is a standard for exposing tools so any
MCP-compatible client can discover and call them. Here it is used with **stdio**
transport (the server is a local subprocess).

The rule this project follows: **MCP earns its place only at a boundary** — a tool
with more than one consumer. A lone agent has no boundary, so wrapping its tools in
a server would be decoration.

- **Agent 1 uses no MCP** — nothing else consumes its tools.
- **Agent 2 is the second consumer** of the shared statistical checks, so they are
  lifted to an MCP server (`mcp_server/server.py`) and Agent 2 calls them as a
  client.
- **Agent 3 is born a client** — it reuses those same checks, and adds one tool
  (`run_event_study`) to the server, which *internally calls* the shared
  significance family rather than reimplementing it.
- **Agent 4 adds nothing to the server** — it is the *fourth consumer* of the
  significance library (calling it at two sites: variance materiality and variance
  persistence). Its decomposition and reforecast are Agent-4-specific and stay
  local. The restraint is the point: a good abstraction is measured by whether what
  is shared is *genuinely* shared, not by tool count.

The discipline is in what *doesn't* move: only the four shared analytical tools go
on the server. `threshold_check`, the data-refresh and Track-A assembly layers, the
news funnel, the scenario engine, the decomposition and reforecast engines, and
every state store stay local — they don't cross a boundary, and putting them on the
server would be the exact "MCP as decoration" mistake this design avoids. The server
*wraps* the existing functions rather than reimplementing them, which is what makes
the two transports provably identical — a full 10-cycle covenant run is
byte-identical in-process vs. over MCP (`AGENT_STATS_VIA_MCP=1`). **One significance
library, four unrelated consumers** — covenant drift, event-study CAAR, variance
materiality, and variance persistence — is the tangible proof that this is one
platform, not four scripts.

---

## The three disciplines — one job each

| Discipline | The question it answers | Its job |
|---|---|---|
| **Probability** | "How likely, and how big could the move be?" | Distributions: scenario weighting, tail/breach likelihood. |
| **Statistics** | "Is this signal real or noise?" | Significance testing, anomaly detection. What confidence scores are, underneath. |
| **Econometrics** | "What's the relationship, over time?" | Regression, trend models, event studies. |

Each is *primary* in at least one agent (**P** primary · **S** secondary · **L** light):

| | Agent 1 — Equity Research | Agent 2 — Monitoring | Agent 3 — Market/News | Agent 4 — FP&A |
|---|---|---|---|---|
| **Probability** | L — scenario-weighted valuation | S — breach probability, tail flags | **P** — catalyst -> forward distribution | S — P(hit target), forecast bands |
| **Statistics** | S — peer-outlier check | **P** — anomaly significance | S — sentiment / significance of CAAR | S — variance significance vs. noise |
| **Econometrics** | S — trend framing | S — drift regression | **P** — event study (market model, CAAR) | **P** — reforecast / expected-range |

(Variance decomposition itself is deterministic accounting arithmetic — like the
DCF, not one of the three disciplines.)

The event study runs all three in one pipeline: econometrics estimates abnormal
returns, statistics tests their significance, probability projects them forward.

---

## Repo layout

```
agent/       loop.py (orchestrator) . models.py (Stub/Anthropic) . state.py
tools/       data.py, analytical.py          (Agent 1 tools)
             covenant_checks.py              (threshold_check — local)
             statistical_checks.py           (shared checks — served over MCP)
             significance.py                 (shared t-test library — 4 consumers)
             event_study.py                  (run_event_study — served over MCP)
validation/  gate.py                         (Agent 1 confidence gate)
composer.py  Agent 1 report + charts + model.json
run.py       Agent 1 entry point

state/       store.py (DuckDB) . classify.py (Agent 2 state + change classification)
scheduler/   cycle.py (run_cycle atom) . trigger.py (thin scheduler)
monitoring/  triage.py                       (Agent 2 model triage; reuses agent/loop.py)
monitor.py   Agent 2 entry point

agent3/      track_a.py, track_a_live.py     (event assembly: fixture + live yfinance)
             peers.py                        (model-proposes-and-pins peer sets)
             scenario.py                     (bootstrap forward distribution)
             news_funnel.py, news_live.py     (Track B funnel + live news)
             sentiment.py, lm_lexicon.py      (LM lexicon, FinBERT, divergence scorer)
             validation.py                   (confound / thin-data / multiple-testing gate)
             catalyst_state.py               (catalyst calendar + outcome history, DuckDB)
             orchestrator.py                 (assembly + brief/scan output modes)
             run_live.py, run_news.py         (Agent 3 entry points)

agent4/      decomposition.py                (variance bridge, integer cents)
             hierarchy.py                    (P&L roll-up, penny-reconcile per node)
             materiality.py                  (materiality x significance 2x2)
             reforecast.py                   (method ladder + P(hit target))
             persistence.py                  (one-off vs structural; 4th consumer)
             state.py                        (versioned budget/actuals/reforecast, DuckDB)
             commentary.py                   (three-tier taxonomy + reconciliation gate)
             output.py                       (board pack / exception view + waterfall SVG)

mcp_server/  server.py (stdio MCP server) . client.py (persistent client shim)
fixtures/    offline sample data (equities, covenants, events, news, P&L)
```

Every layer follows one offline/live pattern: a scripted `StubModel` + fixture data
for deterministic offline runs, the real model + `yfinance` + FinBERT when live, and
local functions vs. the MCP server for the shared checks.

---

## Honest limitations

Stated plainly, because knowing a tool's limits is part of building it:

- **Agent 1's DCF is a deliberate scaffold**, not a full three-statement model — a
  two-stage fade with scenario weights on real FCF. Defensible and auditable, not a
  valuation an equity desk would ship as-is.
- **The peer check is directional at small n**, and the model picks its own peers
  live, so peer sets aren't perfectly reproducible across runs — that's the agentic
  behaviour, with reproducibility as the trade-off (Agent 3 solves the same tension
  by *pinning* the proposed set).
- **Agent 2's fixture series are deliberately clean**, so drift t-stats read sharp;
  real, noisier data would produce more graduated signals. The machinery is what's
  demonstrated.
- **Agent 3's pooled earnings event studies typically come back insignificant on
  real data** — which is the honest, correct result (earnings surprises wash out
  across a diversified peer set), and the scenario engine reports it as a null
  rather than manufacturing a signal. Finding a significant event-driven effect
  needs a sharper event type (e.g. filtered surprises), a documented extension.
- **Track B is current-news only** on free sources — a daily sentiment brief, not
  historical sentiment-return analysis (which the two-track firewall keeps out of
  the rigorous lane by design). Some names return sparse earnings-date history from
  the free source and are labeled and excluded rather than silently dropped.
- **Agent 4 runs on synthetic-company fixtures** — FP&A data is internal, so this
  is the standard, honest way to portfolio it. The reforecast is a *defensible*
  projection (a method ladder with an honest dispersion-based band), not a
  production forecasting engine; portfolio-level correlated Monte Carlo is a
  documented later step, not claimed here.

---

## Roadmap

All four sibling agents on the shared spine are built. Possible extensions:

- **Event-study extensions** — earnings-*surprise* filtering (to isolate a sharper,
  potentially significant effect), standardized cross-sectional (BMP) significance,
  and wider event windows as robustness specs.
- **Agent 4 seasonal model** — a full seasonal-decomposition significance band
  (the current layer degrades to period-aware-when-history-allows, else labelled).
- **Static showcase** — a precompute-only site (`keystone-showcase/`) presents each
  agent's signature output, with Agent 4's variance waterfall as the fourth tile.

---

## Stack

Python 3.11+ · Anthropic API (hand-rolled tool-use loop) · yfinance · DuckDB ·
matplotlib · MCP (stdio) · transformers/torch + FinBERT (optional, Track B live).
Offline runs need no API key, no network, and no heavy ML dependencies.
