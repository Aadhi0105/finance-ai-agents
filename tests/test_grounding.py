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
    signed, allowed = build_number_registry({"x": 8_400_000_000})
    # 8.4bn should be present as 8.4 (bn) in both sets
    assert 8.4 in allowed
    assert 8.4 in signed


def test_grounding_is_sign_aware():
    results = {"run_dcf": {"implied_upside": 0.184}}
    # computed +18.4% -> a stated -18.4% (wrong sign) must be caught
    assert ground_note("Downside of -18.4%.", results)["passed"] is False
    # matching sign passes; unsigned passes (prose carries direction)
    assert ground_note("Upside of +18.4%.", results)["passed"] is True
    assert ground_note("A gap of 18.4%.", results)["passed"] is True


def test_wrong_percentage_caught():
    r = ground_note("Operating margin was 99.9%.", _RESULTS)
    assert r["passed"] is False


def test_grounds_against_earlier_call_output():
    """§6: a note may cite an EARLIER tool call (not just the latest result). When
    grounding against the full successful-call history, that figure is valid."""
    # two DCF calls: latest result is 220, but 205 was produced earlier
    grounded_from_calls = {"call_0": {"scenario_weighted_per_share": 205.0},
                           "call_1": {"scenario_weighted_per_share": 220.0}}
    note = "The initial spec yielded EUR205.00; revised assumptions gave EUR220.00."
    r = ground_note(note, grounded_from_calls)
    assert r["passed"] is True
