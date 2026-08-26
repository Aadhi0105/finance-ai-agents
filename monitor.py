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

_DB = os.path.join("state", "monitor.duckdb")


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
        result = run_cycle()
        print(result["report"])
    elif arg == "--run":
        # Convenience for demos: run N cycles in sequence (each still one cycle
        # of the atom). --once remains the primary/spec path.
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        for _ in range(n):
            print(run_cycle()["report"])
            print()
    else:
        sys.exit("Usage: python monitor.py [--once | --run N | --reset | --state]")
