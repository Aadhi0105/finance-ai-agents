"""
Reforecast / projection engine (Agent 4) — the forward-looking half.

Decomposition explains what already happened; reforecast projects where the year
lands, and reframes a point into a decision: the headline is P(hit annual target |
YTD), with a landing range that widens as the horizon lengthens — never a bare
point estimate.

Honest scope: this is a DEFENSIBLE reforecast, not a production forecasting engine
(the FP&A analogue of "the DCF is a scaffold, not what an equity desk ships"). It
does three honest things well:

  1. METHOD LADDER, names which rung it used:
     - run-rate         : annualize YTD (flat phasing). Simplest; the fallback.
     - phasing-aware    : project YTD performance against the budget's OWN seasonal
                          shape (default) — if the budget front-loads Q4, a slow H1
                          is not linearly extrapolated into a miss.
     - time-series      : a trend fit on a per-period actual history (earned only by
                          sufficient history).

  2. UNCERTAINTY BAND FROM THE LINE'S OWN HISTORICAL DISPERSION, not a made-up
     +/-10%. sigma per period = stdev of the line's past variances; the landing's
     sigma = sigma_period * sqrt(remaining periods), so the band WIDENS WITH
     HORIZON (independent-period variance accumulates) and narrows to zero at
     year-end. Too little history -> point estimate only, band "not computable".

  3. DIRECTION-AWARE P(HIT TARGET): revenue hits by landing at/above target; a cost
     hits by landing at/under budget. A probability plus a range, always.

Single-line only in this checkpoint; portfolio-level correlated Monte Carlo is a
documented later step (it needs a cross-line correlation structure fixtures don't
yet carry, and faking it would be the exact overclaiming this platform avoids).

All money in integer cents.
"""

from __future__ import annotations

import math
import statistics

_MIN_OBS = 6            # dispersion needs at least this many past variance points
_Z80 = 1.2816          # 80% two-sided band
_TS_MIN = 8            # time-series rung needs at least this many per-period actuals


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _project(ytd_cents: int, full_year_budget_cents: int, elapsed_periods: int,
             total_periods: int, budget_phasing_cents, actual_history_cents):
    """Choose a method and produce the point landing estimate. Returns
    (method_name, landing_cents, note)."""
    remaining = total_periods - elapsed_periods

    # time-series rung: earned only by a sufficiently long per-period actual history
    if actual_history_cents and len(actual_history_cents) >= _TS_MIN and remaining > 0:
        n = len(actual_history_cents)
        xs = list(range(n))
        xbar = sum(xs) / n
        ybar = sum(actual_history_cents) / n
        sxx = sum((x - xbar) ** 2 for x in xs)
        sxy = sum((xs[i] - xbar) * (actual_history_cents[i] - ybar) for i in range(n))
        slope = sxy / sxx if sxx else 0.0
        intercept = ybar - slope * xbar
        projected_remaining = sum(int(round(intercept + slope * (n + k)))
                                  for k in range(remaining))
        landing = ytd_cents + projected_remaining
        return ("time-series (trend on per-period actuals)", landing,
                f"linear trend over {n} periods projected {remaining} periods forward")

    # phasing-aware rung (default when a phased budget is available)
    if budget_phasing_cents and len(budget_phasing_cents) == total_periods:
        budget_to_date = sum(budget_phasing_cents[:elapsed_periods])
        if budget_to_date != 0:
            perf_ratio = ytd_cents / budget_to_date
            landing = int(round(full_year_budget_cents * perf_ratio))
            return ("phasing-aware (YTD performance vs. phased budget)", landing,
                    f"running at {perf_ratio*100:.1f}% of phased plan to date")

    # run-rate fallback (flat phasing)
    if elapsed_periods > 0:
        landing = int(round(ytd_cents * total_periods / elapsed_periods))
        return ("run-rate (annualized YTD, flat phasing)", landing,
                "no phased budget available — flat annualization")
    return ("none", ytd_cents, "no elapsed periods")


def reforecast(ytd_cents: int, full_year_budget_cents: int, elapsed_periods: int,
               total_periods: int, *, budget_phasing_cents=None,
               variance_history_cents=None, actual_history_cents=None,
               direction: str = "higher_is_better", target_cents: int | None = None,
               name: str = "line") -> dict:
    """
    Project the full-year landing and P(hit target). direction is
    'higher_is_better' (revenue) or 'lower_is_better' (cost). target defaults to
    the full-year budget.
    """
    target = target_cents if target_cents is not None else full_year_budget_cents
    remaining = total_periods - elapsed_periods
    method, landing, note = _project(ytd_cents, full_year_budget_cents,
                                     elapsed_periods, total_periods,
                                     budget_phasing_cents, actual_history_cents)

    result = {
        "name": name, "method": method, "method_note": note,
        "ytd_cents": ytd_cents, "elapsed_periods": elapsed_periods,
        "total_periods": total_periods, "remaining_periods": remaining,
        "projected_landing_cents": landing,
        "target_cents": target, "direction": direction,
        "computed_by": "reforecast (python, integer cents)",
    }

    # --- uncertainty band + P(hit) from historical dispersion ---------------
    hist = variance_history_cents or []
    if len(hist) < _MIN_OBS:
        result.update({
            "band_cents": None, "prob_hit_target": None,
            "confidence": "not computable",
            "reason": (f"insufficient history (<{_MIN_OBS} prior variance points) — "
                       f"point landing only, no band or probability"),
        })
        return result

    sigma_period = statistics.pstdev(hist) if len(hist) > 1 else 0.0
    sigma_landing = sigma_period * math.sqrt(remaining) if remaining > 0 else 0.0

    if sigma_landing == 0:
        # year complete (or zero dispersion): deterministic
        hit = (landing >= target) if direction == "higher_is_better" else (landing <= target)
        result.update({
            "band_cents": [landing, landing], "sigma_landing_cents": 0,
            "prob_hit_target": 1.0 if hit else 0.0,
            "confidence": "deterministic (no remaining horizon / zero dispersion)",
        })
        return result

    half = int(round(_Z80 * sigma_landing))
    band = [landing - half, landing + half]

    # direction-aware P(hit): standardized distance of target from the landing
    if direction == "higher_is_better":
        z = (landing - target) / sigma_landing          # P(landing >= target)
    else:
        z = (target - landing) / sigma_landing          # P(landing <= target)
    p_hit = _normal_cdf(z)

    result.update({
        "sigma_period_cents": int(round(sigma_period)),
        "sigma_landing_cents": int(round(sigma_landing)),
        "band_cents": band, "band_confidence": "80%",
        "prob_hit_target": round(p_hit, 4),
        "confidence": "computed from the line's own historical dispersion",
        "note": "band widens with horizon (sigma scales with sqrt(remaining periods))",
    })
    return result
