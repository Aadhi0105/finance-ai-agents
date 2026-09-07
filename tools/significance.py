"""
Shared significance primitives (local library, not an MCP-served tool).

One source of truth for the small-sample t-machinery used across the platform:
  - drift_check (Agent 2) uses it to test a regression slope.
  - run_event_study (Agent 3) uses it to test whether mean CAAR differs from zero.

This is the "wrap, don't reimplement" discipline at the library level: the tools
that cross the MCP boundary (drift_check, run_event_study) both call these
functions, so "reuse the significance family" is true at the code level rather
than asserted. The helper itself is NOT served over MCP — it is a library the
boundary tools depend on, so serving it would be MCP-as-decoration.

Pure Python (math + statistics), no heavy deps.
"""

from __future__ import annotations

import math
import statistics


# 95% two-sided t critical values by degrees of freedom (small-sample honesty:
# use t, not z). Falls back to the normal approximation for large dof.
_T_CRIT_95 = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36,
              8: 2.31, 9: 2.26, 10: 2.23, 12: 2.18, 15: 2.13, 20: 2.09, 30: 2.04}


def t_critical(dof: int) -> float:
    """95% two-sided t critical value for `dof` degrees of freedom, with a
    normal-approximation fallback for large samples."""
    if dof <= 0:
        return float("inf")
    if dof in _T_CRIT_95:
        return _T_CRIT_95[dof]
    for k in sorted(_T_CRIT_95):
        if dof <= k:
            return _T_CRIT_95[k]
    return 1.96  # large-sample normal approximation


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def one_sample_t(values: list[float], mu0: float = 0.0) -> dict:
    """
    One-sample t-test: is the mean of `values` significantly different from `mu0`?
    Used by the event study to test whether mean CAAR differs from zero.

    Returns the mean, standard error, t-statistic, dof, 95% critical value, a
    significance flag, and an approximate two-sided p-value.
    """
    n = len(values)
    if n < 2:
        return {"n": n, "mean": (values[0] if n else None), "t_stat": None,
                "significant": None, "reason": "need at least 2 observations"}

    mean = statistics.mean(values)
    sd = statistics.stdev(values)                 # sample standard deviation
    se = sd / math.sqrt(n) if sd > 0 else 0.0
    dof = n - 1
    tcrit = t_critical(dof)

    if se == 0:
        # Zero dispersion (all values identical) is far more likely a data problem
        # -- duplicated observations, a fixture artefact -- than genuine infinite
        # certainty. Flag it degenerate so the validation gate reviews it rather
        # than treating it as a rock-solid result.
        return {"n": n, "mean": round(mean, 6), "se": 0.0, "t_stat": None,
                "dof": dof, "t_crit_95": tcrit, "significant": None,
                "inference_status": "degenerate_zero_dispersion", "p_value": None,
                "note": "all observations identical -- check for duplicated/degenerate data",
                "computed_by": "one_sample_t (python)"}

    t_stat = (mean - mu0) / se
    # Exact two-sided Student-t p-value (scipy). Previously a normal approximation,
    # which disagreed with the Student-t accept/reject decision at small N -- and
    # that p-value feeds Agent 3's Bonferroni gate, so the two must be consistent.
    from scipy import stats as _sps
    p_value = float(2.0 * _sps.t.sf(abs(t_stat), dof))
    return {
        "n": n, "mean": round(mean, 6), "se": round(se, 6),
        "t_stat": round(t_stat, 4), "dof": dof, "t_crit_95": tcrit,
        "significant": bool(abs(t_stat) > tcrit),
        "p_value": round(p_value, 6),
        "computed_by": "one_sample_t (python, scipy Student-t p-value)",
    }


def mean_ci(values: list[float], level: str = "95") -> dict:
    """95% confidence interval for the mean of `values` (t-based)."""
    n = len(values)
    if n < 2:
        return {"n": n, "mean": (values[0] if n else None), "ci": None,
                "reason": "need at least 2 observations"}
    mean = statistics.mean(values)
    sd = statistics.stdev(values)
    se = sd / math.sqrt(n)
    half = t_critical(n - 1) * se
    return {"n": n, "mean": round(mean, 6), "se": round(se, 6),
            "ci": [round(mean - half, 6), round(mean + half, 6)],
            "computed_by": "mean_ci (python)"}
