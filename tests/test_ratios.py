"""compute_ratios — finance-math correctness (the review's §3 fixes)."""

from tools.analytical import compute_ratios
from tests.conftest import make_state

_FIN = {"revenue": 1000, "gross_profit": 600, "operating_income": 200,
        "net_income": 150, "revenue_prior": 800,
        "total_debt": 300, "cash_and_equivalents": 100}
_PRICES = {"market_cap": 2000, "shares_outstanding": 10, "current_price": 200}


def test_ev_ebit_uses_real_enterprise_value():
    r = compute_ratios({"ticker": "TST"}, make_state("TST", _FIN, _PRICES))
    # EV = 2000 + 300 - 100 = 2200 ; EV/EBIT = 2200/200 = 11.0
    assert r["assumptions"]["ev"] == 2200
    assert r["ratios"]["ev_ebit"] == 11.0


def test_pe_on_positive_earnings():
    r = compute_ratios({"ticker": "TST"}, make_state("TST", _FIN, _PRICES))
    assert abs(r["ratios"]["pe"] - round(2000 / 150, 4)) < 1e-6


def test_negative_earnings_pe_nulled_with_status():
    fin = {**_FIN, "net_income": -80}
    r = compute_ratios({"ticker": "TST"}, make_state("TST", fin, _PRICES))
    assert r["ratios"]["pe"] is None
    assert r["multiple_status"]["pe"] == "not_meaningful_negative_earnings"


def test_negative_ebit_ev_ebit_nulled():
    fin = {**_FIN, "operating_income": -50}
    r = compute_ratios({"ticker": "TST"}, make_state("TST", fin, _PRICES))
    assert r["ratios"]["ev_ebit"] is None
    assert r["multiple_status"]["ev_ebit"] == "not_meaningful_negative_ebit"


def test_incomplete_net_debt_blocks_ev_ebit():
    fin = {**_FIN}; del fin["cash_and_equivalents"]
    r = compute_ratios({"ticker": "TST"}, make_state("TST", fin, _PRICES))
    assert r["ratios"]["ev_ebit"] is None
    assert r["multiple_status"]["ev_ebit"] == "not_computable_incomplete_net_debt"


def test_margins_correct():
    r = compute_ratios({"ticker": "TST"}, make_state("TST", _FIN, _PRICES))["ratios"]
    assert r["gross_margin"] == 0.6
    assert r["operating_margin"] == 0.2
    assert r["net_margin"] == 0.15


def test_revenue_growth_yoy():
    r = compute_ratios({"ticker": "TST"}, make_state("TST", _FIN, _PRICES))["ratios"]
    assert r["revenue_growth_yoy"] == 0.25   # (1000-800)/800


def test_zero_denominator_is_none_not_crash():
    fin = {**_FIN, "revenue": 0}
    r = compute_ratios({"ticker": "TST"}, make_state("TST", fin, _PRICES))["ratios"]
    assert r["gross_margin"] is None


def test_multiples_skipped_without_prices():
    r = compute_ratios({"ticker": "TST"}, make_state("TST", _FIN, None))
    assert "multiples" in r["assumptions"]
    assert "pe" not in r["ratios"]
