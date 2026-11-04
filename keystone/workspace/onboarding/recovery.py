"""Explicit, atomic private-workspace restoration. Never execute saved work.

Only mutable control metadata is rebound. Saved inputs, admissions, operation
receipts, accounting proofs and registered reports retain their original bytes.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from datetime import datetime

from keystone import storage
from ..catalog import Catalog, read_json, run_identity
from ..job_contract import JobError, canonical, fingerprint, now, parse_job_record
from ..job_execution import changed
from ..job_files import write_new
from ..job_store import JobStore, MAX_STORE_BYTES, private_member
from . import contracts as c
from .store import InputStore


def path_binding(path):
    return hashlib.sha256(str(Path(path).absolute()).encode()).hexdigest()


def validate_inputs(inputs):
    """Check every ledger object, retained version, permission and accounting head."""
    with inputs.connect() as con:
        for kind, ident in con.execute('SELECT kind,id FROM objects').fetchall():
            inputs._object(con,kind,ident)
        for ident, in con.execute('SELECT id FROM imports').fetchall():
            inputs._attempt(con,ident)
    # This checks current permission evidence and every accepted version; staged
    # validator databases and missing accounting stores remain explicit refusals.
    inputs.backup_plan()
    from .close_state import inspect
    accounting=inputs.root/'accounting'
    if accounting.exists():
        for member in accounting.iterdir():inspect(inputs,member.name)


def prepare_restore(stage, final, manifest):
    sources={s['name']:s for s in manifest['plan']['sources']}
    required={'workspace.json','inputs.sqlite3','inputs','staging','permissions','reports','control/jobs.sqlite3'}
    if not required<=sources.keys():raise ValueError('Incomplete private workspace inventory')
    original=Path(sources['workspace.json']['path']).parent
    if (not original.is_absolute() or original==final or original in final.parents or final in original.parents
            or any(Path(s['path'])!=original/name for name,s in sources.items())
            or any(name not in required|{'control/jobs','control/operations','control/restore-history.json'}
                   and not (name.startswith('accounting/entity-') and name.endswith('/state.duckdb')) for name in sources)):
        raise ValueError('Private inventory identity mismatch')
    # Generic snapshots retain files, not empty directory topology. Reconstruct
    # only the fixed application directories, never a path taken from a payload.
    for name in ('inputs','staging','permissions','reports','reports/runs','control','control/jobs','control/operations'):
        (stage/name).mkdir(parents=True,exist_ok=True,mode=0o700)
        private_member(stage/name,directory=True)
    inputs=InputStore(stage)
    validate_inputs(inputs)
    catalog=Catalog(stage/'reports');inventory=catalog.load()
    if inventory.schema_version!=3 or inventory.workspace_id!=inputs.descriptor['id']:
        raise ValueError('Restored report identity mismatch')
    path=stage/'control/jobs.sqlite3';private_member(path)
    if path.stat().st_size>MAX_STORE_BYTES:raise ValueError('Oversized private ledger')
    info=dict(schema_version=1,snapshot_id=manifest['snapshot_id'],
              manifest_sha256=c.sha(storage.canonical(manifest).encode()),restored_at=now(),
              workspace_id=inputs.descriptor['id'],previous_root=str(original),root=str(final),
              queued_jobs_held=[],interrupted_jobs=[],financial_approval=False)
    history_path=stage/'control/restore-history.json'
    history=read_json(history_path.read_bytes()) if history_path.exists() else []
    if not isinstance(history,list) or len(history)>=100:raise ValueError('Invalid restore history')
    probe=SimpleNamespace(root=stage/'control',workspace=stage/'reports')
    with sqlite3.connect(path,isolation_level=None) as con:
        con.execute('PRAGMA foreign_keys=ON');con.execute('PRAGMA synchronous=EXTRA')
        con.execute('BEGIN IMMEDIATE')
        JobStore.validate_binding(con,path_binding(original/'reports'))
        seal=con.execute("SELECT value FROM metadata WHERE key='restore_history_sha256'").fetchone()
        if (bool(history)!=bool(seal) or seal and seal[0]!=c.fingerprint(history)):
            raise ValueError('Restore history mismatch')
        rows=con.execute('SELECT * FROM jobs ORDER BY sequence').fetchall()
        if len(rows)>1000:raise ValueError('Oversized private history')
        records={}
        for row in rows:
            raw=JobStore._record(row);record=parse_job_record(raw)
            if record.schema_version not in {2,3,4,5} or record.source.workspace_id!=inputs.descriptor['id']:
                raise ValueError('Restored job identity mismatch')
            execution=JobStore._execution(con,record.job_id)
            if JobStore.restoration_hold(con,record.job_id) and execution.status!='queued':
                raise ValueError('Restored queue hold disagrees with execution')
            events=con.execute('SELECT event,created_at FROM events WHERE job_id=? ORDER BY event_id',(record.job_id,)).fetchall()
            allowed={'admitted','claimed','inputs_verified','prepared','registered','failed','source_changed',
                     'interrupted','delivery_failed','recovered'}
            if (not 1<=len(events)<=50 or events[0]!=('admitted',record.created_at)
                    or sum(e=='admitted' for e,_ in events)!=1
                    or any(e not in allowed or len(t)>80 or datetime.fromisoformat(t).utcoffset() is None for e,t in events)):
                raise ValueError('Invalid restored execution events')
            from .execution import current_version,verified_result
            current_version(probe,record)
            if execution.result is not None:
                verified_result(probe,record,execution.result)
            if execution.status=='queued':
                hold=dict(schema_version=1,job_id=record.job_id,snapshot_id=info['snapshot_id'],
                          manifest_sha256=info['manifest_sha256'],held=True,reviewed_at=None,reason=None)
                con.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('restore_hold:'+record.job_id,canonical(hold)))
                info['queued_jobs_held'].append(record.job_id)
            if execution.status=='running':
                interrupted=changed(execution,status='outcome_unknown',finished_at=now(),reason='interrupted')
                raw=interrupted.model_dump()
                con.execute('UPDATE executions SET status=?,record_json=?,record_sha256=? WHERE job_id=?',
                            (interrupted.status,canonical(raw),fingerprint(raw),record.job_id))
                con.execute('INSERT INTO events(job_id,event,created_at) VALUES (?,?,?)',(record.job_id,'interrupted',now()))
                info['interrupted_jobs'].append(record.job_id)
            records[record.job_id]=(record,execution)
        for run in inventory.runs:
            pair=records.get(run.input_origin.job_id)
            if (pair is None or pair[1].result is None
                    or pair[1].result.run_sha256!=fingerprint(run_identity(run))):
                raise ValueError('Registered result disagrees with job history')
            for artifact in run.artifacts:catalog.read(run.id,artifact)
        registered={r.input_origin.job_id for r in inventory.runs}
        if any(execution.status in {'completed','review_required'} and ident not in registered
               for ident,(_,execution) in records.items()):
            raise ValueError('Completed job is missing its registered result')
        history.append(info)
        # Only the binding and recovery controls change, in the copied ledger.
        con.execute("UPDATE metadata SET value=? WHERE key='workspace'",(path_binding(final/'reports'),))
        con.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('restore_history_sha256',c.fingerprint(history)))
        con.commit()
    if history_path.exists():history_path.unlink()
    write_new(history_path,c.canonical(history))
    return [dict(kind='private_workspace_recovery',**info)]


def restore_private(source,destination):
    return storage.restore(source,destination,prepare=prepare_restore)


def release_restored_job(store,job_id,reason):
    """Local operator rechecks one never-started request; no dispatch or approval."""
    if not store.worker or not isinstance(reason,str) or not 1<=len(reason.strip())<=240:
        raise JobError('job_recovery_unavailable',409)
    with store._write() as con:
        if not store.restoration_hold(con,job_id) or store._execution(con,job_id).status!='queued':
            raise JobError('job_recovery_unavailable',409)
        record=parse_job_record(store._record(con.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()))
        from .execution import current_version
        inputs,_=current_version(store,record,executing=record.schema_version in {4,5})
        if record.schema_version==3:
            from .close_state import current
            current(inputs,record.accounting_source)
        if (store.root/'jobs'/job_id).exists() or (store.root/'operations'/record.operation_id).exists():
            raise JobError('job_recovery_unavailable',409)
        row=con.execute('SELECT value FROM metadata WHERE key=?',('restore_hold:'+job_id,)).fetchone()
        hold=json.loads(row[0]);hold.update(held=False,reviewed_at=now(),reason=reason.strip())
        con.execute('UPDATE metadata SET value=? WHERE key=?',(canonical(hold),'restore_hold:'+job_id))
    return dict(job_id=job_id,status='queued',restoration_hold=False,processing_started=False,financial_approval=False)
