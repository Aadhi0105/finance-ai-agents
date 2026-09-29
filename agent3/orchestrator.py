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

Event study is local by default; AGENT_STATS_VIA_MCP=1 selects MCP.
Results are historical; the publication gate never certifies forward prediction.
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
                       live_propose: bool = False, study_plan: dict | None = None) -> dict:
    """
    Run the full Track-A chain for one event type and return a structured result:
    study + scenario + gate verdict + peer accounting. Records the outcome to the
    catalyst store when one is supplied. This is the ONE rigorous path — the live
    CLI routes through it so a live run gets validation, placebo, gate-aware
    scenario, and persistence (not a lighter parallel path).
    """
    es = load_event_set(event_type, source=source, ticker=ticker, peers=peers,
                        live_propose=live_propose, study_plan=study_plan)
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
    assembly_issues = [r for r in es.get("per_peer_report", [])
                       if r.get("excluded") or r.get("error") or r.get("rejected_events")]
    gate = assess(study, contributing_peers=n_peers,
                  n_event_types_tested=n_event_types_tested,
                  study_plan=es.get("study_plan"),
                  comparability_status=es.get("comparability_status", "unverified"),
                  assembly_issues=assembly_issues)
    scen = scenario_from_event_study(study)

    if gate["verdict"] != "PASS":
        scen["publication_state"] = "HELD_FOR_REVIEW"
        scen["diagnostic_distribution"] = scen.pop("distribution", None)
        scen["distribution"] = None
        scen["verdict"] = "HELD_FOR_REVIEW"
        scen["headline"] = "Historical diagnostics are held for review; no forward scenario is published."
    else:
        scen["publication_state"] = scen["verdict"]

    result = {
        "event_type": event_type,
        "study": study,
        "study_plan": es.get("study_plan"),
        "event_class": es.get("event_class", "earnings"),
        "comparability_status": es.get("comparability_status", "unverified"),
        "target_contributed": es.get("target_contributed"),
        "scenario": scen,
        "gate": gate,
        "contributing_peers": contributing or [],
        "excluded_peers": es.get("excluded_peers", []),
        "pinned_peers": es.get("pinned_peers", []),
        "pinned_peer_set": es.get("pinned_peer_set", {}),
        "per_peer_report": es.get("per_peer_report", []),
    }

    if store is not None:
        # Unique attempt identity. Complete replay bundles are a later batch.
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
        return f"EVENT-STUDY BRIEF — {et}\nREFUSED: {result.get('reason')}"
    s, scen, gate = result["study"], result["scenario"], result["gate"]
    caar = f"{s['caar']:+.4%}" if isinstance(s.get('caar'), (int,float)) else "unavailable"
    held = gate.get("verdict") != "PASS" or scen.get("publication_state") == "HELD_FOR_REVIEW"
    lines = [f"EVENT-STUDY BRIEF — {et}",
             f"  Peers used: {result.get('contributing_peers', [])}",
             f"  Peers excluded: {result.get('excluded_peers', [])}",
             f"  Historical events: {s.get('n_events', 0)}; issuers: {s.get('n_issuers', 0)}",
             f"  Historical mean CAR: {caar} (equal weight per event)",
             f"  Inference: {s.get('inference_status', 'unavailable')}; p={s.get('p_value')}",
             f"  Gate: {gate['verdict']}"]
    for c in gate["checks"]:
        lines.append(f"    [{c['status']}] {c['check']}: {c['detail']}")
    for r in result.get('per_peer_report',[]):
        lines.append(f"  Assembly {r['ticker']}: {r.get('assembled',0)} events; "
                     f"{r.get('reason', r.get('error', ''))}; rejected={r.get('rejected_events',[])}")
    lines.append("  Publication: HELD_FOR_REVIEW — descriptive diagnostics only" if held else
                 f"  Publication: {scen.get('publication_state', 'UNDETERMINED')}")
    if not held and scen.get('distribution'):
        d = scen['distribution']
        lines.append(f"  Historical quantiles: p25={d['p25']:+.4%}; median={d['median_car']:+.4%}; p75={d['p75']:+.4%}")
    lines.append("  No forward predictive calibration is claimed.")
    return "\n".join(lines)


def render_scan(results: list[dict]) -> str:
    lines = ["CROSS-ENTITY HISTORICAL SCAN"]
    for r in results:
        if r.get("verdict") == "REFUSED":
            lines.append(f"{r['event_type']}: REFUSED")
            continue
        held = r['gate'].get('verdict') != 'PASS' or r['scenario'].get('publication_state') == 'HELD_FOR_REVIEW'
        status = 'HELD_FOR_REVIEW' if held else r['scenario'].get('publication_state', 'UNDETERMINED')
        sig = r['study'].get('caar_significant')
        lines.append(f"{r['event_type']}: N={r['study'].get('n_events',0)}; "
                     f"significance={'unavailable' if sig is None else sig}; {status}")
    return "\n".join(lines)
