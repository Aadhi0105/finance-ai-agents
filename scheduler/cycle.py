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

_FIXTURE = os.path.join("fixtures", "covenants.json")


def _load_watchlist():
    with open(_FIXTURE) as f:
        fx = json.load(f)
    base = date.fromisoformat(fx.get("base_date", "2026-01-01"))
    return fx["covenants"], base


def run_cycle(db_path: str | None = None) -> dict:
    store = StateStore(db_path) if db_path else StateStore()
    try:
        cycle_n = store.next_cycle()
        is_baseline = cycle_n == 1
        covenants, base_date = _load_watchlist()
        data_ts = base_date + timedelta(days=cycle_n - 1)

        rows = []
        for cov in covenants:
            val = cov.get("cycle_values", {}).get(str(cycle_n))
            if val is None:
                continue  # no data this cycle for this item (freshness handled later)

            chk = threshold_check(val, cov["threshold"], cov["direction"])
            last = store.get_current(cov["item_id"])
            status = classify(last, chk["breached"], chk["margin"], is_baseline)

            row = {
                "item_id": cov["item_id"], "cycle": cycle_n, "data_ts": data_ts,
                "entity": cov["entity"], "covenant_type": cov["covenant_type"],
                "metric": cov["metric"], "value": val, "threshold": cov["threshold"],
                "direction": cov["direction"], "breached": chk["breached"],
                "margin": chk["margin"], "status": status,
            }
            store.write_history(row)
            store.upsert_current(row)
            rows.append(row)

        report = _build_report(cycle_n, data_ts, is_baseline, rows)
        return {"cycle": cycle_n, "data_ts": str(data_ts), "baseline": is_baseline,
                "rows": rows, "report": report}
    finally:
        store.close()


def _build_report(cycle_n, data_ts, is_baseline, rows) -> str:
    """Exception-based report: surface only what changed; count the rest."""
    lines = [f"===== MONITORING CYCLE {cycle_n}  (data {data_ts}) ====="]

    if is_baseline:
        lines.append(f"BASELINE CYCLE — established state for {len(rows)} item(s). "
                     f"Classification and alerting suppressed. Detection begins next cycle.")
        for r in rows:
            state = "breached" if r["breached"] else "ok"
            lines.append(f"  · {r['item_id']} ({r['entity']}): {r['metric']} "
                         f"{r['value']} vs {r['threshold']} [{state}]")
        return "\n".join(lines)

    surfaced = [r for r in rows if r["status"] in SURFACED]
    suppressed = [r for r in rows if r["status"] not in SURFACED]

    if not surfaced:
        lines.append("No exceptions this cycle — nothing changed, breached, or resolved.")
    else:
        lines.append(f"EXCEPTIONS ({len(surfaced)}):")
        # Order by rough severity for readability.
        order = {"NEW_BREACH": 0, "WIDENING": 1, "RESOLVED": 2, "IMPROVING": 3}
        for r in sorted(surfaced, key=lambda x: order.get(x["status"], 9)):
            lines.append(f"  [{r['status']}] {r['item_id']} ({r['entity']}): "
                         f"{r['metric']} = {r['value']} vs {r['threshold']} "
                         f"({r['direction']}), margin {r['margin']:+.3f}")

    lines.append(f"Suppressed (unchanged / known-stable): {len(suppressed)}")
    return "\n".join(lines)
