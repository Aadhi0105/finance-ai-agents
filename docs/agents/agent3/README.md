# Agent 3 · Historical events and current-news evidence

[Project guide](../../../README.md) · [Agent 1](../agent1/README.md) · [Agent 2](../agent2/README.md) · [Agent 4](../agent4/README.md)

## Contents

- [What is this agent?](#what-is-this-agent)
- [Why this agent?](#why-this-agent)
- [What does it do?](#what-does-it-do)
- [Simple examples](#simple-examples)
- [When should you use it?](#when-should-you-use-it)
- [Offline starting points](#offline-starting-points)
- [Track A: live execution and study design](#track-a-live-execution-and-study-design)
- [Track B: retrieval, relevance and scoring](#track-b-retrieval-relevance-and-scoring)
- [Configuration reference](#configuration-reference)
- [Evidence, HTML, and recovery](#evidence-html-and-recovery)
- [Exit codes and troubleshooting](#exit-codes-and-troubleshooting)
- [Validation and implementation](#validation-and-implementation)

## What is this agent?

Agent 3 offers two related research workflows. **Track A** examines historical
share-price behaviour around company events. **Track B** filters and organises
current news and measures the tone of the retained text.

It helps answer: **What happened around comparable past events, and what relevant
news evidence is available now?** The tracks are separate. News sentiment does
not enter the event-study calculation, and neither output is a calibrated
prediction of the next share-price move.

## Why this agent?

A share-price rise on earnings day may partly reflect a rising market. Comparing
raw returns alone can confuse market movement with company-specific movement.
Likewise, ten headlines may repeat one story, concern a different company, or
fall outside the research period.

Agent 3 makes these distinctions inspectable. Event studies retain dates,
benchmarks, return windows, exclusions, and inference limits. News runs retain
retrieval records, relevance/freshness decisions, clusters, scorer evidence, and
review reasons. Saved bundles allow bounded offline replay of the analysis.

## What does it do?

| Track | Workflow | Output |
| --- | --- | --- |
| A · Events | Select universe → assemble dated events/prices → estimate benchmark model → calculate abnormal returns → apply review/inference controls | Historical brief, event evidence, saved attempt and replay bundle |
| B · News | Retrieve records → check entity/time relevance → cluster related headlines → score retained text → apply publication controls | News brief, exclusions and score evidence, saved attempt and replay bundle |

A model can propose peers for Track A; listing consistency checks do not establish
economic comparability. Track B defaults to local lexical diagnostics, with
optional FinBERT modes. Python performs event-study and aggregation calculations.

## Simple examples

### A: an earnings announcement and a rising market

**Illustrative numbers, not an ASML result.** A company's daily return is +4%.
Its fitted market model implies +1.5% for that day, giving an abnormal return of
+2.5 percentage points. Suppose the abnormal returns across the three-day window
are −0.5%, +2.5%, and +0.2%. Their sum, CAR, is +2.2%.

The agent repeats the calculation for eligible historical events and describes
the retained distribution. That does not mean the next announcement will produce
+2.2%. Repeated events for the same firms or overlapping windows can invalidate
independent-sample inference. Missing disclosure timing can also hold publication
even when arithmetic is available.

The practical use is to examine historical evidence and study design, then decide
whether more event/date/benchmark review is needed.

### B: several headlines about the same announcement

Suppose a feed returns five records: two repeat an earnings story, one concerns
another company, one is stale, and one discusses a new order. Relevance and time
checks exclude unsuitable records; clustering groups the near-duplicate story.
The resulting count describes heuristic headline clusters, not five independent
pieces of evidence.

A positive lexical score means the retained text contains more positive tone
under that scorer. It does not establish a positive earnings surprise or a future
return. The brief can remain held, with diagnostic tone shown separately and no
published signal level.

## When should you use it?

Use Track A for bounded historical event research where dates, benchmarks, listing
identity, and return coverage can be inspected. Use Track B to organise news
records and assess document tone, with explicit aliases and freshness choices.

Neither track provides automated event trading, verified exhaustive news coverage,
or a forward-return forecast. Reviewed plans are attestations with source
references, not authenticated approvals. Current pooled repeated-firm studies
remain descriptive where dependence prevents eligible inference.

## Offline starting points

Install the [shared environment](../../../README.md#install-and-configure) and
run from the repository root. Historical fixture brief, printed to the terminal:

```bash
python -c "from agent3.orchestrator import analyze_event_type, render_brief; print(render_brief(analyze_event_type('semicap_earnings')))"
```

This library example uses fixtures and is illustrative/held. Unlike the bounded
CLI flows below, it does not create a sealed attempt bundle.

For a saved offline news attempt:

```bash
python -m agent3.run_news ASML.AS --alias ASML --scorer stub --demo   --fixture fixtures/news.json --as-of 2026-01-28T23:59:00Z   --db state/readme-agent3.duckdb --output-dir output/readme-agent3
```

No provider or model calls are needed. The fixture cutoff is explicit so records
are evaluated consistently. Stub scores require both `--demo` and `--fixture`;
this illustrative result remains held, normally exit **3**. The command prints
the paths of `run.json` and `bundle.json`.

## Track A: live execution and study design

Explicit peers avoid the model-proposal call, but this command retrieves live
provider prices and earnings data:

```bash
python -m agent3.run_live ASML.AS semicap_earnings --peers ASM.AS BESI.AS   --db state/asml-events.duckdb --output-dir output/asml-events --timeout 300
```

Omitting `--peers` normally requests a paid Anthropic peer proposal and requires
`ANTHROPIC_API_KEY`. `--live-propose` selects that explicitly. Do not combine it
with `--peers`. `AGENT3_LIVE_PROPOSE=0` disables the default proposal and requires
explicit peers; it does not enable a fixture fallback. The repository `.env` is
loaded without overriding exported environment variables.

Use `--study-plan PATH` for a sourced review plan conforming to the
[study-plan contract](../../agent3-batch1.md). Checked-in bounded examples are
`fixtures/agent3_closure/asml-as-source-plan.json` and
`fixtures/agent3_closure/nvda-source-plan.json`; inspect their exact universe and
event scope before use. They are not generic approvals for another peer set.

The standard market model uses **250 estimation returns [-280, -31]** and **three
event returns [-1, +1]**. It estimates abnormal returns relative to the benchmark,
aggregates CAR, and reports the equal-event-weighted mean CAR alongside issuer and
event counts. Review includes session timing, first disclosure, estimation/event
coverage, benchmark compatibility, and dependency assumptions.

Historical quantiles are descriptive. Exact Student-t and multiple-testing checks
apply only when eligible. Repeated firms/overlapping windows do not receive an
independent-event inference or iid mean interval simply because many rows exist.
`validation_only` is not an approved research forecast.

## Track B: retrieval, relevance and scoring

Live lexical examples require provider access but no Anthropic model call:

```bash
python -m agent3.run_news ASML.AS --news-query ASML --alias ASML --scorer lm   --db state/asml-news.duckdb --output-dir output/asml-news
python -m agent3.run_news NVDA --alias NVIDIA --scorer lm   --db state/nvda-news.duckdb --output-dir output/nvda-news
```

`--news-query` controls Yahoo search retrieval; it does not prove that an article
is relevant. Explicit headline aliases/cashtags, timezone-aware publication and
retrieval instants, and the freshness window govern inclusion. A valid empty
provider response is recorded differently from retrieval failure.

| Scorer | Requirements and interpretation |
| --- | --- |
| `lm` | Default disclosed curated lexical subset; diagnostic document tone, held |
| `stub` | Explicit fixture/demo only; illustrative scores |
| `finbert` | Optional `torch`/`transformers` and pinned model revision; real-weight acceptance remains unverified |
| `divergence` | Optional model and lexical comparison; disagreement is diagnostic, not a return forecast |

For optional model scoring, install `torch` and `transformers` in the environment
and configure an actual approved 40-character commit in `AGENT_FINBERT_REVISION`
before selecting `--scorer finbert` or `--scorer divergence`. Initial weights may
require a download. No particular revision is certified by the current acceptance.

Scoring validates available language/truncation metadata and probability vectors.
Conservative clustering preserves negation and changed stories, but may miss
reworded duplicates. Scores describe the supplied text, not necessarily sentiment
about the target entity. Held outputs retain `level=null`; diagnostic means are
separate. More records do not automatically remove review restrictions.

## Configuration reference

| Option | Scope / default |
| --- | --- |
| `--db PATH`, `--output-dir PATH` | Both CLI tracks; use separate paths to organise runs |
| `--timeout SECONDS` | 30–3600; event default 300, news default 180 |
| `--study-plan PATH` | Track A sourced review plan |
| `--retry-from RUN_JSON` | Track A request retry with fresh provider data |
| `--alias TEXT` | News; repeatable, 3–200 characters each, at most 20 |
| `--news-query TEXT` | News live retrieval only, 1–200 characters |
| `--max-age-days N` | News freshness, 1–30, default 7 |
| `--as-of INSTANT` | News timezone-aware cutoff; required with fixtures |
| `AGENT_STATS_VIA_MCP=1` | Track A statistical transport |
| `AGENT_MODEL` | Peer-proposal model |

Defaults for saved CLI paths are anchored to the repository; explicit relative
paths resolve from the caller's working directory. Argument details are available
with `python -m agent3.run_live --help` and `python -m agent3.run_news --help`.

## Evidence, HTML, and recovery

A terminal CLI attempt retains a `run.json` checkpoint and sealed `bundle.json`
where persistence succeeds. The bundle includes normalized inputs, available
provider snapshots, settings, peer decisions, result, provenance, and integrity
hashes. Unique attempt identity is separate from the input fingerprint.

Replace these paths with an actual saved bundle and new output filenames:

```bash
python -m agent3.bundles /path/to/bundle.json   --output /path/to/replay.json --html /path/to/report.html
python -m agent3.bundles /path/to/bundle.json --index-db state/catalyst.duckdb
```

Replay and HTML export make no provider/model calls. Outputs are write-once;
choose a new path rather than modifying sealed evidence. The second command
reconciles a verified bundle into the database index after an indexing failure.

| Operation | Preserved inputs / important boundary |
| --- | --- |
| Track A `--retry-from /path/to/run.json` | Reuses request and accepted peers, fetches fresh market data; not historical replay |
| Track A bundle replay | Recomputes from retained normalized return windows, not raw provider reassembly |
| Track B bundle replay | Rebuilds the funnel from retained scorer responses, without rescoring through the model/lexicon |
| Bundle index recovery | Restores index association independently of analytical execution |

Retries cannot simultaneously change ticker, event type, peers, or study plan;
start a new request for changed research scope. Replay can be matched, mismatched,
or not rebuildable. Exact comparison blocks mismatches; failed/incomplete bundles
do not acquire verified analytical results. Held results stay held. Legacy
checkpoints are not retroactively sealed bundles. Hashes establish integrity of
the retained content, not external source authenticity.

## Exit codes and troubleshooting

| Exit | Meaning | Next action |
| --- | --- | --- |
| 0 | Completed eligible/descriptive result | Read scope; not a future-return forecast |
| 2 | Refused inputs/configuration; Track A can also lack usable events | Inspect request, proposal, study plan and exclusions |
| 3 | Held result | Review evidence, timing, dependence or news-scoring restrictions |
| 4 | Unavailable provider/model/scorer/transport, timeout or interruption | Inspect stage and reason; retry only with understood costs/data changes |
| 5 | Unexpected worker, execution or persistence failure | Preserve checkpoint/bundle and resolve the failure |

An unwritable output directory or early configuration refusal may prevent an
attempt file. Empty news is not provider failure; inspect the retrieval status.
A listing-consistent peer can still be economically unsuitable. A replay mismatch
requires investigation, not editing hashes or relaxing review gates.

## Validation and implementation

ASML and NVIDIA closure checks used issuer-confirmed dates for five events each,
retained prices, independent calculations, actual MCP execution, and saved replay.
The studies remained held. The earlier ASML exception could not be reconstructed
without its original inputs; a successful fresh run is not proof of its old cause.

Populated news acceptance retained 20 provider records per company, selecting 12
ASML and four NVIDIA clusters. Saved-evidence accounting, replay, and HTML passed;
headline/language/lexical limitations still held publication. Real FinBERT accuracy
and full-article sentiment accuracy remain unverified.

- [Event contracts, inference and study plans](../../agent3-batch1.md)
- [Live execution, peer selection and retry](../../agent3-batch2.md)
- [News relevance and scoring controls](../../agent3-batch3.md)
- [Bundles, replay, state and HTML](../../agent3-batch4.md)
- [Issuer-dated closure validation](../../agent3-closure-validation.md)
- [Live-news recovery and populated acceptance](../../agent3-live-news-recovery.md)

`run_live.py`/`execution.py` and `run_news.py`/`news_execution.py` own CLI workers.
`track_a_live.py`, `study_plan.py`, `peers.py`, and shared event tools own study
assembly; `news_live.py`, `news_funnel.py`, and `sentiment.py` own news processing.
`bundles.py` and `catalyst_state.py` own saved replay/index/state. All are under
`agent3/` except the shared calculations in `tools/`.
