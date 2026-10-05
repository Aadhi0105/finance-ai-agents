# Agent 4 · FP&A, variance analysis and versioned close

[Project guide](../../../README.md) · [Agent 1](../agent1/README.md) · [Agent 2](../agent2/README.md) · [Agent 3](../agent3/README.md)

## Contents

- [What is this agent?](#what-is-this-agent)
- [Why this agent?](#why-this-agent)
- [What does it do?](#what-does-it-do)
- [Simple example: explaining a profit shortfall](#simple-example-explaining-a-profit-shortfall)
- [When should you use it?](#when-should-you-use-it)
- [Getting started](#getting-started)
- [Inputs and configuration](#inputs-and-configuration)
- [Accounting, history and forecasting](#accounting-history-and-forecasting)
- [Versioned closes and corrections](#versioned-closes-and-corrections)
- [Reports and delivery recovery](#reports-and-delivery-recovery)
- [Exit codes and troubleshooting](#exit-codes-and-troubleshooting)
- [Validation and implementation](#validation-and-implementation)

## What is this agent?

Agent 4 compares actual financial performance with an approved-budget assertion,
explains the arithmetic sources of variance, and saves a traceable period close.
It can retain provisional diagnostics and forecasts alongside an operational HTML
report and the exact evidence used to produce it.

It helps a controller or FP&A analyst answer: **Where did we differ from plan,
do the numbers reconcile, what assumptions underlie the projection, and which
budget/actual versions did this report use?** It uses deterministic Python
accounting and canonical commentary, with no LLM required.

## Why this agent?

A variance report is easy to misunderstand when costs have the wrong sign,
subtotals do not reconcile, missing history is filled implicitly, or a revised
budget quietly changes an older report. A failed file export can also leave the
operator unsure whether the accounting close actually committed.

Agent 4 addresses those problems separately: exact monetary calculations,
explicit tree/sign rules, history and claim controls, immutable source versions,
a transactional close, and recoverable delivery. This makes the report useful
for explaining supplied figures and tracing corrections. It does not establish
why the business changed without supporting causal evidence.

## What does it do?

1. Validate budget/actual panels, account hierarchy, dates, identities, and source labels.
2. Resolve effective actuals, including explicit restatements.
3. Calculate variances and roll them through the hierarchy with cent reconciliation.
4. Assess materiality and eligible history diagnostics; produce conditional forecasts where supported.
5. Generate claims tied to frozen numerical evidence.
6. Commit sources, forecast evidence and a complete close bundle together.
7. Export JSON and optional HTML, retaining recoverability if delivery fails.

The broader library also supports unit-based price/volume/mix decomposition.
The integrated close command currently uses an **amount-based ledger**; it must
not be described as automatically extracting unit drivers from an ERP feed.

## Simple example: explaining a profit shortfall

**Illustrative numbers, not the checked-in June fixture.** A business budgets
€100,000 revenue and €70,000 costs. Actual revenue is €95,000 and costs €72,000.

| Measure | Budget | Actual | Change | Profit effect |
| --- | ---: | ---: | ---: | ---: |
| Revenue | €100,000 | €95,000 | −€5,000 | €5,000 adverse |
| Costs | €70,000 | €72,000 | +€2,000 | €2,000 adverse |
| Profit | €30,000 | €23,000 | −€7,000 | €7,000 adverse |

Agent 4 reconciles the €7,000 shortfall to lower revenue and higher costs. The
cost increase is an upward amount change but adverse for profit. A waterfall and
exact table show both contributions without reversing their meaning.

With amount-only inputs, the agent cannot say that lower revenue was caused by
lower prices or fewer units. With insufficient history, it cannot claim the
shortfall is structural or provide a supported forecast probability. If costs
are later corrected, a new version and explicit corrected close preserve both
the original and revised evidence.

This helps the analyst direct questions to the business and explain the numbers
accurately. Arithmetic attribution is not independent proof of business causation.

## When should you use it?

The accepted integrated scope is **offline, deterministic EUR, calendar-year,
amount-based closes**, with monthly, quarterly, or annual periods. Every leaf
requires a full-year budget and complete closed YTD actuals. The supplied examples
are synthetic; an authorized real-company dataset has not yet been validated.

Multi-currency translation, fiscal calendars, ERP connectors, authenticated budget
approval, unattended scheduling, and calibrated forecasting are outside that
scope. `budget.approved: true` records the caller's assertion, not a sign-off
service. POSIX file locking makes the documented export environment macOS/Linux.

## Getting started

Install the [shared dependencies](../../../README.md#install-and-configure), then
run from the repository root. No API key, provider, or model is needed:

```bash
python -m agent4.close --input fixtures/agent4/close-june.json   --db state/readme-agent4.duckdb --output-dir output/readme-agent4 --html
```

Use a new database path for a fresh demonstration. The command commits `close-june`,
exports `output/readme-agent4/close-june.json`, and reports an HTML path under a
`reports-<fingerprint>/` directory. Open the HTML directly in a browser. Keep the
whole reports directory when copying it: related close pages, evidence files, and
the manifest support its navigation.

Repeating the identical request replays the stored close instead of adding
financial versions. It still records an execution attempt and delivery evidence.
A successful close may contain unavailable diagnostics or a held forecast; inspect
the reasons rather than assuming every section must produce a number.

## Inputs and configuration

Use [the complete June request](../../../fixtures/agent4/close-june.json) as the
schema example rather than inventing a partial request.

| Input | Meaning / contract |
| --- | --- |
| `run_id`, `entity`, `close_period`, `frequency` | Stable close identity, company scope and aligned period boundary |
| Budget version, source, approved flag, rows | Explicit full-year comparison panel; approved is a caller assertion |
| Actuals version, source, rows | Append-only delta; effective prior observations survive unless replaced |
| Row `line`, `period`, `amount_cents` | Stable leaf ID, `YYYY-MM-DD`, exact signed integer cents |
| Hierarchy topology | Stable nodes, leaf types and explicit add/subtract roles |
| `supersedes` | Explicit link to the latest close being corrected |
| `data_kind` | `synthetic` or `unverified`; not external source authentication |

Unknown request fields, duplicate rows, unknown accounts, future actuals,
incomplete YTD panels, and misaligned dates are refused. Enter amounts using the
hierarchy's sign convention; do not negate a cost a second time merely because
it subtracts from profit. Budget phasing and forecasts derive from the selected
panels, not separately supplied caller-written histories.

The close CLI requires `--db` and `--output-dir`, plus either `--input` or
`--recover`. `--html` adds report delivery. `AGENT_STATS_VIA_MCP=1` selects shared
statistical checks over local MCP; accounting and state stay in the local engine.

## Accounting, history and forecasting

| Area | Method and boundary |
| --- | --- |
| Monetary arithmetic | Validated decimal/factor inputs, half-even rounding to integer cents, explicit rounding residuals where applicable |
| Hierarchy | Leaf decomposition plus signed aggregation; every subtotal must reconcile |
| Amount-only variance | Exact total difference; price/volume/mix unavailable without unit inputs |
| Unit-based library | Revenue price/volume/mix, variable-cost rate/volume, fixed-cost spending; convention and interaction treatment disclosed |
| Materiality | Absolute/relative magnitude crossed with eligible robust anomaly evidence |
| Persistence | Provisional recurrence/significance rules; gaps and unavailable history remain unknown |
| Reforecast | Disclosed method ladder and conditional history-based range where eligible; not calibrated confidence |
| Commentary | Exact canonical claims bound to a frozen registry; unsupported rewrites and causal claims rejected |

Current observations are not counted twice in prior history. Calendar gaps remain
gaps. Missing ranges/probabilities are null with reasons, not fabricated zeroes.
At year end there is no remaining forecast horizon; the completed-year amounts
must be interpreted accordingly. Forecast parameter uncertainty and calibration
remain limitations even when the accounting reconciles.

The integrated workflow binds phasing, YTD totals, history and direction from the
selected source panels. Passing source-control checks means agreement with those
panels, not independent verification against an authenticated ledger.

## Versioned closes and corrections

A source version is immutable. Reusing the same version with identical content
is a no-op; different content or metadata conflicts and requires a new version.
Actuals versions are ordered deltas within the entity, so a restated observation
does not erase unaffected accounts or periods. Effective snapshots retain the
winning source identity for each observation.

A new operational close must advance the entity's latest close date. A same-period
correction needs a new run ID and `supersedes` referencing the latest run. An
older-period restatement is incorporated into a new current-close delta;
backdated operational closes are refused. Budget selection remains explicit after
a re-budget, preserving the distinction between original and revised plan.

The close transaction commits sources, forecasts, the full evidence bundle, and
the entity's close head together. Failures roll back that accounting transaction.
Append-only attempt events sit outside it so an interrupted attempt can remain
visible. A failure message by itself does not prove that no close committed.

Populated legacy tables lacking sufficient source/version identities are refused
without silent migration. Preserve the original database and explicitly normalize
verified inputs into a new database if migration is needed.

## Reports and delivery recovery

Export HTML from an already committed close without recalculating its statistics:

```bash
python -m agent4.report --db state/readme-agent4.duckdb   --run-id close-june --output-dir output/readme-agent4
```

The report includes close totals, variance waterfall and table, account detail,
review priorities, history exclusions, forecast assumptions/holds, original actuals
delta versus effective actuals, source versions, and related-close navigation.
The exporter validates saved accounting and claims, escapes text, and builds charts
from saved numbers. The portable pages need no server or external scripts.

If JSON or HTML delivery fails after commitment, recover the saved run:

```bash
python -m agent4.close --recover close-june --db state/readme-agent4.duckdb   --output-dir output/readme-agent4 --html
```

| Artifact | Recovery guarantee / limit |
| --- | --- |
| Saved JSON bundle | Digest-verified stored content; repeated delivery can reproduce identical bytes without recalculation |
| HTML report | Derivative rendering of validated saved evidence; may change with renderer or history-navigation snapshot |
| Report directory | Content-identified snapshot containing related close pages and evidence; retain as a unit |
| Attempts/receipts | Append-only execution/delivery history; not a replacement for checking committed run existence |

Exports use temporary files, atomic publication and advisory locks. Identical
existing content is accepted; conflicting output is refused. Use a new writable
output directory or resolve the specific conflict. Do not edit the frozen bundle
to make a renderer accept it. Local hashes identify integrity, not authenticated
protection against replacing the database itself.

## Exit codes and troubleshooting

| Command / exit | Meaning | Next action |
| --- | --- | --- |
| Close 0 | Committed/replayed/recovered and delivered | Inspect accounting and forecast status |
| Close 2 | Request/state failure | Correct inputs/access and inspect attempt evidence |
| Close 3 | Close exists but delivery failed | Recover the committed run to a writable, nonconflicting destination |
| Separate report 0 / 2 | Delivery success / failure | Inspect saved run and export error |

| Symptom | What to check |
| --- | --- |
| Missing YTD actuals | Every required leaf and closed period; do not insert zero without evidence |
| Version or run conflict | Use exact replay or a new explicit version/correction, not the same ID with changed content |
| Stale close | Incorporate late observations through the current-close correction policy |
| Held forecast / unknown persistence | History completeness, calendar gaps, method eligibility and documented assumptions |
| Report refuses source evidence | Preserve the database; investigate integrity/reconciliation failure |
| File delivery failure | Determine whether the run committed, then recover; do not duplicate the accounting close |

## Validation and implementation

Controlled acceptance covers twelve monthly closes, a restatement, a re-budget,
and a separate history-gap case. Independent arithmetic checks and local/MCP
comparisons cover all 15 evidence snapshots. JSON and HTML delivery failures were
recovered after reopening the database. The latest recorded full suite passed
**930 tests**; this is historical evidence, not a fresh run performed by reading
this guide.

Run the offline acceptance sequence in its own generated output area:

```bash
python -m scripts.check_agent4_closure
```

Browser acceptance examined account/history navigation and narrow layouts. Batch 4
used 1280/390 CSS-pixel widths; the closure follow-up actually measured 984×692 and
300px width despite different requested viewport sizes. These checks are bounded,
not a claim of universal browser/accessibility certification.

- [Financial contracts and decomposition](../../agent4-financial-contracts.md)
- [History and canonical-claim controls](../../agent4-history-claim-controls.md)
- [Transactional close, versioning and recovery](../../agent4-close-recovery.md)
- [Operational HTML and waterfall validation](../../agent4-operational-reports.md)
- [Controlled end-to-end closure acceptance](../../agent4-closure-validation.md)

`agent4/contracts.py`, `decomposition.py`, and `hierarchy.py` own accounting;
`history.py`, `materiality.py`, `persistence.py`, and `reforecast.py` own diagnostic
inputs and methods. `state.py` and `close.py` own durable versioned execution;
`commentary.py`, `output.py`, and `report.py` own claims and delivery. Real-company
acceptance, ERP feeds, authenticated approvals, broader currencies/calendars and
forecast calibration require separate implementation and validation.
