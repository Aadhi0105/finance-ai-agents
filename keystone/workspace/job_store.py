"""Private admission and execution ledger; no browser transition or deletion API."""
from contextlib import contextmanager
import fcntl
import hashlib
import os
import re
from pathlib import Path
from datetime import datetime
import sqlite3
import stat
import threading

from keystone.maintenance import control_write_gate, gate
from keystone.operation import sync_directory
from .catalog import read_json
from .job_contract import (JobError, JobRecord, MAX_PENDING_JOBS,
                           MAX_RETAINED_JOBS, canonical, fingerprint)
from .job_execution import JobExecution, PreparedResult, claimed, changed, TERMINAL, initial_execution, parse_execution
from .job_contract import now
from .job_contract import parse_job_record

APPLICATION_ID = 0x4B534A31
MAX_STORE_BYTES = 64_000_000
MAX_ANALYSIS_BYTES = 100_000_000
ANALYSIS_RESERVATION_BYTES = 16_000_000
MAX_ANALYSIS_FILES = 60000


def private_member(path, *, directory=False):
    info = path.lstat()
    kind_ok = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    if not kind_ok or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise JobError('job_store_unavailable')
    return info.st_dev, info.st_ino


def exclusive_file(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(fd)


class JobStore:
    @classmethod
    def reader(cls, directory, workspace):
        """Existing ledger only; no leases, migrations, recovery or writable DB."""
        value=cls.__new__(cls)
        value.root=Path(directory).absolute();value.workspace=Path(workspace).absolute()
        if any(p.is_symlink() for p in (value.root,*value.root.parents,value.workspace)):
            raise JobError('job_store_unavailable')
        value.path=value.root/'jobs.sqlite3';value._lease=None;value.closed=False
        value.worker=False;value.queue_only=False;value._read_only=True
        value.binding=hashlib.sha256(str(value.workspace.resolve()).encode()).hexdigest()
        value._root_identity=private_member(value.root,directory=True)
        value._db_identity=private_member(value.path)
        with value._connect(write=False):pass
        return value

    def __init__(self, directory, workspace, *, worker=False):
        self.root = Path(directory).absolute()
        self.workspace = Path(workspace).absolute()
        self.path = self.root / 'jobs.sqlite3'
        self._lease = None
        self._lock = threading.Lock()
        self.worker = worker
        self.queue_only = False
        self.closed = False
        try:
            if (any(p.is_symlink() for p in [self.root, *self.root.parents])
                    or self.root.resolve() == self.workspace.resolve()
                    or self.root.resolve() in self.workspace.resolve().parents
                    or self.workspace.resolve() in self.root.resolve().parents):
                raise JobError('job_store_unavailable')
            self.binding = hashlib.sha256(str(self.workspace.resolve()).encode()).hexdigest()
            if worker and not self.path.exists():
                raise JobError('job_store_unavailable')
            with (gate() if worker else control_write_gate()):
                self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
                self._root_identity = private_member(self.root, directory=True)
                lease = self.root / ('worker.lock' if worker else 'session.lock')
                prior_control = lease.exists() or lease.is_symlink() or (self.root / 'access-token.key').exists() or (self.root / 'access-token.key').is_symlink()
                if not lease.exists() and not lease.is_symlink():
                    exclusive_file(lease)
                private_member(lease)
                self._lease = os.open(lease, os.O_RDWR | os.O_NOFOLLOW)
                fcntl.flock(self._lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                new = not self.path.exists() and not self.path.is_symlink()
                if new and prior_control:
                    # Missing identity history is not permission to create a new
                    # queue under the old control directory and repeat requests.
                    raise JobError('job_store_unavailable')
                if new:
                    exclusive_file(self.path)
                self._db_identity = private_member(self.path)
                with self._connect(initial=True) as con:
                    if new:
                        con.executescript('''
                            BEGIN IMMEDIATE;
                            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                            CREATE TABLE jobs (
                                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                                job_id TEXT NOT NULL UNIQUE,
                                key_hash TEXT NOT NULL UNIQUE,
                                request_sha256 TEXT NOT NULL,
                                created_at TEXT NOT NULL,
                                record_json TEXT NOT NULL,
                                record_sha256 TEXT NOT NULL
                            );
                            CREATE TABLE events (
                                job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
                                event TEXT NOT NULL CHECK (event = 'admitted'),
                                created_at TEXT NOT NULL
                            );
                        ''')
                        con.execute('INSERT INTO metadata VALUES (?, ?)', ('workspace', self.binding))
                        con.execute(f'PRAGMA application_id={APPLICATION_ID}')
                        con.execute('PRAGMA user_version=1')
                        con.commit()
                    self._upgrade(con)
                    self._validate_database(con)
                sync_directory(self.root)
                sync_directory(self.root.parent)
        except Exception as exc:
            self.close()
            if isinstance(exc, JobError):
                raise
            raise JobError('job_control_busy' if isinstance(exc, BlockingIOError) else 'job_store_unavailable') from None

    def close(self):
        self.closed = True
        if self._lease is not None:
            os.close(self._lease)
            self._lease = None

    def _validate_database(self, con):
        self.validate_binding(con, self.binding)

    @staticmethod
    def validate_binding(con, binding):
        if (con.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                or con.execute('PRAGMA user_version').fetchone()[0] != 2
                or con.execute('SELECT value FROM metadata WHERE key=?', ('workspace',)).fetchone() != (binding,)
                or con.execute('PRAGMA journal_mode').fetchone()[0] != 'delete'
                or con.execute('PRAGMA quick_check').fetchone()[0] != 'ok'
                or con.execute('PRAGMA foreign_key_check').fetchone() is not None
                or con.execute('''SELECT j.job_id FROM jobs j LEFT JOIN executions x ON x.job_id=j.job_id
                    WHERE x.job_id IS NULL OR NOT EXISTS(SELECT 1 FROM events e WHERE e.job_id=j.job_id
                    AND e.event='admitted' AND e.created_at=j.created_at) LIMIT 1''').fetchone() is not None):
            raise JobError('job_store_unavailable')

    def _upgrade(self, con):
        version = con.execute('PRAGMA user_version').fetchone()[0]
        if version == 2:
            return
        if (version != 1 or self.worker
                or con.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                or con.execute('SELECT value FROM metadata WHERE key=?', ('workspace',)).fetchone() != (self.binding,)
                or con.execute('PRAGMA journal_mode').fetchone()[0] != 'delete'):
            raise JobError('job_store_unavailable')
        rows = con.execute('SELECT * FROM jobs ORDER BY sequence').fetchall()
        events = con.execute('SELECT job_id,event,created_at FROM events').fetchall()
        records = [self._record(row) for row in rows]
        if sorted(events) != sorted((r['job_id'], 'admitted', r['created_at']) for r in records):
            raise JobError('job_store_unavailable')
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute('''CREATE TABLE new_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL REFERENCES jobs(job_id), event TEXT NOT NULL, created_at TEXT NOT NULL)''')
            con.executemany('INSERT INTO new_events(job_id,event,created_at) VALUES (?,?,?)',
                            [(r['job_id'], 'admitted', r['created_at']) for r in records])
            con.execute('DROP TABLE events')
            con.execute('ALTER TABLE new_events RENAME TO events')
            con.execute("CREATE UNIQUE INDEX one_admission ON events(job_id) WHERE event='admitted'")
            con.execute('''CREATE TABLE executions(job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
                status TEXT NOT NULL, record_json TEXT NOT NULL, record_sha256 TEXT NOT NULL)''')
            raw = JobExecution().model_dump()
            con.executemany('INSERT INTO executions VALUES (?,?,?,?)',
                            [(r['job_id'], 'queued', canonical(raw), fingerprint(raw)) for r in records])
            con.execute('PRAGMA user_version=2')
            con.commit()
        except BaseException:
            con.rollback()
            raise

    @contextmanager
    def _connect(self, *, write=True, initial=False):
        if getattr(self,'_read_only',False) and (write or initial):
            raise JobError('job_store_unavailable')
        if (self.closed or private_member(self.root, directory=True) != self._root_identity
                or private_member(self.path) != self._db_identity
                or self.path.stat().st_size > MAX_STORE_BYTES):
            raise JobError('job_store_unavailable')
        for suffix in ('-journal', '-wal', '-shm'):
            member = self.path.with_name(self.path.name + suffix)
            try:
                private_member(member)
            except FileNotFoundError:
                # A DELETE-journal commit may unlink this between metadata
                # probes. Absence is normal; linked, exposed or unreadable
                # companions still fail. SQLite retains its own locking and
                # the read transaction below keeps all records consistent.
                pass
        con = sqlite3.connect(self.path.as_uri() + ('?mode=rw' if write else '?mode=ro'), uri=True,
                              isolation_level=None, timeout=1)
        try:
            con.execute('PRAGMA foreign_keys=ON')
            if not write:
                # Execution state and its audit event are committed together.
                # Keep all validation/record/event SELECTs on the same snapshot
                # so a concurrent worker commit cannot look like corruption.
                con.execute('BEGIN')
            if not initial:
                self._validate_database(con)
            if write:
                # DELETE journals avoid an unaccounted WAL dependency. EXTRA also
                # flushes the parent directory when the rollback journal is removed.
                con.execute('PRAGMA synchronous=EXTRA')
            yield con
        finally:
            con.close()

    @contextmanager
    def _write(self):
        if not self._lock.acquire(timeout=1):
            raise JobError('job_control_busy')
        try:
            with (gate() if self.worker else control_write_gate(queue_only=self.queue_only)), self._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                try:
                    yield con
                    con.commit()
                except BaseException:
                    con.rollback()
                    raise
        except BlockingIOError:
            raise JobError('job_control_busy') from None
        finally:
            self._lock.release()

    @staticmethod
    def _record(row):
        try:
            if row is None or len(row[5]) > 65_536:
                raise ValueError('Missing or oversized job record.')
            raw = read_json(row[5].encode())
            record = parse_job_record(raw)
            if (fingerprint(raw) != row[6] or record.job_id != row[1]
                    or record.request_sha256 != row[3] or record.created_at != row[4]):
                raise ValueError('Inconsistent job record.')
            return record.model_dump()
        except (ValueError, TypeError, KeyError):
            raise JobError('job_store_unavailable') from None

    def existing(self, key_hash, request_sha256):
        with self._connect(write=False) as con:
            return self._existing(con, key_hash, request_sha256)

    def _existing(self, con, key_hash, request_sha256):
        row = con.execute('SELECT * FROM jobs WHERE key_hash=?', (key_hash,)).fetchone()
        if row is None:
            return None
        record = self._record(row)
        if record['request_sha256'] != request_sha256:
            raise JobError('job_request_conflict', 409)
        return self._public(con, row)

    def admit(self, key_hash, record):
        with self._write() as con:
            old = self._existing(con, key_hash, record.request_sha256)
            if old is not None:
                return old, True
            count = con.execute('SELECT count(*) FROM jobs').fetchone()[0]
            pending = con.execute("SELECT count(*) FROM executions WHERE status IN ('queued','running')").fetchone()[0]
            if count >= MAX_RETAINED_JOBS or pending >= MAX_PENDING_JOBS:
                raise JobError('job_capacity_reached', 409)
            if record.schema_version in {4,5}:
                reserved=con.execute("SELECT count(*) FROM jobs j JOIN executions e USING(job_id) WHERE json_extract(j.record_json,'$.schema_version') IN (4,5) AND e.status IN ('queued','running')").fetchone()[0]*ANALYSIS_RESERVATION_BYTES
                total=0;files=0
                for root in (self.root/'jobs',self.root/'operations',self.workspace):
                    if root.exists():
                        for path in root.rglob('*'):
                            private_member(path,directory=path.is_dir())
                            if path.is_file():total+=path.stat().st_size;files+=1
                            if total+reserved+ANALYSIS_RESERVATION_BYTES>MAX_ANALYSIS_BYTES or files>MAX_ANALYSIS_FILES:raise JobError('job_capacity_reached',409)
            raw = record.model_dump()
            con.execute('INSERT INTO jobs(job_id,key_hash,request_sha256,created_at,record_json,record_sha256) VALUES (?,?,?,?,?,?)',
                        (record.job_id, key_hash, record.request_sha256, record.created_at, canonical(raw), fingerprint(raw)))
            con.execute('INSERT INTO events(job_id,event,created_at) VALUES (?,?,?)', (record.job_id, 'admitted', record.created_at))
            execution = initial_execution(record).model_dump()
            con.execute('INSERT INTO executions VALUES (?,?,?,?)', (record.job_id, 'queued', canonical(execution), fingerprint(execution)))
            public = self._public(con, con.execute('SELECT * FROM jobs WHERE job_id=?', (record.job_id,)).fetchone())
        return public, False

    def get(self, job_id):
        with self._connect(write=False) as con:
            row = con.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone()
            if row is None:
                raise JobError('job_not_found', 404)
            record = self._public(con, row)
            events = con.execute('SELECT event,created_at FROM events WHERE job_id=? ORDER BY event_id', (job_id,)).fetchall()
            allowed = {'admitted','claimed','inputs_verified','prepared','registered','failed','source_changed',
                       'interrupted','delivery_failed','recovered'}
            if (len(events) > 50 or any(e not in allowed or len(t)>80 or datetime.fromisoformat(t).utcoffset() is None
                                       for e,t in events)):
                raise JobError('job_store_unavailable')
            return dict(job=record, events=[dict(event=e, created_at=t) for e, t in events])

    def list(self, limit, before):
        with self._connect(write=False) as con:
            cursor = 2**63 - 1
            if before is not None:
                row = con.execute('SELECT sequence FROM jobs WHERE job_id=?', (before,)).fetchone()
                if row is None:
                    raise JobError('job_request_invalid', 422)
                cursor = row[0]
            rows = con.execute('SELECT * FROM jobs WHERE sequence<? ORDER BY sequence DESC LIMIT ?', (cursor, limit + 1)).fetchall()
            jobs = [self._public(con, row) for row in rows[:limit]]
            return dict(jobs=jobs, next_cursor=jobs[-1]['job_id'] if len(rows) > limit else None,
                        worker_enabled=False)

    @staticmethod
    def _execution(con, job_id):
        row = con.execute('SELECT status,record_json,record_sha256 FROM executions WHERE job_id=?', (job_id,)).fetchone()
        if row is None:
            raise JobError('job_store_unavailable')
        raw = read_json(row[1].encode())
        execution = parse_execution(raw)
        bound = parse_job_record(JobStore._record(con.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone()))
        if (execution.schema_version != (3 if bound.schema_version in {4,5} else 2 if bound.schema_version == 3 else 1)
                or row[0] != execution.status or fingerprint(raw) != row[2]
                or execution.result is not None and execution.result.run_id != 'result-' + job_id[4:]):
            raise JobError('job_store_unavailable')
        latest = con.execute('SELECT event FROM events WHERE job_id=? ORDER BY event_id DESC LIMIT 1', (job_id,)).fetchone()
        expected = {'queued':{'admitted'},'running':{'claimed','inputs_verified','prepared'},
            'completed':{'registered','recovered'},'review_required':{'registered','recovered'},
            'failed':{'failed'},'source_changed':{'source_changed'},'delivery_failed':{'delivery_failed'},
            'outcome_unknown':{'interrupted'}}
        if latest is None or latest[0] not in expected[execution.status]:
            raise JobError('job_store_unavailable')
        return execution

    def _public(self, con, row):
        record = self._record(row)
        execution = self._execution(con, record['job_id'])
        held=self.restoration_hold(con,record['job_id'])
        if held and execution.status!='queued':raise JobError('job_store_unavailable')
        return {**record, 'status': execution.status, 'execution': execution.model_dump(),
                'restoration_hold': held}

    @staticmethod
    def restoration_hold(con, job_id):
        row=con.execute('SELECT value FROM metadata WHERE key=?',('restore_hold:'+job_id,)).fetchone()
        if row is None:return False
        value=read_json(row[0].encode())
        if (value.get('schema_version')!=1 or type(value.get('held')) is not bool
                or value.get('job_id')!=job_id or not isinstance(value.get('snapshot_id'),str)
                or re.fullmatch(r'[a-f0-9]{32}',value['snapshot_id']) is None
                or not isinstance(value.get('manifest_sha256'),str)
                or re.fullmatch(r'[a-f0-9]{64}',value['manifest_sha256']) is None
                or value['held'] and (value.get('reviewed_at') is not None or value.get('reason') is not None)
                or not value['held'] and (not isinstance(value.get('reviewed_at'),str)
                    or datetime.fromisoformat(value['reviewed_at']).utcoffset() is None
                    or not isinstance(value.get('reason'),str) or not 1<=len(value['reason'])<=240)):
            raise JobError('job_store_unavailable')
        return value['held']

    @staticmethod
    def next_queued(con):
        for row in con.execute("SELECT j.* FROM jobs j JOIN executions x ON x.job_id=j.job_id WHERE x.status='queued' ORDER BY j.sequence").fetchall():
            if not JobStore.restoration_hold(con,row[1]):return row
        return None

    def immutable(self, job_id):
        with self._connect(write=False) as con:
            return parse_job_record(self._record(con.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone()))

    def _save_execution(self, con, job_id, execution, event):
        if not self.worker:
            raise JobError('job_store_unavailable')
        old = self._execution(con, job_id)
        allowed = (old.status == 'queued' and execution.status == 'running'
                   or old.status == 'running' and execution.status != 'queued'
                   or old.status in {'delivery_failed','outcome_unknown'} and execution.status in {'completed','review_required'}
                   or old.schema_version in {2,3} and old.status == 'failed' and execution.status == 'review_required'
                      and execution.reason == 'recovered' and (getattr(execution,'accounting_commit_sha256',None) or getattr(execution,'analysis_commit_sha256',None)))
        if not allowed or con.execute('SELECT count(*) FROM events WHERE job_id=?', (job_id,)).fetchone()[0] >= 50:
            raise JobError('job_recovery_unavailable', 409)
        raw = execution.model_dump()
        con.execute('UPDATE executions SET status=?,record_json=?,record_sha256=? WHERE job_id=?',
                    (execution.status, canonical(raw), fingerprint(raw), job_id))
        con.execute('INSERT INTO events(job_id,event,created_at) VALUES (?,?,?)', (job_id, event, now()))

    def claim_next(self):
        with self._write() as con:
            row = self.next_queued(con)
            if row is None:
                return None
            record = parse_job_record(self._record(row))
            self._save_execution(con, record.job_id, claimed(record), 'claimed')
            return record

    def update_execution(self, job_id, *, event, **values):
        with self._write() as con:
            execution = changed(self._execution(con, job_id), **values)
            self._save_execution(con, job_id, execution, event)
            return execution

    def interrupt_running(self):
        with self._write() as con:
            for job_id, in con.execute("SELECT job_id FROM executions WHERE status='running'").fetchall():
                current = self._execution(con, job_id)
                self._save_execution(con, job_id, changed(current, status='outcome_unknown',
                    finished_at=now(), reason='interrupted'), 'interrupted')
