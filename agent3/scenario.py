"""
Scenario / catalyst engine (Agent 3, local — the "project" in read -> prove ->
project). This is Agent 3's PROBABILITY-primary layer.

Calibration, not prediction. It re-expresses measured history: "across N
comparable events the abnormal-return distribution was X, so the next comparable
catalyst implies this probability-weighted range, with caveats." It never
forecasts a specific move — every output is a distribution with explicit N,
confidence, and a regime caveat, which is how the "not an alpha engine" scope is
enforced at the output level.

Method:
  - Consume the event study's REALIZED per-event CARs (what actually happened).
  - Bootstrap them (resample with replacement) to build a forward distribution
    for the next comparable catalyst — using the empirical outcomes, not an
    assumed parametric shape. (Monte Carlo is reserved for path / horizon /
    compound-catalyst questions and is intentionally not the default here.)
  - Report percentiles, P(positive), mean, and a confidence that scales with N.

The refusal gate — "no distribution, no scenario":
  - N below a floor  -> REFUSE (can't bootstrap a believable distribution).
  - underlying event study NOT significant, adequate N -> EMIT AS NULL (this is
    the distribution of noise; history shows no reliable effect — an honest null,
    not a blank refusal).
  - otherwise -> a calibrated scenario, confidence scaling with N.

Deterministic Python (the LLM never does the math). Seeded bootstrap for
reproducibility.
"""

from __future__ import annotations

import random
import statistics

_N_FLOOR = 5              # below this, refuse — too few events to bootstrap
_N_ADEQUATE = 10         # at/above this, "high" sample confidence
_BOOTSTRAP = 10000       # resamples
_SEED = 12345            # deterministic


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0,1]."""
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = q * (len(sorted_vals) - 1)
    lo = int(idx)
    frac = idx - lo
    if lo + 1 >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[lo] * (1 - frac) + sorted_vals[lo + 1] * frac


def _confidence(n: int, significant: bool | None) -> str:
    if significant is False:
        return "null"
    if n >= _N_ADEQUATE:
        return "high"
    if n >= _N_FLOOR + 2:
        return "medium"
    return "low"


def scenario_from_event_study(event_study: dict, seed: int = _SEED,
                              n_boot: int = _BOOTSTRAP) -> dict:
    """
    Turn an event-study result into a forward, probability-weighted scenario for
    the next comparable catalyst — or refuse if the evidence is too thin.

    Expects the dict returned by run_event_study (needs `per_event` CARs,
    `n_events`, `caar_significant`, `event_type`).
    """
    event_type = event_study.get("event_type", "unspecified")
    per_event = event_study.get("per_event") or []
    cars = [e["car"] for e in per_event if "car" in e]
    n = len(cars)
    significant = event_study.get("caar_significant")

    # --- refusal gate ---
    if n < _N_FLOOR:
        return {
            "event_type": event_type, "scenario": None, "verdict": "REFUSED",
            "reason": f"only {n} comparable events (floor {_N_FLOOR}); "
                      f"too few to bootstrap a believable distribution",
            "n_events": n, "computed_by": "scenario_engine (python)",
        }

    # --- bootstrap the empirical CAR distribution ---
    rng = random.Random(seed)
    boot_means = []
    for _ in range(n_boot):
        sample = [cars[rng.randrange(n)] for _ in range(n)]
        boot_means.append(statistics.mean(sample))
    boot_means.sort()

    # The forward distribution of a single next outcome is the resampled CARs
    # themselves; the distribution of the *mean* effect is boot_means (tighter).
    outcomes = sorted(cars)
    p_positive = sum(1 for c in cars if c > 0) / n

    dist = {
        "mean_car": round(statistics.mean(cars), 6),
        "median_car": round(_percentile(outcomes, 0.5), 6),
        "p10": round(_percentile(outcomes, 0.10), 6),
        "p25": round(_percentile(outcomes, 0.25), 6),
        "p75": round(_percentile(outcomes, 0.75), 6),
        "p90": round(_percentile(outcomes, 0.90), 6),
        "prob_positive": round(p_positive, 3),
        # bootstrap CI on the MEAN effect (how well-pinned the average is)
        "mean_ci95": [round(_percentile(boot_means, 0.025), 6),
                      round(_percentile(boot_means, 0.975), 6)],
    }

    confidence = _confidence(n, significant)

    if significant is False:
        verdict = "NULL"
        headline = ("The historical effect is not statistically distinguishable "
                    "from zero — this is the distribution of noise. Treat as no "
                    "reliable edge, not as a forecast.")
    else:
        verdict = "CALIBRATED"
        headline = (f"Across {n} comparable {event_type} events the abnormal-return "
                    f"distribution implies the range below for the next comparable "
                    f"catalyst. Calibration of history, not a prediction.")

    return {
        "event_type": event_type,
        "verdict": verdict,
        "confidence": confidence,
        "n_events": n,
        "underlying_significant": significant,
        "distribution": dist,
        "headline": headline,
        "caveats": [
            "Calibration of past comparable events, not a point prediction.",
            "Assumes the next catalyst is drawn from the same regime; prefers recent comparables.",
            f"Confidence scales with N (N={n}).",
        ],
        "method": "empirical bootstrap of realized per-event CARs",
        "computed_by": "scenario_engine (python)",
    }
