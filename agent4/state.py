"""Immutable, transactional Agent 4 state. Actuals versions are ordered deltas.

Existing populated legacy databases require an explicit migration; they are never
silently reinterpreted. One store connection is owned by one execution thread.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os

import duckdb
from agent4.contracts import cents

KINDS = frozenset({'budget', 'actuals', 'reforecast'})


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value, field='identifier'):
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 500 or any(ord(c) < 32 for c in value):
        raise ValueError(f'{field}: expected a nonempty trimmed identifier')
    return value


def iso_period(value):
    try:
        valid = isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('period must be an ISO date (YYYY-MM-DD)')
    return value


class VarianceStore:
    def __init__(self, path='state/variance.duckdb'):
        self.path = str(path)
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        self.con = duckdb.connect(self.path)
        self._in_transaction = False
        try:
            self._init_schema()
        except BaseException:
            self.con.close()
            raise

    def _init_schema(self):
        tables = {r[0] for r in self.con.execute('SHOW TABLES').fetchall()}
        for table in KINDS & tables:
            if self.con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:
                raise ValueError('populated legacy Agent 4 database: explicit migration required; original data preserved')
        with self.transaction():
            self.con.execute('CREATE SEQUENCE IF NOT EXISTS a4_version_seq START 1')
            self.con.execute('''CREATE TABLE IF NOT EXISTS a4_versions (
                kind VARCHAR NOT NULL CHECK(kind IN ('budget','actuals','reforecast')),
                version VARCHAR NOT NULL, sequence BIGINT DEFAULT nextval('a4_version_seq'),
                created_ts TIMESTAMPTZ DEFAULT current_timestamp, digest VARCHAR NOT NULL,
                metadata VARCHAR NOT NULL, row_count BIGINT NOT NULL CHECK(row_count > 0),
                PRIMARY KEY(kind, version), UNIQUE(sequence))''')
            self.con.execute('''CREATE TABLE IF NOT EXISTS a4_rows (
                kind VARCHAR NOT NULL, version VARCHAR NOT NULL, line VARCHAR NOT NULL,
                period VARCHAR NOT NULL, amount_cents BIGINT CHECK(kind='reforecast' OR amount_cents IS NOT NULL),
                prob_hit DOUBLE CHECK(prob_hit IS NULL OR (isfinite(prob_hit) AND prob_hit BETWEEN 0 AND 1)),
                evidence VARCHAR NOT NULL, PRIMARY KEY(kind, version, line, period),
                FOREIGN KEY(kind, version) REFERENCES a4_versions(kind, version))''')
            self.con.execute('''CREATE TABLE IF NOT EXISTS a4_runs (
                run_id VARCHAR PRIMARY KEY, request_digest VARCHAR NOT NULL,
                entity VARCHAR NOT NULL, close_period VARCHAR NOT NULL,
                bundle_digest VARCHAR NOT NULL, bundle VARCHAR NOT NULL,
                created_ts TIMESTAMPTZ DEFAULT current_timestamp)''')
            self.con.execute('''CREATE TABLE IF NOT EXISTS a4_attempts (
                attempt_id VARCHAR NOT NULL, run_id VARCHAR NOT NULL, request_digest VARCHAR NOT NULL,
                created_ts TIMESTAMPTZ DEFAULT current_timestamp,
                status VARCHAR NOT NULL CHECK(status IN ('started','committed','replayed','failed')),
                detail VARCHAR NOT NULL)''')
            self.con.execute('''CREATE TABLE IF NOT EXISTS a4_heads (
                entity VARCHAR PRIMARY KEY, run_id VARCHAR NOT NULL, close_period VARCHAR NOT NULL)''')
            self.con.execute('''CREATE TABLE IF NOT EXISTS a4_delivery (
                run_id VARCHAR NOT NULL REFERENCES a4_runs(run_id),
                created_ts TIMESTAMPTZ DEFAULT current_timestamp,
                status VARCHAR NOT NULL CHECK(status IN ('delivered','failed')),
                detail VARCHAR NOT NULL)''')

    @contextmanager
    def transaction(self):
        if self._in_transaction:
            raise RuntimeError('nested transactions are not supported')
        self.con.execute('BEGIN TRANSACTION')
        self._in_transaction = True
        try:
            yield
            self.con.execute('COMMIT')
        except BaseException:
            try:
                self.con.execute('ROLLBACK')
            except duckdb.TransactionException:
                pass  # A failed COMMIT may already have aborted the transaction.
            raise
        finally:
            self._in_transaction = False

    def _kind(self, kind):
        if kind not in KINDS:
            raise ValueError('unsupported state table')
        return kind

    def _write(self, kind, version, rows, metadata=None, close_period=None):
        self._kind(kind)
        identifier(version, 'version')
        if not isinstance(rows, list) or not rows:
            raise ValueError('version rows must be a nonempty list')
        metadata = {} if metadata is None else metadata
        if not isinstance(metadata, dict):
            raise ValueError('metadata must be an object')
        normalized, keys = [], set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('state row must be an object')
            line = identifier(row.get('line'), 'line')
            period = iso_period(close_period if kind == 'reforecast' else row.get('period'))
            if (line, period) in keys:
                raise ValueError('duplicate line/period within version')
            keys.add((line, period))
            field = 'landing_cents' if kind == 'reforecast' else 'amount_cents'
            amount = row.get(field)
            if not (kind == 'reforecast' and amount is None and row.get('status') == 'held' and row.get('probability_reason')):
                amount = cents(amount, field)
            if kind != 'reforecast' and set(row) != {'line', 'period', 'amount_cents'}:
                raise ValueError('unsupported observation fields')
            prob = row.get('prob_hit') if kind == 'reforecast' else None
            if prob is not None and (type(prob) not in (int, float) or not math.isfinite(prob) or not 0 <= prob <= 1):
                raise ValueError('prob_hit must be null or a finite probability in [0,1]')
            if prob is not None:
                prob = float(prob)
            if amount is None and prob is not None:
                raise ValueError('held forecast cannot have a probability')
            evidence = dict(row)
            if kind == 'reforecast':
                evidence.update(prob_hit=prob, probability_status='unavailable' if prob is None else 'available')
                if prob is None and not evidence.get('probability_reason'):
                    raise ValueError('unavailable probability requires probability_reason')
            normalized.append((line, period, amount, prob, evidence))
        normalized.sort(key=lambda r: (r[0], r[1]))
        content_digest = digest({'rows': normalized, 'metadata': metadata})
        def insert():
            existing = self.version_info(kind, version)
            if existing:
                self._validate_version(kind, version)
                if existing['digest'] != content_digest:
                    raise ValueError(f'{kind} version conflict: use a new version for corrections')
                return
            self.con.execute('INSERT INTO a4_versions(kind,version,digest,metadata,row_count) VALUES (?,?,?,?,?)',
                             [kind, version, content_digest, canonical(metadata), len(rows)])
            for line, period, amount, prob, evidence in normalized:
                self.con.execute('INSERT INTO a4_rows VALUES (?,?,?,?,?,?,?)',
                                 [kind, version, line, period, amount, prob, canonical(evidence)])
        if self._in_transaction:
            insert()
        else:
            with self.transaction():
                insert()
        return version

    def set_budget(self, version, rows, *, metadata=None):
        return self._write('budget', version, rows, metadata)

    def append_actuals(self, version, rows, *, metadata=None):
        return self._write('actuals', version, rows, metadata)

    def record_reforecast(self, close_period, rows, version=None, *, metadata=None):
        iso_period(close_period)
        version = version or 'rf_' + digest([close_period, rows, metadata])[:24]
        return self._write('reforecast', version, rows, metadata, close_period)

    def version_info(self, kind, version):
        self._kind(kind)
        row = self.con.execute('SELECT version,sequence,created_ts,digest,metadata,row_count FROM a4_versions WHERE kind=? AND version=?', [kind, version]).fetchone()
        return None if row is None else dict(version=row[0], sequence=row[1], created_ts=str(row[2]), digest=row[3], metadata=json.loads(row[4]), rows=row[5])

    def _validate_version(self, kind, version):
        info = self.version_info(kind, version)
        if info is None:
            raise ValueError(f'unknown {kind} version')
        rows = self.con.execute('SELECT line,period,amount_cents,prob_hit,evidence FROM a4_rows WHERE kind=? AND version=? ORDER BY line,period', [kind, version]).fetchall()
        normalized = [(r[0],r[1],r[2],r[3],json.loads(r[4])) for r in rows]
        if len(rows) != info['rows'] or digest({'rows':normalized, 'metadata':info['metadata']}) != info['digest']:
            raise ValueError('stored version integrity check failed')

    def versions(self, table):
        self._kind(table)
        return [self.version_info(table, r[0]) for r in self.con.execute('SELECT version FROM a4_versions WHERE kind=? ORDER BY sequence', [table]).fetchall()]

    def _latest(self, table):
        self._kind(table)
        row = self.con.execute('SELECT version FROM a4_versions WHERE kind=? ORDER BY sequence DESC LIMIT 1', [table]).fetchone()
        return row[0] if row else None

    def _observations(self, kind, version):
        version = version or self._latest(kind)
        if version is None:
            return []
        self._validate_version(kind, version)
        return [dict(line=r[0], period=r[1], amount_cents=r[2]) for r in self.con.execute('SELECT line,period,amount_cents FROM a4_rows WHERE kind=? AND version=? ORDER BY line,period', [kind, version]).fetchall()]

    def get_budget(self, version=None):
        """Budget versions are complete caller-defined immutable panels."""
        return self._observations('budget', version)

    def get_actuals(self, version=None):
        """Effective panel as of a delta version; retain all unaffected observations.

        Deltas are scoped by metadata.entity (or the legacy unscoped namespace).
        The snapshot records each winning source version via actuals_snapshot().
        """
        return [{k: r[k] for k in ('line', 'period', 'amount_cents')} for r in self.actuals_snapshot(version)]

    def actuals_delta(self, version):
        return self._observations('actuals', version)

    def actuals_snapshot(self, version=None):
        version = version or self._latest('actuals')
        if version is None:
            return []
        info = self.version_info('actuals', version)
        if info is None:
            raise ValueError('unknown actuals version')
        entity = info['metadata'].get('entity')
        effective = {}
        for v in self.versions('actuals'):
            if v['sequence'] <= info['sequence'] and v['metadata'].get('entity') == entity:
                for row in self.actuals_delta(v['version']):
                    effective[(row['line'], row['period'])] = {**row, 'source_version': v['version'], 'source_digest': v['digest']}
        return [effective[key] for key in sorted(effective)]

    def reforecast_walk(self, line):
        for version in self.versions('reforecast'):
            self._validate_version('reforecast', version['version'])
        rows = self.con.execute('''SELECT r.version,r.period,v.created_ts,r.evidence,v.metadata
            FROM a4_rows r JOIN a4_versions v USING(kind,version)
            WHERE r.kind='reforecast' AND r.line=? ORDER BY v.sequence''', [line]).fetchall()
        return [{**json.loads(r[3]), 'version':r[0], 'close_period':r[1], 'created_ts':str(r[2]), 'lineage':json.loads(r[4])} for r in rows]

    def get_run(self, run_id):
        row = self.con.execute('SELECT request_digest,bundle_digest,bundle FROM a4_runs WHERE run_id=?', [run_id]).fetchone()
        if row is None:
            return None
        bundle = json.loads(row[2])
        if digest(bundle) != row[1]:
            raise ValueError('saved run integrity check failed')
        return {'request_digest': row[0], 'bundle_digest': row[1], 'bundle': bundle}

    def commit_run(self, run_id, request_digest, entity, close_period, bundle):
        if not self._in_transaction:
            raise RuntimeError('run must be committed inside its source transaction')
        self.con.execute('INSERT INTO a4_runs(run_id,request_digest,entity,close_period,bundle_digest,bundle) VALUES (?,?,?,?,?,?)',
                         [identifier(run_id), request_digest, entity, iso_period(close_period), digest(bundle), canonical(bundle)])

    def attempt_event(self, attempt_id, run_id, request_digest, status, detail=''):
        if self._in_transaction:
            raise RuntimeError('attempt events must be outside the accounting transaction')
        self.con.execute('INSERT INTO a4_attempts(attempt_id,run_id,request_digest,status,detail) VALUES (?,?,?,?,?)',
                         [attempt_id, run_id, request_digest, status, detail])

    def attempt_history(self, run_id):
        return [dict(attempt_id=r[0], request_digest=r[1], created_ts=str(r[2]), status=r[3], detail=r[4])
                for r in self.con.execute('SELECT attempt_id,request_digest,created_ts,status,detail FROM a4_attempts WHERE run_id=? ORDER BY created_ts', [run_id]).fetchall()]

    def delivery_event(self, run_id, status, detail):
        self.con.execute('INSERT INTO a4_delivery(run_id,status,detail) VALUES (?,?,?)', [run_id, status, detail])

    def delivery_history(self, run_id):
        return [dict(created_ts=str(r[0]), status=r[1], detail=r[2]) for r in self.con.execute('SELECT created_ts,status,detail FROM a4_delivery WHERE run_id=? ORDER BY created_ts', [run_id]).fetchall()]

    def close(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
