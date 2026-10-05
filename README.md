# finance-ai-agents · Keystone

[![tests](https://github.com/Aadhi0105/finance-ai-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/Aadhi0105/finance-ai-agents/actions/workflows/ci.yml)

Four independently usable finance agents turn financial inputs into research,
monitoring, market-event analysis, and management-accounting reports. Python is
the authoritative calculation layer. Where a language model participates, its
role is constrained by evidence and publication controls.

This repository is for analysts exploring the workflows and developers inspecting
how they work. It includes offline examples, explicit live-data paths, saved
evidence, regression tests, and bounded acceptance records. It does not claim
universal company coverage or unattended production readiness.

## Contents

- [Choose an agent](#choose-an-agent)
- [How the project fits together](#how-the-project-fits-together)
- [Install and configure](#install-and-configure)
- [Try each agent offline](#try-each-agent-offline)
- [Read the result before acting on it](#read-the-result-before-acting-on-it)
- [Shared tools and MCP](#shared-tools-and-mcp)
- [Validation and current scope](#validation-and-current-scope)
- [Repository map](#repository-map)

## Choose an agent

| Agent | Question it helps answer | Inputs → outputs | Model involvement |
| --- | --- | --- | --- |
| [1 · Company research](docs/agents/agent1/README.md) | How has this company performed, and what do explicit valuation assumptions imply? | Ticker, statements, prices, peers → financial evidence, valuation, charts, research report | Live model selects tools and proposes a draft; Python computes and constrains publication |
| [2 · Financial monitoring](docs/agents/agent2/README.md) | What changed, breached a threshold, or deserves investigation? | Watchlist and dated observations → cycle history, exceptions, correction reviews, operational report | Optional model triage orders known items; deterministic code renders facts |
| [3 · Events and news](docs/agents/agent3/README.md) | How did prices behave around past events, and what is the tone of relevant current news? | Event/price evidence or news records → historical study or news brief, replay bundle, HTML | Optional model peer proposals; optional FinBERT document-tone scoring |
| [4 · FP&A and close](docs/agents/agent4/README.md) | How does actual performance differ from budget, and what does the saved close establish? | Budget, actuals, account hierarchy → reconciled variances, provisional forecasts, versioned close, report | Deterministic accounting and canonical commentary; no LLM needed |

Each agent guide starts with **what it is, why it exists, and a worked example**,
then provides commands, methodology, recovery procedures, and evidence links.

## How the project fits together

```text
Provider data / explicit files / offline fixtures
                    ↓
         Agent-specific input contracts
                    ↓
      Python financial and statistical tools
                    ↓
       Evidence and publication controls
                    ↓
        Saved results, state, and reports
```

The four agents are not an automatic pipeline. Agent 1 and Agent 2 reuse the
Anthropic tool loop; Agent 3 has its own bounded execution workers; Agent 4 runs
an accounting workflow. Shared statistics are available locally and over MCP.
Each agent owns its own state and recovery semantics.

For example, researching a company with Agent 1 does not automatically create an
Agent 2 watchlist, and news sentiment from Agent 3 does not enter its event-study
return calculation. Agent 4 requires internal budget/actual inputs; public market
data cannot supply a company's approved phased budget.

## Install and configure

Run the following in a terminal. The examples use macOS/Linux shell syntax.
Python **3.11 and 3.12** are tested in CI. Agent 4's file-export locking uses POSIX
`fcntl`; Windows support is not established by those tests.

```bash
git clone https://github.com/Aadhi0105/finance-ai-agents.git
cd finance-ai-agents
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

If already cloned, enter that checkout and activate its environment instead.
Run all commands in these guides from the repository root. Dependency installation
requires network access; the offline examples below do not require provider or
model calls once dependencies are installed. Dependencies use version ranges,
not a fully locked environment.

| Setting | When it matters |
| --- | --- |
| `ANTHROPIC_API_KEY` | Agent 1 live research, Agent 2 paid live triage, Agent 3 model peer proposals |
| `AGENT_MODEL` | Optional Anthropic text/tool-use model override; the configured default is in `agent/models.py` |
| `AGENT_STATS_VIA_MCP=1` | Shared statistics over the local stdio MCP server for Agents 2, 3 Track A, and 4; local is the default |
| `AGENT_SENTIMENT_SCORER` | Agent 3 news default scorer; an explicit `--scorer` takes precedence |
| `AGENT_FINBERT_REVISION` | Required immutable 40-character model commit for optional FinBERT/divergence scoring |

Configure credentials in your environment or a local, gitignored repository `.env`.
Do not commit keys. Agent 1 offline mode ignores `.env`; other entry points have
the mode-specific behaviour described in their guides. Live data access and paid
model use are separate choices, particularly in Agent 2.

Optional FinBERT modes require `torch` and `transformers`, plus model weights.
They are unnecessary for the basic installation, lexical news analysis, and
fixture examples. Real-weight accuracy remains outside the accepted scope.

## Try each agent offline

Use a new demo directory name if you want a fresh stateful example. Reusing an
Agent 2 database advances its cycles; reusing an identical Agent 4 close replays
its saved result. These commands do not reset an existing database.

### Agent 1: financial research

```bash
python run.py --offline ASML.AS --output output/readme-agent1
```

Creates a unique run directory with `model.json`, charts, and normally
`report_REVIEW.html`. **Exit 3 is expected for illustrative fixture evidence**;
it does not mean artifact generation failed.

### Agent 2: monitoring and saved report

```bash
python monitor.py --run 10 --db state/readme-agent2.duckdb
python monitor.py --state --db state/readme-agent2.duckdb
python monitor.py --report output/readme-agent2.html --db state/readme-agent2.duckdb
```

Runs ten deterministic fixture cycles, saves monitoring state, and exports a
read-only HTML snapshot. `--run` does not perform model triage. Open the HTML in
a browser; export again to reflect later state.

### Agent 3: news evidence demonstration

```bash
python -m agent3.run_news ASML.AS --alias ASML --scorer stub --demo   --fixture fixtures/news.json --as-of 2026-01-28T23:59:00Z   --db state/readme-agent3.duckdb --output-dir output/readme-agent3
```

Saves `run.json` and a sealed `bundle.json` in the printed attempt directory.
The illustrative scores remain held, normally **exit 3**. The agent guide also
provides an offline historical-event example and saved-bundle HTML export.

### Agent 4: versioned close and report

```bash
python -m agent4.close --input fixtures/agent4/close-june.json   --db state/readme-agent4.duckdb --output-dir output/readme-agent4 --html
```

Commits the synthetic June close, exports `close-june.json`, and prints the HTML
location. Keep the entire generated `reports-<fingerprint>/` folder for working
history links and evidence downloads. A valid close can contain a held forecast.

## Read the result before acting on it

A completed calculation, a publishable report, and an externally verified source
are different things. Review requirements are part of the output, not cosmetic
warnings. Missing evidence must not be interpreted as a zero, a clean bill of
health, or a confident forecast.

| Agent | Important interpretation rule |
| --- | --- |
| 1 | `report_REVIEW.html` requires analyst review; selected issuer checks do not verify every company or period |
| 2 | A quiet baseline can still contain active breaches; saved cycles and corrected current state answer different questions |
| 3 | Historical return distributions and document sentiment are not calibrated forecasts of future returns |
| 4 | Reconciliation proves agreement within supplied inputs; it does not authenticate a ledger or validate a forecast |

Exit codes are agent-specific. In particular, Agent 1's exit 3 is a review-required
result, while Agent 4 close's exit 3 means the close committed but delivery failed.
Use the individual guide before building automation around a return code.

Saved JSON, database records, and HTML may contain source financial information,
model audit text, and reviewer attribution. Treat them as evidence artifacts when
sharing. Read-only HTML reports do not provide authenticated approval workflows.
The [showcase](keystone-showcase/README.md) is an illustrative prototype, separate
from reports generated from saved runs.

## Shared tools and MCP

The stdio server in `mcp_server/server.py` exposes
`anomaly_significance_check`, `drift_check`, `breach_probability`, and
`run_event_study`. Set `AGENT_STATS_VIA_MCP=1` on a supported invocation to use the
local MCP transport. This does not install a hosted service or change the input
quality requirements.

Agent 2 monitoring, Agent 3 event analysis, and Agent 4 shared statistical checks
have bounded local/MCP parity evidence. Agent 1's research tools remain local.
Threshold evaluation, providers, news scoring, accounting, and state persistence
are not moved wholesale into MCP.

## Validation and current scope

Documentation status: **5 October 2026**. The latest recorded full-suite closure
validation reports **930 passing tests**; that is a dated acceptance result, not
a promise that every future checkout has the same count. CI runs Python 3.11 and
3.12 on Ubuntu. Historical records retain the counts from their own sessions.

| Agent | Demonstrated scope | Important remaining work |
| --- | --- | --- |
| [1 acceptance](docs/agent1-v1-acceptance.md) | Financial contracts, evidence controls, saved reports, selected live companies and issuer reconciliation | Broader provider/company coverage; economic peer review; comprehensive browser validation |
| [2 acceptance](docs/agent2-v1-acceptance.md) | Monitoring/replay, local/MCP checks, real-model triage; later live annual data, correction recovery and HTML | Installed live scheduling, notifications, broader live-data acceptance |
| [3 closure](docs/agent3-closure-validation.md) and [news acceptance](docs/agent3-live-news-recovery.md) | Issuer-dated ASML/NVIDIA event checks; populated news, saved replay and reports | Real FinBERT validation, sentiment benchmark, stronger dependence-aware inference |
| [4 closure](docs/agent4-closure-validation.md) | Synthetic year of EUR/calendar-year amount closes, corrections, re-budget, recovery and MCP parity | Authorized internal-company pilot, forecast calibration, ERP, fiscal/multi-currency support |

Run deterministic regression tests after installing development dependencies:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Additional offline acceptance entry points:

```bash
python -m scripts.check_agent2_acceptance
python -m scripts.check_agent4_closure
```

Live checks are opt-in and documented separately. A historical successful live
run does not guarantee today's provider availability. Browser inspections are
bounded layout checks, not cross-browser accessibility certification.

## Repository map

| Path | Responsibility |
| --- | --- |
| `run.py`, `agent/`, `composer.py` | Agent 1 entry point, model loop, research artifacts |
| `tools/`, `validation/` | Financial/statistical contracts, calculations, Agent 1 evidence/publication controls |
| `monitor.py`, `scheduler/`, `state/` | Agent 2 cycle execution, persistence, classification |
| `monitoring/` | Agent 2 live ingestion, triage, correction/retry recovery, HTML export |
| `agent3/` | Event and news tracks, peer/study plans, bounded workers, state, sealed bundles/replay |
| `agent4/` | Accounting contracts, decomposition, hierarchy, history, forecasts, close state, report/recovery |
| `mcp_server/` | Shared statistical tools over stdio |
| `fixtures/`, `watchlists/`, `references/` | Offline examples, live monitoring definitions, issuer evidence |
| `scripts/`, `tests/` | Acceptance runners and regression tests |
| `docs/agents/` | The four current operating manuals |
| `docs/` | Detailed contracts, audits, and dated acceptance records |
| `keystone-showcase/` | Illustrative static interface |

Start with an [agent guide](#choose-an-agent), then follow its evidence links for
the detailed calculation and validation boundaries. Earlier batch documents
remain historical records; statements about work planned for a later batch should
be read alongside the current guide and subsequent acceptance record.
