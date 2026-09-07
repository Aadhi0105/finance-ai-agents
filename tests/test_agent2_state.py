"""Agent 2 — classification state machine, persistence, freshness, idempotency,
triage counting, and the cycle atom. The most stateful, most bug-prone agent —
so the most worth testing."""

import os
import tempfile

from state.classify import classify, SURFACED


# --- classification: every transition -----------------------------------

def _last(breached, margin):
    return {"breached": breached, "margin": margin}


def test_classify_baseline_first_sighting():
    assert classify(None, True, 0.2, is_baseline=True) == "BASELINE"


def test_classify_ok_safe_to_safe():
    assert classify(_last(False, -0.3), False, -0.2, is_baseline=False) == "OK"


def test_classify_new_breach():
    assert classify(_last(False, -0.1), True, 0.2, is_baseline=False) == "NEW_BREACH"


def test_classify_resolved():
    assert classify(_last(True, 0.2), False, -0.1, is_baseline=False) == "RESOLVED"


def test_classify_widening():
    assert classify(_last(True, 0.1), True, 0.3, is_baseline=False) == "WIDENING"


def test_classify_improving():
    assert classify(_last(True, 0.3), True, 0.1, is_baseline=False) == "IMPROVING"


def test_classify_known_stable():
    assert classify(_last(True, 0.2), True, 0.2, is_baseline=False) == "KNOWN_STABLE"


def test_surfaced_set_contents():
    assert SURFACED == {"NEW_BREACH", "WIDENING", "IMPROVING", "RESOLVED"}


# --- persistence: history append + idempotency --------------------------

def _store():
    from state.store import StateStore
    return StateStore(os.path.join(tempfile.mkdtemp(), "t.duckdb"))


def _row(item="acme", ts="2026-01-01", value=3.2, **extra):
    base = {"item_id": item, "cycle": 1, "data_ts": ts, "entity": "Acme Corp",
            "covenant_type": "leverage", "metric": "lev", "value": value,
            "threshold": 3.5, "direction": "below", "breached": False,
            "margin": -0.3, "status": "OK",
            "anomaly_significant": False, "anomaly_z": None, "drifting": False,
            "drift_slope": None, "drift_tstat": None, "breach_prob": None,
            "breach_tail": False}
    base.update(extra)
    return base


def test_history_append_and_read():
    s = _store()
    s.write_history(_row(value=3.2))
    hist = s.get_history_series("acme")
    assert [h["value"] for h in hist] == [3.2]
    s.close()


def test_history_idempotent_same_ts():
    """Idempotency: the SAME (item, data_ts) inserted twice must not create a
    phantom second observation."""
    s = _store()
    s.write_history(_row(ts="2026-01-01", value=3.2))
    s.write_history(_row(ts="2026-01-01", value=3.2))   # duplicate
    assert len(s.get_history_series("acme")) == 1
    s.close()


def test_history_distinct_ts_both_kept():
    s = _store()
    s.write_history(_row(ts="2026-01-01", value=3.2))
    s.write_history(_row(ts="2026-02-01", value=3.4))
    assert len(s.get_history_series("acme")) == 2
    s.close()


# --- the cycle atom: cold start + change detection ----------------------

def test_run_cycle_cold_start_then_detect():
    from scheduler.cycle import run_cycle
    db = os.path.join(tempfile.mkdtemp(), "c.duckdb")
    r1 = run_cycle(db_path=db)                 # cycle 1 = baseline
    assert isinstance(r1, dict)
    r2 = run_cycle(db_path=db)                 # cycle 2 = detection begins
    assert isinstance(r2, dict)


# --- triage counting: §14 regression ------------------------------------

def test_triage_widening_counts_as_threshold_breach():
    """§14 REGRESSION: a still-breached covenant classified WIDENING (not
    NEW_BREACH) must still count as a threshold-breach diagnostic. The old
    `"BREACH" in status` test dropped it."""
    from monitoring.triage import recheck_flag

    class FakeStore:
        def get_history_series(self, item_id):
            return [{"value": v} for v in [3.6, 3.7, 3.8, 3.9]]

    flags = {"acme": {"entity": "Acme", "breached": True, "status": "WIDENING",
                      "drifting": False, "direction": "below", "threshold": 3.5,
                      "value": 3.9, "margin": 0.4, "anomaly_significant": False,
                      "breach_tail": False, "_breach_detail": {"toward_breach": True}}}
    r = recheck_flag(FakeStore(), flags, "acme")
    assert "threshold_breach" in r["signals"]


def test_triage_not_breached_no_threshold_signal():
    from monitoring.triage import recheck_flag

    class FakeStore:
        def get_history_series(self, item_id):
            return [{"value": v} for v in [3.0, 3.0, 3.0, 3.0]]

    flags = {"acme": {"entity": "Acme", "breached": False, "status": "OK",
                      "drifting": False, "direction": "below", "threshold": 3.5,
                      "value": 3.0, "margin": -0.5, "anomaly_significant": False,
                      "breach_tail": False, "_breach_detail": {"toward_breach": False}}}
    r = recheck_flag(FakeStore(), flags, "acme")
    assert "threshold_breach" not in r["signals"]
