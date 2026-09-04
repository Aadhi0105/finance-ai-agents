"""
Versioned state store (Agent 4). Private, file-based DuckDB — NOT a shared MCP
service (state is never a boundary; only the analytical tools are).

The auditability signature at the state level is that NOTHING IS EVER OVERWRITTEN.
Three objects, each with a different mutation discipline, all append-only under the
hood so any historical version is retrievable and the version list IS the audit
trail:

  - budget      : immutable; a formal re-budget writes a NEW version, the original
                  (the thing you measure against) is never erased.
  - actuals     : append-only; a restatement of a prior period writes a NEW version,
                  the original figure stays for audit.
  - reforecast  : evolving; a new version is written EVERY close, so you can see how
                  the forecast walked across the year.

Close-driven cadence: the natural trigger is "new closed actuals available"
(irregular, freshness-gated) — `--close` is the manual/demo path.

All money in integer cents.
"""

from __future__ import annotations

import os
from datetime import datetime

import duckdb

_DEFAULT_DB = os.path.join("state", "variance.duckdb")


class VarianceStore:
    def __init__(self, path: str = _DEFAULT_DB):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.con = duckdb.connect(path)
        self._init_schema()

    def _init_schema(self) -> None:
        # budget: versioned on re-budget
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS budget (
                version VARCHAR, created_ts TIMESTAMP,
                line VARCHAR, period VARCHAR, amount_cents BIGINT
            )
        """)
        # actuals: append-only, versioned on restatement
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS actuals (
                version VARCHAR, created_ts TIMESTAMP,
                line VARCHAR, period VARCHAR, amount_cents BIGINT
            )
        """)
        # reforecast: a new version every close
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS reforecast (
                version VARCHAR, created_ts TIMESTAMP, close_period VARCHAR,
                line VARCHAR, landing_cents BIGINT, prob_hit DOUBLE
            )
        """)

    # --- budget (immutable; new version on re-budget) -----------------------

    def set_budget(self, version: str, rows: list[dict]) -> None:
        """rows: [{line, period, amount_cents}]. Writes a new immutable version;
        refuses to overwrite an existing version label."""
        exists = self.con.execute(
            "SELECT COUNT(*) FROM budget WHERE version=?", [version]).fetchone()[0]
        if exists:
            raise ValueError(f"budget version '{version}' already exists — "
                             f"re-budgets must use a new version label (nothing overwritten)")
        ts = datetime.now()
        self.con.executemany(
            "INSERT INTO budget VALUES (?, ?, ?, ?, ?)",
            [[version, ts, r["line"], r["period"], int(r["amount_cents"])] for r in rows])

    def get_budget(self, version: str | None = None) -> list[dict]:
        version = version or self._latest("budget")
        rows = self.con.execute(
            "SELECT line, period, amount_cents FROM budget WHERE version=? ORDER BY line, period",
            [version]).fetchall()
        return [{"line": r[0], "period": r[1], "amount_cents": r[2]} for r in rows]

    # --- actuals (append-only; new version on restatement) ------------------

    def append_actuals(self, version: str, rows: list[dict]) -> None:
        ts = datetime.now()
        self.con.executemany(
            "INSERT INTO actuals VALUES (?, ?, ?, ?, ?)",
            [[version, ts, r["line"], r["period"], int(r["amount_cents"])] for r in rows])

    def get_actuals(self, version: str | None = None) -> list[dict]:
        version = version or self._latest("actuals")
        rows = self.con.execute(
            "SELECT line, period, amount_cents FROM actuals WHERE version=? ORDER BY line, period",
            [version]).fetchall()
        return [{"line": r[0], "period": r[1], "amount_cents": r[2]} for r in rows]

    # --- reforecast (new version every close) -------------------------------

    def record_reforecast(self, close_period: str, rows: list[dict],
                          version: str | None = None) -> str:
        version = version or f"rf_{close_period}_{datetime.now():%Y%m%d%H%M%S}"
        ts = datetime.now()
        self.con.executemany(
            "INSERT INTO reforecast VALUES (?, ?, ?, ?, ?, ?)",
            [[version, ts, close_period, r["line"], int(r["landing_cents"]),
              float(r.get("prob_hit") if r.get("prob_hit") is not None else float("nan"))]
             for r in rows])
        return version

    def reforecast_walk(self, line: str) -> list[dict]:
        """How the forecast for a line evolved across closes — the versioned trail."""
        rows = self.con.execute("""
            SELECT close_period, created_ts, landing_cents, prob_hit
            FROM reforecast WHERE line=? ORDER BY created_ts
        """, [line]).fetchall()
        return [{"close_period": r[0], "created_ts": str(r[1]),
                 "landing_cents": r[2], "prob_hit": r[3]} for r in rows]

    # --- audit trail --------------------------------------------------------

    def versions(self, table: str) -> list[dict]:
        rows = self.con.execute(f"""
            SELECT version, MIN(created_ts) AS ts, COUNT(*) AS n
            FROM {table} GROUP BY version ORDER BY ts
        """).fetchall()
        return [{"version": r[0], "created_ts": str(r[1]), "rows": r[2]} for r in rows]

    def _latest(self, table: str) -> str | None:
        row = self.con.execute(
            f"SELECT version FROM {table} ORDER BY created_ts DESC LIMIT 1").fetchone()
        return row[0] if row else None

    def close(self) -> None:
        self.con.close()
