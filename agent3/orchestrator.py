"""
Agent 3 orchestrator + output composer (the assembly).

Ties the proven parts into a runnable agent:
  assemble events (Track A) -> run_event_study (via MCP) -> scenario ->
  validation gate -> record outcome to the catalyst store -> compose a report.

Two output modes (spec §Agent 3, output composer), mirroring Agent 2's
exception-report + full-state split:
  - per-entity BRIEF : one event type in depth — the study, the scenario, the
                       gate verdict, the contributing/excluded peers.
  - cross-entity SCAN: several event types at a glance — CAAR, significance,
                       verdict per type — the "what's moving / what's clean" view.

Governing ethos holds: every number is from a deterministic tool; this module
orchestrates and composes, it does not compute. The model's role (materiality /
escalation narration) is a thin layer on top and is kept optional so the agent
runs fully offline on fixtures.

Event study is called through the MCP client by default (Agent 3 is born a
client); a local fallback keeps offline dev fast.
"""

from __future__ import annotations

import os

from agent3.track_a import load_event_set
from agent3.scenario import scenario_from_event_study
from agent3.validation import assess


def _event_study_fn():
    """Prefer the MCP-served event study (Agent 3 as client); fall back to local."""
    if os.environ.get("AGENT_STATS_VIA_MCP") == "1":
        from mcp_server.client import run_event_study
        return run_event_study
    from tools.event_study import run_event_study
    return run_event_study


def analyze_event_type(event_type: str, *, source: str = "fixture",
                       ticker: str | None = None, peers: list[str] | None = None,
                       n_event_types_tested: int = 1, store=None,
                       live_propose: bool = False) -> dict:
    """
    Run the full Track-A chain for one event type and return a structured result:
    study + scenario + gate verdict + peer accounting. Records the outcome to the
    catalyst store when one is supplied. This is the ONE rigorous path — the live
    CLI routes through it so a live run gets validation, placebo, gate-aware
    scenario, and persistence (not a lighter parallel path).
    """
    es = load_event_set(event_type, source=source, ticker=ticker, peers=peers,
                        live_propose=live_propose)
    if es.get("verdict") == "REFUSED":
        return {"event_type": event_type, "stage": "assembly",
                "verdict": "REFUSED", "reason": es.get("reason"),
                "contributing_peers": es.get("contributing_peers", []),
                "excluded_peers": es.get("excluded_peers", []),
                "per_peer_report": es.get("per_peer_report", []),
                "pinned_peer_set": es.get("pinned_peer_set", {})}

    run_event_study = _event_study_fn()
    study = run_event_study(es["events"], event_type, es.get("placebo_events"))

    contributing = es.get("contributing_peers")
    n_peers = len(contributing) if contributing is not None else None
    gate = assess(study, contributing_peers=n_peers,
                  n_event_types_tested=n_event_types_tested)
    scen = scenario_from_event_study(study)

    # §23: a scenario must not publish as CALIBRATED when the validation gate held
    # the study for review (significant placebo, confound, multiple-testing, etc.).
    # The distribution is still computed for diagnostics, but its PUBLICATION STATE
    # inherits the gate verdict.
    if gate.get("verdict") == "HOLD_FOR_REVIEW" and scen.get("verdict") == "CALIBRATED":
        scen["publication_state"] = "HELD_FOR_REVIEW"
        scen["held_reason"] = "validation gate held the underlying study for review"
    else:
        scen["publication_state"] = scen.get("verdict")

    result = {
        "event_type": event_type,
        "study": study,
        "scenario": scen,
        "gate": gate,
        "contributing_peers": contributing or [],
        "excluded_peers": es.get("excluded_peers", []),
        "pinned_peers": es.get("pinned_peers", []),
        "pinned_peer_set": es.get("pinned_peer_set", {}),
        "per_peer_report": es.get("per_peer_report", []),
    }

    if store is not None:
        # §28: content-addressed run_id so a rerun with the same N doesn't collide
        # and get silently dropped by ON CONFLICT DO NOTHING.
        import hashlib, json as _json, datetime as _dt
        payload = _json.dumps({
            "event_type": event_type,
            "source": es.get("source", "fixture"),
            "pinned_peers": es.get("pinned_peers"),
            "event_dates": sorted(e.get("event_date") for e in es.get("events", [])),
            "n_events": study.get("n_events"),
            "run_ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }, sort_keys=True, default=str)
        run_id = f"{event_type}:{hashlib.sha256(payload.encode()).hexdigest()[:16]}"
        store.record_outcome(run_id, study, gate, es.get("pinned_peers"))

    return result


# --- output mode 1: per-entity brief -----------------------------------------

def render_brief(result: dict) -> str:
    et = result["event_type"]
    if result.get("verdict") == "REFUSED":
        return (f"EVENT-STUDY BRIEF — {et}\n"
                f"  REFUSED at assembly: {result.get('reason')}\n"
                f"  excluded peers: {result.get('excluded_peers')}")

    s, scen, gate = result["study"], result["scenario"], result["gate"]
    lines = [f"EVENT-STUDY BRIEF — {et}", ""]
    lines.append(f"  Peers used     : {result['contributing_peers']}")
    if result["excluded_peers"]:
        lines.append(f"  Peers excluded : {result['excluded_peers']} (unusable data)")
    lines.append(f"  Events (N)     : {s.get('n_events')}")
    lines.append(f"  CAAR           : {s.get('caar'):+.4f}  "
                 f"(t={s.get('t_stat')}, significant={s.get('caar_significant')})")
    if s.get("placebo"):
        lines.append(f"  Placebo        : {s['placebo'].get('interpretation')}")
    lines.append("")
    lines.append(f"  Gate           : {gate['verdict']} (confidence {gate['confidence']})")
    for c in gate["checks"]:
        mark = {"pass": "ok", "warn": "!!", "fail": "XX"}[c["status"]]
        lines.append(f"    [{mark}] {c['check']}: {c['detail']}")
    lines.append("")
    lines.append(f"  Scenario       : {scen['verdict']} ({scen.get('confidence')})")
    if scen.get("distribution"):
        d = scen["distribution"]
        lines.append(f"    next comparable catalyst: p25={d['p25']:+.4f} "
                     f"median={d['median_car']:+.4f} p75={d['p75']:+.4f} "
                     f"| P(pos)={d['prob_positive']}")
    lines.append(f"    {scen.get('headline','')}")
    return "\n".join(lines)


# --- output mode 2: cross-entity scan ----------------------------------------

def render_scan(results: list[dict]) -> str:
    lines = ["CROSS-ENTITY SCAN", "",
             f"  {'event_type':<22} {'N':>4} {'CAAR':>9} {'sig':>5} {'gate':<16} scenario",
             f"  {'-'*22} {'-'*4} {'-'*9} {'-'*5} {'-'*16} {'-'*10}"]
    for r in results:
        et = r["event_type"]
        if r.get("verdict") == "REFUSED":
            lines.append(f"  {et:<22} {'--':>4} {'REFUSED':>9} {'--':>5} {'assembly':<16} --")
            continue
        s, gate, scen = r["study"], r["gate"], r["scenario"]
        caar = f"{s.get('caar'):+.4f}" if s.get("caar") is not None else "--"
        sig = "yes" if s.get("caar_significant") else "no"
        lines.append(f"  {et:<22} {s.get('n_events'):>4} {caar:>9} {sig:>5} "
                     f"{gate['verdict']:<16} {scen['verdict']}")
    return "\n".join(lines)
