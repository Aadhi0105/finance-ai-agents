


"""run_dcf — FCFF base, parameter guards, net-debt bridge, refusal paths."""

from tools.analytical import run_dcf
from tests.conftest import make_state

# FCFF lines: EBIT*(1-T) + D&A - CapEx - dNWC = 1000*(1-0.25)+200-100-0 = 850.
_FIN = {"ebit": 1000, "depreciation_amortization": 200, "capex": -100,
        "tax_provision": 250, "pretax_income": 1000,
        "change_in_working_capital": 0,
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


def test_refuses_when_fcff_lines_missing():
    # the old net-income fallback is gone: an enterprise DCF must have EBIT/D&A/CapEx
    fin = {"net_income": 800, "operating_income": 1000,
           "total_debt": 300, "cash_and_equivalents": 100}
    r = run_dcf({"ticker": "TST"}, _state(fin))
    assert "error" in r
    assert r["value_basis"] == "not_computable"


def test_refuses_negative_fcff():
    # a firm with non-positive unlevered FCF is not suitable for a two-stage DCF
    fin = {**_FIN, "ebit": -5000}
    r = run_dcf({"ticker": "TST"}, _state(fin))
    assert "error" in r
    assert r["value_basis"] == "not_applicable_negative_fcff"


def test_fcff_base_is_unlevered():
    r = run_dcf({"ticker": "TST"}, _state())
    # 1000*(1-0.25) + 200 - 100 - 0 = 850
    assert r["assumptions"]["fcf_base"] == 850
    assert "FCFF" in r["assumptions"]["fcf_source"]


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
