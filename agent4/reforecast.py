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

from fractions import Fraction
from agent4.contracts import cents
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
        xbar = Fraction(sum(xs), n)
        ybar = Fraction(sum(actual_history_cents), n)
        sxx = sum((x - xbar) ** 2 for x in xs)
        sxy = sum((xs[i] - xbar) * (actual_history_cents[i] - ybar) for i in range(n))
        slope = sxy / sxx if sxx else Fraction(0)
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
            perf_ratio = Fraction(ytd_cents, budget_to_date)
            landing = int(round(full_year_budget_cents * perf_ratio))
            return ("phasing-aware (YTD performance vs. phased budget)", landing,
                    f"running at {float(perf_ratio)*100:.1f}% of phased plan to date")

    # run-rate fallback (flat phasing)
    if elapsed_periods > 0:
        landing = round(Fraction(ytd_cents * total_periods, elapsed_periods))
        return ("run-rate (annualized YTD, flat phasing)", landing,
                "no phased budget available — flat annualization")
    return ("none", ytd_cents, "no elapsed periods")


def _calculate(ytd_cents: int, full_year_budget_cents: int, elapsed_periods: int,
               total_periods: int, *, budget_phasing_cents=None,
               variance_history_cents=None, actual_history_cents=None,
               direction: str = "higher_is_better", target_cents: int | None = None,
               name: str = "line", persistence: str | None = None) -> dict:
    """
    Project the full-year landing and P(hit target). direction is
    'higher_is_better' (revenue) or 'lower_is_better' (cost). target defaults to
    the full-year budget.

    §26 — persistence-aware: the one-off/structural classification MECHANICALLY
    shapes the landing, so the README claim "a one-off spike isn't extrapolated"
    is actually true:
      - ONE_OFF     -> the YTD variance is NOT carried forward; remaining periods
                       are assumed to revert to the phased plan.
      - STRUCTURAL  -> the shift IS carried (the default projection already does).
      - AMBIGUOUS   -> landing kept, but the uncertainty band is widened.
    """
    try:
        for value, label in [(ytd_cents, 'YTD'), (full_year_budget_cents, 'full-year budget')]:
            cents(value, label)
        if target_cents is not None:
            cents(target_cents, 'target')
        if type(total_periods) is not int or type(elapsed_periods) is not int or not 0 <= elapsed_periods <= total_periods or not 1 <= total_periods <= 366:
            raise ValueError('periods must be integers: 0 <= elapsed <= total <= 366')
        if direction not in ('higher_is_better', 'lower_is_better'):
            raise ValueError('invalid direction')
        if persistence not in (None, 'ONE_OFF', 'STRUCTURAL', 'AMBIGUOUS', 'INSUFFICIENT_HISTORY', 'UNKNOWN'):
            raise ValueError('invalid persistence classification')
        for values, label in [(budget_phasing_cents, 'phasing'), (variance_history_cents, 'variance history'), (actual_history_cents, 'actual history')]:
            if values is not None:
                if not isinstance(values, list):
                    raise ValueError(label + ' must be a list of integer cents')
                for value in values:
                    cents(value, label)
        if budget_phasing_cents is not None:
            if len(budget_phasing_cents) != total_periods or sum(budget_phasing_cents) != full_year_budget_cents:
                raise ValueError('phasing must cover every period and sum to full-year budget')
        if elapsed_periods == 0 and ytd_cents != 0:
            raise ValueError('nonzero YTD with no elapsed periods')
    except ValueError as exc:
        return {'name': name, 'error': str(exc), 'computed_by': 'reforecast (python)'}

    target = target_cents if target_cents is not None else full_year_budget_cents
    remaining = total_periods - elapsed_periods
    if elapsed_periods == 0:
        return {'name': name, 'method': 'none', 'projected_landing_cents': None,
                'target_cents': target, 'direction': direction, 'band_cents': None,
                'prob_hit_target': None, 'reason': 'no elapsed observations',
                'computed_by': 'reforecast (python, integer cents)'}
    if remaining == 0:
        hit = ytd_cents >= target if direction == 'higher_is_better' else ytd_cents <= target
        return {'name': name, 'method': 'closed-year actual', 'ytd_cents': ytd_cents,
                'elapsed_periods': elapsed_periods, 'total_periods': total_periods,
                'remaining_periods': 0, 'projected_landing_cents': ytd_cents,
                'target_cents': target, 'direction': direction, 'band_cents': [ytd_cents, ytd_cents],
                'sigma_landing_cents': 0, 'prob_hit_target': float(hit),
                'confidence': 'deterministic (no remaining horizon)',
                'persistence': persistence, 'persistence_effect': None,
                'computed_by': 'reforecast (python, integer cents)'}
    if budget_phasing_cents is not None and sum(budget_phasing_cents[:elapsed_periods]) == 0 and persistence != 'ONE_OFF' and not (actual_history_cents and len(actual_history_cents) >= _TS_MIN):
        return {'name': name, 'error': 'zero phased budget to date: performance ratio undefined',
                'computed_by': 'reforecast (python)'}
    method, landing, note = _project(ytd_cents, full_year_budget_cents,
                                     elapsed_periods, total_periods,
                                     budget_phasing_cents, actual_history_cents)

    # --- §26: persistence adjustment ---------------------------------------
    persistence_effect = None
    if persistence == "ONE_OFF" and remaining > 0:
        if budget_phasing_cents and len(budget_phasing_cents) == total_periods:
            # Preferred: remaining periods assumed on the phased plan.
            remaining_budget = sum(budget_phasing_cents[elapsed_periods:])
            landing = ytd_cents + remaining_budget
            persistence_effect = {"classification": "ONE_OFF",
                                  "adjustment": "remaining periods assumed on phased plan (spike not carried)"}
            method = f"{method} + one-off normalization (phased) (§26)"
        else:
            # No phasing available: still MUST NOT extrapolate the spike. Assume
            # remaining periods run at the flat pro-rata full-year budget. The
            # assumption is flagged, rather than silently carrying a known one-off.
            remaining_budget = round(Fraction(full_year_budget_cents * remaining, total_periods))
            landing = ytd_cents + remaining_budget
            persistence_effect = {"classification": "ONE_OFF",
                                  "adjustment": "no phasing — remaining periods assumed at "
                                                "flat pro-rata budget (spike not carried); "
                                                "phased budget would refine this"}
            method = f"{method} + one-off normalization (flat pro-rata, no phasing) (§26)"

    try:
        cents(landing, 'projected landing')
    except ValueError as exc:
        return {'name': name, 'error': str(exc), 'computed_by': 'reforecast (python)'}
    result = {
        "name": name, "method": method, "method_note": note,
        "ytd_cents": ytd_cents, "elapsed_periods": elapsed_periods,
        "total_periods": total_periods, "remaining_periods": remaining,
        "projected_landing_cents": landing,
        "target_cents": target, "direction": direction,
        "persistence": persistence,
        "persistence_effect": persistence_effect,
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
    # §26: an AMBIGUOUS persistence classification means we're unsure whether the
    # variance carries — widen the band to reflect that model uncertainty.
    if persistence == "AMBIGUOUS":
        sigma_landing *= 1.5

    if sigma_landing == 0:
        # §30: remaining periods exist but historical dispersion is zero (often a
        # flat/degenerate fixture). This is NOT certainty about the future — report
        # a point landing with no probability rather than a false 0%/100%.
        result.update({
            "band_cents": None, "sigma_landing_cents": 0,
            "prob_hit_target": None,
            "confidence": "not computable (zero historical dispersion, horizon remaining)",
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
        "prob_hit_target": p_hit,
        "confidence": "computed from the line's own historical dispersion",
        "note": "band widens with horizon (sigma scales with sqrt(remaining periods))",
    })
    return result


def reforecast(ytd_cents, full_year_budget_cents, elapsed_periods, total_periods, *,
               budget_phasing_cents=None, variance_history_cents=None, actual_history_cents=None,
               direction='higher_is_better', target_cents=None, name='line', persistence=None,
               actual_periods=None, close_period=None, frequency=None):
    """Freeze inputs and publish conditional, uncalibrated model estimates explicitly.

    Trend actuals must be contiguous dated periods ending at this close, and their
    last elapsed_periods must reconcile to YTD. A trend point has no probability
    until parameter uncertainty is implemented and validated.
    """
    from copy import deepcopy
    from datetime import date
    inputs = deepcopy(dict(ytd_cents=ytd_cents, full_year_budget_cents=full_year_budget_cents,
        elapsed_periods=elapsed_periods, total_periods=total_periods,
        budget_phasing_cents=budget_phasing_cents, variance_history_cents=variance_history_cents,
        actual_history_cents=actual_history_cents, direction=direction, target_cents=target_cents,
        name=name, persistence=persistence, actual_periods=actual_periods,
        close_period=close_period, frequency=frequency))
    args = {k:v for k,v in inputs.items() if k not in ('actual_periods','close_period','frequency')}
    try:
        if actual_history_cents:
            if frequency not in ('monthly','quarterly','annual') or not isinstance(actual_periods,list) or len(actual_periods)!=len(actual_history_cents):
                raise ValueError('actual history requires aligned dates and reporting frequency')
            stamps = [date.fromisoformat(s) for s in actual_periods]
            close = date.fromisoformat(close_period)
            step = {'monthly':1,'quarterly':3,'annual':12}[frequency]
            if stamps[-1] != close or any(a>=b or (b.year-a.year)*12+b.month-a.month!=step for a,b in zip(stamps,stamps[1:])):
                raise ValueError('actual history must be contiguous and end at close_period')
            if type(elapsed_periods) is not int or elapsed_periods < 1 or len(stamps)<elapsed_periods:
                raise ValueError('actual history does not cover YTD')
            if any(type(v) is not int for v in actual_history_cents) or sum(actual_history_cents[-elapsed_periods:]) != ytd_cents:
                raise ValueError('actual history does not reconcile to YTD')
        elif actual_periods is not None or frequency is not None:
            raise ValueError('actual dates/frequency require actual history')
        result = _calculate(**args)
    except (ValueError, TypeError) as exc:
        result = {'name':name,'error':str(exc),'computed_by':'reforecast (python)'}
    # Invalid input is not serializable evidence (e.g. NaN); do not archive it as a result.
    if 'error' in result:
        import json
        try:
            json.dumps(inputs, allow_nan=False)
        except (ValueError, TypeError):
            return {**result, 'publication_status':'held_invalid_inputs'}
        return {**result, 'inputs':inputs, 'publication_status':'held_invalid_inputs'}
    result['inputs'] = inputs
    result['assumptions'] = [
        'Single-line projection; no cross-line correlation model.',
        'Historical variance dispersion assumes independent, comparable reporting periods.',
        'Normal-distribution range/probability is conditional on the projection method; coverage is not backtested.',
        'Persistence is a provisional rule or explicit caller scenario, not established business causation.'
    ]
    result['probability_kind'] = 'uncalibrated model estimate'
    result['publication_status'] = 'point_only' if result.get('prob_hit_target') is None else 'model_estimate'
    if result.get('remaining_periods') == 0:
        result['probability_kind'] = 'deterministic closed-year outcome'
        result['publication_status'] = 'deterministic'
    elif result.get('method','').startswith('time-series'):
        result.update(band_cents=None, prob_hit_target=None, publication_status='point_only',
                      confidence='not computable', reason='trend parameter uncertainty has not been estimated')
    elif persistence in ('UNKNOWN','INSUFFICIENT_HISTORY'):
        result.update(band_cents=None, prob_hit_target=None, publication_status='point_only',
                      confidence='not computable', reason='persistence evidence unavailable; point is an unconfirmed scenario')
    return result
