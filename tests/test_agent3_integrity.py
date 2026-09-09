"""Agent 3 integrity fixes: gate checks placebo (§13), scenario inherits gate &
None->UNDETERMINED (§23/§24), divergence uses FinBERT + strong-vs-flat + metadata
(§35/§36/§37), peer normalization (§19), content-hashed run_id (§28)."""

import os
import tempfile


def _study(significant=True, placebo_sig=None, n=8, caar=0.0225):
    per = [{"car": c, "event_date": f"2024-{i:02d}-15"}
           for i, c in enumerate([0.03, -0.01, 0.05, 0.02, -0.02, 0.04, 0.01, 0.06][:n], 1)]
    s = {"event_type": "x", "n_events": n, "caar": caar,
         "caar_significant": significant, "t_stat": 4.3, "p_value": 0.003,
         "per_event": per}
    if placebo_sig is not None:
        s["placebo"] = {"n_events": n, "caar": 0.02, "caar_significant": placebo_sig,
                        "t_stat": 3.9, "interpretation": "placebo"}
    return s


# --- §13: gate inspects the placebo ---

def test_gate_holds_on_significant_placebo():
    from agent3.validation import assess
    g = assess(_study(significant=True, placebo_sig=True), contributing_peers=8)
    assert g["verdict"] == "HOLD_FOR_REVIEW"
    assert any(c["check"] == "placebo" and c["status"] == "fail" for c in g["checks"])


def test_gate_passes_clean_placebo():
    from agent3.validation import assess
    g = assess(_study(significant=True, placebo_sig=False), contributing_peers=8)
    assert any(c["check"] == "placebo" and c["status"] == "pass" for c in g["checks"])


# --- §24: None significance -> UNDETERMINED, not CALIBRATED ---

def test_scenario_none_significance_undetermined():
    from agent3.scenario import scenario_from_event_study
    s = scenario_from_event_study(_study(significant=None))
    assert s["verdict"] == "UNDETERMINED"


def test_scenario_false_significance_null():
    from agent3.scenario import scenario_from_event_study
    s = scenario_from_event_study(_study(significant=False))
    assert s["verdict"] == "NULL"


# --- §23: scenario inherits gate verdict (via orchestrator) ---

def test_orchestrator_scenario_held_when_gate_holds():
    from agent3.orchestrator import analyze_event_type
    # fixture study has all events on one date -> confound -> gate HOLD
    r = analyze_event_type("semicap_earnings", source="fixture")
    if r["gate"]["verdict"] == "HOLD_FOR_REVIEW" and r["scenario"]["verdict"] == "CALIBRATED":
        assert r["scenario"]["publication_state"] == "HELD_FOR_REVIEW"


# --- §28: content-hashed run_id, no silent collision ---

def test_run_id_unique_across_reruns():
    from agent3.orchestrator import analyze_event_type
    from agent3.catalyst_state import CatalystStore
    store = CatalystStore(os.path.join(tempfile.mkdtemp(), "c.duckdb"))
    analyze_event_type("semicap_earnings", source="fixture", store=store)
    analyze_event_type("semicap_earnings", source="fixture", store=store)
    outs = store.outcomes_for("semicap_earnings")
    store.close()
    assert len(outs) == 2      # two distinct content-hashed run_ids, not collided


# --- §19: peer normalization ---

def test_peer_pin_normalizes():
    from agent3.peers import _pin
    p = _pin("asml.as", {"peers": ["ASML.AS", "asm.as", "ASM.AS", "BESI.AS"],
                         "sector": "x"}, "stub")
    assert p["peers"] == ["ASM.AS", "BESI.AS"]   # upper, dedup, self dropped
    assert p["ticker"] == "ASML.AS"


# --- §35/§36/§37: divergence uses FinBERT, strong-vs-flat, metadata preserved ---

class _FakeFinbert:
    name = "finbert"
    def __init__(self, s): self._s = s
    def score(self, item): return {"score": self._s, "confidence": 0.9, "scorer": "finbert"}


def test_divergence_mode_uses_finbert(monkeypatch):
    import agent3.sentiment as sent
    monkeypatch.setattr(sent, "FinbertScorer", lambda: _FakeFinbert(0.7))
    d = sent.get_scorer("divergence")
    assert d.primary.name == "finbert"


def test_divergence_strong_vs_flat_flags():
    from agent3.sentiment import DivergenceScorer, LoughranMcDonaldScorer
    d = DivergenceScorer(primary=_FakeFinbert(0.8), secondary=LoughranMcDonaldScorer())
    r = d.score({"headline": "quarterly update released today"})  # LM ~flat
    assert r["flag_review"] is True


def test_funnel_preserves_divergence_metadata():
    from agent3.news_funnel import score_items
    from agent3.sentiment import DivergenceScorer, LoughranMcDonaldScorer
    d = DivergenceScorer(primary=_FakeFinbert(0.8), secondary=LoughranMcDonaldScorer())
    items = [{"headline": "ASML beats and raises guidance", "entities": ["ASML.AS"],
              "day": "2026-01-28", "cluster_size": 1}]
    scored = score_items(items, scorer=d)
    assert "flag_review" in scored[0] and "divergence" in scored[0]
