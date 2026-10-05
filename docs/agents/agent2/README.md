# Agent 2 · Financial monitoring and correction review

[Project guide](../../../README.md) · [Agent 1](../agent1/README.md) · [Agent 3](../agent3/README.md) · [Agent 4](../agent4/README.md)

## Contents

- [What is this agent?](#what-is-this-agent)
- [Why this agent?](#why-this-agent)
- [What does it do?](#what-does-it-do)
- [Simple example: leverage crosses a policy threshold](#simple-example-leverage-crosses-a-policy-threshold)
- [When should you use it?](#when-should-you-use-it)
- [Getting started](#getting-started)
- [Observation source and triage are independent](#observation-source-and-triage-are-independent)
- [Monitoring methodology](#monitoring-methodology)
- [Operating commands](#operating-commands)
- [Corrections and review](#corrections-and-review)
- [Saved reports and recovery](#saved-reports-and-recovery)
- [Status and troubleshooting](#status-and-troubleshooting)
- [Validation and implementation](#validation-and-implementation)

## What is this agent?

Agent 2 monitors dated financial measures against explicit policies and their own
history. It records what changed between monitoring cycles, identifies threshold
breaches and unusual patterns, and preserves the evidence behind each result.

It helps answer: **Which items need attention now, how have they changed, and
what did we know when we raised the concern?** Its audience is an analyst or
finance team maintaining a watchlist. The repository calls this covenant
monitoring, but its example live thresholds are analyst policies, not verified
contractual covenant terms.

## Why this agent?

Checking a spreadsheet once can reveal a threshold breach. Repeating that check
reliably requires more: dated observations, consistent definitions, change
classification, handling of missing inputs, and a record of later corrections.
A corrected historical value must not quietly erase what an earlier report said.

Agent 2 separates detection, triage, and review. Deterministic checks establish
facts; optional model triage prioritises known exceptions; an explicit correction
workflow changes effective history while retaining original cycle evidence.
This helps a user focus investigation without losing the audit trail.

## What does it do?

1. Load a watchlist and obtain fixture or supported live annual observations.
2. Check thresholds, anomalies, drift, and eligible breach probabilities.
3. Compare the observation with stored state and classify the change.
4. Commit the cycle and its evidence to DuckDB.
5. Optionally triage surfaced items, constraining publication to known facts.
6. Hold corrections for explicit decisions and export a read-only operational report.

A monitoring cycle is an execution step, not necessarily a new financial reporting
period. Fetching the same annual statement again does not create a new year of
independent financial information.

## Simple example: leverage crosses a policy threshold

**Illustrative numbers, not an issuer result.** An analyst chooses a maximum
leverage policy of 3.0×. A company previously reported 2.4× and now reports 3.2×.
The threshold check identifies a breach, and stored history determines whether
it is new, widening, improving, or stable. Trend/probability diagnostics are
available only if their input and history requirements are met.

The analyst investigates and discovers that the 3.2× observation was later
corrected to 2.8×. The new value is held for review rather than silently replacing
the earlier reading. An explicit approval recalculates effective history and
records the reviewer, reason, and before/after evidence. The original cycle still
shows what was known when 3.2× was assessed.

The report therefore answers two different questions: **what was reported then**
and **what is the accepted current view now**. Neither the chosen 3.0× policy nor
the approval establishes a legal covenant or authenticates the reviewer.

## When should you use it?

Use the fixture workflow to understand monitoring over repeated cycles. Use live
annual ingestion for the documented watchlist schema and available provider
metrics, with explicit source and period review. Selected Stadler Rail FY2025
inputs have issuer reconciliation evidence.

Live ingestion supports `--once` and `--catchup`, not unattended `--run`, `--loop`,
or `--cron`. No live schedule or notification service is installed. Catch-up
records missed monitoring cycles; it does not backfill missing provider history.
The system is a local stateful application, not an authenticated multi-user review
service.

## Getting started

After [installation](../../../README.md#install-and-configure), run from the
repository root with a new demo database name:

```bash
python monitor.py --run 10 --db state/readme-agent2.duckdb
python monitor.py --state --db state/readme-agent2.duckdb
python monitor.py --report output/readme-agent2.html --db state/readme-agent2.duckdb
```

This is offline and deterministic. It writes a database and HTML snapshot without
provider/model calls. `--run` advances cycles without triage. Running it again on
the same database continues that history. For a reproducible clean demonstration,
choose a different database path rather than deleting an existing one.

Open the exported HTML directly in a browser. Initial baselines can suppress
alerts while still containing active breaches; inspect state, not just alert count.

## Observation source and triage are independent

| Choice | Meaning | Network/model requirements |
| --- | --- | --- |
| Default fixture source | Bundled observations | No provider connection |
| `--data-source yfinance --watchlist PATH` | Supported annual statement ingestion | Live provider requests |
| Default `--once` triage | Scripted triage when flags are surfaced | No paid model |
| `--once --live` | Real model triage of surfaced flags | `ANTHROPIC_API_KEY`; paid calls when triage is needed |
| `--run N` / fixture loop | Deterministic monitoring cycles | No model triage |

For the reviewed live annual configuration:

```bash
python monitor.py --once --data-source yfinance   --watchlist watchlists/stadler-annual.json --db state/stadler-live.duckdb
python monitor.py --state --db state/stadler-live.duckdb
python monitor.py --reviews --db state/stadler-live.duckdb
```

Add `--live` to the first command only if you want paid model triage. It loads
local credential configuration; the flag alone does not fetch live observations.
Use a separate database for each intended monitoring configuration. Inspect the
[watchlist contract](../../agent2-live-observations.md) before changing definitions.

## Monitoring methodology

| Check | Question | Boundary |
| --- | --- | --- |
| Threshold | Is the value outside the allowed boundary? | Inclusive allowed boundaries; definition and direction must be correct |
| Robust anomaly | Is the latest reading unusual versus its history? | Robust modified z-score; unavailable diagnostics are explicit |
| Drift | Is a dated trend evident? | OLS and Student-t slope inference; projections rely on model assumptions |
| Breach probability | What barrier-crossing probability follows from estimated drift/volatility? | Conditional first-passage model, not a calibrated universal risk score |

Changes include `NEW_BREACH`, `WIDENING`, `IMPROVING`, `RESOLVED`, and
`KNOWN_STABLE`. Coverage gaps, held corrections, and stale/unavailable inputs must
be read alongside those classifications. A missing diagnostic is not zero risk.

The model may investigate and propose an ordering of known item IDs. Publication
requires a complete valid ordering; Python renders the facts and recommendations,
with active breaches first. Unsupported model prose is withheld. Each triage
attempt retains prompts, responses, tool evidence, and outcome for inspection.

## Operating commands

| Action | Command pattern / effect |
| --- | --- |
| One cycle | `python monitor.py --once --db PATH` |
| Catch up to a cycle | `python monitor.py --catchup N --db PATH`; skip-to-now accounting, not provider backfill |
| Current state | `python monitor.py --state --db PATH` |
| Pending reviews | `python monitor.py --reviews --db PATH` |
| Recorded decisions | `python monitor.py --review-decisions --db PATH` |
| Fixture cadence | `python monitor.py --loop 2 --max 10 --db PATH` |
| Reset | `python monitor.py --reset --db PATH`; **deletes the selected database**, use only for disposable demos |

`PATH`, `N`, and IDs in command patterns are placeholders. Use the exact database
associated with the relevant watchlist. The fixture cron helper prints a schedule
line; it does not install an unattended live service.

## Corrections and review

First inspect `--reviews`, then replace `REVIEW_ID` with the full saved identifier:

```bash
python monitor.py --approve-review REVIEW_ID --reviewer 'Analyst name'   --reason 'Verified corrected observation against source' --db state/stadler-live.duckdb
python monitor.py --reject-review REVIEW_ID --reviewer 'Analyst name'   --reason 'Candidate unsupported; retain prior observation' --db state/stadler-live.duckdb
```

These are alternative decisions, not a sequence to execute on the same review.
Approval changes effective history and recalculates downstream assessments in a
transaction; original completed cycles and model audits remain unchanged. Rejection
leaves accepted history unchanged and suppresses only the identical candidate.
Neither action triggers a notification or model call.

A changed threshold, metric, ticker, or other series definition requires approval
with `--replacement-item-id NEW_ITEM_ID`. Update the watchlist to that new identity
before refreshing; the command does not edit configuration. Retired definitions
remain in history. Issuer-reconciliation failures and missing inputs cannot be
overridden through the correction approval command.

Repeating an identical decision is idempotent; conflicting or stale decisions are
refused. Reviewer names and reasons are local attestations, not authenticated
signatures. See the [complete review contract](../../agent2-review-recovery.md).

## Saved reports and recovery

```bash
python monitor.py --report output/stadler-cycle-2.html --report-cycle 2   --audit-dir output/monitor-triage --db state/stadler-live.duckdb
```

Choose an existing cycle. Without `--report-cycle`, export selects the latest one.
The HTML contains the original selected cycle, current effective state as of
export, pending corrections, decisions, and attributable triage attempts. It is a
snapshot, not a live dashboard; export again after new activity.

Export uses a read-only database connection under the process lock. It does not
advance cycles, decide corrections, or rerun triage. Missing databases/cycles are
rejected; an initialized empty database produces an explicit empty report. The
chosen HTML path is atomically replaced. Audit association uses database path and
cycle digest, so old unlinked audits or audits from a moved database may be omitted.
Raw audit text can be unvalidated even when displayed for inspection.

Retry triage for an existing saved cycle without refetching or advancing state:

```bash
python monitor.py --retry-triage 9 --db state/stadler-live.duckdb
# Opt-in paid attempt against the same frozen cycle evidence:
python monitor.py --retry-triage 9 --live --db state/stadler-live.duckdb
```

Replace `9` with an available cycle. Each retry creates a new audit and uses the
original frozen inputs, even after corrections change current effective state.
Incomplete legacy evidence may prevent retry. This is a new triage attempt, not
continuation of a partially completed model conversation.

## Status and troubleshooting

| Outcome | Meaning / next action |
| --- | --- |
| Normal command exit 0 | Operation completed; still inspect coverage and active breaches |
| Live observation exit 3 | Review-required coverage; inspect held, unavailable, stale, or unaccepted observations |
| Triage retry exit 2 | Failed/withheld retry; saved cycle remains available |
| Usage/data access failure | Read the specific error; exit handling varies by command and can return 1 or 2 |
| Quiet first cycle | Baseline alert suppression; inspect active state before inferring compliance |
| Pending correction | Inspect the exact review and source evidence before choosing a decision |
| Missing probability | Check history and applicability; do not substitute 0% |
| No linked audit in HTML | Check database path, cycle digest, audit directory and legacy-record limits |
| Database busy | Let the existing writer finish; do not reset to bypass locking |

## Validation and implementation

Evidence includes twelve-cycle local/MCP parity, saved-cycle replay, transaction
and concurrency failures, real-model triage, bounded Stadler annual ingestion,
correction approval/rejection, and standalone HTML. Browser checks cover desktop
and narrow layouts, not universal accessibility or browser compatibility.

```bash
python -m scripts.check_agent2_acceptance
```

This creates isolated offline acceptance state. Adding `--live` explicitly opts
into a paid model check. The main code is `monitor.py`, `scheduler/cycle.py`,
`state/store.py`, and `monitoring/{live_data,triage,recovery,reporting}.py`.

- [Calculation and alert contracts](../../agent2-calculation-alerts.md)
- [State and recovery](../../agent2-state-recovery.md)
- [Triage publication controls](../../agent2-triage-publication.md)
- [Bounded v1 acceptance](../../agent2-v1-acceptance.md)
- [Live annual observations](../../agent2-live-observations.md)
- [Correction decisions and triage recovery](../../agent2-review-recovery.md)
- [Operational HTML reports](../../agent2-operational-reports.md)
- [Browser review](../../agent2-browser-review-parts2-and3.md)
