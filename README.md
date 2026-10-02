# finance-ai-agents

[![tests](https://github.com/Aadhi0105/finance-ai-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/Aadhi0105/finance-ai-agents/actions/workflows/ci.yml)

Four finance agents share deterministic analytical tools: **equity research**,
**covenant monitoring**, **historical market-event and current-news analysis**, and
**FP&A / variance analysis**. Shared statistical checks are also available through
an MCP server.

> **Governing principle: the LLM never does the math.** Python computes financial
> figures and statistical results. Agents 1 and 2 constrain model output against
> saved evidence; Agent 3 has a separate deterministic event-study orchestrator,
> and Agent 4 uses a deterministic accounting engine.

The agents run independently. Covenant drift and event-study inference share
Student-t primitives; monitoring and FP&A reuse robust anomaly checks. Tested
local/MCP paths preserve the same calculation contracts. Fixture monitoring can
loop on a cadence; no unattended live schedule or notification service is installed.

## Current status — 2 October 2026

| Component | Completed scope | Remaining boundary |
|---|---|---|
| Agent 1 | Batches 1–4, issuer-filing reconciliation, numerical and qualitative claim controls, bounded v1 acceptance | Company/provider coverage and economic peer comparability still require review; not universal listed-company support |
| Agent 2 | Batches 1–4, Stadler annual live observations, audited correction approval/rejection and saved-cycle triage recovery | Live scheduling and notifications deferred; live validation covers the documented annual workflow |
| Agent 3 | Batches 1–3: historical calculation/review controls, audited live peer selection/recovery, news relevance and publication evidence | Batch 4 replay/state/integration; real FinBERT weight validation and populated live-news validation remain unverified |
| Agent 4 | Synthetic-fixture accounting, variance and board-pack implementation | Detailed hardening audit still pending |
| Showcase | Static illustrative prototype in `keystone-showcase/` | Does not yet publish verified linked run artifacts |

The per-agent guides below record acceptance evidence and operating limits.

---

## Quickstart

```bash
pip install -r requirements.txt
```

**Agent 1 — equity research** (single ticker -> report):

```bash
python run.py                 # offline: scripted model + fixture data (normally exits 3)
python run.py --live ASML.AS  # live: the model decides the tool sequence, data via yfinance
```

Live mode needs `ANTHROPIC_API_KEY` (loaded from a gitignored `.env`). A run
saves `model.json` first, then charts and either `report.html` or
`report_REVIEW.html` in a unique per-run `output/` folder. Add `--trace` for the
execution trace. See [execution and reporting](docs/agent1-execution-reporting.md)
for checkpoints, rebuild behavior, and exit codes.

**Agent 2 — covenant monitoring** (watchlist -> change detection over cycles):

```bash
python monitor.py --reset      # deletes the default fixture database; demo reset only
python monitor.py --run 10     # run 10 cycles; drift is flagged before the hard breach
python monitor.py --once       # one cycle, with model triage of any exceptions
python monitor.py --state      # on-demand full-state snapshot
python monitor.py --catchup 9  # records missed monitoring cycles; not provider history backfill
```

For the reviewed live annual workflow, use a separate database:

```bash
python monitor.py --once --data-source yfinance --watchlist watchlists/stadler-annual.json --db state/stadler-live.duckdb
python monitor.py --state --db state/stadler-live.duckdb
python monitor.py --reviews --db state/stadler-live.duckdb
python monitor.py --review-decisions --db state/stadler-live.duckdb
```

`--live` selects paid model triage; `--data-source yfinance` selects live observations.
Approval/rejection requires an explicit review ID, reviewer and reason; see
[review and recovery commands](docs/agent2-review-recovery.md). Triage retry reuses
saved cycle evidence without fetching data or advancing monitoring state.

Run the same monitoring cycles with the statistical checks served over MCP
instead of in-process — the output is byte-identical:

```bash
AGENT_STATS_VIA_MCP=1 python monitor.py --run 10
```

**Agent 3 — market / news intelligence** (event study + scenario, and a news brief):

```bash
# Track A: historical earnings analysis; unresolved evidence is held for review
python -m agent3.run_live ASML.AS semicap_earnings --peers ASM.AS BESI.AS
python -m agent3.run_live ALO.PA european_rail --peers SRAIL.SW CAF.MC

# Track B: current news -> reviewed document-tone evidence
python -m agent3.run_news ASML.AS --alias ASML --scorer lm  # lexical diagnostics; live retrieval
# FinBERT/divergence also require dependencies and AGENT_FINBERT_REVISION:
python -m agent3.run_news ASML.AS --alias ASML --scorer divergence
```

Exit 3 means historical evidence is held for review, not a publishable forecast.
FinBERT/divergence scoring needs optional `torch` and `transformers` dependencies
and a 40-character model commit in `AGENT_FINBERT_REVISION`;
real FinBERT weights have not been validated in the current acceptance work.
For an illustrative, held event study without network access:

```bash
python -c "from agent3.orchestrator import analyze_event_type, render_brief; print(render_brief(analyze_event_type('semicap_earnings')))"
```

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

A shared architectural spine — reused where each agent needs it, not four
identical copies. It's what makes this one platform rather than scripts that
happen to rhyme:

- **Data access** — prices, fundamentals, and earnings dates via `yfinance` (EU
  *and* US tickers: `ASML.AS`, `SAP.DE`, `AAPL`, ...). Used by the market-facing
  agents (1 and 3) and Agent 2’s explicit annual-statement mode; Agent 4 uses
  internal-budget fixtures.
- **Agent loop** — one *plan -> call tool -> observe -> decide -> repeat*
  controller, hand-rolled on the raw Anthropic tool-use API (no framework).
  Written once in `agent/loop.py`; Agent 1 uses it directly and Agent 2's triage
  reuses it. (Agent 3 has its own orchestrator; Agent 4's engine is deterministic
  and needs no model loop.)
- **Analytical tools** — the computations (DCF, robust peer stats, anomaly
  significance, drift, breach probability, event study). Built as local Python,
  and the shared ones are lifted to an MCP server once a second agent consumes
  them. The significance/anomaly primitives in `tools/significance.py` and the
  robust anomaly check are reused across covenant drift, event studies, and
  variance materiality/persistence.
- **Validation layer** — Agents 1 and 2 constrain evidence and publication,
  Agent 3 Track A holds unresolved inference, and Agent 4 checks accounting and
  commentary integrity. Agent 3 Track B retains news evidence and holds unresolved tone results.
  Review verdicts are not calibrated confidence probabilities.

---

## Agent 1 — Equity Research

Batch 1 financial hardening adds explicit currency/unit/period contracts,
provider working-capital normalization, finite-input checks, and tested DCF,
peer, consensus, and trend edge cases. See the
[financial contract and model limitations](docs/agent1-financial-contract.md).
Batch 2 adds [evidence validation and named numerical claims](docs/agent1-evidence-validation.md).
Batch 3 adds [execution checkpoints and report lifecycle controls](docs/agent1-execution-reporting.md).
Batch 4 adds [acceptance tests and a verification record](docs/agent1-verification.md).
The [Agent 1 v1 acceptance record](docs/agent1-v1-acceptance.md) defines supported
scope, final closure results and the analyst review procedure.
Live drafts now get at most one numerical-grounding correction request, followed
by revalidation. A rejected revision falls back to explicitly labelled evidence
statements with model interpretation withheld. All published notes also pass the
strict named-evidence-only qualitative control. Charts may end before invalid trailing observations with visible
warnings and retained excluded rows; internal gaps are never bridged.

Give it a ticker; it produces an auditable financial-evidence report. Unsourced
model interpretation is withheld from publication and retained in the audit record.
See the [issuer reconciliation and qualitative controls](docs/agent1-issuer-and-claims.md). It is deliberately the *least* agentic of the platform: the loop is
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

**The agentic moment:** `get_consensus` returns unavailable when usable provider
estimates are missing. When that happens, the model *decides*
to call `get_historical_trend` and anchor its view to the company's own history
instead — a real branch, visible in the trace, not a hidden fallback.

**Output — three artifacts per run:** `report.html` or `report_REVIEW.html` (financial evidence with up to five
embedded charts: price vs. home index, price + moving averages, volatility &
drawdown, the peer-multiple scatter, and the DCF football-field), `model.json`
(the evidence, conversation, configuration, and execution audit trail), and
`charts/`. Rebuild with `python run.py --rebuild <model.json>`; this revalidates
saved evidence without model or provider calls. Failed charts are explicitly
labelled and preserve a review report plus the saved analysis.

A **validation gate** (`validation/gate.py`) requires complete evidence and
reconciled calculations. Any quality warning or failure requires review,
while a dramatic-but-legitimate finding (a big DCF-vs-price gap) is surfaced
without penalty. A flagged run is emitted as `report_REVIEW.html` with a
watermark, never as an approved `report.html` — the gate gates, it doesn't just
label. Illustrative offline runs also require review. Rebuilds rerun validation;
legacy records without explicit completion evidence require review.

**Integrity — the numbers are hard to break, and the note can't outrun them.**
Agent 1 was the first agent built and was later hardened under a detailed code
review; the fixes are what make its auditability claim mechanical rather than
aspirational:

- **EV/EBIT uses real enterprise value** (market cap + debt − cash), never
  approximated by market cap; a multiple with a non-positive denominator returns
  `None` with a status, not a meaningless negative.
- **The DCF refuses nonsensical parameters** (discount rate ≤ terminal growth,
  out-of-range inputs) rather than printing a broken number, and reports its
  terminal-value concentration.
- **The net-debt bridge is complete only when both debt and cash are known** — a
  missing side reports enterprise value only, never silently assuming zero (which
  would overstate equity).
- **Ticker integrity:** a dependent tool refuses to compute on another ticker's
  stored data.
- **Named numerical evidence** (`validation/note_grounding.py`): the model selects
  standalone evidence markers; Python supplies complete statements with metric,
  company, period, value and unit. Unbound numerical prose requires review.
  Unsourced qualitative interpretation is withheld from reports. Original text,
  rendered statements and evidence references are preserved in the sidecar.
- **Auditable + reproducible:** `model.json` carries full provenance (model id, git
  commit, data source, statement period, currency) and the complete append-only
  tool-call history; offline runs are reproducible across processes (stable
  hashing).

---

## Agent 2 — Covenant Monitoring / Surveillance

[Batch 1 calculation and alert contracts](docs/agent2-calculation-alerts.md) document
finite inputs, dated drift, probability applicability and breach-priority triage.
The [Batch 2 state and recovery contract](docs/agent2-state-recovery.md) adds a
transactional cycle ledger, replay, correction holds and process locking.
[Batch 3 publication controls](docs/agent2-triage-publication.md) constrain model
triage to known item IDs and render facts in Python. [Batch 4 acceptance](docs/agent2-v1-acceptance.md)
checks the bounded workflow, local/MCP parity and real-model triage. Subsequent
[live ingestion](docs/agent2-live-observations.md) and
[review/recovery](docs/agent2-review-recovery.md) extend that reviewed scope.

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

**Persistent state** (`state/store.py`) — a transactional DuckDB cycle ledger,
current snapshots, observation history and immutable completed-cycle reports.
Explicitly approved corrections can restate effective history, preserving the
before/after evidence and decision audit. Change is classified against stored
status — `NEW_BREACH / WIDENING / IMPROVING / RESOLVED / KNOWN_STABLE`.
Cold-start baselines suppress initial alerts; active baseline breaches remain
visible in state and are not evidence of compliance.

**Execution and recovery** (`scheduler/cycle.py`, `scheduler/trigger.py`):
transactional writes, process locking, freshness gating, idempotent replay and
skip-to-now catch-up with missed cycles surfaced. Live observations support
`--once` and `--catchup`; live `--run`, `--loop` and `--cron` are refused.
The fixture scheduler/cron helper does not install a live schedule. Catch-up does
not retrieve missing historical provider statements.

**Live observations:** an explicit Stadler Rail annual watchlist now supports
`--data-source yfinance --watchlist watchlists/stadler-annual.json --db state/stadler-live.duckdb`.
Its selected FY2025 inputs are checked against the issuer filing. Thresholds are
illustrative analyst policies, not contractual covenants. See the
[live observation guide](docs/agent2-live-observations.md) for commands and limits.

**Review and recovery:** held corrections now support explicit approval/rejection,
audited recalculation and saved-cycle triage retry. Reviewer names are recorded
attestations, not authenticated signatures. Definition changes require a new
series identity; legacy cycles lacking enough frozen evidence cannot be retried.
See the
[review commands and recovery contract](docs/agent2-review-recovery.md).

**Model triage** (`monitoring/triage.py`) reuses Agent 1's tool loop to
investigate flags and propose an ordering. Publication accepts only a complete
list of known item IDs. Python renders facts and recommendations for every flag,
with active breaches first; model prose is withheld. Each attempt saves its input
snapshot, prompts, responses, tools and outcome under `output/monitor-triage/`.

`monitor.py --once --live` and `--catchup N --live` use the real model, loading the
repository `.env`; missing credentials fail explicitly. **The triage flag does not select the observation source.** Without
`--data-source yfinance`, observations remain bundled fixtures. Offline triage is scripted. `--run` and `--loop`
perform deterministic monitoring only. See [Batch 3 controls](docs/agent2-triage-publication.md).

Agent 2 v1 acceptance includes twelve-cycle local/MCP parity and a successful
real-model CLI triage run. See [acceptance evidence and operating limits](docs/agent2-v1-acceptance.md).
Repeat offline with `python -m scripts.check_agent2_acceptance`; add `--live` for
an opt-in paid model check. Both modes create isolated test databases.

---

## Agent 3 — Market / News Intelligence

Agent 3 has two separate tracks. Track A measures **historical** earnings-window
abnormal returns. Track B produces a current-news sentiment brief; its sentiment
never enters the event-study calculation.

### Track A — bounded historical analysis

Live assembly fetches prices and earnings timestamps for an explicit or proposed
peer universe. An OLS market model uses **250 estimation returns [-280,-31]** and
three event returns **[-1,+1]**. The output includes an equal-event-weighted mean
CAR, event/issuer counts, excluded evidence and historical quantiles.

Batch 1 enforces finite numeric/window contracts, exact Student-t decisions,
duplicate/overlap rejection, timezone/session-aware anchoring and a publication
guard. Provider dates, default benchmarks and generated controls remain
**unverified**. A sourced study plan can supply reviewed dates, return bases,
peer-comparability and sampling assumptions, and a declared hypothesis family.

Repeated quarterly observations from the same firms and overlapping market dates
are **descriptive only**: no independence-based significance claim or iid bootstrap
interval is issued. At least ten independently eligible single-event issuers and
complete reviewed evidence are required by the bounded inference policy. This
minimum is not a power guarantee. Unresolved data, calendar, comparability,
sampling or control evidence holds publication. No result is called a calibrated
forecast; held distributions are diagnostics only.

```sh
python -m agent3.run_live ASML.AS semicap_earnings --peers ASM.AS BESI.AS
# Optional sourced reviewer input:
python -m agent3.run_live ASML.AS semicap_earnings --peers ASM.AS BESI.AS --study-plan reviewed-plan.json
```

[Batch 2](docs/agent3-batch2.md) repairs live model peer selection. Without `--peers`,
the CLI requests an audited proposal using `ANTHROPIC_API_KEY`; it loads the
repository `.env` without overriding exported variables. Missing credentials and
invalid proposals fail explicitly, with no fixture fallback. Model assessments and
source leads remain unverified; provider listing/source-domain mismatches or missing
identity evidence exclude model-selected peers before their events are pooled.
Economic comparability still requires explicit review.

Every started CLI attempt writes a unique `output/agent3-runs/<id>/run.json`, with
proposal decisions, per-peer progress, review results and failure stages. The worker
has a 300-second default deadline (`--timeout`, 30–3600 seconds); it makes no automatic
model or whole-run retries. `--retry-from <run.json>` creates a new attempt using
saved peers/review inputs and **fresh** provider data, without modifying the original.
It is not historical snapshot replay. Process-group deadline cleanup supports macOS/Linux.

MCP is opt-in with `AGENT_STATS_VIA_MCP=1`; local calculation remains the default.
Exit statuses: 0 completed historical result, 2 refused, 3 held, 4 unavailable,
5 failed. Brief and scan output recheck saved evidence and hold unknown publication
states. DuckDB retains conflict-checked summary history and an index of immutable
run bundles. Calendar transitions and corrections retain revision history;
calendar ingestion and automatic scheduling are not in the live flow.

See [Agent 3 Batch 1](docs/agent3-batch1.md) for the review-plan schema, date,
benchmark and inference policies, and [Batch 2](docs/agent3-batch2.md) for live
selection, checkpoints, retry commands, exit codes and verification evidence.

### Track B — current-news evidence and document tone

[Batch 3](docs/agent3-batch3.md) replaces assumed ticker relevance with explicit
headline alias/cashtag checks. It validates timezone-aware publication/retrieval
instants, applies a bounded freshness window, groups UTC days and records exclusions.
Conservative text clustering preserves negation, changed stories and every cluster
member; counts are heuristic clusters, not demonstrated independent stories.

The live default is a disclosed curated lexical subset (`lm`), held as diagnostic
lexical tone. Explicit dictionary errors do not fall back. Optional FinBERT modes
require a pinned revision and validate probability vectors, language metadata and
truncation. Stub scores require explicit fixture/demo mode. Unknown scorer names
fail. No calibrated confidence is reported.

Per-story scorer evidence, source references, review reasons and aggregate flags
are saved in `output/agent3-news/<id>/run.json`. Held signals have `level=null`;
diagnostic means are separate. The CLI uses the saved scores without rescoring,
rechecks published levels against their evidence, and has a bounded worker deadline.
Scores describe document tone, not entity-specific sentiment or expected returns.

Live Stadler and ASML checks returned empty feeds and correctly produced held
records. Populated-feed processing is verified with deterministic fixtures;
real FinBERT weights have not been run in the current environment.


### Saved evidence, offline replay and delivery

[Batch 4](docs/agent3-batch4.md) seals each terminal CLI attempt into `bundle.json`,
including held results and failures. Bundles retain normalized inputs, available
provider snapshots, settings, peer decisions, output, code/runtime provenance and
integrity hashes. Unique attempt IDs are separate from input fingerprints.

```bash
python -m agent3.bundles /path/to/bundle.json --output replay.json --html report.html
# Recover a missing database index entry from its sealed bundle:
python -m agent3.bundles /path/to/bundle.json --index-db state/catalyst.duckdb
```

Replay makes no provider/model calls: Track A recomputes from saved return windows;
Track B rebuilds its funnel using retained scorer responses. Exact output comparison
blocks mismatches. Incomplete attempts receive no verified analytical output.
Held and failed results stay restricted. Legacy checkpoint files are not retroactive
replay bundles. Hashes verify file integrity, not source authenticity.

Outcome IDs reject conflicting writes; significance remains true/false/unknown.
Calendar corrections require reasons and keep before/after history. Bundle indexing
can be recovered independently after a database failure. Actual HTML exports are
separate from the visibly labelled illustrative showcase.


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

## Shared tools over MCP

The MCP server uses stdio transport and wraps four existing Python tools:
`anomaly_significance_check`, `drift_check`, `breach_probability` and
`run_event_study`. Agent 2 and Agent 3 Track A can opt in with
`AGENT_STATS_VIA_MCP=1`; local execution is the default. The monitoring acceptance
runner checks twelve-cycle local/MCP parity, and event-study regressions check the
shared result contract.

Agent 1 uses its tools locally. Agent 4 reuses the robust anomaly checker locally
for materiality and persistence. Threshold checks, data acquisition, event
assembly, news scoring, scenario summaries, accounting engines and state stores
remain local. MCP does not independently verify the underlying financial evidence.

---

## The three disciplines — one job each

| Discipline | The question it answers | Its job |
|---|---|---|
| **Probability** | "How likely, and how big could the move be?" | Distributions: scenario weighting, tail/breach likelihood. |
| **Statistics** | "Is this signal real or noise?" | Significance testing, anomaly detection. Eligibility and assumptions determine when inference is available. |
| **Econometrics** | "What's the relationship, over time?" | Regression, trend models, event studies. |

Each is *primary* in at least one agent (**P** primary · **S** secondary · **L** light):

| | Agent 1 — Equity Research | Agent 2 — Monitoring | Agent 3 — Market/News | Agent 4 — FP&A |
|---|---|---|---|---|
| **Probability** | L — scenario-weighted valuation | S — breach probability, tail flags | **P** — historical event distributions | S — P(hit target), forecast bands |
| **Statistics** | S — peer-outlier check | **P** — anomaly significance | S — sentiment / significance of CAAR | S — variance significance vs. noise |
| **Econometrics** | S — trend framing | S — drift regression | **P** — event study (market model, CAAR) | **P** — reforecast / expected-range |

(Variance decomposition itself is deterministic accounting arithmetic — like the
DCF, not one of the three disciplines.)

The event study runs all three in one pipeline: econometrics estimates abnormal
returns, statistics tests eligible independent samples, and probability summarizes their historical distribution.

---

## Repo layout

```
agent/       loop.py (orchestrator) . models.py (Stub/Anthropic) . state.py
tools/       data.py, analytical.py          (Agent 1 tools)
             covenant_checks.py              (threshold_check — local)
             statistical_checks.py           (shared checks — served over MCP)
             significance.py                 (Student-t primitives: drift and event studies)
             event_contracts.py              (strict event/window/evidence contracts)
             event_study.py                  (run_event_study — served over MCP)
validation/  gate.py                         (Agent 1 confidence gate)
composer.py  Agent 1 report + charts + model.json
run.py       Agent 1 entry point

state/       store.py (DuckDB) . classify.py (Agent 2 state + change classification)
scheduler/   cycle.py (run_cycle atom) . trigger.py (thin scheduler)
monitoring/  triage.py                       (Agent 2 model triage; reuses agent/loop.py)
monitor.py   Agent 2 entry point

agent3/      track_a.py, track_a_live.py     (event assembly: fixture + live yfinance)
             peers.py, study_plan.py          (explicit peers and reviewer attestations)
             scenario.py                     (historical quantiles; eligible mean bootstrap)
             news_funnel.py, news_live.py     (Track B funnel + live news)
             news_contracts.py, news_execution.py (UTC evidence contracts + bounded news worker)
             sentiment.py, lm_lexicon.py      (LM lexicon, FinBERT, divergence scorer)
             validation.py                   (evidence, eligibility and multiple-testing gate)
             catalyst_state.py               (catalyst calendar + outcome history, DuckDB)
             orchestrator.py                 (assembly + brief/scan output modes)
             execution.py                    (bounded worker, attempt checkpoints and retry)
             run_live.py, run_news.py         (Agent 3 entry points)

agent4/      decomposition.py                (variance bridge, integer cents)
             hierarchy.py                    (P&L roll-up, penny-reconcile per node)
             materiality.py                  (materiality x significance 2x2)
             reforecast.py                   (method ladder + P(hit target))
             persistence.py                  (one-off vs structural; robust anomaly reuse)
             state.py                        (versioned budget/actuals/reforecast, DuckDB)
             commentary.py                   (three-tier taxonomy + reconciliation gate)
             output.py                       (board pack / exception view + waterfall SVG)

mcp_server/  server.py (stdio MCP server) . client.py (persistent client shim)
fixtures/    offline sample data (equities, covenants, events, news, P&L)
tests/       deterministic regression and acceptance tests
docs/        per-agent contracts, operating guides and acceptance records
watchlists/  explicit live monitoring configurations
references/  issuer reconciliation evidence
scripts/     check_agent2_acceptance.py (isolated offline / opt-in paid checks)
keystone-showcase/  illustrative static prototype
.github/     workflows/ci.yml — pytest on pull requests and pushes to main
```

Agent 1 separates scripted fixture mode from live model/provider mode. Agent 2's
`--live` flag changes only triage; its explicit `--data-source yfinance` mode fetches
annual statements. Agent 3 Track A uses fixture or live price/date assembly;
Track B independently selects stub, lexicon or optional ML sentiment scoring.

---

## Testing

GitHub Actions runs deterministic tests on pull requests and pushes to `main`,
with Python 3.11 and 3.12:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

The latest local Agent 3 Batch 4 validation passed **726 tests on Python 3.11.9**,
including 40 new Batch 4 regressions (Batch 3 added 47; Batch 2 added 53; Batch 1 added 49). Earlier acceptance guides retain their historical
suite counts. Coverage includes financial contracts and report grounding, monitoring
transactions/replay/review recovery, publication controls, exact statistical decisions,
event timing and dependence holds, local/MCP parity and cross-agent fixture smoke tests.
Offline tests need no API key or live provider calls.

`python -m scripts.check_agent2_acceptance` verifies the isolated offline monitoring
workflow; `--live` explicitly opts into a paid model check. Live provider and model
observations are documented separately and are not a guarantee of universal coverage.
The Batch 2 live recovery check reused model-proposed peers without another model
call, excluded a provider/model listing mismatch, and held 48 events across four
contributing firms for review. ASML remained excluded at window assembly. This did
not establish an approved forecast or validate real FinBERT weights. See the
[Batch 2 verification record](docs/agent3-batch2.md).

---

## Honest limitations

Stated plainly, because knowing a tool's limits is part of building it:

- **Agent 1's DCF is a deliberate scaffold**, not a full three-statement model — a
  two-stage fade with scenario weights on reconstructed FCFF with explicit assumptions. Defensible and auditable, not a
  valuation an equity desk would ship as-is.
- **The peer check is directional at small n.** In Agent 1, `--peers` enforces
  the requested set at dispatch; without it, the live model selects peers.
  Neither path establishes economic comparability automatically.
- **Agent 2's fixture series are deliberately clean**, so drift t-stats read sharp;
  real, noisier data would produce more graduated signals. The machinery is what's
  demonstrated.
- **Agent 2's live scope is bounded:** latest annual statements and selected Stadler
  FY2025 issuer reconciliation. Example thresholds are analyst policies, not verified
  contractual terms. No historical provider backfill, installed live schedule or
  notification delivery is claimed.
- **Agent 3's pooled quarterly studies are descriptive.** Repeated firms and
  overlapping windows do not receive independent-event inference or an iid mean
  interval. Provider dates and calendars remain unverified unless supported by
  review evidence; date/gap/benchmark uncertainty holds publication. Historical
  quantiles are not forward predictive calibration. See the bounded policy in
  [Agent 3 Batch 1](docs/agent3-batch1.md).
- **Agent 3 is not fully hardened.** Model-proposed peers remain unverified even
  after listing consistency checks. News aliases and language metadata are not
  automatically verified; conservative clustering can miss reworded copies.
  Real FinBERT accuracy and a populated live news feed remain unverified. Offline
  replay verifies retained windows/scores; it does not establish source authenticity
  or rerun provider/model retrieval. Sparse or invalid event histories are
  reported as exclusions or assembly refusals.
- **Agent 4 still awaits its detailed audit and runs on synthetic-company fixtures** — FP&A data is internal, so this
  is the standard, honest way to portfolio it. The reforecast is a *defensible*
  projection (a method ladder with an honest dispersion-based band), not a
  production forecasting engine; portfolio-level correlated Monte Carlo is a
  documented later step, not claimed here.

---

## Roadmap

The next hardening work is:

1. **Agent 3 closure validation:** issuer-checked US/non-US live event studies, resolve
   ASML target assembly, verify a populated live news feed and optional real FinBERT.
2. **Agent 4:** detailed audit and bounded acceptance before claiming completion.

Agent 2 live scheduling and notification delivery remain deferred. The existing
showcase is illustrative; Agent 3 can export separate replay-verified saved-run reports.
Further statistical extensions (cluster-aware inference, surprise filtering,
robustness windows and richer seasonal forecasting) require separate implementation
and validation.

---

## Stack

Python 3.11+ · Anthropic API (hand-rolled tool-use loop) · yfinance · DuckDB ·
matplotlib · MCP (stdio) · transformers/torch + FinBERT (optional, Track B live) ·
pytest + GitHub Actions CI. Offline runs and the full test suite need no API key,
no network, and no heavy ML dependencies.
