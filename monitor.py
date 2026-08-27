"""
Agent 2 — Monitoring / surveillance. Entry point.

    python monitor.py --once     run one cycle (the primary, demoable path)
    python monitor.py --reset    delete the state DB (fresh two-cycle demo)
    python monitor.py --state     print the on-demand full-state view

`--once` is the atom the spec builds everything on: run it once to establish the
baseline, run it again to detect change. A thin scheduler wrapper (cadence) is a
later checkpoint; this manual path is the interview demo.
"""

from __future__ import annotations

import os
import sys

from scheduler.cycle import run_cycle
from state.store import StateStore
from monitoring.triage import run_triage

_DB = os.path.join("state", "monitor.duckdb")


def _triage_if_needed(result, live: bool) -> None:
    surfaced = result.get("surfaced", [])
    if not surfaced:
        return
    store = StateStore()
    try:
        commentary = run_triage(store, surfaced, live=live)
    finally:
        store.close()
    if commentary:
        print("\n----- MODEL TRIAGE -----")
        print(commentary)
        print("------------------------")


def _reset():
    if os.path.exists(_DB):
        os.remove(_DB)
        print(f"reset: removed {_DB}")
    else:
        print("reset: no state DB to remove")


def _print_state():
    store = StateStore()
    try:
        rows = store.full_state()
    finally:
        store.close()
    if not rows:
        print("full-state: (empty — no cycles run yet)")
        return
    print("===== FULL STATE (current snapshot per item) =====")
    for r in rows:
        state = "breached" if r["breached"] else "ok"
        print(f"  {r['item_id']} ({r['entity']}): {r['metric']} = {r['value']} "
              f"vs {r['threshold']} [{state}] status={r['status']} cycle={r['cycle']}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--once"
    if arg == "--reset":
        _reset()
    elif arg == "--state":
        _print_state()
    elif arg == "--once":
        live = "--live" in sys.argv
        result = run_cycle()
        print(result["report"])
        _triage_if_needed(result, live)
    elif arg == "--catchup":
        # Simulate the monitor coming back online after downtime: data has
        # advanced to cycle ASOF; skip-to-now and surface the gap.
        if len(sys.argv) < 3:
            sys.exit("Usage: python monitor.py --catchup ASOF_CYCLE")
        result = run_cycle(asof_cycle=int(sys.argv[2]))
        print(result["report"])
        _triage_if_needed(result, "--live" in sys.argv)
    elif arg == "--run":
        # Convenience for demos: run N cycles in sequence (each still one cycle
        # of the atom). No triage — use --once to triage a cycle's exceptions.
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        for _ in range(n):
            print(run_cycle()["report"])
            print()
    elif arg == "--loop":
        # Thin scheduler: fire run_cycle() on a cadence. INTERVAL seconds
        # (default 2 for demos; 86400 = daily in production), optional --max N.
        from scheduler.trigger import run_forever
        interval = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else 2.0
        max_cycles = None
        if "--max" in sys.argv:
            max_cycles = int(sys.argv[sys.argv.index("--max") + 1])
        run_forever(interval_seconds=interval, max_cycles=max_cycles)
    elif arg == "--cron":
        from scheduler.trigger import cron_line
        sched = sys.argv[2] if len(sys.argv) > 2 else "0 6 * * 1-5"
        print("# Add to your crontab (crontab -e) to run one cycle on a cadence:")
        print(cron_line(sched))
    else:
        sys.exit("Usage: python monitor.py "
                 "[--once [--live] | --catchup N | --loop [INTERVAL] [--max N] | "
                 "--cron [SCHEDULE] | --run N | --reset | --state]")
