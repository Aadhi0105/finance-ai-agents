# Agent 4 — detailed implementation and hardening audit

Follow-up: [Batch 1 implementation and remaining limits](agent4-financial-contracts.md).
Follow-up: [Batch 2 history and claim controls](agent4-history-claim-controls.md).
The findings below describe the pre-fix baseline.

Audit date: **4 October 2026**. Reviewed implementation: **0cb6ea1**, after
Agent 2 operational reports merged. This is a review, not a fix batch.

## Executive assessment

Agent 4 is a useful deterministic FP&A prototype, but is **not ready to be called
complete or to publish an unattended board pack from arbitrary company inputs**.
The standard synthetic P&L works. Important advertised guarantees are narrower
than the implementation suggests: integer-cent outputs do not guarantee decimal
input accuracy; an internally balanced bridge is not reconciliation to independent
accounts; and a claim's own numeric references are not independent grounding.

The highest-priority problems are financial input contracts, reforecast boundary
conditions, commentary grounding, and transactional/versioned state. They should
be fixed before adding a live model, polished dashboard, or scheduling.

This audit records **24 grouped findings**. P1 means fix before operational use;
P2 means a material correctness, interpretation or usability issue that belongs in
the hardening plan. Feature gaps are identified separately from executable bugs.
No P0 incident is claimed: this is a local synthetic-data prototype, and the audit
found no evidence of deployed financial decisions being affected.

## Scope, method and limits

Read all eight substantive Agent 4 modules, its fixture, direct tests and smoke
coverage, shared anomaly implementation/validation boundary, README claims and
showcase integration. Traced the actual public functions and their callers.

Executed:

- **33 existing tests passed** across the three Agent 4 test files and smoke tests.
- The checked-in audit probe exercises 32 named cases, including deliberately
  invalid inputs, forged claims, altered output, and isolated state writes.
- **2,000 independent arithmetic controls passed**: seeded two-decimal unit prices
  and integer volumes, comparing results to integer multiplication outside the
  implementation. This supports that bounded domain, not arbitrary monetary inputs.
- Local and MCP execution of the complete fixture rollup returned identical JSON;
  both processes exited successfully. This establishes fixture parity, not all-input parity.
- Extended checks compare current-vs-prior history semantics, diagnostic metadata,
  root/child forecast publication and actual SVG output.
- Browser inspection of an explicitly synthetic review wrapper around the real
  renderer, including normal, all-negative and single-leaf charts. The all-negative
  clipping defect was reproduced visually and in SVG coordinates.

The review did not change Agent 4 production code or production databases. State
failure probes use temporary databases. No external company data, paid model calls,
ERP credentials, or live LLM were used. There is no Agent 4 model execution path to
validate yet. Forecast calibration, multi-process races, large-dataset performance,
and exhaustive browser/accessibility compatibility remain unverified.

Reproduce from the repository root:

```sh
.venv/bin/python -m pytest tests/test_agent4_decomp.py tests/test_agent4_commentary.py tests/test_agent4_behavior.py tests/test_smoke.py -q
PYTHONPATH=. .venv/bin/python docs/audits/agent4_probe.py
PYTHONPATH=. .venv/bin/python docs/audits/agent4_extended.py
```

The probes record observed behavior; they are **not acceptance tests declaring
those behaviors correct**. Their JSON/screenshots/HTML live in ignored
`output/agent4-audit/`. The first script must run before the extended script.

## What actually exists

| Layer | Implemented behavior | Important boundary |
| --- | --- | --- |
| Decomposition | Single-product sequential/symmetric price-volume; sequential multiproduct price/rate-volume-mix; amount-only spending | Float inputs converted to cents; no complete source/units/schema contract |
| Hierarchy | Recursively signed leaf/subtotal aggregation and classifications | Requires caller-built tree; no independent accounting control total |
| Materiality | Absolute/relative thresholds and shared robust anomaly result | Default base is inferred; significance is a diagnostic, not a calibrated p-value |
| Persistence | Recurrence/sign consistency/significance rules | List must end with the current variance; confidence is heuristic |
| Reforecast | Run-rate, phasing and trend; persistence adjustment; normal-based bands | Separate callable function; history alignment and assumptions largely caller-owned |
| State | DuckDB budget/actual/reforecast tables | Not integrated into a close workflow; no transaction/version integrity guarantee |
| Commentary | Deterministic templates, numeric registry and regex checks | No LLM; refs are not bound to authoritative registry paths |
| Output | Python dictionaries and inline SVG | No saved-run HTML report, exporter, close manifest or live browser dashboard |

The README demo calls `rollup(fixture)` then `board_pack(tree)` and writes only the
SVG. It does not load versioned actuals, compute persistence/reforecasts, write a
forecast version, freeze a registry, or save an auditable run bundle. The state
module mentions `--close`; no such entry point was found. The showcase explicitly
sets Agent 4's renderer to `null` and disables the tab.

## Findings register

| ID | Priority | Area | Finding |
| --- | --- | --- | --- |
| A01 | P1 | Money | Float conversion and permissive numeric inputs undermine the money contract |
| A02 | P1 | Inputs | Conflicting representations and missing semantic metadata are not controlled |
| A03 | P1 | Hierarchy | Rate-based multiproduct cost crashes in default-base estimation |
| A04 | P2 | Attribution | Zero-budget mix, zero-net interactions and efficiency wording mislead |
| A05 | P1 | Tree identity | Ambiguous trees, duplicate names and cost-root signs are accepted |
| A06 | P1 | Reconciliation | Output trusts a stale flag and has no independent accounting gate |
| A07 | P2 | Materiality | Zero/tiny/inferred bases produce misleading materiality |
| A08 | P2 | Diagnostics | Shared-tool reasons and deterministic-break metadata are discarded |
| A09 | P1 | History | Prior-only versus current-included history contracts are inconsistent in usage |
| A10 | P2 | Persistence | Invalid/unknown evidence can become an actionable one-off classification |
| A11 | P1 | Forecast | Inconsistent phasing can rewrite a closed year's actual result |
| A12 | P1 | Forecast | No-elapsed and year-end probability handling is wrong |
| A13 | P2 | Forecast | Trend eligibility, dispersion assumptions and confidence need explicit controls |
| A14 | P1 | Grounding | Fabricated claim references bypass the numeric registry |
| A15 | P1 | Claims | Taxonomy, causal qualifiers and non-euro figures are not enforced |
| A16 | P1 | Publication | Root forecast omitted; published child forecast loses its band and caveats |
| A17 | P1 | State | Failed writes can commit a partial immutable budget version |
| A18 | P1 | Versions | Duplicate version/observation writes and invalid amounts/probabilities persist |
| A19 | P2 | Snapshots | Latest-actuals semantics do not define a restated effective history |
| A20 | P2 | Audit trail | Forecast walk lacks version/source lineage and full result evidence |
| A21 | P1 | Lifecycle gap | No transactional close-to-report execution or recovery workflow |
| A22 | P2 | Charts | Negative charts clip; leaf bridges omit drivers; reconciliation unchecked |
| A23 | P2 | Product gap | No operational browser report or complete board-pack delivery |
| A24 | P2 | Assurance | Tests and documentation overstate several guarantees |

## Financial data and accounting findings

### A01 — Numeric contract and rounding

**Source:** `agent4/decomposition.py:42`, `agent4/state.py:65`,
`agent4/reforecast.py:90`. **Probe:** `decimal_rounding`, `bool_money`,
`fractional_cents_forecast`, `state_integrity`.

`_c` uses `int(round(x * 100))`. Input `1.015` becomes **101 cents**, while decimal
half-even conversion of the decimal value 1.015 yields **102**. The precision is
already lost before the integer bridge begins. `True` and `False` are accepted as
€1 and €0. State writers silently truncate fractional cents (`300.9` becomes
`300`); reforecast accepts fractional target and YTD cents.

This does not invalidate the 2,000 bounded arithmetic controls. It establishes
that an enforceable ingestion policy is missing. Define accepted decimal strings
or Decimal values, explicit rounding precision, finite/non-boolean checks, range
limits and integer-cent persistence. Reject invalid values with field context.
Do not simply replace all values with floats or truncate them.

**Acceptance:** half-cent positive/negative cases, large values, boolean/nonfinite
rejection, fractional-cent rejection, exact stored/reloaded values and a documented
per-unit versus extended-amount rounding policy.

### A02 — Conflicting representations and financial semantics

**Source:** `decomposition.py:58,95`. **Probe:** `conflicting_amount_and_units`.

When either side contains `amount`, it takes priority over price/rate × volume.
A budget containing amount 100 and price 100 × volume 100 is accepted as 100;
an actual amount 110 with price 1 × volume 100 becomes 110. No inconsistency notice
is raised. The resulting €10 spending variance says nothing about the contradictory
unit data. Fixed-cost nodes also accept factor data through `_amount_of`.

There is no period, currency, scale, entity, quantity-unit or source-version
validation at this boundary. All displays assume euros. This is an unsupported
input-domain gap, not evidence that currencies were mixed in the fixture.

**Fix:** explicit amount-only/factor/product schemas; reject conflicts or record an
approved authoritative representation and reconciliation adjustment. Declare the
single-currency domain, quantity units, closed period and source provenance.

### A03 — Valid rate basket fails through public rollup

**Source:** `hierarchy.py:169`. **Probe:** `rate_basket_rollup`.

`decompose_multiproduct(..., 'variable_cost', products)` supports `rate`, as its
existing test confirms. But `rollup` first estimates the materiality base using
`p['budget']['price']` for every product. A valid rate basket raises
`KeyError: 'price'`. Supplying an explicit base avoids that path but does not fix
the default public behavior.

**Fix/acceptance:** one common type-aware amount resolver used by decomposition
and base determination; exercise variable-cost baskets through `rollup` and output,
not just the leaf helper.

### A04 — Attribution limitations are not surfaced consistently

**Source:** `decomposition.py:178,194`; `README.md` Agent 4 section.
**Probes:** `empty_products`, `zero_budget_mix`, `zero_net_joint`.

An empty basket returns a reconciled zero result. A basket with zero total budget
volume has no defined budget mix; the code sets mix shares to zero and attributes
all €1,000 of a new product's activity to mix, with zero pure volume effect. This
is mechanically balanced but an unsupported economic attribution.

When price doubles and volume halves, net variance is zero and the €50 absorbed
joint term is not surfaced because the condition requires nonzero total variance.
Multiproduct output does not expose a comparable joint-term note. The README calls
variable-cost analysis “rate × efficiency”, but the implementation has only rate
and volume; it lacks standard input allowed for actual output, needed to isolate
efficiency from activity.

**Fix:** reject empty input, label undefined budget mix/new-business activity, use
a stable gross/base materiality denominator for joint effects, and call the cost
split rate/volume unless genuine efficiency inputs are implemented.

### A05 — Tree shape, identity and root semantics

**Source:** `hierarchy.py:55,142,148`; `commentary.py:53,130`.
**Probes:** `leaf_and_children`, `duplicate_paths`, `leaf_cost_root_favourability`.

A node with both `leaf` and `children` silently takes the leaf and ignores its
children. Repeated names produce identical registry paths; the later node
replaces the earlier registry entry. Persistence and forecast maps are keyed only
by name, so separate departments with the same line name cannot be distinguished.
A standalone cost leaf rising from 100 to 110 is classified favourable because
rollup assumes the root's positive sign means profit.

The intended profit-root convention explains the last behavior, but it is not
validated. Callers can accidentally treat a cost subtotal as profit.

**Fix:** stable node IDs, unique paths, exclusive node forms, cycle/depth checks,
consistent leaf/node names, and explicit root measure/sign semantics. Test repeated
names across departments and reject ambiguous shapes rather than dropping data.

### A06 — Internal arithmetic is not independent reconciliation

**Source:** `hierarchy.py:62,100`; `output.py:127`; `commentary.py:43`.
**Probes:** `claimed_control_total_ignored`, `tampered_board_pack`.

The rollup compares two quantities derived from the same children. That is a useful
internal identity check, but cannot detect a missing account or wrong source total.
A declared parent control total is ignored (it is not part of the current schema).
Residuals are computed as total minus explained, so their existence always restores
the leaf identity; there is no maximum acceptable unexplained amount.

More directly, changing a valid rolled tree's `actual_cents` by **10,000,000** while
leaving its old variance/reconciliation flag intact still lets `board_pack` return
`reconciles=True` and a passed commentary gate. It publishes budget €143,000,
actual €225,160 and variance -€17,840, an inconsistent headline.

**Fix:** revalidate immutable computed results at publication; compare against
independent signed control totals and source completeness; distinguish rounding
residual from unexplained variance with explicit tolerance/hold rules.

## Statistical and forecast findings

### A07 — Materiality base and zero variance

**Source:** `materiality.py:55`; `hierarchy.py:148,169`.
**Probe:** `zero_materiality`.

Zero variance with zero total base is material because both the floor and variance
are zero and the comparison is `>=`. Tiny bases suffer the same issue after
integer truncation. A zero line budget is represented as relative percentage 0%,
although the ratio is undefined.

The default base is the largest top-level child budget magnitude, not guaranteed
revenue. `_first_budget` adds descendants without respecting subtract signs, so a
net subtotal's inferred base can differ from the actual subtotal. A leaf root gets
a base of one cent. Thresholds are printed, but the selected base itself is not
returned in materiality metadata.

**Fix:** require or explicitly select an eligible base, expose its identity/value,
classify zero variance as nonmaterial, preserve undefined relative percentage, and
specify rounding/minimum floor policy.

### A08 — Lost diagnostic meaning

**Source:** `materiality.py:112`; `persistence.py:58`.
**Probes:** `invalid_history_reason`, extended `lost_zero_dispersion_context`.

The shared statistics boundary correctly detects invalid data, but wrappers discard
its error/reason. A NaN history becomes “significance not computable ()”. A break
from perfectly flat history returns `significant=True` and
`inference_status='zero_dispersion_break'` in the shared tool; Agent 4 drops that
status and may describe it as ordinary statistical significance.

**Fix:** retain structured validity, reason, basis, sample count, method and
inference status. Distinguish an arithmetic break from a stochastic significance
claim. This is a wrapper issue; do not undo the shared tool's fail-closed behavior.

### A09 — Current-period history contract mismatch

**Source:** `hierarchy.py:124`; `persistence.py:77`;
`tests/test_agent4_commentary.py:12`. **Extended probe:** `history_semantics`.

Materiality takes prior history and appends the current variance. Persistence takes
a list whose final value is already current. The existing fixture helper passes
`n['history']` directly to persistence, omitting the current computed variance.
For Product Premium the history ends at **195,000 cents**, while the current
variance is **4,080,000 cents**. The helper classifies the former as STRUCTURAL;
including the actual current variance changes the result to ONE_OFF.

Neither function alone violates its documented signature. Their composition is
incorrect and there is no orchestrator enforcing compatible inputs. There are also
no dated observations to enforce order, unique periods, gaps or prevention of
current-period leakage into a historical baseline.

**Fix:** a shared dated history contract with an explicit current observation and
prior-only selection, assembled once by the close workflow. Add a regression for
this exact fixture mismatch and for restatement/gap behavior.

### A10 — Persistence can turn unavailable evidence into a decision

**Source:** `persistence.py:77`. **Probe:** `persistence_invalid_history`.

A list ending in NaN produces `ONE_OFF`, confidence 0.5, and advice not to carry the
shift. The shared significance result is unavailable, but recurrence logic still
runs and falls into the transient branch. More generally, a first isolated spike
is labelled one-off without future evidence of reversion; this is an explicit rule,
not established business causation. The numerical confidence is hand-set, not a
calibrated probability.

**Fix:** validate all inputs before classification, use UNKNOWN/REVIEW_REQUIRED
when evidence is invalid, label provisional rules and confidence scores, and keep
business confirmation distinct from repeat-pattern diagnostics.

### A11 — Phasing inconsistency changes closed actuals

**Source:** `reforecast.py:51,90`. **Probe:** `year_end_rewrites_actual`.

`reforecast(600, 1200, 4, 4, budget_phasing_cents=[150]*4,
variance_history_cents=[-10,10,-20,20,-30,30])` returns landing **1200**, a zero-width
band and **100% hit probability**, although the closed-year actual is **600**.
The phased sum is 600 while full-year budget is 1200. No consistency check exists,
and the phasing projection runs before the deterministic year-end branch.

Wrong-length phasing silently falls back to run-rate and says no phased budget is
available. Unknown persistence values are accepted. These are invalid-input
handling failures, not merely different forecasting preferences.

**Fix:** require integer valid periods/cents, consistent phasing totals and shapes,
recognized enums and finite arrays. At year-end, landing must equal actual YTD
regardless of forecasting method. Invalid phasing should hold or fail explicitly.

### A12 — No-observation and year-end probability states

**Source:** `reforecast.py:173` onward.
**Probes:** `year_end_no_history`, `no_elapsed_probability`.

With no variance history, year-end probability remains unavailable because the
minimum-history return precedes deterministic handling. Whether a closed year's
actual met the target is known without historical dispersion.

Conversely, with zero elapsed periods and supplied variance history, method `none`
can produce a band around zero and 0% hit probability. There is no current-year
forecast basis, yet a probability is published.

**Fix:** order state decisions before model selection: no elapsed observations
means no YTD-conditioned forecast unless an explicit prior/budget-only mode is
chosen; no remaining horizon means deterministic actual-versus-target comparison.

### A13 — Forecast eligibility and uncertainty are weakly constrained

**Source:** `reforecast.py:51,173`. **Probe:** `unaligned_actual_history`.

Eight arbitrary per-period values automatically select the trend method. No dates,
frequency or relationship to YTD are checked. YTD 100 after one elapsed period,
with eight historical actuals all 10,000, projects **110,100 cents** over 12 periods.
The API could intentionally accept prior-year history, but there is no metadata to
establish that interpretation or reconcile it with the current close.

The band uses population standard deviation of historical variances times
sqrt(remaining), a normal CDF and a 1.5 multiplier for AMBIGUOUS. It does not include
trend-estimation uncertainty or serial correlation, and does not validate residual
stationarity or backtest coverage. The square-root rule is reasonable only under
its stated independence assumptions; it is not a demonstrated 80% coverage claim
for these data or all three methods. Rounded probabilities can display 0%/100%
under a nonzero uncertainty distribution.

**Fix:** dated aligned method eligibility, explicit model assumptions and diagnostic
holds, a distinction between illustrative model probability and calibrated
probability, and holdout/backtest coverage before stronger claims. Do not invent
cross-line covariance or claim portfolio Monte Carlo is implemented.

## Grounding and publication findings

### A14 — Claim references can fabricate their own authority

**Source:** `commentary.py:191`. **Probe:** `forged_reference_passes`.

A claim “Sales were €999,999.00” with refs `{'actual': 99999900}` passes, although
that figure does not occur in the computed registry. The gate builds an allowed
set from the claim's refs without proving those refs point to authoritative values.
With no numeric refs it falls back to any signed value in the global registry,
reintroducing context-blind acceptance. Unsigned amounts accept either sign, while
words such as favourable/adverse are not independently validated.

The existing test catches a text-only mutation whose refs stay unchanged. It does
not catch tampering with both text and refs or an incorrect classification/name.
The current deterministic composer reduces exposure, but the gate is not safe as
an advertised boundary for future LLM rewrites or imported claims.

**Fix:** typed references containing immutable node ID, field path, period and
source/result version; resolve values from the trusted registry; render numbers
and polarity from those values. Reject unknown references and missing required
references, with no global fallback. Tests must alter both text and refs.

### A15 — Claim taxonomy and qualitative controls are incomplete

**Source:** `commentary.py:33,179,191`.
**Probes:** `empty_percent_refs_pass`, `unverified_classification_passes`,
`unlabelled_causal_hypothesis_passes`, `unknown_tier_passes`,
`other_numeric_formats_pass`.

A 99% target-hit claim with empty refs passes: percentage validation runs only if
there is a nonempty allowed set. Arbitrary quadrant/confidence text passes without
checking stored classifications. “The new supplier caused the loss” passes as a
hypothesis without “requires confirmation”. Unknown tiers pass. Numbers written as
USD, EUR words, bare counts, basis points or millions are not covered by the euro
and percentage regexes.

**Fix:** whitelist tiers; require structured evidence for observations; generate
mandatory causal qualification; validate every supported numeric type or prohibit
free numeric prose. Negative and wrong-context claims must be tested. Regex alone
cannot establish that a business cause follows from arithmetic.

### A16 — Published forecast loses key evidence

**Source:** `commentary.py:110,148`; `output.py:119,127`.
**Extended probes:** `root_forecast_claim_count`, `child_forecast_claims`.

The root is excluded from the per-node observation branch, so a forecast supplied
for Operating Profit produces **zero forecast claims**. For a child, commentary
includes landing and rounded P(hit) but no band, target, target direction,
horizon, history sufficiency reason or persistence adjustment. The board-pack
result does not separately retain the full reforecast object or registry. Thus
the README's “probability plus range” publication claim is not met.

The flattened hierarchy keeps only name, depth, variance, favourability and
quadrant; no budget/actual/period fields. `compose` omits a nonzero rounding
residual from driver text, so the narrated driver amounts can fail to sum even
while the structured bridge reconciles.

**Fix:** first-class root forecast and full structured forecast section; include
range, assumptions and unavailable states alongside any probability; persist the
trusted registry and full hierarchy; make residuals visible in the narrative.

## State and execution findings

### A17 — Failed writes leave partial versions

**Source:** `state.py:65,87,102`. **Probe:** `state_integrity`.

A two-row budget insert, first row valid and second outside BIGINT range, raises
`ConversionException` **after the first row is already present**. A retry with the
same label then encounters the immutable-budget duplicate check. There is no
transaction around the batch or complete payload validation before insertion.
Actuals and forecasts use the same unguarded insertion pattern.

**Fix:** validate whole payload, atomically create a version header and rows in one
transaction, roll back every failed row, and define idempotent replay by content
digest. Test failures at each write phase and verify no partial version survives.

### A18 — Versions do not enforce their claimed identity

**Source:** `state.py:40,87,102`. **Probe:** `state_integrity`.

Actuals version `v1` accepts two rows for the same line/period with different
amounts. An explicit reforecast version `rf` can be appended twice. Budget rows
within the initial insert have no unique line/period constraint either. The tables
have no primary/unique keys. Monetary inputs are coerced with `int`; probability
2.0 is accepted; missing probability is stored as NaN rather than an explicit
unavailable state. Version labels, dates and line identifiers are not validated. Public `versions(table)`
also interpolates its table argument into SQL; whitelist the three supported table
names. No remote SQL exposure or exploitation is claimed in this audit.

**Fix:** immutable unique version identity, unique `(version,line_id,period)` rows,
validated cents, nullable probability constrained to [0,1], explicit status/reason,
and a conflict policy for replay versus correction. Native DuckDB locking does not
supply those application-level guarantees.

### A19 — Latest actuals are not a defined effective snapshot

**Source:** `state.py:93,136`. **Probe:** `state_integrity`.

After A/Q1 is stored in v1 and B/Q2 in v2, `get_actuals()` returns only B/Q2.
This is not necessarily incorrect if each version is required to be a complete
snapshot—but no such requirement is documented or enforced, and “append actuals”
plus “restatement” suggests an accumulating panel. A partial restatement can
therefore be mistaken for complete effective actuals.

**Fix:** choose immutable full snapshots or explicit deltas with deterministic
as-of resolution. Expose completeness, supersession and budget basis. Test a
single-line restatement while retaining unaffected lines and earlier periods.
Do not silently sum all versions together.

### A20 — Version trail lacks source lineage and full evidence

**Source:** `state.py:102,118`; `output.py:127`.

Forecast storage retains only line, close period, landing and probability.
`reforecast_walk` omits the version ID itself. It cannot identify the budget and
actuals versions used, the method, uncertainty band, assumptions, classifications,
source digests or code/schema version. There is no persisted Agent 4 `model.json`
writer despite comments describing the registry as that artifact. Timestamps alone
cannot reconstruct a historical report.

**Fix:** immutable run manifest and result bundle referencing exact source versions;
include version ID in the walk and persist full result/status metadata. An original
report should be reproducible after restatements and re-budgets.

### A21 — Missing operational close lifecycle

**Source:** repository call-site search; `state.py:18`; README demo.

This is an **implementation gap**, not a failing existing CLI. No connected entry
point consumes closed actuals, selects the approved budget version, builds dated
histories, computes persistence/forecast, writes state, gates commentary and
exports a report. There is no saved-close replay/freshness gate, execution ledger,
failed-publication recovery, or connection between `VarianceStore` and board-pack
creation. Independent library calls can be assembled incorrectly, as A09 shows.

**Fix:** a bounded offline close command first, with run IDs, explicit inputs,
atomic state/result publication, meaningful exit states and idempotent retry.
Implementing an LLM is optional; a deterministic integrated workflow is already
useful. Scheduling, ERP connectors and interactive approvals can follow later.

## Output, browser and assurance findings

### A22 — Waterfall does not enforce its advertised guarantees

**Source:** `output.py:34,44`. **Probes:** `negative_waterfall`, `leaf_waterfall`.

For budget -100 cents and actual -200 cents, the chart's upper bound is -100
instead of including zero. Its zero line and anchor rectangles start at **y=-240**
inside a `0 0 720 360` viewBox. Browser inspection confirmed clipping and the title
being covered by the anchor bar. This affects ordinary loss-making P&Ls.

For a standalone revenue leaf, budget €100 and actual €150 render as two anchors
with **no €50 driver step**. The renderer only reads children, not leaf drivers.
It never asserts that step impacts reach actual; changed or malformed public inputs
can produce an untied bridge. A root residual can also be double-counted if it is
already part of a child impact under an undefined input contract.

**Fix:** include zero and all cumulative endpoints in bounds, enforce budget plus
steps equals actual, support leaf drivers explicitly, define residual ownership,
and validate dimensions. Test losses, sign crossings, zero movement, leaf trees,
large offsets and residual cases in both SVG geometry and visual acceptance.

### A23 — Browser/report delivery remains a feature gap

**Source:** `output.py:127,145`; `keystone-showcase/index.html:535`.

The operational board pack is a dictionary plus SVG. There is no report with
company/period/currency/source versions, evidence drilldown, forecast history,
publication status or errors. The showcase's Agent 4 button is disabled (“planned”)
and correctly does not pretend to be a working interface.

The audit wrapper is **not** a new product UI. A requested narrow viewport of 390
measured 300 CSS pixels in this session; the SVG scaled to about 210 pixels within
the wrapper. Containment is not readability: 9–11-unit text shrinks with the whole
chart. Long labels, many accounts, keyboard interaction and accessible chart
summaries need dedicated implementation and testing. The SVG has no accessible
`title`/`desc` or tabular alternative in the output function.

**Fix:** portable saved-run HTML with a financial summary, annotated waterfall,
readable table, exception coverage, root forecast with caveats, and evidence links.
Provide an accessible numeric alternative and clear synthetic disclosure.

### A24 — Existing assurance is too narrow for completion claims

**Source:** all direct Agent 4 tests, README Agent 4 section.

The 33 passing checks are useful but mostly demonstrate selected happy paths and
previously fixed examples. There are no dedicated state-store tests among the
three Agent 4 test files. Reconciliation tests largely compare outputs that share
the same arithmetic. The cost-basket test does not call rollup; grounding tests
mutate prose without forging refs; forecast tests miss year-end phasing and
zero-elapsed states. The persistence helper uses prior-only history.

README phrases including “the commentary cannot fabricate a number”, “every
figure”, “always tying”, “rate × efficiency” and “probability plus a range” exceed
what this review verified. This audit preserves that documentation as reviewed;
fix batches should update claims along with behavior, not merely hide failures.

## Confirmed strengths to preserve

- Deterministic accounting is separated from commentary; no LLM performs arithmetic.
- Standard revenue/cost signs and the supplied profit fixture work as intended.
- Sequential convention is named; symmetric single-product mode exists;
  unsupported multiproduct symmetric mode is explicitly rejected.
- Missing amount and invalid line type/sign examples fail rather than become zero.
- The ordinary fixture bridge is €143,000 budget + €15,050 revenue − €17,290 COGS
  − €15,600 Opex = **€125,160 actual**, variance **−€17,840**.
- Shared anomaly logic handles a flat-baseline break, and unknown significance is
  not universally coerced to false; preserve and extend that distinction.
- A known ONE_OFF changes the reforecast; AMBIGUOUS widens its model band;
  zero historical dispersion with horizon remaining does not imply certainty.
- Deterministic commentary normally uses source values, and SVG labels are escaped.
- Original stored rows are not deleted by the append methods; strengthen version
  integrity without discarding history.

## Proposed implementation batches and exit criteria

### Batch 1 — financial contracts and deterministic correctness

Address A01–A07 and A11–A12, plus the inputs needed for A09. Define money, unit,
period, node identity, phasing and root-sign contracts. Fix rate-basket rollup,
zero-budget attribution, materiality edge cases and year-end forecasts. Distinguish
internal arithmetic balance from source reconciliation. Add regression tests for
every reproduced financial case and independent expected-value/property checks.

**Exit:** valid supported inputs produce independently correct values; invalid or
ambiguous inputs are rejected/held; a closed-year forecast always equals actual;
missing data is never silently interpreted as zero or an accepted alternative.

### Batch 2 — history, statistical interpretation and claim controls

Address A08–A10, A13–A16. Assemble current/prior dated history consistently, retain
shared-tool diagnostics, qualify heuristic persistence and probabilities, bind
claims to immutable typed registry paths, enforce taxonomy and causal qualifiers,
and publish root/child forecasts with ranges and unavailable states.

**Exit:** forging both a claim and its refs fails; wrong entity/period/sign/target
fails; unavailable inputs cannot create a confident one-off/forecast; current-close
classification is reproducible; publication includes essential uncertainty.

### Batch 3 — versioned state and reliable close execution

Address A17–A21. Add unique version/data identities, transaction rollback,
idempotency, explicit restatement semantics, source lineage and a deterministic
close orchestrator. Freeze inputs/results/registry into an immutable run bundle;
separate committed accounting from failed report delivery.

**Exit:** duplicate close replays without duplication; conflicting restatements
require a new version; every interrupted write rolls back or has a defined recovery
state; historical reports can be regenerated from their saved evidence.

### Batch 4 — operational reports and browser acceptance

Address A22–A24 and remaining A16 publication work. Build the real report, fix
waterfall geometry/ties, expose sources/versions, and align README/showcase claims.
Exercise desktop and narrow views, losses, many/long account names, empty/held/error
states, uncertainty and decision-history navigation.

**Exit:** every chart has an accurate table equivalent; report headline agrees with
saved results and controls; selected original and effective versions are distinct;
no unsupported live/verified/causal claims appear.

### Bounded closure validation after the four batches

Use a controlled synthetic close sequence with an independently reconciled answer
key: initial budget, several closes, a one-off, persistent shift, missing input,
late close, restatement, formal re-budget, year-end and publication failure/retry.
Add a sanitized internal-company dataset only if one is available and authorized;
public issuer filings do not supply a company's confidential phased budget and
cannot substitute for a genuine budget-versus-actual acceptance dataset.

Require end-to-end source/version reproducibility, numeric and narrative checks,
probability assumption disclosure, local/shared-tool parity where supported, and
browser acceptance. ERP integration, scheduling, authentication and cross-line
correlated forecasts are separate optional scope. Agent 4 can be complete within
a clearly stated offline deterministic domain without pretending those exist.

## Audit artifacts and status

Tracked: this report and the two reproducible probe scripts in `docs/audits/`.
Ignored local evidence: `probes.json`, `extended.json`, `mcp-parity.json`,
`visual.html`, `desktop.png`, `narrow.png` under `output/agent4-audit/`.
The saved probe JSON intentionally contains NaN where it demonstrates the storage
problem; it is diagnostic evidence, not a standards-compliant production export.

No production fixes, push or merge are included in this audit. The next recommended
action is **Batch 1**, with financial contracts and closed-year forecast correctness
first; UI expansion should follow those controls.
