"""
Catalyst-calendar state store (Agent 3). Private, file-based DuckDB — the same
pattern as Agent 2's store, and emphatically NOT a shared MCP service (state is
never a shared boundary; only the analytical tools are).

Two tables, each with a clear job:
  - catalyst_calendar : upcoming, scheduled events to watch (an earnings date, a
                        guidance day). The daily brief is ephemeral; THIS persists.
  - event_outcomes: summary rows (event type, CAR, nullable significance, gate).

Immutable CLI bundles retain evidence; this database indexes them and stores
conflict-checked outcome summaries plus an audited calendar lifecycle.
"""

from __future__ import annotations

import os
import json
from uuid import uuid4
from contextlib import contextmanager
from pathlib import Path
from datetime import date, datetime

import duckdb

_DEFAULT_DB = str(Path(__file__).resolve().parents[1] / "state" / "catalyst.duckdb")


class CatalystStore:
    def __init__(self, path: str = _DEFAULT_DB):
        self.path = path
        os.makedirs(os.path.dirname(os.fspath(path)) or ".", exist_ok=True)
        self.con = duckdb.connect(str(path))
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

        self.con.execute("""CREATE TABLE IF NOT EXISTS outcome_evidence (
            run_id VARCHAR PRIMARY KEY, payload VARCHAR, sha256 VARCHAR, inference_status VARCHAR)""")
        self.con.execute("""CREATE TABLE IF NOT EXISTS calendar_revisions (
            revision_id VARCHAR PRIMARY KEY, catalyst_id VARCHAR, changed_at TIMESTAMP,
            before_json VARCHAR, after_json VARCHAR, reason VARCHAR)""")
        self.con.execute("""CREATE TABLE IF NOT EXISTS run_bundles (
            run_id VARCHAR PRIMARY KEY, bundle_sha256 VARCHAR, content_fingerprint VARCHAR,
            bundle_path VARCHAR, status VARCHAR, indexed_at TIMESTAMP, reconciliation VARCHAR)""")

    @contextmanager
    def _transaction(self):
        self.con.execute('BEGIN TRANSACTION')
        try:
            yield
            self.con.execute('COMMIT')
        except Exception:
            self.con.execute('ROLLBACK')
            raise

    def _calendar(self, catalyst_id):
        row = self.con.execute('SELECT entity,event_type,scheduled_date,status FROM catalyst_calendar WHERE catalyst_id=?',
                               [catalyst_id]).fetchone()
        return dict(zip(('entity', 'event_type', 'scheduled_date', 'status'),
                        (row[0], row[1], str(row[2]), row[3]))) if row else None

    def upsert_catalyst(self, catalyst_id: str, entity: str, event_type: str,
                       scheduled_date, status: str = 'upcoming', *, reason=None) -> None:
        """Create or explicitly correct a calendar record; repeated identical writes are no-ops."""
        if any(not isinstance(v, str) or not v.strip() for v in (catalyst_id, entity, event_type)):
            raise ValueError('calendar identity fields must be nonempty')
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            raise ValueError('correction reason must be nonempty text')
        if status not in ('upcoming', 'occurred', 'cancelled'):
            raise ValueError('unknown calendar status')
        sd = date.fromisoformat(str(scheduled_date))
        after = dict(entity=entity, event_type=event_type, scheduled_date=str(sd), status=status)
        with self._transaction():
            before = self._calendar(catalyst_id)
            if before == after:
                return
            if before and (any(before[k] != after[k] for k in ('entity', 'event_type', 'scheduled_date'))
                           or before['status'] != 'upcoming'):
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError('calendar correction requires a reason')
            self.con.execute("""INSERT INTO calendar_revisions VALUES (?, ?, ?, ?, ?, ?)""",
                             [uuid4().hex, catalyst_id, datetime.now(), json.dumps(before), json.dumps(after),
                              reason or ('created' if before is None else 'status transition')])
            self.con.execute("""INSERT INTO catalyst_calendar VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (catalyst_id) DO UPDATE SET entity=excluded.entity,
                event_type=excluded.event_type, scheduled_date=excluded.scheduled_date, status=excluded.status""",
                             [catalyst_id, entity, event_type, sd, status, datetime.now()])

    def calendar_history(self, catalyst_id):
        rows = self.con.execute('SELECT revision_id,changed_at,before_json,after_json,reason FROM calendar_revisions WHERE catalyst_id=? ORDER BY changed_at,revision_id', [catalyst_id]).fetchall()
        return [dict(revision_id=r[0], changed_at=str(r[1]), before=json.loads(r[2]), after=json.loads(r[3]), reason=r[4]) for r in rows]

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

    def mark_status(self, catalyst_id: str, status: str, *, reason=None) -> None:
        before = self._calendar(catalyst_id)
        if before is None:
            raise KeyError('unknown catalyst ID')
        self.upsert_catalyst(catalyst_id, before['entity'], before['event_type'],
                             before['scheduled_date'], status, reason=reason)

    def record_outcome(self, run_id: str, study: dict, verdict: dict,
                       pinned_peers: list[str] | None = None) -> None:
        from agent3.bundles import canonical, digest
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError('run ID required')
        significant = study.get('caar_significant')
        if significant is not None and type(significant) is not bool:
            raise ValueError('significance must be true, false or unknown')
        payload = {'study': study, 'verdict': verdict, 'pinned_peers': pinned_peers or []}
        encoded, fingerprint = canonical(payload), digest(payload)
        with self._transaction():
            old = self.con.execute('SELECT payload FROM outcome_evidence WHERE run_id=?', [run_id]).fetchone()
            if old:
                if old[0] != encoded:
                    raise ValueError('conflicting outcome for existing run ID')
                return
            if self.con.execute('SELECT 1 FROM event_outcomes WHERE run_id=?', [run_id]).fetchone():
                raise ValueError('legacy run ID has no full evidence; use a new attempt ID')
            self.con.execute("""INSERT INTO event_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                             [run_id, study.get('event_type'), datetime.now(), study.get('n_events'),
                              study.get('caar'), study.get('t_stat'), significant, verdict.get('verdict'),
                              verdict.get('confidence'), ','.join(pinned_peers or [])])
            self.con.execute('INSERT INTO outcome_evidence VALUES (?, ?, ?, ?)',
                             [run_id, encoded, fingerprint, study.get('inference_status', 'unknown')])

    def index_bundle(self, path):
        """Explicit, repeatable recovery after interruption; never promote an outcome row."""
        from agent3.bundles import read_bundle, canonical
        b = read_bundle(path)
        run_id = b['attempt_id']
        with self._transaction():
            old = self.con.execute('SELECT bundle_sha256 FROM run_bundles WHERE run_id=?', [run_id]).fetchone()
            if old:
                if old[0] != b['bundle_sha256']:
                    raise ValueError('conflicting bundle for attempt ID')
                return
            summary = self.con.execute('SELECT payload FROM outcome_evidence WHERE run_id=?', [run_id]).fetchone()
            result = b['record'].get('result', {})
            expected = canonical({'study': result.get('study'), 'verdict': result.get('gate'),
                                  'pinned_peers': result.get('pinned_peers') or []})
            legacy = self.con.execute('SELECT 1 FROM event_outcomes WHERE run_id=?', [run_id]).fetchone()
            reconciliation = ('no_summary' if not legacy else 'legacy_unverified' if not summary else
                              'matched' if summary[0] == expected and b['record']['status'] in ('held', 'completed') else
                              'summary_conflict_or_terminal_failure')
            self.con.execute('INSERT INTO run_bundles VALUES (?, ?, ?, ?, ?, ?, ?)',
                             [run_id, b['bundle_sha256'], b['content_fingerprint'], str(Path(path).resolve()),
                              b['record']['status'], datetime.now(), reconciliation])

    def bundles(self):
        rows = self.con.execute('SELECT run_id,bundle_sha256,content_fingerprint,bundle_path,status,reconciliation FROM run_bundles ORDER BY indexed_at').fetchall()
        return [dict(zip(('run_id','bundle_sha256','content_fingerprint','bundle_path','status','reconciliation'), r)) for r in rows]

    def outcomes_for(self, event_type: str) -> list[dict]:
        rows = self.con.execute("""
            SELECT o.run_id, o.run_ts, o.n_events, o.caar, o.t_stat, o.significant,
                   o.verdict, o.confidence, o.pinned_peers, e.inference_status, e.payload,
                   b.status, b.reconciliation
            FROM event_outcomes o LEFT JOIN outcome_evidence e ON o.run_id=e.run_id
            LEFT JOIN run_bundles b ON o.run_id=b.run_id
            WHERE o.event_type = ? ORDER BY o.run_ts DESC
        """, [event_type]).fetchall()
        return [{"run_id": r[0], "run_ts": str(r[1]), "n_events": r[2], "caar": r[3],
                 "t_stat": r[4], "significant": r[5], "verdict": r[6], "confidence": r[7],
                 "pinned_peers": r[8].split(',') if r[8] else [], 'inference_status': r[9] or 'unknown',
                 'evidence_status': 'retained' if r[10] else 'legacy_summary_only',
                 'bundle_status': r[11], 'reconciliation': r[12]} for r in rows]

    def close(self) -> None:
        self.con.close()
