"""Ticker-integrity invariant (§14): a dependent tool must not compute on another
ticker's stored data."""

from tools.analytical import compute_ratios, run_dcf, peer_outlier_check
from tests.conftest import make_state

_FIN = {"revenue": 1000, "operating_income": 200, "net_income": 150,
        "free_cash_flow": 900, "total_debt": 100, "cash_and_equivalents": 50}
_PRICES = {"market_cap": 2000, "shares_outstanding": 10, "current_price": 200}


def test_compute_ratios_refuses_ticker_mismatch():
    s = make_state("ASML.AS", _FIN, _PRICES)
    r = compute_ratios({"ticker": "AAPL"}, s)
    assert "error" in r and "mismatch" in r["error"]


def test_run_dcf_refuses_ticker_mismatch():
    s = make_state("ASML.AS", _FIN, _PRICES)
    r = run_dcf({"ticker": "AAPL"}, s)
    assert "error" in r and "mismatch" in r["error"]


def test_peer_check_refuses_ticker_mismatch():
    s = make_state("ASML.AS", _FIN, _PRICES)
    r = peer_outlier_check({"ticker": "AAPL", "peers": ["A", "B"]}, s)
    assert "error" in r and "mismatch" in r["error"]


def test_upstream_result_ticker_must_match():
    # stored financials are for ASML but the run + request are TST -> refuse
    s = make_state("TST", None, _PRICES)
    s.results["get_financials"] = {"ticker": "ASML.AS", "financials": _FIN}
    r = compute_ratios({"ticker": "TST"}, s)
    assert "error" in r
