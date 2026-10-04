# Agent 4 Batch 3 — versioned state and reliable offline closes

Implemented on 4 October 2026, following the Batch 2 history and claim controls.
Addresses the operational scope of audit findings **A17–A21**. Acceptance uses
synthetic EUR data; no ERP integration or real-company FP&A validation is claimed.

## Run and recover

From the repository root, with dependencies installed:

```bash
python -m agent4.close \
  --input fixtures/agent4/close-june.json \
  --db state/agent4-close.duckdb \
  --output-dir output/agent4-close
```

The command commits a close and exports `output/agent4-close/close-june.json`.
Running the same command again replays the saved result without appending financial
versions or recalculating statistics. It does append an execution attempt and a
delivery receipt. To regenerate a missing export, including after a process restart:

```bash
python -m agent4.close \
  --recover close-june \
  --db state/agent4-close.duckdb \
  --output-dir output/agent4-close
```

Exit codes:

| Code | Meaning | Next action |
| --- | --- | --- |
| 0 | Committed/replayed/recovered run delivered | Inspect the JSON evidence/report |
| 2 | Request/state failure | Correct inputs or state access; inspect the error and attempt history |
| 3 | Close exists, delivery failed | Retry with `--recover` and a writable, nonconflicting output directory |

A zero exit code does not certify forecast accuracy. A valid close can retain a
held forecast or unavailable probability with its reason. Output is a complete
JSON evidence bundle containing the existing board-pack result and SVG, **not the
operational HTML report** planned for Batch 4.

## Explicit input boundary

The fixture is the complete request example. It contains a stable `run_id`, entity,
close date, frequency, approved budget panel, actuals delta, and hierarchy topology.
An optional `supersedes` names a corrected close. Unknown request/topology fields
are rejected rather than silently ignored.

- The bounded command supports **EUR, calendar years and month/quarter/year ends**.
  Fiscal calendars, mixed currencies and unit-driver feeds are not implemented.
- Budget and actuals rows use `{line, period, amount_cents}`. `line` is a stable
  leaf `node_id`; period is `YYYY-MM-DD`; amounts are exact signed integer cents.
- Every leaf needs a full-year budget and all closed YTD actuals. Extra unknown
  lines, duplicate observations, misaligned periods and future actuals are refused.
- `budget.approved: true` is an explicit **caller assertion**, not an approval
  service or authenticated finance sign-off. `source` is a required source label;
  content digests cover the supplied rows, not an externally verified ledger.
- Topology supplies names, stable node IDs, signs and leaf types. The workflow binds
  monetary amounts and histories itself. It cannot accept caller-written histories
  or replace ledger values with independently supplied forecast YTD values.
- Amount-only leaves preserve aggregate variance. Price/volume/mix attribution
  remains unavailable without unit data. No fabricated split is introduced.

Source-control matches mean the tree agrees with the selected panels. They do not
establish external source authenticity or independently audit the panels themselves.

## Immutable versions and restatements

All budget, actuals and forecast writes validate the complete payload before rows
are inserted. A version header and its rows commit in one DuckDB transaction.
Database keys enforce unique version identities and `(kind, version, line, period)`
observations. An exact replay is a no-op; different content or metadata under the
same label is a conflict. Corrections require new labels. Row ordering is canonical
for state-version identity; a close request itself is hashed as supplied, so changing
its array order under the same `run_id` is a request conflict.

Budgets are immutable panels. Actuals are **ordered deltas**: a later version
supersedes only matching line/period observations within the same entity. All other
lines and periods survive. The sequence of committed versions defines order,
including restatements; timestamps are not a tie-breaking financial rule.

`get_actuals(version)` returns the effective panel as of that version.
`actuals_delta(version)` returns just its changed rows. `actuals_snapshot(version)`
also returns each winning observation's source version and digest. Standalone store
calls without entity metadata share an unscoped namespace; the close command always
requires and records the entity. New closes refuse stale actuals versions that would
ignore newer entity deltas. Budget selection remains explicit, so the approved
original plan can continue to be used after a re-budget exists.

Missing probabilities are SQL NULL with an explicit unavailable reason, never NaN.
Non-null probabilities must be finite and in [0,1]. Held projections retain a null
landing, status, reason and full result. Forecast walks include version IDs, source
version lineage and full method/range/assumption evidence. Public table selectors
are whitelisted. Reads verify stored version content against its digest.

Populated legacy `budget`/`actuals`/`reforecast` tables are **refused without writes**.
Their old rows lack reliable uniqueness, date and source identities, so this batch
does not silently migrate them. Preserve the original file and explicitly normalize
and import verified observations into a new database. Empty legacy tables can coexist
with the new namespaced schema. Automatic legacy migration is not implemented.

## Close lifecycle and accounting boundary

For each request, the workflow:

1. Records a durable started attempt outside the accounting transaction.
2. Checks the run ID for exact replay, or checks close freshness and correction scope.
3. In one transaction, creates/reuses validated source versions, resolves effective
   actuals, verifies completeness, builds dated variances, rolls up the hierarchy,
   computes persistence and forecasts, gates commentary, and freezes the full bundle.
4. Commits source versions, forecast evidence, the bundle and the entity's close
   head together. A failure rolls back all of those changes.
5. Records the committed/replayed outcome and exports the saved bundle separately.

A new close date must advance the entity's latest committed close. A same-period
correction requires a new run ID and `supersedes` pointing to that latest run.
An older-period restatement is incorporated through a new current-close delta;
backdated operational closes are refused. An entity-head constraint/write detects
concurrent conflicting closes. DuckDB also supplies its normal process/file locking;
this is not a multi-host service, and a store connection is not shared among threads.

An interrupted attempt may have only a started event. The authoritative recovery
check is whether `get_run(run_id)` exists: replay it if committed, otherwise retry
the original request. Attempt events and delivery receipts are append-only audit
records; the financial versions and saved reports remain unchanged. A failed event
receipt or unexpected I/O error should be resolved by replay/recovery, not by assuming
that an error message proves no commit happened.

## History and forecast binding

All nodes use the same selected source panels and close boundary. Prior observations
are built only where every leaf has both budget and actual data; incomplete older
periods are explicitly listed as exclusions. Calendar gaps remain gaps, allowing
Batch 2's diagnostic holds. The selected approved budget supplies the comparison
basis for every included period, which is recorded rather than mixed implicitly
across budget versions.

Node-level YTD, annual budget, budget phasing and variance histories are aggregated
from those panels using the hierarchy's signs. Forecast direction follows each
node's contribution to the root. Persistence comes from the current rolled result.
The workflow uses the existing phasing/persistence model, not a new trend estimator.
Batch 2's withholding and uncalibrated-probability disclosures continue to apply.

## Saved evidence and delivery recovery

Each immutable run bundle contains the exact request and its digest, source-version
metadata/digests, effective actuals including per-observation lineage, budget rows,
bound hierarchy, full board-pack registry, claims, diagnostics and forecast results.
Schema version and hashes of Agent 4 and shared statistical entry-point source files
identify the implementation. These hashes are identifiers, not bundled executable
code or a guarantee of reproducing another dependency/runtime environment.

The database stores the entire JSON bundle and its digest. Recovery verifies that
digest and writes the stored content; it never consults a newer budget, restatement,
model or provider. Historical exports therefore remain byte-identical after later
closes or re-budgets. This is saved-evidence regeneration, not a fresh statistical
backtest or proof of source truth. Local digests are not authenticated signatures.

Export writes a same-directory temporary file, flushes/fsyncs it, atomically renames
it, and fsyncs the directory. A per-run OS advisory lock serializes exporters.
Identical existing output is accepted; conflicting output is refused. A database
commit and a filesystem export are deliberately separate operations: interrupted
exports leave a recoverable committed bundle. No success receipt is required to
recover a fully written file. Crash-left `.tmp` files are not published artifacts;
`.lock` files may remain and are harmless. The export implementation uses POSIX
`fcntl` and is intended for the repository's macOS/Linux environment.

## Validation and remaining scope

Regression coverage includes whole-version rollback, injected header/row/commit
failures, interruption at run commit, replay conflicts, single-line restatements,
entity isolation, source corruption, stale closes, concurrent head conflicts,
probability boundaries, held forecasts, quarterly/annual closes, commentary gate
failure, failed atomic export, failed delivery receipts, CLI exit codes and recovery
after database reopen/re-budget. Validation completed on 4 October 2026:

- **896 repository tests passed**, including **51 new Batch 3 tests**.
- The checked-in June fixture completed through the CLI with local statistics and
  with `AGENT_STATS_VIA_MCP=1`; complete report objects and frozen source panels
  matched exactly. Database timestamps make independently committed bundle digests
  different, as expected.
- A separate recovery invocation reproduced the original local export byte for byte.
- Generated acceptance artifacts are retained locally under
  `output/agent4-batch3/acceptance-vc5ihs_i/` and are not committed.

Batch 4 still owns the HTML report, waterfall defects and browser acceptance. ERP
connectors, scheduling, interactive budget approvals, fiscal calendars, automatic
legacy migration and forecast calibration remain outside this bounded batch.
