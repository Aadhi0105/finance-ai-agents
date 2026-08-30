"""
Catalyst-calendar state store (Agent 3). Private, file-based DuckDB — the same
pattern as Agent 2's store, and emphatically NOT a shared MCP service (state is
never a shared boundary; only the analytical tools are).

Two tables, each with a clear job:
  - catalyst_calendar : upcoming, scheduled events to watch (an earnings date, a
                        guidance day). The daily brief is ephemeral; THIS persists.
  - event_outcomes    : the result of each event study run (event_type, CAAR, t,
                        significant, N, verdict, when). So a scenario can calibrate
                        on the accumulated real outcome history over time, and so
                        the agent can answer "what did comparable catalysts do?"
                        from stored fact rather than recomputing from scratch.

Design carried from Agent 2: stable IDs, append-only outcome history for audit,
straightforward reads. The store holds facts the agent produced; the model stays
stateless per run and is fed only what a given run needs.
"""

from __future__ import annotations

import os
from datetime import date, datetime

import duckdb

_DEFAULT_DB = os.path.join("state", "catalyst.duckdb")


class CatalystStore:
    def __init__(self, path: str = _DEFAULT_DB):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.con = duckdb.connect(path)
        self._init_schema()

    def _init_schema(self) -> None:
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS catalyst_calendar (
                catalyst_id VARCHAR PRIMARY KEY,
                entity VARCHAR, event_type VARCHAR, scheduled_date DATE,
                status VARCHAR, added_ts TIMESTAMP
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS event_outcomes (
                run_id VARCHAR PRIMARY KEY,
                event_type VARCHAR, run_ts TIMESTAMP,
                n_events INTEGER, caar DOUBLE, t_stat DOUBLE,
                significant BOOLEAN, verdict VARCHAR, confidence DOUBLE,
                pinned_peers VARCHAR
            )
        """)

    # --- catalyst calendar --------------------------------------------------

    def upsert_catalyst(self, catalyst_id: str, entity: str, event_type: str,
                        scheduled_date, status: str = "upcoming") -> None:
        sd = scheduled_date if isinstance(scheduled_date, date) else date.fromisoformat(str(scheduled_date))
        self.con.execute("""
            INSERT INTO catalyst_calendar VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (catalyst_id) DO UPDATE SET
                entity=excluded.entity, event_type=excluded.event_type,
                scheduled_date=excluded.scheduled_date, status=excluded.status
        """, [catalyst_id, entity, event_type, sd, status, datetime.now()])

    def upcoming(self, on_or_after: date | None = None) -> list[dict]:
        cutoff = on_or_after or date.today()
        rows = self.con.execute("""
            SELECT catalyst_id, entity, event_type, scheduled_date, status
            FROM catalyst_calendar
            WHERE scheduled_date >= ? AND status = 'upcoming'
            ORDER BY scheduled_date
        """, [cutoff]).fetchall()
        return [{"catalyst_id": r[0], "entity": r[1], "event_type": r[2],
                 "scheduled_date": str(r[3]), "status": r[4]} for r in rows]

    def mark_status(self, catalyst_id: str, status: str) -> None:
        self.con.execute("UPDATE catalyst_calendar SET status=? WHERE catalyst_id=?",
                         [status, catalyst_id])

    # --- event-outcome history ---------------------------------------------

    def record_outcome(self, run_id: str, study: dict, verdict: dict,
                       pinned_peers: list[str] | None = None) -> None:
        self.con.execute("""
            INSERT INTO event_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (run_id) DO NOTHING
        """, [run_id, study.get("event_type"), datetime.now(),
              study.get("n_events"), study.get("caar"), study.get("t_stat"),
              bool(study.get("caar_significant")), verdict.get("verdict"),
              verdict.get("confidence"), ",".join(pinned_peers or [])])

    def outcomes_for(self, event_type: str) -> list[dict]:
        rows = self.con.execute("""
            SELECT run_id, run_ts, n_events, caar, t_stat, significant, verdict, confidence
            FROM event_outcomes WHERE event_type = ? ORDER BY run_ts DESC
        """, [event_type]).fetchall()
        return [{"run_id": r[0], "run_ts": str(r[1]), "n_events": r[2], "caar": r[3],
                 "t_stat": r[4], "significant": r[5], "verdict": r[6], "confidence": r[7]}
                for r in rows]

    def close(self) -> None:
        self.con.close()
