"""
Persistent state store for Agent 2 (spec §3.3, State).

Core observation layers over one DuckDB file:
  - current_state : latest snapshot per item. Serves compare-to-last AND is the
                    on-demand full-state view.
  - history       : effective dated observations; approved restatements are archived.
  - cycle_runs    : complete results, including empty cycles, for replay/progress.
  - observation_details / review_queue : diagnostic snapshots and review holds.
  - review_decisions : immutable decision records, including before/after histories.

Shape is long/tidy panel data: one row per (item_id, cycle, metric). This is the
same shape the thesis / Safe Assets econometrics live in, so the drift model
(later) reads this store as a time-series regression over a panel.

This is Agent 2's PRIVATE store — file-based, no server, and emphatically NOT a
shared MCP service (spec §3.3 MCP).

A process lock covers the store lifetime. Cycle ledger, observations and diagnostic
evidence commit atomically; legacy observations remain readable.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from filelock import FileLock
from contextlib import contextmanager
from datetime import date

import duckdb

_DEFAULT_DB = str(Path(__file__).resolve().parent / "monitor.duckdb")

_COLUMNS = ("item_id", "cycle", "data_ts", "entity", "covenant_type", "metric",
           "value", "threshold", "direction", "breached", "margin", "status",
           "anomaly_significant", "anomaly_z", "drifting", "drift_slope", "drift_tstat",
           "breach_prob", "breach_tail")


class StateStore:
    def __init__(self, path: str = _DEFAULT_DB):
        self.path = str(Path(path).expanduser().resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(self.path + '.lock', timeout=10)
        self._lock.acquire()
        self.con = None
        try:
            self.con = duckdb.connect(self.path)
            self._init_schema()
        except BaseException:
            self.close()
            raise

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
        self.con.execute("CREATE TABLE IF NOT EXISTS monitor_metadata (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL)")
        self.con.execute("CREATE TABLE IF NOT EXISTS review_decisions (review_id VARCHAR PRIMARY KEY, payload VARCHAR NOT NULL)")
        self.con.execute("CREATE TABLE IF NOT EXISTS retired_series (item_id VARCHAR PRIMARY KEY, replacement_id VARCHAR NOT NULL)")
        self.con.execute("CREATE TABLE IF NOT EXISTS review_queue (item_id VARCHAR PRIMARY KEY, payload VARCHAR NOT NULL)")
        self.con.execute("CREATE TABLE IF NOT EXISTS cycle_runs (cycle INTEGER PRIMARY KEY, payload VARCHAR NOT NULL)")
        self.con.execute("CREATE TABLE IF NOT EXISTS observation_details (item_id VARCHAR, data_ts DATE, payload VARCHAR NOT NULL, PRIMARY KEY(item_id, data_ts))")

    @contextmanager
    def transaction(self):
        """Wrap a cycle's writes in one transaction: all-or-nothing, so a
        mid-cycle crash rolls back and leaves last-good state intact."""
        self.con.execute("BEGIN TRANSACTION")
        try:
            yield
            self.con.execute("COMMIT")
        except BaseException:
            self.con.execute("ROLLBACK")
            raise

    def source_mode(self):
        row = self.con.execute("SELECT value FROM monitor_metadata WHERE key='data_mode'").fetchone()
        return row[0] if row else ('bundled_fixtures' if self.next_cycle() > 1 else None)

    def bind_source(self, mode):
        existing = self.source_mode()
        if existing is not None and existing != mode:
            raise ValueError('database data source mismatch; use a separate database')
        self.con.execute("INSERT INTO monitor_metadata VALUES ('data_mode', ?) ON CONFLICT DO NOTHING", [mode])

    def next_cycle(self) -> int:
        row = self.con.execute("SELECT max(cycle) FROM (SELECT cycle FROM history UNION ALL SELECT cycle FROM cycle_runs)").fetchone()
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
            "SELECT cycle, value, data_ts FROM history WHERE item_id = ? ORDER BY data_ts", [item_id]
        ).fetchall()
        return [{"cycle": r[0], "value": r[1], "data_ts": r[2]} for r in rows]

    def write_history(self, r: dict) -> None:
        existing = self.con.execute('SELECT ' + ', '.join(_COLUMNS) +
                                    ' FROM history WHERE item_id=? AND data_ts=?',
                                    [r['item_id'], r['data_ts']]).fetchone()
        if existing:
            expected = [r[c] for c in _COLUMNS]
            expected[2] = date.fromisoformat(expected[2]) if isinstance(expected[2], str) else expected[2]
            if tuple(expected) != existing:
                raise ValueError('conflicting observation; explicit correction review required')
            return
        self.con.execute(
            f"INSERT INTO history ({', '.join(_COLUMNS)}) VALUES ({', '.join(['?']*len(_COLUMNS))})",
            [r[c] for c in _COLUMNS])
        self.con.execute('INSERT INTO observation_details VALUES (?, ?, ?)',
                         [r['item_id'], r['data_ts'], json.dumps(r, default=_json_date, allow_nan=False)])

    def get_observation(self, item_id, data_ts):
        row = self.con.execute('SELECT * FROM history WHERE item_id=? AND data_ts=?',
                               [item_id, data_ts]).fetchone()
        return dict(zip([d[0] for d in self.con.description], row)) if row else None

    def get_observation_evidence(self, item_id, data_ts):
        row = self.con.execute('SELECT payload FROM observation_details WHERE item_id=? AND data_ts=?',
                               [item_id, data_ts]).fetchone()
        return json.loads(row[0]) if row else None  # legacy detail is unknown, never fabricated

    def pending_review(self, item_id):
        row = self.con.execute('SELECT payload FROM review_queue WHERE item_id=?', [item_id]).fetchone()
        return json.loads(row[0]) if row else None

    def write_review(self, skipped, cycle):
        self.con.execute('INSERT INTO review_queue VALUES (?, ?) ON CONFLICT DO NOTHING',
                         [skipped['item_id'], json.dumps({'cycle': cycle, **skipped},
                                                        default=_json_date, allow_nan=False)])

    def reviews(self):
        from monitoring.recovery import review_id
        return [{'review_id': review_id(json.loads(row[0])), **json.loads(row[0])}
                for row in self.con.execute('SELECT payload FROM review_queue ORDER BY item_id').fetchall()]

    def decisions(self):
        return [json.loads(row[0]) for row in self.con.execute('SELECT payload FROM review_decisions ORDER BY review_id').fetchall()]

    def rejected_candidate(self, item_id, candidate):
        from monitoring.recovery import candidate_key
        key = candidate_key(candidate)
        return any(d['item_id'] == item_id and d['action'] == 'reject' and d['candidate_key'] == key
                   for d in self.decisions())

    def is_retired(self, item_id):
        return self.con.execute('SELECT replacement_id FROM retired_series WHERE item_id=?', [item_id]).fetchone() is not None

    def get_run(self, cycle):
        row = self.con.execute('SELECT payload FROM cycle_runs WHERE cycle=?', [cycle]).fetchone()
        return json.loads(row[0]) if row else None

    def write_run(self, result):
        self.con.execute('INSERT INTO cycle_runs VALUES (?, ?)',
                         [result['cycle'], json.dumps(result, default=_json_date, allow_nan=False)])

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
        result = [dict(zip(cols, row)) for row in rows]
        retired = dict(self.con.execute('SELECT item_id, replacement_id FROM retired_series').fetchall())
        for row in result:
            if row['item_id'] in retired:
                row['retired_to'] = retired[row['item_id']]
        return result

    def close(self) -> None:
        try:
            if self.con is not None:
                self.con.close()
                self.con = None
        finally:
            self._lock.release()


def _json_date(value):
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError('unsupported audit value')
