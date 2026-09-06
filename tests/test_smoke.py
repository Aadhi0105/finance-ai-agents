"""Cross-agent smoke tests: all four agents import and run offline on fixtures.
These guard against a change in one agent silently breaking another (they share
the spine)."""

import json
import os

os.environ.setdefault("AGENT_DATA_SOURCE", "fixture")


def test_agent1_offline_run_emits_grounded_sidecar(tmp_path):
    # Drive the analytical chain directly (no model needed) and ground a note.
    from tools import data
    from tools.analytical import compute_ratios, run_dcf
    from validation import gate, note_grounding
    from tests.conftest import make_state

    fin = data.get_financials({"ticker": "ASML.AS"})["financials"]
    pr = data.get_prices({"ticker": "ASML.AS"})
    s = make_state("ASML.AS", fin, {"market_cap": pr["market_cap"],
                                    "shares_outstanding": pr["shares_outstanding"],
                                    "current_price": pr["current_price"]})
    s.results["compute_ratios"] = compute_ratios({"ticker": "ASML.AS"}, s)
    s.results["run_dcf"] = run_dcf({"ticker": "ASML.AS"}, s)
    v = gate.assess(s.results)
    assert v["verdict"] in ("pass", "flag_for_review")
    # a note using only computed numbers must ground cleanly
    dcf = s.results["run_dcf"]
    note = f"Scenario-weighted value {dcf['scenario_weighted_per_share']}."
    assert note_grounding.ground_note(note, s.results)["passed"] is True


def test_agent2_cycle_runs():
    from scheduler.cycle import run_cycle
    import tempfile
    db = os.path.join(tempfile.mkdtemp(), "t.duckdb")
    # a single cold-start cycle against a fresh DB should not raise
    result = run_cycle(db_path=db)
    assert isinstance(result, dict)


def test_agent3_event_study_fixture():
    from agent3.track_a import load_event_set
    from tools.event_study import run_event_study
    es = load_event_set("semicap_earnings")
    r = run_event_study(es["events"], "semicap_earnings", es.get("placebo_events"))
    assert r["n_events"] > 0
    assert "caar" in r


def test_agent4_board_pack_reconciles():
    from agent4.hierarchy import rollup
    from agent4.output import board_pack
    bp = board_pack(rollup(json.load(open("fixtures/pnl.json"))))
    assert bp["reconciliation"]["passed"] is True


def test_significance_library_shared_by_all():
    # The platform thesis: one significance library, importable by every consumer.
    from tools.significance import one_sample_t
    from tools.statistical_checks import drift_check          # Agent 2
    from tools.event_study import run_event_study             # Agent 3
    from agent4.materiality import classify_variance          # Agent 4
    assert callable(one_sample_t)
    assert all(callable(f) for f in (drift_check, run_event_study, classify_variance))
