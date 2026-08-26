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
from datetime import date

import duckdb

_DEFAULT_DB = os.path.join("state", "monitor.duckdb")

_COLUMNS = ("item_id", "cycle", "data_ts", "entity", "covenant_type", "metric",
           "value", "threshold", "direction", "breached", "margin", "status")


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
            direction VARCHAR, breached BOOLEAN, margin DOUBLE, status VARCHAR
        """
        self.con.execute(f"CREATE TABLE IF NOT EXISTS history ({cols});")
        self.con.execute(f"CREATE TABLE IF NOT EXISTS current_state ({cols});")

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

    def write_history(self, r: dict) -> None:
        self.con.execute(
            f"INSERT INTO history ({', '.join(_COLUMNS)}) VALUES ({', '.join(['?']*len(_COLUMNS))})",
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
