"""Cross-agent smoke tests: all four agents import and run offline on fixtures.
These guard against a change in one agent silently breaking another (they share
the spine)."""

import json
import os

def test_agent1_offline_run_emits_grounded_sidecar(tmp_path):
    from run import run_offline
    assert run_offline(output_root=tmp_path) == 3
    sidecar, = tmp_path.glob("*/model.json")
    record = json.loads(sidecar.read_text())
    assert record["execution"]["status"] == "completed"
    assert record["validation"]["verdict"] == "flag_for_review"
    assert record["validation"]["note_grounding"]["passed"]
    assert record["artifacts"]["status"] == "complete"
    assert len(record["call_history"]) == 7
    assert len(record["artifacts"]["charts"]) == 5
    assert (sidecar.parent / "report_REVIEW.html").exists()
    assert not (sidecar.parent / "report.html").exists()


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
