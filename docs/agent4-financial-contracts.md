# Agent 4 Batch 1 — financial contracts and deterministic correctness

Implemented after the [4 October audit](agent4-detailed-audit.md). This batch
addresses A01–A07 and A11–A12 within the bounded offline EUR domain, and establishes
a prior-only dated input contract for the history integration work in Batch 2.
It does not complete Agent 4.

## Money and source domain

Source amounts are **EUR major units**, not already-cent integers. Decimal strings
and `Decimal` values are recommended. Integer and finite float inputs remain
supported for compatibility; floats use their shortest decimal spelling. Input
precision is limited to 12 decimal places. Factor operations use exact rational
arithmetic, and each extended monetary amount is rounded half-even to cents once.
Integer-cent values and results are bounded to ±(2^63 − 1).

Booleans, NaN/infinity, out-of-range values and ambiguous representations are
rejected. Stored amounts and forecast inputs must already be integer cents;
fractional cents are never truncated. Transaction/version guarantees for state
remain Batch 3 work.

A line uses exactly one representation on both budget and actual:

- Revenue: `{amount}` or `{price, volume}`.
- Variable cost: `{amount}` or `{rate, volume}`.
- Fixed cost: `{amount}` only.

Amounts may be signed to represent credits. Unit prices/rates and quantities must
be nonnegative. Amount fields mixed with factor fields, missing factors, unknown
fields and mismatched budget/actual representations are rejected. The cost split
is **rate/volume**, not an efficiency analysis.

Optional `context` metadata accepts `currency`, `monetary_unit`, `quantity_unit`,
`entity`, `close_date` (ISO date), and `source_version`. Only `EUR` and `major` are
supported for monetary context. Conflicting supplied entity/date/source metadata
within a tree is rejected. Product baskets require compatible contexts/quantity
units. Metadata is retained in results. Omitted provenance remains unknown; the
legacy fixture is accepted as an EUR example, not certified source data.

## Product attribution and rounding

Nonempty unique-name product baskets use price for revenue and rate for variable
cost, including the hierarchy's materiality-base calculation. Zero total budget
volume has undefined budget mix and is rejected; use amount-only new-activity
reporting until a deliberate baseline is established. Empty baskets are not zero
activity.

Single-product joint-term materiality is measured against gross driver movement,
so offsetting price and volume changes no longer hide an interaction at zero net
variance. Multiproduct results retain the joint amount. Rounding residuals are
explicit and bounded: two cents for a single factor bridge, three cents per
product for a basket, zero for amount-only lines. These tolerances cover separate
rounding of exact terms, not unexplained accounting adjustments.

## Hierarchy, signs and controls

Every node has exactly one of `leaf` or nonempty `children`. Non-root signs are
explicit. Shared/cyclic objects, depth above 50, duplicate IDs/names, mismatched
node/leaf names and unsupported fields are rejected. Names cannot contain `/`;
missing IDs derive from their unique path. Global name uniqueness is a deliberate
interim restriction while downstream claim/forecast maps still use names.

Internal roots default to profit orientation. A standalone cost leaf defaults to
cost orientation; internal cost roots can specify `root_measure: 'cost'`. Supported
root measures are profit, revenue and cost. A cost overrun is adverse.

An explicit nonnegative integer `materiality_base_cents` is preferred. Otherwise,
the largest absolute **signed** top-level budget is selected and labelled; it is
not assumed to be revenue. Standalone leaves use their actual budget magnitude.
Zero variance is nonmaterial even for zero/tiny bases; relative percentage is
unavailable for zero line budgets; absolute gates have a one-cent minimum.

Optional node-level `budget_cents` and `actual_cents` are **paired source control
totals**. Both must match the computed totals or rollup fails. A successful match
is labelled `source_reconciliation: matched`; absence is `not_provided`.
This checks caller-provided control totals, not authenticity of an issuer/source.

Before publishing a board pack or exception view, the engine rechecks actual minus
budget, driver/residual ties, child/sign aggregation, profit impact, favourability
and provided source controls. It no longer relies on a cached `reconciles` flag.
Source-reconciliation status is returned separately from internal arithmetic status.
Raw SVG rendering and chart geometry remain Batch 4 work.

## Historical input boundary

Legacy `history` is explicitly a prior-only list of integer-cent variances.
Alternatively, nodes may supply:

```json
{
  "observation_history": [
    {"period": "2026-01-31", "variance_cents": 10000},
    {"period": "2026-02-28", "variance_cents": -5000}
  ]
}
```

Dated history requires root `context.close_date`. Periods must be strictly ordered,
unique and earlier than that close. Supplying both forms is rejected. This prevents
current-close leakage at ingestion; persistence/current-observation assembly and
statistical interpretation are still Batch 2 work. The interface does not invent
missing periods or assert that supplied history is complete.

## Reforecast boundaries

Periods must be integer counts, 0 ≤ elapsed ≤ total ≤ 366. YTD, budgets, targets,
phasing and historical values must be valid integer cents. Persistence and direction
must be recognized. A supplied phasing list must have exactly one entry per period
and sum exactly to the annual budget. Invalid phasing is never silently ignored.

- Zero elapsed periods: no landing, band or target-hit probability is published.
  Nonzero YTD with zero elapsed periods is rejected.
- Closed year: landing equals actual YTD; the band is that same deterministic value;
  hit/miss follows the target direction. Historical dispersion is unnecessary.
- Undefined phased performance (zero phased budget to date): no ratio-based
  projection. An explicitly selected one-off remaining-plan calculation or an
  eligible trend calculation can still be used.

Invalid inputs return the existing structured `error` result. The trend eligibility,
normal-distribution assumptions, calibration and uncertainty model remain Batch 2
work. The fixed boundary cases do not establish calibrated future probabilities.

## Validation and remaining work

Regression coverage includes decimal half-even ties, invalid money, conflicting
representations, rate baskets through rollup and output, zero mix, joint interaction,
tree identity, cost-root signs, source-control mismatch, stale/tampered publication,
materiality edge cases, dated-history ordering, forecast boundaries and storage
precision. Independent decimal controls cover both single-product conventions.

A small integration fix also allows a correctly referenced zero driver to pass
commentary reconciliation. It does not resolve the audit's fabricated-reference,
unknown-tier or causal-claim loopholes; those remain Batch 2 priorities.

Batch 2: history/statistical interpretation and grounded claims. Batch 3: atomic
versions and a reliable close workflow. Batch 4: operational reports and charts.

Validation on this batch: the full repository suite passed **816 tests** before
final metadata/materiality refinements; the final focused Agent 4 plus smoke suite
passed **81 tests**. Local and MCP fixture board-pack results matched exactly and
serialized as strict JSON. No live provider/model call was needed.
