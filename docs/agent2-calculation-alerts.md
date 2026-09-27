# Agent 2 batch 1 — calculation and alert correctness

This batch fixes the calculation/alert boundary from the initial Agent 2 audit.
It does not complete state recovery or model-publication controls.

## Contracts

Threshold values and observations must be finite numeric scalars, never booleans.
Invalid inputs return an unavailable/error result, not a compliant covenant.
The cycle validates watchlist identities, duplicate IDs, direction, threshold,
observation values and future dates before its write transaction. Any invalid
item aborts that cycle's calculations without partially persisting earlier items.
Missing observations retain the existing skip behavior; run-ledger/no-data semantics
are deferred to batch 2. Threshold margins retain full precision for classification.

Shared anomaly, drift and probability functions validate sequences, minimum
observations, matching strictly increasing time axes and parameter ranges. Output
must serialize as strict JSON. Arithmetic overflow is unavailable, not Infinity.
MCP schemas reject boolean/string coercion; transport-level rejections return an
explicit unavailable result. This uses the installed MCP 2.x `is_error` field.

## Time and probability semantics

Drift in the monitoring cycle uses actual elapsed observation days, not row numbers.
The saved history reader now includes observation dates. Drift slope is per day;
its projected boundary time is displayed in days. The shared function retains its
legacy `cycles_to_breach_at_current_drift` key for compatibility: its numerical unit
is the supplied time axis, declared in `time_unit`.

Probability requires equally spaced observations. The cycle declines probability
on irregular spacing, retains threshold/anomaly/dated-drift analysis and displays
unavailability. On regular spacing the result declares observation interval and
calendar-day horizon. The default six-step horizon means six observation intervals,
not six scheduler invocations. Date corrections in the synthetic fixture replace
future April/July observations with Jan 4/7 updates; it now demonstrates intermittent
updates, not a quarterly series pretending to occur within ten January days.

The probability model is a **continuous Brownian crossing approximation** estimated
from increments, not a calibrated empirical probability or an exact discrete walk.
Stable erfc/erfcx evaluation avoids multiplying an overflowing exponential by an
underflowed normal tail. An independent reflection-identity and direct erfc benchmark
cover the formula.

Covenants breach strictly above a maximum or below a minimum. Constant observations
exactly on a boundary, with zero estimated drift and volatility, therefore have
zero crossing probability. Deterministic movement that only touches the boundary
at the horizon is also not a breach. Nonzero Brownian volatility starting on the
boundary crosses immediately under that model. Already-breached observations have
probability one regardless of subsequent drift.

Perfect linear drift returns `slope_tstat=null` and
`inference_status=zero_residual_trend`, preserving the deterministic trend signal
without pretending an infinite statistic is a finite inference result.

## Alerts and deterministic triage

High crossing probability surfaces regardless of drift direction. Drift itself
surfaces only when heading toward the covenant boundary. These are separate signals;
a volatile series can cross a boundary despite a drift away from it.

A surfaced active threshold breach always receives an escalation-for-review
recommendation from `recheck_flag`, without requiring a second diagnostic. An isolated
anomalous observation adds verification of magnitude; it does not cancel the breach.
The triage prompt now distinguishes diagnostics of one series from independent
sources. Free model prose is **not yet mechanically constrained** by these changes;
that remains batch 3. Baseline and known-stable suppression policies are unchanged.

## Validation and remaining batches

Regression tests in `tests/test_agent2_batch1.py` cover invalid numbers/parameters,
strict deterministic boundaries, a probability identity/tail benchmark, perfect-fit
JSON, probability alerts against drift, breach priority, future/duplicate/invalid
watchlists, all-or-nothing pre-write validation, irregular and regular dates, and
real MCP rejection/parity cases. Ten synthetic cycles are compared in full across
local/MCP modes, including deterministic triage output, using temporary databases.
No API keys, external monitoring data or paid model calls are needed.

Batch 2 remains responsible for empty/stale cycle progression, corrections,
run-ledger durability, concurrency/recovery and fuller persisted diagnostics.
Batch 3 covers live-mode honesty, durable model audit and grounded publication.
Batch 4 covers final CLI, fault-injection and acceptance documentation.

Verification on 28 September 2026: **436 tests passed** on Python 3.11.9
(including 34 new cases). Ten-cycle local/MCP results and deterministic triage
were identical and strict-JSON serializable. Local evidence is retained under
`output/agent2-batch1/`. No existing monitoring database was modified.
