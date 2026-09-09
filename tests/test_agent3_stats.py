"""Agent 3 — statistical inference fixes (§7 exact Student-t p-value, §8 exact
binomial sign test, §9 degenerate zero-dispersion)."""

import math
from scipy import stats
from tools.significance import one_sample_t
from tools.event_study import _sign_test


def test_one_sample_t_exact_student_p_value():
    """§7: reported p-value must be the exact Student-t p, not a normal approx
    (the two differ materially at small N, and this p feeds the Bonferroni gate)."""
    vals = [0.021, 0.015, -0.004, 0.032, 0.009, 0.018, -0.011, 0.025]
    r = one_sample_t(vals)
    n = len(vals)
    mean = sum(vals) / n
    sd = (sum((v - mean) ** 2 for v in vals) / (n - 1)) ** 0.5
    t = mean / (sd / math.sqrt(n))
    exact = float(2 * stats.t.sf(abs(t), n - 1))
    assert abs(r["p_value"] - exact) < 1e-5


def test_one_sample_t_p_differs_from_normal_at_small_n():
    """Guard that we're actually using Student-t: the normal approx would be
    meaningfully smaller at n=8."""
    vals = [0.021, 0.015, -0.004, 0.032, 0.009, 0.018, -0.011, 0.025]
    r = one_sample_t(vals)
    n = len(vals); mean = sum(vals) / n
    sd = (sum((v - mean) ** 2 for v in vals) / (n - 1)) ** 0.5
    t = mean / (sd / math.sqrt(n))
    normal_p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / 2 ** 0.5)))
    assert r["p_value"] > normal_p          # Student-t p is larger (fatter tails)


def test_one_sample_t_degenerate_zero_dispersion():
    """§9: identical values -> degenerate, NOT false certainty."""
    r = one_sample_t([0.02, 0.02, 0.02, 0.02, 0.02])
    assert r["significant"] is None
    assert r["inference_status"] == "degenerate_zero_dispersion"
    assert r["p_value"] is None


def test_sign_test_exact_binomial():
    """§8: exact two-sided binomial p-value, correct at small N."""
    cars = [0.03, 0.02, 0.05, -0.01, 0.04, 0.01, 0.06, 0.02]  # 7/8 positive
    r = _sign_test(cars)
    exact = float(stats.binomtest(7, 8, 0.5, alternative="two-sided").pvalue)
    assert abs(r["p_value"] - exact) < 1e-5
    assert r["significant"] is (exact < 0.05)   # 7/8 -> p=0.070 -> not significant


def test_sign_test_balanced_not_significant():
    r = _sign_test([0.01, -0.01, 0.02, -0.02])   # 2/2, clearly not significant
    assert r["significant"] is False
