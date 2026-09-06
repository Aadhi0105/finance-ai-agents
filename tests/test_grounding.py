"""Note grounding — 'the LLM never does the math' as a mechanical property (§2)."""

from validation.note_grounding import ground_note, build_number_registry

_RESULTS = {
    "compute_ratios": {"ratios": {"operating_margin": 0.3462, "pe": 13.33}},
    "run_dcf": {"scenario_weighted_per_share": 214.21, "implied_upside": 0.184,
                "current_price": 180.0},
}


def test_clean_note_grounds():
    note = ("Operating margin 34.6%. DCF implies 18.4% upside to €214.21 vs the "
            "current €180.00, on a P/E of 13.3x.")
    assert ground_note(note, _RESULTS)["passed"] is True


def test_fabricated_figure_caught():
    r = ground_note("I estimate fair value at €850.", _RESULTS)
    assert r["passed"] is False
    assert any("850" in u["figure"] for u in r["unmatched"])


def test_percentage_matches_ratio():
    # 0.3462 stored as a ratio should validate a 34.6% mention
    assert ground_note("Operating margin was 34.6%.", _RESULTS)["passed"] is True


def test_multiple_matches():
    assert ground_note("Trades on 13.3x earnings.", _RESULTS)["passed"] is True


def test_registry_includes_scaled_forms():
    reg = build_number_registry({"x": 8_400_000_000})
    # 8.4bn should be present as 8.4 (bn), 8400 (m), etc.
    assert 8.4 in reg


def test_wrong_percentage_caught():
    r = ground_note("Operating margin was 99.9%.", _RESULTS)
    assert r["passed"] is False
