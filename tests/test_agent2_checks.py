"""Agent 2 — deterministic check tools: threshold, anomaly, drift, breach
probability. Includes the perfect-linear-trend drift regression (the P0 bug)."""

from tools.covenant_checks import threshold_check
from tools.statistical_checks import (
    anomaly_significance_check, drift_check, breach_probability)


# --- threshold_check (max/min, equality, invalid direction) --------------

def test_threshold_max_covenant_breach():
    r = threshold_check(3.7, 3.5, "below")   # must stay below -> 3.7 breaches
    assert r["breached"] is True
    assert r["margin"] > 0


def test_threshold_min_covenant_breach():
    r = threshold_check(2.7, 3.0, "above")   # must stay above -> 2.7 breaches
    assert r["breached"] is True
    assert r["margin"] > 0                    # signed margin > 0 means "in breach"


def test_threshold_safe_has_negative_margin():
    r = threshold_check(3.2, 3.5, "below")
    assert r["breached"] is False
    assert r["margin"] < 0                     # headroom


def test_threshold_equality_not_breached_below():
    r = threshold_check(3.5, 3.5, "below")     # strictly greater breaches
    assert r["breached"] is False


def test_threshold_invalid_direction():
    r = threshold_check(3.0, 3.5, "sideways")
    assert "error" in r


# --- anomaly (stable, real outlier) --------------------------------------

def test_anomaly_stable_series_no_flag():
    r = anomaly_significance_check([3.5, 3.5, 3.4, 3.6, 3.5, 3.5, 3.5])
    assert r["significant"] is False


def test_anomaly_real_outlier_flagged():
    r = anomaly_significance_check([3.5, 3.5, 3.4, 3.6, 3.5, 3.5, 2.0])
    assert r["significant"] is True


def test_anomaly_insufficient_history():
    r = anomaly_significance_check([3.5, 3.5])
    assert r["significant"] is None


# --- drift (flat, noisy trend, PERFECT LINEAR TREND) ---------------------

def test_drift_flat_series_no_drift():
    r = drift_check([1, 2, 3, 4, 5, 6], [2.5] * 6, threshold=3.0, direction="above")
    assert r["drifting"] is False


def test_drift_perfect_linear_trend_is_significant():
    """§5 REGRESSION: a perfect deteriorating line has zero residuals -> se_slope 0.
    The old code reported t=0 -> drifting=False, i.e. it missed the single clearest
    case of drift. It must now be significant."""
    r = drift_check([1, 2, 3, 4, 5, 6], [2.0, 2.1, 2.2, 2.3, 2.4, 2.5],
                    threshold=3.0, direction="above")
    assert r["drifting"] is True
    assert r["slope"] > 0


def test_drift_noisy_trend_detected():
    r = drift_check([1, 2, 3, 4, 5, 6], [2.0, 2.15, 2.18, 2.35, 2.4, 2.55],
                    threshold=3.0, direction="above")
    assert r["drifting"] is True


def test_drift_insufficient_history():
    r = drift_check([1, 2], [2.0, 2.1])
    assert r["drifting"] is None


# --- breach probability --------------------------------------------------

def test_breach_probability_already_breached_high():
    # trending hard toward a 'below' covenant it's about to cross
    r = breach_probability([3.0, 3.1, 3.2, 3.3, 3.4, 3.45], 3.5, "below")
    assert 0.0 <= r["breach_probability"] <= 1.0
    assert r["breach_probability"] > 0.5


def test_breach_probability_invalid_direction():
    r = breach_probability([3.0, 3.1, 3.2, 3.3, 3.4, 3.45], 3.5, "sideways")
    assert "error" in r or r.get("breach_probability") is None
