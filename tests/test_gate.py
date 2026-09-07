"""Validation gate — findings vs quality-warns vs fails; the gate actually gates
(§19, §20)."""

from validation import gate


def _clean():
    return {
        "get_financials": {"ticker": "T", "financials": {
            "revenue": 1000, "net_income": 150, "period": "2025-12-31",
            "free_cash_flow": 120, "total_debt": 100, "cash_and_equivalents": 50}},
        "get_prices": {"ticker": "T", "market_cap": 2000, "shares_outstanding": 10},
        "compute_ratios": {"ticker": "T", "ratios": {"net_margin": 0.15}},
        "run_dcf": {"assumptions": {"fcf_source": "free_cash_flow (cash-flow statement)",
                                    "net_debt_bridge_status": "complete", "high_growth": 0.12},
                    "implied_upside": 0.1,
                    "terminal_value_concentration": {"base": 0.5}},
    }


def test_clean_run_passes_high_confidence():
    v = gate.assess(_clean(), now=__import__("datetime").date(2026, 3, 1))
    assert v["verdict"] == "pass"
    assert v["confidence"] == "high"


def test_implausible_margin_fails():
    a = _clean(); a["compute_ratios"]["ratios"]["net_margin"] = 5.0
    v = gate.assess(a)
    assert v["verdict"] == "flag_for_review"
    assert v["n_fail"] >= 1


def test_missing_net_income_fails():
    a = _clean(); a["get_financials"]["financials"]["net_income"] = None
    v = gate.assess(a)
    assert v["verdict"] == "flag_for_review"


def test_valuation_gap_is_info_finding_not_fault():
    a = _clean(); a["run_dcf"]["implied_upside"] = 0.9   # huge gap
    v = gate.assess(a, now=__import__("datetime").date(2026, 3, 1))
    vg = [c for c in v["checks"] if c["check"] == "valuation_gap"][0]
    assert vg["status"] == "info_finding"
    # a finding alone must NOT drag the run into review
    assert v["verdict"] == "pass"


def test_incomplete_bridge_is_quality_warn():
    a = _clean(); a["run_dcf"]["assumptions"]["net_debt_bridge_status"] = "incomplete"
    v = gate.assess(a, now=__import__("datetime").date(2026, 3, 1))
    nb = [c for c in v["checks"] if c["check"] == "net_debt_bridge"][0]
    assert nb["status"] == "quality_warn"


def test_info_findings_do_not_lower_score():
    a = _clean()
    a["run_dcf"]["implied_upside"] = 0.9
    a["run_dcf"]["terminal_value_concentration"]["base"] = 0.95
    a["peer_outlier_check"] = {"peer_pes": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5},
                               "n_peers": 5, "verdict_divergence": True}
    v = gate.assess(a, now=__import__("datetime").date(2026, 3, 1))
    # three findings present, but score should still pass
    assert v["n_info_finding"] >= 3
    assert v["verdict"] == "pass"


def test_small_peer_set_quality_warns():
    a = _clean()
    a["peer_outlier_check"] = {"peer_pes": {"a": 1, "b": 2}, "n_peers": 2}
    v = gate.assess(a, now=__import__("datetime").date(2026, 3, 1))
    ps = [c for c in v["checks"] if c["check"] == "peer_sample_size"][0]
    assert ps["status"] == "quality_warn"


def test_aggregate_checks_consistent_after_added_fail():
    """§7: adding a fail and re-aggregating keeps score/verdict/confidence
    mutually consistent (no 'score 1.0 but 1 fail' contradiction)."""
    checks = [{"check": "x", "status": "pass", "detail": ""},
              {"check": "note_grounding", "status": "fail", "detail": "fabricated figure"}]
    agg = gate.aggregate_checks(checks)
    assert agg["n_fail"] == 1
    assert agg["verdict"] == "flag_for_review"
    assert agg["confidence"] == "low"
    assert agg["score"] < 0.7          # score reflects the fail, not left at 1.0
