"""
Event study engine (Agent 3, the flagship). Local function first; lifted to the
MCP server in a later checkpoint.

This is the owner's master's-thesis DiD, relabelled — not new skill, a transfer:
  abnormal return          = treatment effect
  market model             = the counterfactual (what the return would have been)
  estimation window        = the pre-period / parallel-trend baseline
  placebo on non-event days = the 2019 placebo (no effect where none should exist)
  t-test on mean CAAR      = the SE / p-value
  multiple windows / models = the four specifications

Method (all deterministic Python; the LLM never does the math):
  1. Per event, fit a market model  R_it = alpha + beta * R_mt + e  by OLS on an
     estimation window that ENDS before the event (no look-ahead, event-free).
  2. Abnormal return AR_t = R_t - (alpha_hat + beta_hat * R_mt) over the event window.
  3. Cumulate -> CAR for that event.
  4. Average CAR across N comparable events -> CAAR (cross-ticker, same event type).
     This averaging is what gives statistical power; a single event is noise.
  5. Significance: one-sample t-test on the per-event CARs (via tools.significance),
     is mean CAAR different from zero? Non-parametric sign test shipped alongside.
  6. Placebo: run the identical machinery on non-event ("pseudo-event") dates; a
     clean study shows no significant CAAR there.

Comparability is the load-bearing assumption for cross-ticker CAAR: the caller
supplies events judged to be the same catalyst type. N and basis are always
reported; power is honestly low at small N.
"""

from __future__ import annotations

import statistics

from tools.significance import one_sample_t, t_critical


def _ols_market_model(stock_rets: list[float], mkt_rets: list[float]) -> tuple[float, float]:
    """OLS of stock returns on market returns over the estimation window.
    Returns (alpha, beta)."""
    n = len(stock_rets)
    mbar = statistics.mean(mkt_rets)
    sbar = statistics.mean(stock_rets)
    s_mm = sum((mkt_rets[i] - mbar) ** 2 for i in range(n))
    if s_mm == 0:
        return sbar, 0.0
    s_ms = sum((mkt_rets[i] - mbar) * (stock_rets[i] - sbar) for i in range(n))
    beta = s_ms / s_mm
    alpha = sbar - beta * mbar
    return alpha, beta


def _car_for_event(event: dict) -> dict | None:
    """
    Compute one event's CAR.

    event = {
      "ticker": str, "event_date": str,
      "est_stock": [...], "est_market": [...],     # estimation window returns
      "evt_stock": [...], "evt_market": [...],     # event-window returns (e.g. [-1,+1])
    }
    Returns per-event abnormal returns and CAR, or None if the estimation window
    is too short to fit a market model.
    """
    est_s, est_m = event["est_stock"], event["est_market"]
    evt_s, evt_m = event["evt_stock"], event["evt_market"]
    if len(est_s) < 10 or len(est_s) != len(est_m) or len(evt_s) != len(evt_m):
        return None

    alpha, beta = _ols_market_model(est_s, est_m)
    ars = [evt_s[i] - (alpha + beta * evt_m[i]) for i in range(len(evt_s))]
    car = sum(ars)
    return {
        "ticker": event.get("ticker"), "event_date": event.get("event_date"),
        "alpha": round(alpha, 6), "beta": round(beta, 4),
        "abnormal_returns": [round(a, 6) for a in ars], "car": round(car, 6),
    }


def _sign_test(cars: list[float]) -> dict:
    """Non-parametric sign test: are positive CARs more common than chance?
    Robust to the non-normality that a parametric t-test assumes."""
    pos = sum(1 for c in cars if c > 0)
    neg = sum(1 for c in cars if c < 0)
    n = pos + neg
    if n == 0:
        return {"n_nonzero": 0, "positive": 0, "significant": None}
    # Normal approximation to the binomial (p=0.5).
    import math
    z = (pos - n / 2) / math.sqrt(n / 4) if n > 0 else 0.0
    return {"n_nonzero": n, "positive": pos, "negative": neg,
            "z": round(z, 3), "significant": bool(abs(z) > 1.96)}


def run_event_study(events: list[dict], event_type: str = "unspecified",
                    placebo_events: list[dict] | None = None) -> dict:
    """
    Multi-event CAAR study over a set of comparable events (cross-ticker, same
    event type). Returns the CAAR, its significance (parametric t via the shared
    helper + non-parametric sign test), the per-event detail, and — always — a
    placebo result when placebo events are supplied.
    """
    per_event = [c for c in (_car_for_event(e) for e in events) if c is not None]
    n = len(per_event)
    if n < 2:
        return {"event_type": event_type, "n_events": n,
                "reason": "need at least 2 usable events for a CAAR test",
                "computed_by": "run_event_study (python)"}

    cars = [c["car"] for c in per_event]
    caar = statistics.mean(cars)
    ttest = one_sample_t(cars, mu0=0.0)
    sign = _sign_test(cars)

    result = {
        "event_type": event_type,
        "n_events": n,
        "caar": round(caar, 6),
        "caar_significant": ttest["significant"],
        "t_stat": ttest["t_stat"],
        "p_value": ttest.get("p_value"),
        "sign_test": sign,
        "power_note": ("low power at small N — interpret with caution"
                       if n < 10 else "adequate N for a CAAR test"),
        "per_event": per_event,
        "method": "market-model OLS; multi-event CAAR; t-test via tools.significance",
        "computed_by": "run_event_study (python)",
    }

    # Placebo: identical machinery on non-event dates. A clean study finds nothing.
    if placebo_events:
        pe = [c for c in (_car_for_event(e) for e in placebo_events) if c is not None]
        if len(pe) >= 2:
            p_cars = [c["car"] for c in pe]
            p_t = one_sample_t(p_cars, mu0=0.0)
            result["placebo"] = {
                "n_events": len(pe),
                "caar": round(statistics.mean(p_cars), 6),
                "caar_significant": p_t["significant"],
                "t_stat": p_t["t_stat"],
                "interpretation": ("PASS — no significant effect on non-event dates"
                                   if not p_t["significant"]
                                   else "WARN — placebo is significant; the design may be confounded"),
            }

    return result
