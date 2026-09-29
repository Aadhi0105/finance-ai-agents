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
from state.store import StateStore, _DEFAULT_DB
from filelock import FileLock
from monitoring.triage import run_triage_record, HistorySnapshot, prepare_live

_DB = _DEFAULT_DB


def _triage_if_needed(result, live: bool) -> None:
    surfaced = result.get("surfaced", [])
    if result.get('replayed'):
        print('Triage skipped: saved cycle replay; no new model call.')
        return
    if not surfaced:
        print('Triage not needed: no newly surfaced flags; this does not establish compliance.')
        return
    try:
        store = StateStore(_DB)
        try:
            snapshot = HistorySnapshot(store, surfaced, result['cycle'])
        finally:
            store.close()
        triage = run_triage_record(snapshot, surfaced, live=live, cycle=result['cycle'])
    except (Exception, KeyboardInterrupt) as exc:
        print(f"Triage failed ({type(exc).__name__}); monitoring cycle remains committed.", file=sys.stderr)
        raise SystemExit(2)
    print(f"\nTriage mode: {'live model' if live else 'offline stub'}; data: {result.get('data_mode', 'bundled_fixtures')}")
    print(f"Triage audit: {triage['audit_path']}")
    if triage['status'] != 'completed':
        print(f"Triage {triage['status']}: {triage['reason']}; commentary withheld. "
              "Monitoring cycle remains committed.", file=sys.stderr)
        raise SystemExit(2)
    print(triage['commentary'])


def _reset():
    os.makedirs(os.path.dirname(_DB), exist_ok=True)
    with FileLock(_DB + ".lock", timeout=10):
        if os.path.exists(_DB):
            os.remove(_DB)
            if os.path.exists(_DB + ".wal"):
                os.remove(_DB + ".wal")
            print(f"reset: removed {_DB}")
        else:
            print("reset: no state DB to remove")


def _print_state():
    store = StateStore(_DB)
    try:
        rows = store.full_state()
        print(f"Data source: {store.source_mode() or 'uninitialized'}")
        if store.source_mode() == "yfinance":
            print("Threshold basis: analyst policies, not contractual covenants.")
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
    import argparse
    from pathlib import Path
    options = argparse.ArgumentParser(add_help=False)
    options.add_argument('--db', default=_DB)
    options.add_argument('--data-source', choices=['fixture', 'yfinance'], default='fixture')
    options.add_argument('--watchlist')
    parsed, remaining = options.parse_known_args()
    _DB = str(Path(parsed.db).expanduser().resolve())
    sys.argv = [sys.argv[0], *remaining]
    arg = sys.argv[1] if len(sys.argv) > 1 else "--once"
    watchlist = None
    if parsed.data_source == 'yfinance':
        if not parsed.watchlist or arg not in {'--once', '--catchup'}:
            sys.exit('Live observations require --watchlist PATH with --once or --catchup; inspect state using --state --db PATH')
        watchlist = str(Path(parsed.watchlist).expanduser().resolve())
        from monitoring.live_data import load_profile
        load_profile(watchlist)
    elif parsed.watchlist:
        sys.exit('--watchlist requires --data-source yfinance')
    if "--live" in sys.argv:
        if arg not in {"--once", "--catchup"}:
            sys.exit("--live is supported only with --once or --catchup")
        try:
            prepare_live()
        except ValueError as exc:
            sys.exit(str(exc))
    if arg in {"--once", "--catchup", "--run", "--loop"}:
        print("Data source: live annual statements; analyst policies." if watchlist else "Data source: bundled fixtures (not a live market feed).")
    if arg == "--reset":
        _reset()
    elif arg == "--state":
        _print_state()
    elif arg == "--once":
        live = "--live" in sys.argv
        result = run_cycle(db_path=_DB, watchlist_path=watchlist)
        print(result["report"])
        _triage_if_needed(result, live)
        if watchlist and result["status"] == "review_required":
            raise SystemExit(3)
    elif arg == "--catchup":
        # Simulate the monitor coming back online after downtime: data has
        # advanced to cycle ASOF; skip-to-now and surface the gap.
        if len(sys.argv) < 3:
            sys.exit("Usage: python monitor.py --catchup ASOF_CYCLE")
        result = run_cycle(db_path=_DB, asof_cycle=int(sys.argv[2]), watchlist_path=watchlist)
        print(result["report"])
        _triage_if_needed(result, "--live" in sys.argv)
        if watchlist and result["status"] == "review_required":
            raise SystemExit(3)
    elif arg == "--run":
        # Convenience for demos: run N cycles in sequence (each still one cycle
        # of the atom). No triage — use --once to triage a cycle's exceptions.
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        for _ in range(n):
            print(run_cycle(db_path=_DB)["report"])
            print()
    elif arg == "--loop":
        # Thin scheduler: fire run_cycle() on a cadence. INTERVAL seconds
        # (default 2 for demos; 86400 = daily in production), optional --max N.
        from scheduler.trigger import run_forever
        interval = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else 2.0
        max_cycles = None
        if "--max" in sys.argv:
            max_cycles = int(sys.argv[sys.argv.index("--max") + 1])
        run_forever(interval_seconds=interval, max_cycles=max_cycles, db_path=_DB)
    elif arg == "--cron":
        from scheduler.trigger import cron_line
        sched = sys.argv[2] if len(sys.argv) > 2 else "0 6 * * 1-5"
        print("# Add to your crontab (crontab -e) to run one cycle on a cadence:")
        print(cron_line(sched, db_path=_DB))
    else:
        sys.exit("Usage: python monitor.py "
                 "[--once [--live] | --catchup N | --loop [INTERVAL] [--max N] | "
                 "--cron [SCHEDULE] | --run N | --reset | --state]")
