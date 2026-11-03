"""Server-owned per-company accounting state and atomic close attribution.

Only the worker/operator opens canonical state for writing. HTTP report reads use
the immutable registry proof. Attempts/delivery logs do not change a financial pin.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil

import duckdb

from agent4.state import VarianceStore, digest
from ..job_contract import JobError, now
from ..job_store import private_member
from . import contracts as c

TABLES = {
    'a4_versions': 'kind,version,sequence,digest,metadata,row_count',
    'a4_rows': 'kind,version,line,period,amount_cents,prob_hit,evidence',
    'a4_runs': 'run_id,request_digest,entity,close_period,bundle_digest,bundle',
    'a4_heads': 'entity,run_id,close_period',
}


def state_path(inputs, entity_id):
    from .store import ident
    path = inputs.root / 'accounting' / ident(entity_id) / 'state.duckdb'
    for member in (path.parent.parent, path.parent):
        if member.exists() or member.is_symlink(): private_member(member, directory=True)
    if path.exists() or path.is_symlink():
        private_member(path)
        if path.stat().st_size > c.MAX_INPUT_BYTES: raise c.InputError('input_capacity', 409)
    wal = Path(str(path) + '.wal')
    if wal.exists() or wal.is_symlink(): private_member(wal)
    return path


@contextmanager
def open_state(path, *, write=False):
    path = Path(path)
    if not write and Path(str(path) + '.wal').exists():
        raise c.InputError('input_unavailable', 503)
    if write:
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        store = VarianceStore(path)
        if str(path) != ':memory:': os.chmod(path, 0o600)
        store.con.execute('CREATE TABLE IF NOT EXISTS keystone_close_commits (job_id VARCHAR PRIMARY KEY, proof VARCHAR, sha256 VARCHAR)')
    else:
        store = VarianceStore.__new__(VarianceStore)
        store.path = str(path); store._in_transaction = False
        store.con = duckdb.connect(str(path), read_only=True)
    try: yield store
    finally: store.close()


def domain(store=None):
    return {table: [] if store is None else [list(row) for row in store.con.execute(
        'SELECT ' + columns + ' FROM ' + table + ' ORDER BY ALL').fetchall()]
        for table, columns in TABLES.items()}


def summary(inputs, entity_id, store=None):
    """A semantic generation, independent of checkpoint bytes or failed attempts."""
    values = domain(store); proofs = []
    if store is not None:
        for job_id, raw, sha in store.con.execute('SELECT job_id,proof,sha256 FROM keystone_close_commits ORDER BY job_id').fetchall():
            value = json.loads(raw)
            if (c.fingerprint(value) != sha or value['job_id'] != job_id
                    or value['workspace_id'] != inputs.descriptor['id'] or value['entity_id'] != entity_id):
                raise c.InputError('input_unavailable', 503)
            proofs.append(value)
        runs = {row[0]: row for row in values['a4_runs']}
        if set(runs) != {p['run_id'] for p in proofs} or len(runs) != len(proofs):
            raise c.InputError('input_unavailable', 503)
        from agent4.report import validate_bundle
        for proof in proofs:
            saved = store.get_run(proof['run_id'])
            validate_bundle(saved)
            if saved['bundle_digest'] != proof['bundle_digest'] or saved['request_digest'] != proof['native_request_sha256']:
                raise c.InputError('input_unavailable', 503)
        if proofs:
            heads = values['a4_heads']
            if len(heads) != 1: raise c.InputError('input_unavailable', 503)
            head = next((p for p in proofs if p['run_id'] == heads[0][1]), None)
            if head is None or head['post_domain_sha256'] != c.fingerprint(values):
                raise c.InputError('input_unavailable', 503)
        elif any(values.values()): raise c.InputError('input_unavailable', 503)
    lineage = sorted({v for p in proofs for v in p['lineage_versions']})
    scope = dict(workspace_id=inputs.descriptor['id'], entity_id=entity_id)
    return dict(**scope, generation_sha256=c.fingerprint(dict(**scope, domain=values, proofs=proofs)), lineage_versions=lineage)


def inspect(inputs, entity_id, *, recovery=False):
    path = state_path(inputs, entity_id)
    if not path.exists():
        if Path(str(path)+'.wal').exists(): raise c.InputError('input_unavailable', 503)
        # Once a close intent exists, a missing canonical DB is lost state,
        # never evidence that the attempted close did not commit.
        with inputs.connect() as con:
            for id_, in con.execute("SELECT id FROM objects WHERE kind='close_intent'").fetchall():
                if inputs._object(con,'close_intent',id_)['entity_id'] == entity_id:
                    raise c.InputError('input_unavailable',503)
        return summary(inputs, entity_id)
    with open_state(path, write=recovery) as store: return summary(inputs, entity_id, store)


def check_lineage(inputs, versions, entity_id):
    classifications = set()
    for id_ in versions:
        version = inputs.version(id_)
        if version['contract']['metadata']['dataset']['entity_id'] != entity_id:
            raise c.InputError('input_unavailable', 503)
        classifications.add(version['contract']['policy']['classification'])
    return next(iter(classifications)) if len(classifications) == 1 else 'mixed'


def unresolved(inputs, entity_id, *, except_job=None):
    with inputs.connect() as con:
        for id_, in con.execute("SELECT id FROM objects WHERE kind='close_intent'").fetchall():
            intent = inputs._object(con, 'close_intent', id_)
            if intent['entity_id'] == entity_id and id_ != except_job:
                row = con.execute("SELECT 1 FROM objects WHERE kind='close_resolution' AND id=?", ('resolved-'+id_,)).fetchone()
                if row is None: raise c.InputError('input_busy', 409)


def current(inputs, pin, *, except_job=None):
    pin = c.AccountingSource.model_validate(pin).model_dump()
    unresolved(inputs, pin['entity_id'], except_job=except_job)
    if inspect(inputs, pin['entity_id']) != pin: raise c.InputError('input_conflict', 409)
    check_lineage(inputs, pin['lineage_versions'], pin['entity_id'])
    return pin


def validation_copy(inputs, entity_id, folder):
    unresolved(inputs, entity_id)
    pin = inspect(inputs, entity_id)
    check_lineage(inputs, pin['lineage_versions'], entity_id)
    path = state_path(inputs, entity_id)
    if path.exists():
        target = folder / 'predecessor.duckdb'
        # Financial mutator gate excludes every cooperating writer here.
        with target.open('xb') as out, path.open('rb') as src:
            os.chmod(target, 0o600); shutil.copyfileobj(src, out); out.flush(); os.fsync(out.fileno())
    return pin


def begin(inputs, record):
    pin = current(inputs, record.accounting_source, except_job=record.job_id)
    path=state_path(inputs,pin['entity_id'])
    if not path.exists():
        path.parent.parent.mkdir(mode=0o700,exist_ok=True)
        path.parent.mkdir(mode=0o700,exist_ok=True)
        with open_state(path,write=True) as state:
            if summary(inputs,pin['entity_id'],state) != pin: raise JobError('job_source_unavailable',409)
            state.con.execute('CHECKPOINT')
        from ..job_files import flush_tree
        flush_tree(path.parent.parent)
    value = dict(job_id=record.job_id, entity_id=pin['entity_id'], source=record.source.model_dump(),
                 request_sha256=record.request_sha256, accounting_source=pin, created_at=now())
    with inputs.write() as con: inputs._put(con, 'close_intent', record.job_id, value)


def put_once(inputs, kind, id_, value):
    with inputs.write() as con:
        if con.execute('SELECT 1 FROM objects WHERE id=?', (id_,)).fetchone():
            if inputs._object(con, kind, id_) != value: raise c.InputError('input_conflict', 409)
        else: inputs._put(con, kind, id_, value)


def calculate(inputs, record, request):
    pin = current(inputs, record.accounting_source, except_job=record.job_id)
    intent = inputs.object('close_intent', record.job_id)
    if intent['source'] != record.source.model_dump() or intent['accounting_source'] != pin:
        raise JobError('job_source_unavailable', 409)
    lineage = sorted(set(pin['lineage_versions'] + [record.source.version_id]))
    classification = check_lineage(inputs, lineage, pin['entity_id'])
    path = state_path(inputs, pin['entity_id'])
    from agent4.close import execute_close
    with open_state(path, write=True) as store:
        if summary(inputs, pin['entity_id'], store) != pin or store.get_run(request['run_id']) is not None:
            raise JobError('job_source_unavailable', 409)
        def attribute(state, saved):
            proof = dict(schema_version=1, job_id=record.job_id, workspace_id=record.source.workspace_id,
                entity_id=pin['entity_id'], source=record.source.model_dump(), request_sha256=record.request_sha256,
                pre_generation_sha256=pin['generation_sha256'], post_domain_sha256=c.fingerprint(domain(state)),
                run_id=request['run_id'], native_request_sha256=digest(request), bundle_digest=saved['bundle_digest'],
                lineage_versions=lineage, classification=classification, committed_at=now())
            state.con.execute('INSERT INTO keystone_close_commits VALUES (?,?,?)',
                              [record.job_id, c.canonical(proof).decode(), c.fingerprint(proof)])
        saved = execute_close(store, request, commit_hook=attribute)
        store.con.execute('CHECKPOINT')
    return committed(inputs, record)


def committed(inputs, record, *, recovery=False):
    """Explicit recovery may replay a database WAL, never a financial calculation."""
    pin = record.accounting_source
    path = state_path(inputs, pin['entity_id'])
    if not path.exists(): raise JobError('job_recovery_unavailable', 409)
    with open_state(path, write=recovery) as store:
        summary(inputs, pin['entity_id'], store)
        row = store.con.execute('SELECT proof,sha256 FROM keystone_close_commits WHERE job_id=?', [record.job_id]).fetchone()
        if row is None: raise JobError('job_recovery_unavailable', 409)
        proof = json.loads(row[0]); saved = store.get_run(proof['run_id'])
        if (c.fingerprint(proof) != row[1] or proof['source'] != record.source.model_dump()
                or proof['request_sha256'] != record.request_sha256 or proof['pre_generation_sha256'] != pin['generation_sha256']
                or saved['bundle_digest'] != proof['bundle_digest']): raise JobError('job_recovery_unavailable', 409)
    check_lineage(inputs, proof['lineage_versions'], pin['entity_id'])
    return saved, proof


def remember(inputs, proof):
    put_once(inputs, 'close_commit', 'commit-'+proof['job_id'], proof)
    return c.fingerprint(proof)


def resolve(inputs, record, *, no_commit=False):
    if no_commit:
        # This operator-only action is under worker lease + financial gate.
        intent=inputs.object('close_intent',record.job_id)
        if intent['source'] != record.source.model_dump(): raise JobError('job_recovery_unavailable',409)
        with inputs.connect() as con:
            if con.execute("SELECT 1 FROM objects WHERE id=?",('commit-'+record.job_id,)).fetchone():
                raise JobError('job_recovery_unavailable',409)
        actual = inspect(inputs, record.accounting_source['entity_id'], recovery=True)
        if actual != record.accounting_source: raise JobError('job_recovery_unavailable', 409)
        status = 'no_commit_verified'
    else:
        proof = inputs.object('close_commit', 'commit-'+record.job_id)
        if proof['source'] != record.source.model_dump(): raise JobError('job_recovery_unavailable', 409)
        status = 'committed_delivery_registered'
    value = dict(job_id=record.job_id, status=status)
    put_once(inputs, 'close_resolution', 'resolved-'+record.job_id, value)


def registry_proof(inputs, record):
    proof = inputs.object('close_commit', 'commit-'+record.job_id)
    if proof['source'] != record.source.model_dump() or proof['request_sha256'] != record.request_sha256:
        raise JobError('job_recovery_unavailable', 409)
    check_lineage(inputs, proof['lineage_versions'], proof['entity_id'])
    return proof
