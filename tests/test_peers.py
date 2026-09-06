"""peer_outlier_check — robust stats + hygiene (§10, §11). Uses real fixtures."""

import os
from tools.analytical import peer_outlier_check
from tools import data
from tests.conftest import make_state


def _target_state():
    fin = data.get_financials({"ticker": "ASML.AS"})["financials"]
    pr = data.get_prices({"ticker": "ASML.AS"})
    return make_state("ASML.AS", fin, {"market_cap": pr["market_cap"],
                                       "shares_outstanding": pr["shares_outstanding"],
                                       "current_price": pr["current_price"]})


def test_robust_verdict_is_primary():
    r = peer_outlier_check({"ticker": "ASML.AS", "peers": ["ASM.AS", "BESI.AS", "LRCX"]}, _target_state())
    assert "median/MAD" in r["verdict_basis"]
    assert r["peer_median"] is not None


def test_self_ticker_dropped_from_peers():
    r = peer_outlier_check({"ticker": "ASML.AS", "peers": ["ASML.AS", "ASM.AS", "BESI.AS"]}, _target_state())
    assert "ASML.AS" not in r["peer_pes"]


def test_duplicate_peers_deduped():
    r = peer_outlier_check({"ticker": "ASML.AS", "peers": ["ASM.AS", "ASM.AS", "BESI.AS"]}, _target_state())
    assert list(r["peer_pes"].keys()).count("ASM.AS") == 1


def test_too_few_peers_errors():
    r = peer_outlier_check({"ticker": "ASML.AS", "peers": ["ASM.AS"]}, _target_state())
    assert "error" in r


def test_reports_n_peers():
    r = peer_outlier_check({"ticker": "ASML.AS", "peers": ["ASM.AS", "BESI.AS", "LRCX"]}, _target_state())
    assert r["n_peers"] == len(r["peer_pes"])
