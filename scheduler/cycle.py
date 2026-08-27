"""
run_cycle() — the atom (spec §3.3 / §3.4).

One pass over the watchlist: for each covenant item, resolve this cycle's value,
run threshold_check, compare to last state, classify, and write both layers of
state. Then produce an exception-based report (surface only what changed).

This checkpoint proves the DETERMINISTIC spine: state read/write + classification
+ cold-start baseline + a two-cycle baseline->change-detect via `monitor.py
--once`. The model triage, statistical checks, freshness/robustness, scheduler,
and MCP are later checkpoints and are intentionally absent here.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

from state.store import StateStore
from state.classify import classify, SURFACED
from tools.covenant_checks import threshold_check

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

_FIXTURE = os.path.join("fixtures", "covenants.json")


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


def run_cycle(db_path: str | None = None, asof_cycle: int | None = None) -> dict:
    store = StateStore(db_path) if db_path else StateStore()
    try:
        next_c = store.next_cycle()
        # Catch-up (skip-to-now): if data has advanced past the next cycle, process
        # the latest directly and record the gap rather than replaying every missed
        # cycle.
        cycle_n = asof_cycle if (asof_cycle and asof_cycle > next_c) else next_c
        gap = max(0, cycle_n - next_c)
        is_baseline = cycle_n == 1
        covenants, base_date = _load_watchlist()
        cycle_ts = base_date + timedelta(days=cycle_n - 1)

        # --- COMPUTE phase: read prior state, classify, run stats. No writes yet,
        # so a crash here leaves last-good state untouched. ---
        rows, skipped = [], []
        for cov in covenants:
            val = cov.get("cycle_values", {}).get(str(cycle_n))
            if val is None:
                continue  # no value defined this cycle

            item_ts = _item_data_ts(cov, cycle_n, base_date)
            last = store.get_current(cov["item_id"])

            # Freshness gate: skip if this item's data has not advanced since last
            # processed (e.g. quarterly data on a daily cadence).
            if last is not None and last.get("data_ts") is not None and item_ts <= last["data_ts"]:
                skipped.append({"item_id": cov["item_id"], "entity": cov["entity"],
                                "reason": f"no new data (still {item_ts})"})
                continue

            chk = threshold_check(val, cov["threshold"], cov["direction"])
            status = classify(last, chk["breached"], chk["margin"], is_baseline)

            prior = [r["value"] for r in store.get_history_series(cov["item_id"])]
            series = prior + [val]
            times = list(range(1, len(series) + 1))
            anom = anomaly_significance_check(series)
            drift = drift_check(times, series,
                                threshold=cov["threshold"], direction=cov["direction"])
            breach = breach_probability(series, cov["threshold"], cov["direction"])

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
                "_drift_detail": drift,
                "_breach_detail": breach,
            })

        # --- WRITE phase: one transaction, all-or-nothing. ---
        with store.transaction():
            for row in rows:
                clean = {k: v for k, v in row.items() if not k.startswith("_")}
                store.write_history(clean)
                store.upsert_current(clean)

        report = _build_report(cycle_n, cycle_ts, is_baseline, rows, skipped, gap)
        surfaced = [] if is_baseline else [r for r in rows if _surfaces(r)]
        return {"cycle": cycle_n, "data_ts": str(cycle_ts), "baseline": is_baseline,
                "gap": gap, "skipped": skipped, "rows": rows, "surfaced": surfaced,
                "report": report}
    finally:
        store.close()


def _stat_tags(r) -> list[str]:
    """Statistical annotations for an item this cycle."""
    tags = []
    if r.get("anomaly_significant"):
        tags.append(f"ANOMALY(z={r['anomaly_z']})")
    b = r.get("_breach_detail", {})
    toward = bool(b.get("toward_breach"))
    # Only annotate drift when it's heading toward breach — a trend toward safety
    # is not a warning.
    if r.get("drifting") and toward:
        d = r.get("_drift_detail", {})
        ctb = d.get("cycles_to_breach_at_current_drift")
        proj = f", ~{ctb} cycles to breach" if ctb is not None else ""
        tags.append(f"DRIFT(slope={r['drift_slope']}, t={r['drift_tstat']}{proj})")
    if b.get("tail_flag") and toward:
        tags.append(f"BREACH_PROB({r['breach_prob']} within {b.get('horizon_cycles')}c)")
    return tags


def _surfaces(r) -> bool:
    """Surface on a threshold change OR a significant anomaly OR a trend/tail that
    is heading TOWARD breach. A metric drifting toward safety is not surfaced."""
    if r["status"] in SURFACED:
        return True
    if r.get("anomaly_significant"):
        return True
    b = r.get("_breach_detail", {})
    toward = bool(b.get("toward_breach"))
    return toward and (bool(r.get("drifting")) or bool(b.get("tail_flag")))


def _build_report(cycle_n, data_ts, is_baseline, rows, skipped=None, gap=0) -> str:
    """Exception-based report: threshold changes AND statistical signals, plus
    freshness-skip and catch-up-gap notices."""
    skipped = skipped or []
    lines = [f"===== MONITORING CYCLE {cycle_n}  (data {data_ts}) ====="]

    if gap > 0:
        lines.append(f"CATCH-UP: {gap} cycle(s) missed before this run — flagged "
                     f"changes may have originated during the gap, not just now.")

    if is_baseline:
        lines.append(f"BASELINE CYCLE — established state for {len(rows)} item(s). "
                     f"Classification and alerting suppressed. Detection begins next cycle.")
        for r in rows:
            state = "breached" if r["breached"] else "ok"
            lines.append(f"  · {r['item_id']} ({r['entity']}): {r['metric']} "
                         f"{r['value']} vs {r['threshold']} [{state}]")
        if skipped:
            lines.append(f"Freshness: skipped {len(skipped)} item(s) with no new data.")
        return "\n".join(lines)

    surfaced = [r for r in rows if _surfaces(r)]
    suppressed = [r for r in rows if not _surfaces(r)]

    if not surfaced:
        lines.append("No exceptions this cycle — nothing changed, breached, drifted, or resolved.")
    else:
        lines.append(f"EXCEPTIONS ({len(surfaced)}):")
        order = {"NEW_BREACH": 0, "WIDENING": 1, "RESOLVED": 2, "IMPROVING": 3}
        # threshold-OK-but-flagged items sort after real status changes
        for r in sorted(surfaced, key=lambda x: order.get(x["status"], 8)):
            tags = _stat_tags(r)
            tagstr = ("  " + " ".join(tags)) if tags else ""
            label = r["status"]
            if label not in SURFACED and tags:
                label = "EARLY_WARNING"  # threshold OK, but statistics flag it
            lines.append(f"  [{label}] {r['item_id']} ({r['entity']}): "
                         f"{r['metric']} = {r['value']} vs {r['threshold']} "
                         f"({r['direction']}), margin {r['margin']:+.3f}{tagstr}")

    lines.append(f"Suppressed (quiet: no change, no drift, no anomaly): {len(suppressed)}")
    if skipped:
        lines.append(f"Freshness: skipped {len(skipped)} item(s) with no new data "
                     f"({', '.join(s['item_id'] for s in skipped)}).")
    return "\n".join(lines)
