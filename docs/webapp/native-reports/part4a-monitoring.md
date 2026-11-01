# Part 4A — native financial monitoring

Implemented 1 November 2026 for registered saved synthetic Agent 2 snapshots.
Agent 2 opens directly inside Keystone, with the shared visual style, navigation,
source inspection and interactive SVG charts. The original HTML remains a
verified download. Agent 4's native reader remains Part 4B.

## Reading order

1. **Monitoring summary:** selected cycle, observation date, observation count,
   recorded breach count and surfaced-item count. Baseline alert suppression and
   no-new-observation cycles receive different explanations.
2. **Observations and policy thresholds:** searchable cards and attention filters,
   exact values/units, allowed policy direction, saved breach flag, classification,
   early-warning flags, original observation table and skipped-input evidence.
3. **Original-cycle observation history:** select an item, inspect actual retained
   dates and values using pointer/keyboard controls, then open its exact table or
   source. A current row or cycle inventory cannot create a history. No threshold
   line is extrapolated over a possibly changed definition.
4. **Effective state at export:** separate counts and cards spanning retained
   observation dates. Older observations remain visible. Retired series retain
   their replacement identifiers; breach totals exclude retired rows.
5. **Corrections and recovery:** unapplied proposals, locally attributed decisions,
   separately retained before/after histories and triage process metadata. This
   reader cannot submit, approve, reject or retry a correction.
6. **Review requirements:** policy, coverage, correction and diagnostic limitations.
7. **Saved evidence:** exact values, artifact/field references, definitions and
   verified original downloads.

The example distinguishes **four selected-cycle observations, one recorded breach
and two surfaced items**, from **five export-state rows and two non-retired
breaches**. Acme leverage is surfaced as an early warning while still within its
saved policy. Delta's breach is retained from 7 January, despite its duplicate
input being skipped in the selected 9 January cycle. No “all clear” is inferred.

## Data boundaries

`agent2-native-report` **1.1.0** extends the original **1.0.0** mapping without
changing that recipe. The shared view schema remains version 1; the source family
remains `agent2.snapshot/unversioned`. Fresh projections use 1.1.0. Existing
registered 1.0.0 views remain readable and explicitly lack the newer context.
They do not acquire fabricated item associations, flags or export metadata.

Python counts exact saved Boolean `breached` flags, including widening, improving
and stable breaches. The export count excludes rows with `retired_to` set.
Incomplete/non-Boolean flags withhold a count. Each count has its source pointer
and predicate recorded as a bounded Python presentation derivation. The reader
does not reassess thresholds, rerun detection or estimate a new probability.

Only explicitly recognised ratio metrics display as multiples. Unknown units
withhold numerical values/plots. Missing history and invalid/duplicate dates do
not create a series. Actual zero is retained. Original histories are not joined
to effective-state rows or decision histories. Pending candidates are separately
labelled and never applied by the presentation. Original cycles remain immutable.

Thresholds are analyst policies, not verified contractual covenants. Diagnostic
flags are not calibrated financial risk. Local reviewer names are attribution,
not authenticated signatures. Raw model commentary and local audit paths are not
published as report narrative. Unreadable audit counts remain visible.

## Reading and print copy

Agent 2 also has a complete reading copy, independently of card filters or table
pagination. It contains every presentation measure, chart, table row, restriction
and evidence reference. Saved histories retain line geometry and missing gaps;
Agent 3's existing bars retain their geometry. Opening the copy and requesting
print recheck the registered evidence first.

Actual PDF pagination/reconciliation, physical printing, physical touchscreen and
screen-reader sessions, human interpretation acceptance and browser saved-download
completion remain pending. The complete-copy content checks do not close those
gates.

## Reproduce controlled acceptance

From the repository, with the locked local environment and an existing registered
synthetic workspace, choose a **new** output directory:

```sh
.venv/bin/python scripts/prepare_monitoring_report_qa.py \
  --workspace output/workspace-news-3b-final \
  --destination output/workspace-monitoring-qa-new

cd web
pnpm test
pnpm run build
cd ..

.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-monitoring-qa-new --port 8787
```

Open `http://127.0.0.1:8787/#/runs/monitoring-example`. The helper copies registered
originals unchanged and prepares eight labelled synthetic cases: baseline, pending
correction, approved restatement, replacement definition, quiet cycle, no new
observations, missing/unknown evidence and a 32-observation pagination case.
Correction cases exercise the real deterministic fixture engine and existing
decision function in a disposable local database. Controlled coverage variants
are labelled UI fixtures, not verified replay or new market evidence. The helper
refuses an existing destination and publishes the catalogue only after all native
views validate. It checks original source hashes after preparation.

Automated evidence is in `tests/test_native_monitoring.py` and
`web/tests/monitoring-report.test.mjs`, alongside the existing workspace, correction,
source-binding and chart tests. No dependency, provider call, paid-model call,
execution endpoint, approval permission or deployment scope is added by 4A.
