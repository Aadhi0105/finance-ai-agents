# Agent 4 Batch 2 — history, interpretation and claim controls

This batch implements the [audit](agent4-detailed-audit.md)'s A08–A16 controls within
the existing offline, deterministic workflow. It does not implement the close
ledger, transactions or HTML report planned for Batches 3 and 4.

## Current and prior observations

`rollup` now assembles a `history_snapshot` per node, containing prior variances,
the current calculated variance, optional observation dates, the close date and
cadence status. Materiality uses the prior list; persistence uses exactly that list
plus the current variance once. The supplied Product Premium fixture now classifies
the current 4,080,000-cent variance, rather than its previous 195,000-cent variance.

Every rolled node includes its computed persistence result, including unavailable
states. Callers should use this result instead of separately passing `history`
straight to `classify_persistence`. The standalone function still accepts a list
ending in the current observation, for explicit library use. Supplied persistence
maps at publication must equal the node's current computed result; stale maps fail.

Dated histories can declare `history_frequency` as `monthly`, `quarterly` or
`annual`. Calendar-month spacing is checked through the current close. Missing or
irregular periods hold significance and recurrence-based persistence. No periods
are filled or fabricated. Legacy arrays remain supported and labelled as undated,
with unverified cadence. They are ordered observations, not verified consecutive
calendar closes. Same-period history remains an explicitly supplied diagnostic
input and is not automatically inferred from business descriptions.

## Diagnostic meaning and persistence

Shared anomaly results retain reason, method, inference status, sample metadata
and other returned diagnostics. A flat-baseline break is explicitly described as
**deterministic**, not a stochastic significance result. The multiple-line
threshold adjustment remains a heuristic, not calibrated family-wise error control.

Invalid/nonfinite persistence inputs and unavailable significance produce UNKNOWN,
not ONE_OFF. Recurrence labels are provisional pattern rules. A numerical confidence
field is labelled a **heuristic score, not a calibrated probability**. A first
isolated spike is a one-off candidate; reversion and its business cause are not
established. All persistence commentary requires business confirmation.

## Forecast eligibility and publication

Actual-history trend inputs must include:

- `actual_periods`, aligned one-for-one with actual values;
- `frequency` (`monthly`, `quarterly`, `annual`);
- `close_period`, matching the final observation;
- enough dated observations to cover YTD, with the last `elapsed_periods` summing
  exactly to the supplied YTD amount.

The sequence must be ordered, contiguous at the declared frequency and end at the
close. Arbitrary eight-element arrays no longer automatically authorize a trend.
A trend can publish its point landing, but its probability and range are withheld
until parameter uncertainty has been implemented and validated.

Run-rate/phasing probabilities are labelled **uncalibrated model estimates**.
Assumptions explicitly identify comparable independent reporting periods, normal
conditional uncertainty, untested coverage and the absence of cross-line covariance.
UNKNOWN/INSUFFICIENT_HISTORY persistence suppresses probability publication.
Model estimates near zero or one are displayed as `<0.1%` or `>99.9%`, rather than
implying certainty. Closed-year deterministic outcomes may still display 0%/100%.

Successful results contain replayable `inputs`; publication recomputes the result
and rejects changed numbers or metadata. Forecast name/node ID must match its map
entry, and a dated report requires the forecast's close period to match. A forecast's
YTD is kept separate from a single-close P&L value: the report explicitly labels it
as a **caller-supplied YTD scenario**, not automatically reconciled annual actuals.
Source-version/YTD assembly from the ledger belongs to Batch 3.

Both root and child forecasts now publish landing, range, target, direction,
remaining horizon, method, probability interpretation, assumptions and any
persistence adjustment. Insufficient-history states remain visible. Serializable
invalid-input results can be replay-checked and displayed as held; results without
a safe replayable input snapshot are refused at publication instead of silently
omitted.

## Grounding boundary

The former numeric-magnitude/regex gate has been replaced with a canonical claim
registry. Each registry freezes a complete validated hierarchy, its diagnostic
inputs and forecasts, and receives a deterministic content digest. Each claim
contains a node ID, claim kind, tier, registry ID and typed field references.

Allowed claim kinds are deterministic accounting, classification, persistence,
forecast and a qualified business-cause hypothesis. Numbers, signs, labels and
wording are generated from the registry. Publication rejects:

- text or reference mutations, including forged values that do not occur in inputs;
- wrong node, source snapshot, tier or field;
- unsupported numeric formats added to prose, arbitrary causal assertions and
  removed confirmation wording;
- missing or duplicate required claims;
- changed accounting/diagnostic results, stale persistence and altered forecasts.

The gate permits **no free-form rewrite**, including a plausible paraphrase, in
this batch. A future LLM can propose structured selections under a separate design;
it cannot currently publish arbitrary commentary. Exception mode has an explicit
claim scope and retains the root, including its forecast. Rounding residuals are
included in accounting prose, even when zero.

The registry is trusted application data. Its digest detects accidental/mismatched
snapshots; it is **not a signature, authenticated source identity or protection
against an actor replacing both the registry and its digest**. Source truth still
depends on validated inputs and the source-control boundary introduced in Batch 1.

## Output and API changes

`board_pack` and `exception_view` now return `registry`, `full_hierarchy` and
`reforecasts` as serializable evidence alongside their existing outputs. This
retains budget/actual inputs, dates, diagnostics, bands and references that the
flattened presentation previously omitted. Returned evidence can be saved by a
caller; a transactional immutable run-bundle writer is still Batch 3 work.

`build_registry` no longer supplies global sets of allowable magnitudes. Old
unbound claims are rejected. `compose` emits schema-2 canonical claims;
`reconcile` checks the complete requested claim set. The old test helper was fixed
to consume the rolled node's persistence instead of classifying prior-only history.

## Acceptance coverage

Regression tests reproduce the audit's six forged/unsupported claim cases, mutate
canonical claims and registries, omit/duplicate claims, change classifications,
and try wrong-line/wrong-close/tampered forecasts. They also exercise current/prior
alignment, invalid persistence, flat-baseline meaning, dated gaps, root forecasts,
held/unavailable forecasts, trend eligibility, deterministic year-end outcomes,
strict JSON serialization and exception scope.

Forecast calibration/backtesting is **not established** by these tests. The batch
adds explicit scope and withholding rules, not an assertion of reliable 80% coverage.
Browser layout and the known SVG defects remain Batch 4 work.

Validation completed on 2026-10-04: all **845 repository tests** passed, including
**108 focused Agent 4 and smoke tests**. Complete board-pack output matched exactly
between local and MCP statistics execution and passed strict JSON serialization.
The local acceptance sample is saved at `output/agent4-batch2/board-pack.json`
(generated output, not committed).
