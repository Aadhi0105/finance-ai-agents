"""
Statistical check tools for Agent 2 (spec §3.3). THE discipline-carrying set —
the difference between a monitoring *system* and a cron job full of if-statements.

Two tools here, both destined for the shared MCP server (they are reused by
Agent 3); for now they are plain local Python called by run_cycle:

  anomaly_significance_check  -> STATISTICS (Agent 2's PRIMARY discipline):
      is the latest value a significant outlier vs the item's OWN history, or
      noise? Robust modified z-score (median / MAD) — the same robust-stats
      philosophy as Agent 1's peer check, applied to a time series.

  drift_check                 -> ECONOMETRICS:
      is there a significant TREND, measured by a fitted model rather than a
      hand-set line? OLS of value on time, with a proper t-test on the slope
      (t-distribution, not z, because samples are small), a prediction band,
      and R^2. Optionally projects cycles-to-breach at the current drift rate.

Governing principle carries: the LLM never does the math. These are deterministic
Python; the model only triages their output.

Sampling coherence (resolved decision): these operate over the history panel's
distinct data observations — coherent with the data's true update frequency, not
the monitoring cadence. (Freshness gating, a later checkpoint, guarantees history
holds one row per real data update.)

Pure Python (statistics + math) — no heavy deps, so MCP extraction stays light.
"""

from __future__ import annotations

import math
import statistics


# 95% two-sided t critical values by degrees of freedom (small-sample honesty:
# use t, not z). Falls back to the normal approximation for large dof.
_T_CRIT_95 = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36,
              8: 2.31, 9: 2.26, 10: 2.23, 12: 2.18, 15: 2.13, 20: 2.09, 30: 2.04}


def _t_crit(dof: int) -> float:
    if dof <= 0:
        return float("inf")
    if dof in _T_CRIT_95:
        return _T_CRIT_95[dof]
    keys = sorted(_T_CRIT_95)
    for k in keys:
        if dof <= k:
            return _T_CRIT_95[k]
    return 1.96  # large-sample normal approximation


# --- anomaly_significance_check (statistics) ------------------------------

def anomaly_significance_check(values: list[float], min_obs: int = 6,
                               z_flag: float = 3.5) -> dict:
    """
    Assess whether the LATEST value in `values` is a significant anomaly vs the
    PRIOR history. Robust: median + MAD, so one earlier spike doesn't poison the
    baseline. Modified z-score (Iglewicz-Hoaglin); |z| > z_flag => significant.
    """
    if values is None or len(values) < min_obs + 1:
        return {"significant": None, "modified_z": None,
                "reason": f"insufficient history (have {len(values or [])}, need {min_obs + 1})",
                "computed_by": "anomaly_significance_check (python)"}

    current = values[-1]
    history = values[:-1]
    median = statistics.median(history)
    abs_devs = [abs(x - median) for x in history]
    mad = statistics.median(abs_devs)

    if mad > 0:
        z = 0.6745 * (current - median) / mad
        method = "modified z (median/MAD)"
    else:
        std = statistics.pstdev(history)
        if std == 0:
            return {"significant": False, "modified_z": 0.0, "median": median,
                    "reason": "no variation in history", "n_history": len(history),
                    "computed_by": "anomaly_significance_check (python)"}
        z = (current - median) / std
        method = "z (MAD=0 fallback to std)"

    return {
        "significant": bool(abs(z) > z_flag),
        "modified_z": round(z, 2),
        "current": current, "median": round(median, 4), "mad": round(mad, 4),
        "n_history": len(history), "method": method,
        "caveat": "robust anomaly test; still noisy on short histories",
        "computed_by": "anomaly_significance_check (python)",
    }


# --- drift_check (econometrics) -------------------------------------------

def drift_check(times: list[float], values: list[float], min_obs: int = 6,
                threshold: float | None = None, direction: str | None = None) -> dict:
    """
    OLS of value on time. Reports the drift rate (slope), a t-test on the slope,
    R^2, and a prediction band for the latest point. `drifting` = the slope is
    significantly non-zero (a real trend, not noise). If a covenant threshold and
    direction are supplied, project cycles-to-breach at the current drift rate
    (early-warning).
    """
    n = len(values)
    if n < min_obs:
        return {"drifting": None, "slope": None,
                "reason": f"insufficient history (have {n}, need {min_obs})",
                "computed_by": "drift_check (python)"}

    tbar = statistics.mean(times)
    vbar = statistics.mean(values)
    s_tt = sum((t - tbar) ** 2 for t in times)
    if s_tt == 0:
        return {"drifting": None, "reason": "no variation in time axis",
                "computed_by": "drift_check (python)"}
    s_tv = sum((times[i] - tbar) * (values[i] - vbar) for i in range(n))
    slope = s_tv / s_tt
    intercept = vbar - slope * tbar

    resid = [values[i] - (intercept + slope * times[i]) for i in range(n)]
    rss = sum(r * r for r in resid)
    tss = sum((v - vbar) ** 2 for v in values)
    r2 = 1 - rss / tss if tss > 0 else 0.0
    dof = n - 2
    rse = math.sqrt(rss / dof) if dof > 0 else 0.0
    se_slope = rse / math.sqrt(s_tt) if s_tt > 0 else float("inf")
    t_slope = slope / se_slope if se_slope > 0 else 0.0
    tcrit = _t_crit(dof)
    slope_significant = abs(t_slope) > tcrit

    # Prediction band for the latest point.
    t0 = times[-1]
    pred = intercept + slope * t0
    se_pred = rse * math.sqrt(1 + 1 / n + (t0 - tbar) ** 2 / s_tt)
    band_low, band_high = pred - tcrit * se_pred, pred + tcrit * se_pred

    # Early-warning: project cycles-to-breach at the current drift rate.
    cycles_to_breach = None
    if threshold is not None and direction in ("below", "above") and abs(slope) > 1e-12:
        current = values[-1]
        heading_up = slope > 0
        # breach when value crosses threshold in the covenant-violating direction
        if direction == "below" and heading_up and current < threshold:
            cycles_to_breach = round((threshold - current) / slope, 1)
        elif direction == "above" and not heading_up and current > threshold:
            cycles_to_breach = round((threshold - current) / slope, 1)  # slope<0

    return {
        "drifting": bool(slope_significant),
        "slope": round(slope, 5),
        "slope_tstat": round(t_slope, 2),
        "r_squared": round(r2, 3),
        "predicted_latest": round(pred, 4),
        "actual_latest": round(values[-1], 4),
        "band": [round(band_low, 4), round(band_high, 4)],
        "n_obs": n,
        "cycles_to_breach_at_current_drift": cycles_to_breach,
        "method": "OLS value~time; t-test on slope (t-dist)",
        "caveat": "trend estimate; unreliable on short or non-stationary histories",
        "computed_by": "drift_check (python)",
    }


# --- breach_probability (probability) -------------------------------------

def _phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _first_passage_prob(a: float, m: float, s: float, T: float) -> float:
    """
    Probability that a random walk with per-step drift `m` and per-step volatility
    `s`, starting at 0, reaches barrier `a > 0` within `T` steps. Reflection-
    principle (first-passage) formula for arithmetic Brownian motion — this is the
    VaR-style barrier-crossing calc, not a terminal-value CDF.
    """
    if a <= 0:
        return 1.0                      # already at/over the barrier
    if s <= 0:
        return 1.0 if m * T >= a else 0.0
    sT = s * math.sqrt(T)
    term1 = _phi((m * T - a) / sT)
    expo = min(2.0 * m * a / (s * s), 700.0)   # guard overflow
    term2 = math.exp(expo) * _phi((-m * T - a) / sT)
    return max(0.0, min(1.0, term1 + term2))


def breach_probability(values: list[float], threshold: float, direction: str,
                       horizon: int = 6, min_obs: int = 6, tail_at: float = 0.25) -> dict:
    """
    Probability the metric BREACHES its covenant within `horizon` cycles, given
    its own drift and volatility. Estimates per-step drift and vol from the
    series' increments (random-walk-with-drift), then computes the first-passage
    probability to the covenant barrier.
    """
    n = len(values)
    if n < min_obs:
        return {"breach_probability": None,
                "reason": f"insufficient history (have {n}, need {min_obs})",
                "computed_by": "breach_probability (python)"}

    diffs = [values[i] - values[i - 1] for i in range(1, n)]
    mu = statistics.mean(diffs)                       # per-cycle drift (raw units)
    sigma = statistics.pstdev(diffs) if len(diffs) > 1 else 0.0
    current = values[-1]

    # Distance to the barrier, and drift *toward* it, in the covenant's direction.
    if direction == "below":                          # breach when value > threshold
        a = threshold - current
        m = mu                                        # rising = toward barrier
    elif direction == "above":                        # breach when value < threshold
        a = current - threshold
        m = -mu                                       # falling = toward barrier
    else:
        return {"breach_probability": None, "reason": f"unknown direction '{direction}'",
                "computed_by": "breach_probability (python)"}

    p = _first_passage_prob(a, m, sigma, horizon)
    toward_breach = a > 0 and m > 0                    # not yet breached, heading in

    return {
        "breach_probability": round(p, 4),
        "horizon_cycles": horizon,
        "toward_breach": bool(a <= 0 or toward_breach),
        "tail_flag": bool(p >= tail_at),
        "distance_to_breach": round(a, 4),
        "drift_per_cycle": round(mu, 5),
        "volatility_per_cycle": round(sigma, 5),
        "method": "first-passage (reflection principle) for RW-with-drift",
        "caveat": "assumes a random-walk-with-drift; probabilities sharpen as volatility falls",
        "computed_by": "breach_probability (python)",
    }
