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
    """Use the explicitly selected transport; never fall back after an MCP error."""
    if os.environ.get("AGENT_STATS_VIA_MCP") == "1":
        from mcp_server.client import run_event_study
        return run_event_study
    from tools.event_study import run_event_study
    return run_event_study


def analyze_event_type(event_type: str, *, source: str = "fixture",
                       ticker: str | None = None, peers: list[str] | None = None,
                       n_event_types_tested: int = 1, store=None,
                       live_propose: bool = False, study_plan: dict | None = None, checkpoint=None, peer_decision=None) -> dict:
    """
    Run the full Track-A chain for one event type and return a structured result:
    study + scenario + gate verdict + peer accounting. Records the outcome to the
    catalyst store when one is supplied. This is the ONE rigorous path — the live
    CLI routes through it so a live run gets validation, placebo, gate-aware
    scenario, and persistence (not a lighter parallel path).
    """
    if not isinstance(event_type, str) or not event_type.strip() or len(event_type) > 200:
        raise ValueError('event_type must be nonempty text of at most 200 characters')
    if checkpoint:
        checkpoint('assembly', {})
    es = load_event_set(event_type, source=source, ticker=ticker, peers=peers,
                        live_propose=live_propose, study_plan=study_plan, checkpoint=checkpoint, peer_decision=peer_decision)
    if es.get("verdict") == "REFUSED":
        reports = es.get('per_peer_report', [])
        unavailable = bool(reports) and all(r.get('error') for r in reports)
        return {"event_type": event_type, "stage": "assembly",
                "verdict": "UNAVAILABLE" if unavailable else "REFUSED",
                "status": "unavailable" if unavailable else "refused", "reason": es.get("reason"),
                "contributing_peers": es.get("contributing_peers", []),
                "excluded_peers": es.get("excluded_peers", []),
                "per_peer_report": es.get("per_peer_report", []),
                "pinned_peer_set": es.get("pinned_peer_set", {})}

    if checkpoint:
        checkpoint('calculation', {})
    run_event_study = _event_study_fn()
    study = run_event_study(es["events"], event_type, es.get("placebo_events"))

    if not isinstance(study, dict) or study.get('error'):
        return {'event_type': event_type, 'status': 'unavailable', 'verdict': 'UNAVAILABLE',
                'stage': 'calculation', 'reason': 'event_study_unavailable',
                'pinned_peer_set': es.get('pinned_peer_set', {}),
                'per_peer_report': es.get('per_peer_report', [])}
    if checkpoint:
        checkpoint('validation', {})
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
        "status": "completed" if gate["verdict"] == "PASS" else "held",
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

    if checkpoint:
        checkpoint('result', {'result': result})
    if store is not None:
        if checkpoint:
            checkpoint('persistence', {})
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


def publication_allowed(result):
    """Render only known eligible historical states; stale/unknown shapes fail closed."""
    from tools.event_contracts import finite
    if not isinstance(result, dict) or result.get('status') not in (None, 'completed'):
        return False
    gate, study, scen = (result.get(k) for k in ('gate', 'study', 'scenario'))
    if not all(isinstance(x, dict) for x in (gate, study, scen)):
        return False
    checks = gate.get('checks')
    if gate.get('verdict') != 'PASS' or not isinstance(checks, list) or not checks or any(
            not isinstance(c, dict) or c.get('status') != 'pass' for c in checks):
        return False
    if study.get('inference_status') != 'available' or type(study.get('caar_significant')) is not bool:
        return False
    if not finite(study.get('caar')) or not finite(study.get('p_value')) or not 0 <= study['p_value'] <= 1:
        return False
    expected = 'HISTORICAL' if study['caar_significant'] else 'NULL'
    if scen.get('verdict') != expected or scen.get('publication_state') != expected:
        return False
    # Do not trust a saved PASS label independently of its retained evidence.
    reports = result.get('per_peer_report', [])
    if not isinstance(reports, list) or any(not isinstance(r, dict) for r in reports):
        return False
    issues = [r for r in reports if r.get('excluded') or r.get('error') or r.get('rejected_events')]
    try:
        reviewed = assess(study, contributing_peers=len(result.get('contributing_peers', [])),
                          study_plan=result.get('study_plan'),
                          comparability_status=result.get('comparability_status', 'unverified'),
                          assembly_issues=issues)
    except (ValueError, TypeError, KeyError, AttributeError):
        return False
    if reviewed['verdict'] != 'PASS':
        return False
    dist = scen.get('distribution')
    return isinstance(dist, dict) and all(finite(dist.get(k)) for k in ('p25', 'median_car', 'p75'))


def render_brief(result: dict) -> str:
    from tools.event_contracts import finite
    et = result.get('event_type', 'unspecified')
    header = f'EVENT-STUDY BRIEF — {et}'
    if result.get('status') in ('refused', 'unavailable', 'failed') or result.get('verdict') == 'REFUSED':
        return f"{header}\n{result.get('status', 'refused').upper()}: {result.get('reason', 'unavailable')}"
    s, scen, gate = (result.get(k) if isinstance(result.get(k), dict) else {} for k in ('study', 'scenario', 'gate'))
    caar = f"{s['caar']:+.4%}" if finite(s.get('caar')) else 'unavailable'
    allowed = publication_allowed(result)
    lines = [header,
             f"  Peers used: {result.get('contributing_peers', [])}",
             f"  Peers excluded: {result.get('excluded_peers', [])}",
             f"  Historical events: {s.get('n_events', 0)}; issuers: {s.get('n_issuers', 0)}",
             f"  Historical mean CAR: {caar} (equal weight per event)",
             f"  Diagnostic inference: {s.get('inference_status', 'unavailable')}; p={s.get('p_value')}",
             f"  Gate: {gate.get('verdict', 'UNAVAILABLE')}"]
    checks = gate.get('checks')
    for c in checks if isinstance(checks, list) else []:
        if not isinstance(c, dict):
            continue
        lines.append(f"    [{c.get('status', 'unknown')}] {c.get('check')}: {c.get('detail')}")
    reports = result.get('per_peer_report')
    for r in reports if isinstance(reports, list) else []:
        if not isinstance(r, dict):
            continue
        lines.append(f"  Assembly {r.get('ticker')}: {r.get('assembled', 0)} events; "
                     f"{r.get('reason', r.get('error', ''))}; rejected={r.get('rejected_events', [])}")
    lines.append(f"  Publication: {scen['publication_state']}" if allowed else
                 '  Publication: HELD_FOR_REVIEW — descriptive diagnostics only')
    if allowed:
        d = scen['distribution']
        lines.append(f"  Historical quantiles: p25={d['p25']:+.4%}; median={d['median_car']:+.4%}; p75={d['p75']:+.4%}")
    lines.append('  No forward predictive calibration is claimed.')
    return '\n'.join(lines)


def render_scan(results: list[dict]) -> str:
    lines = ['CROSS-ENTITY HISTORICAL SCAN']
    for r in results:
        et = r.get('event_type', 'unspecified')
        if r.get('status') in ('refused', 'unavailable', 'failed') or r.get('verdict') == 'REFUSED':
            lines.append(f"{et}: {r.get('status', 'refused').upper()}")
            continue
        allowed = publication_allowed(r)
        s = r.get('study') if isinstance(r.get('study'), dict) else {}
        status = r['scenario']['publication_state'] if allowed else 'HELD_FOR_REVIEW'
        sig = s.get('caar_significant') if allowed else None
        lines.append(f"{et}: N={s.get('n_events', 0)}; significance={'unavailable' if sig is None else sig}; {status}")
    return '\n'.join(lines)
