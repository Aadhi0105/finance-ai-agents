"""
Persistent state store for Agent 2 (spec §3.3, State).

Two logical layers over one DuckDB file:
  - current_state : latest snapshot per item. Serves compare-to-last AND is the
                    on-demand full-state view.
  - history       : append-only, every cycle. Serves drift, audit, trend.

Shape is long/tidy panel data: one row per (item_id, cycle, metric). This is the
same shape the thesis / Safe Assets econometrics live in, so the drift model
(later) reads this store as a time-series regression over a panel.

This is Agent 2's PRIVATE store — file-based, no server, and emphatically NOT a
shared MCP service (spec §3.3 MCP).

Note: the single-transaction crash-safety write is a LATER robustness checkpoint;
this checkpoint keeps writes straightforward to prove the state machine first.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date

import duckdb

_DEFAULT_DB = os.path.join("state", "monitor.duckdb")

_COLUMNS = ("item_id", "cycle", "data_ts", "entity", "covenant_type", "metric",
           "value", "threshold", "direction", "breached", "margin", "status",
           "anomaly_significant", "anomaly_z", "drifting", "drift_slope", "drift_tstat",
           "breach_prob", "breach_tail")


class StateStore:
    def __init__(self, path: str = _DEFAULT_DB):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.con = duckdb.connect(path)
        self._init_schema()

    def _init_schema(self) -> None:
        cols = """
            item_id VARCHAR, cycle INTEGER, data_ts DATE, entity VARCHAR,
            covenant_type VARCHAR, metric VARCHAR, value DOUBLE, threshold DOUBLE,
            direction VARCHAR, breached BOOLEAN, margin DOUBLE, status VARCHAR,
            anomaly_significant BOOLEAN, anomaly_z DOUBLE,
            drifting BOOLEAN, drift_slope DOUBLE, drift_tstat DOUBLE,
            breach_prob DOUBLE, breach_tail BOOLEAN
        """
        # UNIQUE(item_id, data_ts): a given observation is recorded at most once,
        # so re-running a cycle / catch-up cannot double-append (idempotency).
        self.con.execute(
            f"CREATE TABLE IF NOT EXISTS history ({cols}, UNIQUE(item_id, data_ts));")
        self.con.execute(f"CREATE TABLE IF NOT EXISTS current_state ({cols});")

    @contextmanager
    def transaction(self):
        """Wrap a cycle's writes in one transaction: all-or-nothing, so a
        mid-cycle crash rolls back and leaves last-good state intact."""
        self.con.execute("BEGIN TRANSACTION")
        try:
            yield
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise

    def next_cycle(self) -> int:
        row = self.con.execute("SELECT max(cycle) FROM history").fetchone()
        return (row[0] or 0) + 1

    def get_current(self, item_id: str) -> dict | None:
        row = self.con.execute(
            "SELECT * FROM current_state WHERE item_id = ?", [item_id]
        ).fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self.con.description]
        return dict(zip(cols, row))

    def get_history_series(self, item_id: str) -> list[dict]:
        """The item's prior observations, oldest first — the input to the
        statistical checks (drift regression, anomaly baseline)."""
        rows = self.con.execute(
            "SELECT cycle, value FROM history WHERE item_id = ? ORDER BY cycle", [item_id]
        ).fetchall()
        return [{"cycle": r[0], "value": r[1]} for r in rows]

    def write_history(self, r: dict) -> None:
        # ON CONFLICT DO NOTHING: idempotent on (item_id, data_ts).
        self.con.execute(
            f"INSERT INTO history ({', '.join(_COLUMNS)}) "
            f"VALUES ({', '.join(['?']*len(_COLUMNS))}) ON CONFLICT DO NOTHING",
            [r[c] for c in _COLUMNS],
        )

    def upsert_current(self, r: dict) -> None:
        # Simple upsert: delete the item's row, insert the fresh snapshot.
        self.con.execute("DELETE FROM current_state WHERE item_id = ?", [r["item_id"]])
        self.con.execute(
            f"INSERT INTO current_state ({', '.join(_COLUMNS)}) VALUES ({', '.join(['?']*len(_COLUMNS))})",
            [r[c] for c in _COLUMNS],
        )

    def full_state(self) -> list[dict]:
        """On-demand full-state view: a read onto current_state (all items)."""
        rows = self.con.execute("SELECT * FROM current_state ORDER BY item_id").fetchall()
        cols = [d[0] for d in self.con.description]
        return [dict(zip(cols, row)) for row in rows]

    def close(self) -> None:
        self.con.close()
