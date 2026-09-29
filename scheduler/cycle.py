"""
run_cycle() — the atom (spec §3.3 / §3.4).

One pass over the watchlist: for each covenant item, resolve this cycle's value,
run threshold_check, compare to last state, classify, and write both layers of
state. Then produce an exception-based report (surface only what changed).

This is the DETERMINISTIC spine: state read/write + classification + cold-start
baseline + two-cycle baseline->change-detect via `monitor.py --once`. Statistical
checks (anomaly / drift / breach probability), freshness gating, transactional
robustness, the thin scheduler, model triage, and the MCP boundary are all built
and wired around this atom.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import date, timedelta, datetime, timezone

from state.store import StateStore
from state.classify import classify, SURFACED
from tools.covenant_checks import threshold_check
from tools.financial_contract import finite

# The three shared statistical checks: local by default, or over the MCP stdio
# server when AGENT_STATS_VIA_MCP=1. Same functions, same results, two transports
# (proven identical). Mirrors the fixture/live and stub/model switches.
if os.environ.get("AGENT_STATS_VIA_MCP") == "1":
    from mcp_server.client import (
        anomaly_significance_check, drift_check, breach_probability,
    )
else:
    from tools.statistical_checks import (
        anomaly_significance_check, drift_check, breach_probability,
    )

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "covenants.json"


def _load_watchlist():
    with open(_FIXTURE) as f:
        fx = json.load(f)
    base = date.fromisoformat(fx.get("base_date", "2026-01-01"))
    return fx["covenants"], base


def _item_data_ts(cov, cycle_n, base_date):
    """This item's data timestamp for the cycle. An item may carry an explicit
    per-cycle map (e.g. a quarterly covenant re-checked daily); otherwise its data
    advances every cycle."""
    m = cov.get("data_ts_by_cycle")
    if m and str(cycle_n) in m:
        return date.fromisoformat(m[str(cycle_n)])
    return base_date + timedelta(days=cycle_n - 1)


def run_cycle(db_path: str | None = None, asof_cycle: int | None = None,
              watchlist_path=None) -> dict:
    if watchlist_path is None:
        return _run_cycle(db_path, asof_cycle)
    # Replay is served without network access. Provider fetches never hold the DB lock.
    store = StateStore(db_path) if db_path else StateStore()
    try:
        if store.source_mode() not in (None, 'yfinance'):
            raise ValueError('live observations require a separate database')
        if asof_cycle is not None:
            if type(asof_cycle) is not int or asof_cycle < 1:
                raise ValueError('asof_cycle must be a positive integer')
            if asof_cycle < store.next_cycle():
                saved = store.get_run(asof_cycle)
                if saved is None:
                    raise ValueError('cannot replay unavailable cycle')
                return {**saved, 'replayed': True}
    finally:
        store.close()
    from monitoring.live_data import prepare
    today = datetime.now(timezone.utc).date()
    prepared = prepare(watchlist_path, today)
    return _run_cycle(db_path, asof_cycle, prepared, today)


def _run_cycle(db_path=None, asof_cycle=None, live_inputs=None, observed_on=None) -> dict:
    store = StateStore(db_path) if db_path else StateStore()
    try:
        mode = 'yfinance' if live_inputs is not None else 'bundled_fixtures'
        if store.source_mode() not in (None, mode):
            raise ValueError('database data source mismatch; use a separate database')
        if asof_cycle is not None and (type(asof_cycle) is not int or asof_cycle < 1):
            raise ValueError("asof_cycle must be a positive integer")
        next_c = store.next_cycle()
        if asof_cycle is not None and asof_cycle < next_c:
            saved = store.get_run(asof_cycle)
            if saved is None:
                raise ValueError('cycle predates ledger or was skipped; cannot replay unavailable evidence')
            return {**saved, 'replayed': True}
        # Catch-up (skip-to-now): if data has advanced past the next cycle, process
        # the latest directly and record the gap rather than replaying every missed
        # cycle.
        cycle_n = asof_cycle if (asof_cycle and asof_cycle > next_c) else next_c
        gap = max(0, cycle_n - next_c)
        is_baseline = cycle_n == 1
        if live_inputs is None:
            covenants, base_date = _load_watchlist()
            cycle_ts = base_date + timedelta(days=cycle_n - 1)
        else:
            cycle_ts = base_date = observed_on
            covenants = []
            for entry in live_inputs:
                item, obs = entry['item'], entry['observation']
                covenants.append({**item, 'covenant_type': 'analyst_policy',
                    'cycle_values': {str(cycle_n): obs['value']},
                    'data_ts_by_cycle': {str(cycle_n): str(obs.get('data_ts', cycle_ts))},
                    '_evidence': obs['evidence'], '_unavailable_reason': obs.get('reason')})

        # --- COMPUTE phase: read prior state, classify, run stats. No writes yet,
        # so a crash here leaves last-good state untouched. ---
        rows, skipped = [], []
        identities = [c.get('item_id') for c in covenants]
        if any(not isinstance(i, str) or not i.strip() for i in identities) or len(set(identities)) != len(identities):
            raise ValueError('watchlist item IDs must be nonempty and unique')
        for cov in covenants:
            for field in ('entity', 'metric', 'covenant_type'):
                if not isinstance(cov.get(field), str) or not cov[field].strip():
                    raise ValueError('missing watchlist identity: ' + field)
            if not finite(cov.get('threshold')) or cov.get('direction') not in ('below', 'above'):
                raise ValueError('invalid covenant threshold or direction')
            pending = store.pending_review(cov['item_id'])
            if pending:
                skipped.append({'item_id': cov['item_id'], 'entity': cov['entity'],
                                'reason': 'pending_review', 'original_review': pending,
                                'candidate_value': cov.get('cycle_values', {}).get(str(cycle_n))})
                continue
            val = cov.get("cycle_values", {}).get(str(cycle_n))
            if val is None:
                skipped.append({'item_id': cov['item_id'], 'entity': cov['entity'],
                                'reason': cov.get('_unavailable_reason') or 'missing_observation',
                                'evidence': cov.get('_evidence')})
                continue

            item_ts = _item_data_ts(cov, cycle_n, base_date)
            if item_ts > cycle_ts:
                raise ValueError('observation is later than cycle date: ' + cov['item_id'])
            if not finite(val):
                raise ValueError('invalid observation: ' + cov['item_id'])
            last = store.get_current(cov["item_id"])

            # Revisions are quarantined with evidence, never silently overwritten.
            definition = ('entity', 'metric', 'covenant_type', 'threshold', 'direction')
            candidate = {k: cov[k] for k in definition}
            candidate.update(value=val, data_ts=str(item_ts))
            if live_inputs is not None:
                candidate['evidence'] = cov['_evidence']
                prior = store.get_observation_evidence(cov['item_id'], last['data_ts']) if last else None
                if last and (prior or {}).get('_evidence', {}).get('definition_hash') != cov['_evidence']['definition_hash']:
                    skipped.append({'item_id': cov['item_id'], 'entity': cov['entity'],
                        'reason': 'definition_change_requires_review', 'candidate': candidate, 'previous': prior})
                    continue
            if last is not None and any(last[k] != cov[k] for k in definition):
                skipped.append({'item_id': cov['item_id'], 'entity': cov['entity'],
                                'reason': 'definition_change_requires_review', 'candidate': candidate,
                                'previous': {k: last[k] for k in definition}})
                continue
            if last is not None and last.get('data_ts') is not None and item_ts <= last['data_ts']:
                previous = store.get_observation(cov['item_id'], item_ts)
                identical = previous is not None and previous['value'] == val
                skipped.append({'item_id': cov['item_id'], 'entity': cov['entity'],
                                'reason': 'duplicate_observation' if identical else 'correction_requires_review',
                                'candidate': candidate,
                                'previous_value': previous['value'] if previous else None})
                continue

            chk = threshold_check(val, cov["threshold"], cov["direction"])
            if chk.get("error"):
                raise ValueError(chk["error"])
            status = classify(last, chk["breached"], chk["margin"], is_baseline)

            history = store.get_history_series(cov['item_id'])
            series = [r['value'] for r in history] + [val]
            dates = [r['data_ts'] for r in history] + [item_ts]
            if any(d is None for d in dates):
                raise ValueError('history lacks observation dates')
            times = [(d - dates[0]).days for d in dates]
            if any(b <= a for a, b in zip(times, times[1:])):
                raise ValueError('observation dates must increase')
            anom = anomaly_significance_check(series)
            drift = drift_check(times, series,
                                threshold=cov['threshold'], direction=cov['direction'])
            drift['time_unit'] = 'days'
            gaps = [b - a for a, b in zip(times, times[1:])]
            if len(set(gaps)) > 1:
                breach = {'breach_probability': None, 'tail_flag': None,
                          'reason': 'irregular observation intervals; probability unavailable'}
            else:
                breach = breach_probability(series, cov['threshold'], cov['direction'])
                breach['observation_interval_days'] = gaps[0] if gaps else None
                breach['horizon_days'] = (gaps[0] * breach['horizon_cycles']
                                          if gaps and 'horizon_cycles' in breach else None)
            for diagnostic in (anom, drift, breach):
                if diagnostic.get('error'):
                    raise ValueError('statistical calculation unavailable: ' + diagnostic['error'])

            rows.append({
                "item_id": cov["item_id"], "cycle": cycle_n, "data_ts": item_ts,
                "entity": cov["entity"], "covenant_type": cov["covenant_type"],
                "metric": cov["metric"], "value": val, "threshold": cov["threshold"],
                "direction": cov["direction"], "breached": chk["breached"],
                "margin": chk["margin"], "status": status,
                "anomaly_significant": anom.get("significant"),
                "anomaly_z": anom.get("modified_z"),
                "drifting": drift.get("drifting"),
                "drift_slope": drift.get("slope"),
                "drift_tstat": drift.get("slope_tstat"),
                "breach_prob": breach.get("breach_probability"),
                "breach_tail": breach.get("tail_flag"),
                "_anomaly_detail": anom,
                "_drift_detail": drift,
                "_breach_detail": breach,
                **({"_evidence": cov["_evidence"], "data_mode": mode} if live_inputs is not None else {}),
            })

        # Render and serialize BEFORE committing so report failures cannot advance state.
        report = _build_report(cycle_n, cycle_ts, is_baseline, rows, skipped, gap)
        if live_inputs is not None:
            report = ('Data: live yfinance annual statements; thresholds: analyst policies, not contractual covenants.\n'
                      'Observation dates are statement periods, not publication or retrieval dates.\n' + report)
            report += '\n' + '\n'.join(f"Period {r['data_ts']}: {r['item_id']}" for r in rows)
        surfaced = [] if is_baseline else [r for r in rows if _surfaces(r)]
        review = any(s['reason'] in ('correction_requires_review', 'definition_change_requires_review', 'pending_review') for s in skipped)
        if live_inputs is not None and any(s['reason'] != 'duplicate_observation' for s in skipped):
            review = True
        status = 'review_required' if review else ('processed' if rows else 'no_new_observations')
        result = {'cycle': cycle_n, 'data_ts': str(cycle_ts), 'baseline': is_baseline,
                  'status': status, 'gap': gap, 'skipped': skipped, 'rows': rows,
                  'surfaced': surfaced, 'report': report, 'replayed': False, 'data_mode': mode}
        if live_inputs is not None:
            result['observation_attempts'] = live_inputs
        from state.store import _json_date
        result = json.loads(json.dumps(result, default=_json_date, allow_nan=False))
        with store.transaction():
            store.bind_source(mode)
            for row in rows:
                store.write_history(row)
                store.upsert_current(row)
            for item in skipped:
                if item['reason'] in ('correction_requires_review', 'definition_change_requires_review'):
                    store.write_review(item, cycle_n)
            store.write_run(result)
        return result

    finally:
        store.close()


def _stat_tags(r) -> list[str]:
    """Statistical annotations for an item this cycle."""
    tags = []
    if r.get("anomaly_significant"):
        tags.append(f"ANOMALY(z={r['anomaly_z']})")
    b = r.get("_breach_detail", {})
    toward = bool(r.get("_drift_detail", {}).get("toward_breach"))
    # Only annotate drift when it's heading toward breach — a trend toward safety
    # is not a warning.
    if r.get("drifting") and toward:
        d = r.get("_drift_detail", {})
        ctb = d.get("cycles_to_breach_at_current_drift")
        proj = f", ~{ctb} days to boundary" if ctb is not None else ""
        tags.append(f"DRIFT(slope={r['drift_slope']}, t={r['drift_tstat']}{proj})")
    if b.get("tail_flag"):
        tags.append(f"BREACH_PROB({r['breach_prob']} within {b.get('horizon_days')} days)")
    return tags


def _surfaces(r) -> bool:
    """Surface changes, anomalies, adverse drift, or high crossing probability."""
    if r["status"] in SURFACED:
        return True
    if r.get("anomaly_significant"):
        return True
    b = r.get("_breach_detail", {})
    toward = bool(r.get("_drift_detail", {}).get("toward_breach"))
    return (toward and bool(r.get("drifting"))) or bool(b.get("tail_flag"))


def _build_report(cycle_n, data_ts, is_baseline, rows, skipped=None, gap=0) -> str:
    """Exception-based report: threshold changes AND statistical signals, plus
    freshness-skip and catch-up-gap notices."""
    skipped = skipped or []
    lines = [f"===== MONITORING CYCLE {cycle_n}  (data {data_ts}) ====="]

    if gap > 0:
        lines.append(f"CATCH-UP: {gap} cycle(s) missed before this run — flagged "
                     f"changes may have originated during the gap, not just now.")

    if skipped:
        lines.append('Observation coverage: ' + '; '.join(s['item_id'] + ': ' + s['reason'] for s in skipped))
    if not rows:
        lines.append('NO NEW OBSERVATIONS — compliance was not reassessed; prior state is retained.')
        return '\n'.join(lines)
    if is_baseline:
        lines.append(f"BASELINE CYCLE — established state for {len(rows)} item(s). "
                     f"Classification and alerting suppressed. Detection begins next cycle.")
        for r in rows:
            state = "breached" if r["breached"] else "ok"
            lines.append(f"  · {r['item_id']} ({r['entity']}): {r['metric']} "
                         f"{r['value']} vs {r['threshold']} [{state}]")
        if skipped:
            lines.append(f"Coverage: skipped {len(skipped)} item(s); see reasons above.")
        return "\n".join(lines)

    surfaced = [r for r in rows if _surfaces(r)]
    suppressed = [r for r in rows if not _surfaces(r)]

    if not surfaced:
        lines.append("No newly surfaced exceptions among the observations assessed; prior breaches may remain active.")
    else:
        lines.append(f"EXCEPTIONS ({len(surfaced)}):")
        order = {"NEW_BREACH": 0, "WIDENING": 1, "RESOLVED": 2, "IMPROVING": 3}
        # threshold-OK-but-flagged items sort after real status changes
        for r in sorted(surfaced, key=lambda x: order.get(x["status"], 8)):
            tags = _stat_tags(r)
            if r.get("_breach_detail", {}).get("reason"):
                tags.append("PROBABILITY_UNAVAILABLE: " + r["_breach_detail"]["reason"])
            tagstr = ("  " + " ".join(tags)) if tags else ""
            label = r["status"]
            if label not in SURFACED and tags:
                label = "EARLY_WARNING"  # threshold OK, but statistics flag it
            lines.append(f"  [{label}] {r['item_id']} ({r['entity']}): "
                         f"{r['metric']} = {r['value']} vs {r['threshold']} "
                         f"({r['direction']}), margin {r['margin']:+.3f}{tagstr}")

    unavailable = [r['item_id'] for r in rows if r.get('_breach_detail', {}).get('reason')]
    if unavailable:
        lines.append('Probability unavailable (insufficient or irregular observations): ' + ', '.join(unavailable))
    lines.append(f"Suppressed (quiet: no change, no drift, no anomaly): {len(suppressed)}")
    if skipped:
        lines.append(f"Coverage: skipped {len(skipped)} item(s); see reasons above "
                     f"({', '.join(s['item_id'] for s in skipped)}).")
    return "\n".join(lines)
