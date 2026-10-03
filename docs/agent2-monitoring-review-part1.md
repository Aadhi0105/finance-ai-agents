# Agent 2 browser review, Part 1 — monitoring reports and clarity

Reviewed 2026-10-03 against main commit `66ead9724b735474f986db8c101de6e92cd09ccd`.
Scope: routine monitoring, new/resolved breaches, held/unavailable observations,
and clarity of company, period, thresholds, evidence and status. This is a review,
not an implementation batch. Correction approvals/recovery (Part 2) and responsive
layout/usability/disclosure audit (Part 3) were not performed.

## Outcome

The underlying saved reports distinguish the sampled monitoring outcomes correctly.
The browser-delivery requirement is **not passed**: Agent 2 has no existing HTML
export or browser view connected to saved monitoring results. Its showcase has only
two illustrative scenarios. It does not represent saved resolved, held or error
states. A generated review-only wrapper made actual text outputs inspectable in the
browser; that wrapper is not a new product capability.

No production code, thresholds, monitoring state, approval decisions or alert rules
were changed. The review used isolated databases and previously saved Stadler
outputs; it made no provider or paid model calls.

## Evidence examined

- Existing showcase: selected both Agent 2 scenarios in the in-app browser.
  Keyboard activation selected the Agent 2 tab after automation clicks did not
  switch it. This is an observation, not a diagnosed product click defect.
- Twelve new deterministic fixture cycles, saved separately for this review.
- A separate Beta-only fixture run to obtain genuinely quiet valid monitoring.
- A controlled `provider_timeout` response through the actual live-observation
  cycle path, producing `review_required` with no assessed rows.
- Existing live Stadler baseline and duplicate-refresh reports from
  `output/agent2-live-validation/cycle-1.json` and `cycle-2.json`. These were
  previously retrieved results, not newly refreshed company observations.
- Browser inspection of unchanged report text in a clearly labelled review wrapper.

| State | Evidence | Observation |
|---|---|---|
| Baseline | Fixture cycle 1; saved Stadler cycle 1 | Baseline suppression is explicit; existing breached state is shown |
| Quiet valid monitoring | Beta-only cycle 2 | Says no newly surfaced exceptions and warns prior breaches may remain active |
| New breach | Fixture cycle 7, Delta leverage | 4.6 vs 4.5, NEW_BREACH; matches saved row |
| Resolved breach | Fixture cycle 5, Gamma liquidity | 1.22 vs 1.2, RESOLVED; matches saved row |
| Multiple exceptions | Fixture cycle 9 | Acme coverage breach is separate from leverage early warning |
| No fresh observations | Fixture cycle 11; saved Stadler cycle 2 | Explicitly says compliance was not reassessed and prior state remains |
| Provider unavailable | Injected timeout, isolated live-mode database | Saved status is review_required; reasons preserved; no compliance claim |

Scenario assertions checked the expected breach/resolution labels against saved
rows, a quiet nonbreached observation, and the no-reassessment wording. No full
regression suite was needed or rerun for this documentation-only review.

## Findings and recommended changes

### 1. Missing browser delivery for actual monitoring runs — material gap

`monitor.py` emits text; the showcase embeds illustrative values. There is no
Agent 2 equivalent of Agent 3's saved-run HTML export. A reader cannot inspect a
real saved monitoring cycle, held state or source evidence from the existing panel.

Recommended: a read-only export based on saved cycle evidence, with run status,
source mode, assessed/skipped coverage, exceptions and retained evidence. This is
new implementation work, not something this review pretends already exists.

### 2. Review-required status is not prominent in the report text — material clarity gap

The controlled outage persisted `status=review_required`, but its report displays
coverage reasons such as `provider_timeout` followed by the generic no-new-data
message. The status added above the report in the review wrapper came from saved
JSON; the existing renderer itself does not print it. A reader relying only on the
report has to infer the difference between an unchanged refresh and a review hold.

Recommended: render an explicit overall status and coverage summary; distinguish
successful unchanged refresh, unavailable data and review-required observations.
Continue to state that compliance was not reassessed. Preserve detailed reasons.

Source: `scheduler/cycle.py`, report construction around lines 185–198 and
`_build_report` around lines 250–264.

### 3. Demo warning timing contradicts itself — confirmed content defect

The leverage illustration displays first drift at cycle **7** in the chart caption,
while its narrative and colour strip start at cycle **6**. It then calls this
three cycles before the cycle **10** breach. Seven to ten is three cycles; six to
ten is four. The embedded `flaggedCycle=6` is displayed as a one-based cycle 7,
while the hand-written narrative and class strip use different conventions.

Recommended: use one event index for caption, strip, narrative and lead time.
This finding concerns internal consistency of illustrative content; it does not
establish any real lead-time or statistical result.

Source: `keystone-showcase/index.html`, embedded Agent 2 data around lines 274–280
and `renderAgent2` around lines 454–485.

### 4. Threshold direction and margin need plain-language meaning

Exception text such as `4.6 vs 4.5 (below), margin +0.100` does not say that “below”
is the required limit, rather than the observed relationship. Baseline rows omit
direction entirely. Positive margins represent breaches, while a resolved Gamma
row has a negative margin, which is not explained in the output.

Recommended: label maximum/minimum or the exact supported inequality explicitly,
explain margin sign, and use consistent ratio units. Preserve full precision in
saved evidence; do not change threshold comparison semantics when formatting.

### 5. Period, provenance and numeric presentation are hard to scan

The saved Stadler baseline labels its header `data 2026-09-29` but appends the
actual statement period `2025-12-31` below the rows. The existing explanatory text
is correct, yet the two dates need clearer names. Ratios render as values such as
`0.9567418366614171`, and technical metric identifiers are used directly.

Source evidence and issuer-reconciliation information exist in the saved cycle,
but are not exposed by the short report as a navigable evidence view. Quiet rows
are deliberately suppressed, so the exception report alone is not a full current
watchlist view.

Recommended: separately label run/assessment date and observation period, show
readable metric names and ratio precision, and provide evidence/current-state
access without suggesting a quiet exception report proves compliance.

## What already reads correctly

Company names, metric identifiers, observed values and thresholds appear in the
sampled baseline and exception rows. New and resolved breach labels agree with
saved deterministic results. Missing probability estimates remain unavailable,
not zero. Baseline suppression and no-reassessment warnings are explicit. The
saved live reports correctly identify thresholds as analyst policies rather than
contractual covenants. Those controls should be retained in any presentation work.

## Local review artifacts

Ignored folder: `output/agent2-part1-review/`.

- `cycles.json`: twelve actual fixture cycle results.
- `quiet.json`: isolated Beta-only quiet cycle.
- `outage.json`: controlled provider-unavailable cycle.
- `reports.html`: review-only browser wrapper around unmodified saved report text.
- `review.duckdb`, `quiet.duckdb`, `outage.duckdb`: isolated review state.

The wrapper was inspected through a localhost server serving only that file and
the existing showcase. No responsive width changes or browser compatibility claims
were made. No correction approvals, rejected corrections, restatements, triage
recovery or notification/scheduling flows were exercised.

Part 1 is complete as a **review with findings**, not a clean bill of health or a
claim that the missing browser features have been implemented. Parts 2 and 3 remain
unstarted.
