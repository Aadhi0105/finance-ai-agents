"""
Scheduler / trigger for Agent 2 (spec §3.3, Scheduling).

DELIBERATELY THIN. `run_cycle()` is the atom and already contains all the
sophistication — freshness gating, skip-to-now catch-up, transactional writes,
idempotency. The scheduler's only job is to FIRE the atom on a cadence. No
Airflow / Celery / Kafka: a dumb trigger over a robust atom is the whole point.

Because the atom is robust, the trigger can be dumb *safely*:
  - cron may fire daily even over quarterly data — run_cycle freshness-gates the
    stale items, while recording an empty cycle in the run ledger.
  - store users serialize through a process lock. Explicit cycle IDs replay the
    saved result; automatic ticks intentionally allocate successive cycle IDs.
  - a tick that raises self-heals — run_cycle's transaction already rolled back
    any partial write, so the next tick simply retries from last-good state.

Two ways to run on a cadence:
  1. In-process loop (run_forever) — demos and lightweight deployment.
  2. cron — call `monitor.py --once` on a schedule; cron_line() prints the entry.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path
import sys
import time
from datetime import datetime

from scheduler.cycle import run_cycle


def run_forever(interval_seconds: float = 86400, max_cycles: int | None = None,
                verbose: bool = True, db_path: str | None = None) -> int:
    """Fire run_cycle() every `interval_seconds`. Stops after `max_cycles` (or runs
    until interrupted). Returns the number of ticks fired. A failing tick is logged
    and skipped — the loop keeps going."""
    fired = 0
    try:
        while max_cycles is None or fired < max_cycles:
            fired += 1
            ts = datetime.now().strftime("%H:%M:%S")
            try:
                result = run_cycle(db_path=db_path)
                if verbose:
                    print(f"[{ts}] tick {fired} —")
                    print(result["report"])
                    print()
            except Exception as e:
                # Self-healing: run_cycle already rolled back; retry next tick.
                print(f"[{ts}] tick {fired} FAILED: {e!r} — cycle failed; inspect stored ledger before retrying, continuing.\n")
            if max_cycles is None or fired < max_cycles:
                time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nscheduler stopped (KeyboardInterrupt).")
    return fired


def cron_line(schedule: str = "0 6 * * 1-5", db_path: str | None = None) -> str:
    """Return a crontab entry that fires one cycle on the given schedule.
    Default: 06:00 on weekdays. The trigger stays dumb — cron is the cadence,
    run_cycle is the intelligence."""
    project_dir = str(Path(__file__).resolve().parents[1])
    python_bin = sys.executable or "python"
    db_arg = ' --db ' + shlex.quote(str(Path(db_path).expanduser().resolve())) if db_path else ''
    return (f"{schedule} cd {shlex.quote(project_dir)} && "
            f"{shlex.quote(python_bin)} monitor.py --once{db_arg} >> monitor.log 2>&1")
