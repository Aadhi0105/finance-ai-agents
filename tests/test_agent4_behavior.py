"""Agent 4 behavioural fixes: zero-dispersion anomaly (§19), persistence-driven
reforecast (§26), zero-budget materiality (§24), reforecast validation (§30/§31)."""

from tools.statistical_checks import anomaly_significance_check
from agent4.materiality import classify_variance
from agent4.reforecast import reforecast


# --- §19: the zero-dispersion anomaly bug (the P0) ----------------------

def test_flat_history_big_break_is_significant():
    """A perfectly flat history with a large current value is a deterministic
    baseline break — must flag, not return 'not significant'."""
    r = anomaly_significance_check([0, 0, 0, 0, 0, 0, 500000])
    assert r["significant"] is True
    assert r.get("inference_status") == "zero_dispersion_break"


def test_flat_history_matching_value_not_significant():
    r = anomaly_significance_check([100, 100, 100, 100, 100, 100, 100])
    assert r["significant"] is False


def test_flat_break_classifies_top_priority():
    """End-to-end: the §19 fix flips this from EXPECTED_VOLATILITY to TOP_PRIORITY."""
    line = {"name": "L", "total_variance_cents": 500_000_00, "favourable": False}
    r = classify_variance(line, 2_000_000_00, 10_000_000_00,
                          variance_history_cents=[0, 0, 0, 0, 0, 0])
    assert r["quadrant"] == "TOP_PRIORITY"


# --- §26: persistence drives the reforecast -----------------------------

_PHASING = [2_200_000_00, 2_750_000_00, 2_750_000_00, 3_300_000_00]  # FY 11M
_HIST = [300_000_00, -300_000_00, 250_000_00, -250_000_00,
         320_000_00, -280_000_00, 310_000_00, -290_000_00]


def _rf(persistence):
    return reforecast(6_500_000_00, 11_000_000_00, 2, 4,
                      budget_phasing_cents=_PHASING, variance_history_cents=_HIST,
                      persistence=persistence)


def test_one_off_not_extrapolated():
    """§26: a ONE_OFF spike must land LOWER than STRUCTURAL (spike not carried)."""
    one_off = _rf("ONE_OFF")["projected_landing_cents"]
    structural = _rf("STRUCTURAL")["projected_landing_cents"]
    assert one_off < structural
    assert _rf("ONE_OFF")["persistence_effect"] is not None


def test_structural_carries_shift():
    structural = _rf("STRUCTURAL")
    assert structural["persistence_effect"] is None      # default projection, carried


def test_ambiguous_widens_band():
    amb = _rf("AMBIGUOUS")
    struct = _rf("STRUCTURAL")
    wa = amb["band_cents"][1] - amb["band_cents"][0]
    ws = struct["band_cents"][1] - struct["band_cents"][0]
    assert wa > ws


# --- §30/§31: reforecast validation -------------------------------------

def test_reforecast_rejects_invalid_direction():
    r = reforecast(1, 1, 1, 4, direction="banana")
    assert "error" in r


def test_reforecast_rejects_bad_periods():
    assert "error" in reforecast(1, 1, 5, 4)      # elapsed > total
    assert "error" in reforecast(1, 1, 1, 0)      # total <= 0


def test_zero_dispersion_with_horizon_not_certain():
    """§30: flat history but periods remaining -> not computable, not 0%/100%."""
    r = reforecast(5_000_000_00, 11_000_000_00, 2, 4,
                   budget_phasing_cents=_PHASING,
                   variance_history_cents=[0, 0, 0, 0, 0, 0, 0, 0])
    assert r["prob_hit_target"] is None
