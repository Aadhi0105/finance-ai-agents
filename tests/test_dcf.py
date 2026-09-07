"""run_dcf — parameter guards, net-debt bridge, None-vs-zero (§5, §8, §9)."""

from tools.analytical import run_dcf
from tests.conftest import make_state

_FIN = {"free_cash_flow": 1000, "net_income": 800,
        "total_debt": 300, "cash_and_equivalents": 100}
_PRICES = {"shares_outstanding": 10, "current_price": 500}


def _state(fin=None, prices=None):
    return make_state("TST", fin or _FIN, prices if prices is not None else _PRICES)


def test_refuses_r_le_g():
    r = run_dcf({"ticker": "TST", "discount_rate": 0.02, "terminal_growth": 0.025}, _state())
    assert "error" in r and "exceed terminal_growth" in r["error"]


def test_refuses_out_of_range_horizon():
    r = run_dcf({"ticker": "TST", "horizon_years": 99}, _state())
    assert "error" in r


def test_refuses_nonpositive_discount_rate():
    r = run_dcf({"ticker": "TST", "discount_rate": -0.01}, _state())
    assert "error" in r


def test_complete_bridge_gives_equity_value():
    r = run_dcf({"ticker": "TST"}, _state())
    assert r["value_basis"] == "equity_value"
    assert r["equity_value"] is not None
    assert r["assumptions"]["net_debt_bridge_status"] == "complete"


def test_net_cash_company_equity_above_ev():
    # net cash: cash (100) > debt (0) -> equity should exceed EV
    fin = {**_FIN, "total_debt": 0, "cash_and_equivalents": 100}
    r = run_dcf({"ticker": "TST"}, _state(fin))
    assert r["equity_value"]["base"] > r["enterprise_value"]["base"]


def test_partial_bridge_reports_ev_only():
    fin = {**_FIN}; del fin["total_debt"]        # only one side known
    r = run_dcf({"ticker": "TST"}, _state(fin))
    assert r["value_basis"] == "enterprise_value_only"
    assert r["equity_value"] is None
    assert r["assumptions"]["net_debt_bridge_status"] == "incomplete"
    # §4: NO equity-derived per-share/upside figures when the bridge is incomplete
    # (an EV-per-share compared to the equity share price is meaningless).
    assert r["value_per_share"] is None
    assert r["scenario_weighted_per_share"] is None
    assert r["implied_upside"] is None
    # enterprise value is still reported
    assert r["enterprise_value"]["base"] is not None


def test_zero_fcf_is_not_treated_as_missing():
    # None vs 0: a genuine 0.0 FCF must be USED, not replaced by net income.
    fin = {**_FIN, "free_cash_flow": 0.0}
    r = run_dcf({"ticker": "TST"}, _state(fin))
    assert r["assumptions"]["fcf_source"].startswith("free_cash_flow")


def test_terminal_value_concentration_reported():
    r = run_dcf({"ticker": "TST"}, _state())
    tvc = r["terminal_value_concentration"]["base"]
    assert 0.0 < tvc < 1.0


def test_scenario_weight_basis_labelled():
    r = run_dcf({"ticker": "TST"}, _state())
    assert "scenario_weighted_per_share" in r
    assert "not empirically estimated" in r["assumptions"]["weight_basis"]


def test_missing_financials_errors():
    from agent.state import RunState
    r = run_dcf({"ticker": "TST"}, RunState(ticker="TST"))
    assert "error" in r
