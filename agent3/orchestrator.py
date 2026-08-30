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
                       n_event_types_tested: int = 1, store=None) -> dict:
    """
    Run the full Track-A chain for one event type and return a structured result:
    study + scenario + gate verdict + peer accounting. Records the outcome to the
    catalyst store when one is supplied.
    """
    es = load_event_set(event_type, source=source, ticker=ticker, peers=peers)
    if es.get("verdict") == "REFUSED":
        return {"event_type": event_type, "stage": "assembly",
                "verdict": "REFUSED", "reason": es.get("reason"),
                "contributing_peers": es.get("contributing_peers", []),
                "excluded_peers": es.get("excluded_peers", [])}

    run_event_study = _event_study_fn()
    study = run_event_study(es["events"], event_type, es.get("placebo_events"))

    contributing = es.get("contributing_peers")
    n_peers = len(contributing) if contributing is not None else None
    gate = assess(study, contributing_peers=n_peers,
                  n_event_types_tested=n_event_types_tested)
    scen = scenario_from_event_study(study)

    result = {
        "event_type": event_type,
        "study": study,
        "scenario": scen,
        "gate": gate,
        "contributing_peers": contributing or [],
        "excluded_peers": es.get("excluded_peers", []),
        "pinned_peers": es.get("pinned_peers", []),
    }

    if store is not None:
        run_id = f"{event_type}:{es.get('source','fixture')}:{study.get('n_events')}"
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
