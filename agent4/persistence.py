"""
Persistence classification (Agent 4) — one-off vs structural.

Given a line's variance history, is this period's variance a ONE-OFF (a spike that
reverts) or STRUCTURAL (a level shift that persists)? This drives the reforecast
and the commentary: a one-off must NOT be extrapolated into the full-year landing;
a structural break should be.

Rule-based, not a fitted model (a fitted persistence model on thin close-history
would overclaim, and a controller can actually follow a rule). Three signals:

  1. RECURRENCE   — the length of the consecutive same-signed, non-trivial run of
                    variances ending at this period. A shift that has held for
                    several closes is structural.
  2. SIGN CONSISTENCY — the fraction of recent periods sharing this period's sign.
                    Consistent = structural; alternating = transient/noise.
  3. SIGNIFICANCE — is this period a break from the line's pattern? Reused from
                    anomaly_significance_check — the FOURTH independent consumer of
                    the shared significance library (covenant drift, event-study
                    CAAR, variance materiality, and now variance persistence). One
                    library, four unrelated agents — the platform thesis at full
                    strength.

The important nuance recurrence catches that significance alone misses: a variance
that has been STABLY elevated for months is NOT a "break from pattern"
(significance says no — the values are all alike) but IS structural (the level has
moved and held). So the two signals are complementary, not redundant.

Seasonality: variances are assumed computed vs the PHASED budget (as the
materiality and reforecast layers assume), so seasonal shape is already removed
from the variance itself; recurrence on those variances is legitimately
like-for-like. The significance call additionally uses the period-aware path when
same-period history is supplied.

All money in integer cents.
"""

from __future__ import annotations

import os
import statistics

if os.environ.get("AGENT_STATS_VIA_MCP") == "1":
    from mcp_server.client import anomaly_significance_check
else:
    from tools.statistical_checks import anomaly_significance_check

_MIN_OBS = 6                 # need at least this many prior points
_STRUCT_RUN = 3             # a run of >= this many consecutive same-sign is structural
_CONSISTENCY = 0.6          # recent same-sign fraction for "consistent"
_TRIVIAL_FRAC = 0.30        # a run element must be >= this * median|variance| to count


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def _significance(variances: list[int], period=None,
                  period_history: list[tuple] | None = None) -> dict:
    """Is the latest variance a break from the line's pattern? Period-aware when
    same-period history is supplied (the fourth call site of the shared library)."""
    current = variances[-1]
    series = None
    period_aware = False
    if period is not None and period_history:
        same = [v for (pk, v) in period_history if pk == period]
        if len(same) >= _MIN_OBS:
            series = same + [current]
            period_aware = True
    if series is None:
        series = variances
    res = anomaly_significance_check([float(x) for x in series], min_obs=_MIN_OBS)
    return {"significant": res.get("significant"), "modified_z": res.get("modified_z"),
            "period_aware": period_aware}


def classify_persistence(variances: list[int], period=None,
                         period_history: list[tuple] | None = None,
                         name: str = "line") -> dict:
    """
    Classify the latest variance in `variances` (most recent last) as ONE_OFF,
    STRUCTURAL, or AMBIGUOUS, with a confidence — or report insufficient history.
    """
    n = len(variances)
    if n < _MIN_OBS + 1:
        return {"name": name, "persistence": "INSUFFICIENT_HISTORY",
                "reason": f"need >{_MIN_OBS} periods, have {n}",
                "computed_by": "classify_persistence (python)"}

    current = variances[-1]
    cur_sign = _sign(current)

    # significance (the shared-library call)
    sig = _significance(variances, period=period, period_history=period_history)
    significant = sig["significant"]

    # recurrence: consecutive same-sign run ending at the latest, counting only
    # periods whose magnitude is COMPARABLE to the current one (a small blip is not
    # part of a large shift's run). Floor is relative to the current variance, with
    # a median guard so a modest-but-persistent shift still counts.
    scale = statistics.median([abs(v) for v in variances]) or 1
    floor = max(_TRIVIAL_FRAC * abs(current), _TRIVIAL_FRAC * scale)
    run = 0
    for v in reversed(variances):
        if _sign(v) == cur_sign and cur_sign != 0 and abs(v) >= floor:
            run += 1
        else:
            break

    # sign consistency over the recent window
    K = min(6, n)
    recent = variances[-K:]
    same = sum(1 for v in recent if _sign(v) == cur_sign)
    consistency = same / len(recent)

    structural = (run >= _STRUCT_RUN and consistency >= _CONSISTENCY)

    if structural:
        verdict = "STRUCTURAL"
        conf = min(0.95, 0.5 + 0.1 * run + 0.3 * (consistency - _CONSISTENCY))
        reason = (f"variance has held the same direction for {run} consecutive closes "
                  f"({consistency*100:.0f}% sign-consistent) — a persistent level shift; "
                  f"carry into the reforecast")
    elif significant and run <= 1:
        verdict = "ONE_OFF"
        conf = 0.7
        reason = ("a significant break from pattern with no recurring run — an "
                  "isolated spike; do NOT extrapolate into the landing")
    elif significant and run == 2:
        verdict = "AMBIGUOUS"
        conf = 0.4
        reason = ("a significant variance recurring for 2 closes — may be an "
                  "emerging shift or a short run; watch the next close")
    else:
        # not significant and not an established run -> transient / noise
        verdict = "ONE_OFF"
        conf = 0.5
        reason = ("neither a break from pattern nor a sustained run — transient; "
                  "not a persistent shift")

    return {
        "name": name, "persistence": verdict, "confidence": round(conf, 3),
        "reason": reason,
        "signals": {"run_length": run, "sign_consistency": round(consistency, 3),
                    "significant_break": significant,
                    "period_aware_significance": sig["period_aware"]},
        "computed_by": "classify_persistence (python; significance via shared library)",
    }
