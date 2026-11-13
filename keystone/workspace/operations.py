"""Read-only, bounded local operating observations; never repairs or executes work.

Each component has its own failure boundary. All output is structured and
allowlisted: no paths, payloads, credentials, raw exceptions or subprocess logs.
This is an observation across stores, not a transactionally consistent backup.
"""
import os
import shutil
import stat
from typing import Literal

from pydantic import Field

from .catalog import Record, ID
from .job_contract import JOB_ID, MAX_PENDING_JOBS, MAX_RETAINED_JOBS, now
from .job_execution import STATES
from .job_store import MAX_STORE_BYTES, MAX_ANALYSIS_BYTES, ANALYSIS_RESERVATION_BYTES, private_member
from .onboarding import contracts as c
from .review.notes import MAX_WORKSPACE_NOTES
from .review.corrections import MAX_CORRECTIONS
from .review.decisions import MAX_WORKSPACE_DECISIONS

MAX_SCAN_MEMBERS = 60_000
MAX_RESPONSE_BYTES = 1_500_000
INPUT_LEDGER_LIMIT = 64_000_000
JOB_STATES = ('queued','running','completed','review_required','source_changed','failed','outcome_unknown','delivery_failed')
IMPORT_STATES = ('reserved','receiving','validating','accepted','rejected','interrupted','delivery_failed')
COMPONENTS = ('jobs','inputs','reports','worker','storage')
Level = Literal['ok','attention','unavailable','disabled']
Code = Literal['job_records_checked','job_records_unavailable','input_database_readable','input_database_unavailable',
    'report_sources_checked','report_sources_held','report_inventory_unavailable','worker_process_running',
    'worker_not_enabled','worker_queue_waiting','worker_process_stopped','storage_observed','storage_near_limit',
    'storage_unavailable','recovery_inspection_required']


class Check(Record):
    key: Literal['jobs','inputs','reports','worker','storage']
    state: Level
    code: Code


class Capacity(Record):
    key: Literal['pending_jobs','retained_jobs','pending_imports','retained_imports','datasets','versions',
        'notes','corrections','decisions','input_ledger','job_ledger','input_storage','analysis_evidence']
    used: int | None = Field(ge=0)
    limit: int = Field(gt=0)
    state: Literal['ok','attention','unavailable']


class Job(Record):
    id: str = Field(pattern=JOB_ID)
    workflow: Literal['research','monitoring','events','news','close']
    status: STATES
    created_at: str
    started_at: str | None
    finished_at: str | None
    stage: Literal['admitted','claimed','inputs_verified','prepared','registered','failed','source_changed','interrupted','delivery_failed','recovered']
    timeout_seconds: int = Field(ge=1,le=600)
    restoration_hold: bool
    recovery_required: bool


class Import(Record):
    id: str = Field(pattern=r'^import-[a-f0-9]{32}$')
    state: Literal['reserved','receiving','validating','accepted','rejected','interrupted','delivery_failed']
    created_at: str


class Snapshot(Record):
    schema_version: Literal[1]
    kind: Literal['keystone.operations']
    workspace_id: str = Field(pattern=ID)
    observed_at: str
    state: Literal['ok','attention','unavailable']
    checks: list[Check] = Field(min_length=5,max_length=5)
    capacities: list[Capacity] = Field(min_length=13,max_length=13)
    jobs: list[Job] = Field(max_length=1000)
    job_total: int | None = Field(ge=0,le=1000)
    unreadable_jobs: int | None = Field(ge=0,le=1000)
    job_counts: dict[STATES,int] | None
    imports: list[Import] = Field(max_length=1000)
    import_total: int | None = Field(ge=0,le=1000)
    unreadable_imports: int | None = Field(ge=0,le=1000)
    report_total: int | None = Field(ge=0,le=100)
    held_reports: list[str] = Field(max_length=100)
    disk_free_bytes: int | None = Field(ge=0)
    disk_total_bytes: int | None = Field(ge=1)
    live_data_enabled: Literal[False]
    paid_models_enabled: Literal[False]
    financial_approval: Literal[False]
    production_release_approved: Literal[False]


def tree_usage(roots):
    """Fixed private roots only; bounded iteration, no symlinks/hardlinks followed."""
    totals=[];members=0
    for root in roots:
        size=0;pending=[root]
        while pending:
            folder=pending.pop();private_member(folder,directory=True)
            with os.scandir(folder) as entries:
                for entry in entries:
                    members+=1
                    if members>MAX_SCAN_MEMBERS:raise ValueError('Scan bound reached')
                    info=entry.stat(follow_symlinks=False)
                    directory=stat.S_ISDIR(info.st_mode)
                    path=folder/entry.name
                    private_member(path,directory=directory)
                    if directory:pending.append(path)
                    else:size+=info.st_size
        totals.append(size)
    return totals


def observe(session):
    checks={};uses={};jobs=[];imports=[]
    job_total=unreadable_jobs=job_counts=import_total=unreadable_imports=report_total=None
    held_reports=[];disk_free=disk_total=None;reserved=0;analysis_reserved=0
    # One read transaction for each ledger. A corrupt record is not a zero count.
    try:
        with session.store._connect(write=False) as con:
            rows=con.execute('SELECT * FROM jobs ORDER BY sequence DESC LIMIT ?', (MAX_RETAINED_JOBS+1,)).fetchall()
            if len(rows)>MAX_RETAINED_JOBS:raise ValueError('Job observation bound reached')
            job_total=len(rows);unreadable_jobs=0
            for row in rows:
                try:
                    internal=session.store._public(con,row)
                    raw=session.public_job(internal)
                    if raw['source']['workspace_id']!=session.inputs.descriptor['id']:raise ValueError('Workspace mismatch')
                    execution=raw['execution']
                    stage=con.execute('SELECT event FROM events WHERE job_id=? ORDER BY event_id DESC LIMIT 1',(raw['job_id'],)).fetchone()[0]
                    j=Job(id=raw['job_id'],workflow=raw['request']['workflow'],status=raw['status'],created_at=raw['created_at'],
                        started_at=execution['started_at'],finished_at=execution['finished_at'],stage=stage,
                        timeout_seconds=raw['request']['timeout_seconds'],restoration_hold=raw['restoration_hold'],recovery_required=raw['recovery_required'])
                    for value in (j.created_at,j.started_at,j.finished_at):
                        if value is not None:c.instant(value)
                    jobs.append(j)
                    if internal['schema_version'] in (4,5) and j.status in ('queued','running'):analysis_reserved+=ANALYSIS_RESERVATION_BYTES
                except Exception:
                    unreadable_jobs+=1
            job_counts={state:sum(j.status==state for j in jobs) for state in JOB_STATES}
            uses.update(retained_jobs=job_total,pending_jobs=None if unreadable_jobs else job_counts['queued']+job_counts['running'])
            attention=any(j.recovery_required for j in jobs)
            checks['jobs']=Check(key='jobs',state='unavailable' if unreadable_jobs else 'attention' if attention else 'ok',
                code='job_records_unavailable' if unreadable_jobs else 'recovery_inspection_required' if attention else 'job_records_checked')
    except Exception:
        jobs=[];job_total=unreadable_jobs=job_counts=None
        for key in ('retained_jobs','pending_jobs'):uses.pop(key,None)
        checks['jobs']=Check(key='jobs',state='unavailable',code='job_records_unavailable')
    try:
        with session.inputs.connect() as con:
            rows=con.execute('SELECT id FROM imports ORDER BY sequence DESC LIMIT ?', (c.MAX_ATTEMPTS+1,)).fetchall()
            if len(rows)>c.MAX_ATTEMPTS:raise ValueError('Import observation bound reached')
            import_total=len(rows);unreadable_imports=0
            for ident, in rows:
                try:
                    descriptor,r=session.inputs._attempt(con,ident)
                    parsed=c.Preflight.model_validate(descriptor)
                    item=Import(id=ident,state=r['state'],created_at=r['created_at']);c.instant(item.created_at)
                    if r['dataset_id']!=parsed.dataset_id or r['financial_approval'] is not False:raise ValueError('Receipt mismatch')
                    imports.append(item)
                    if item.state not in ('accepted','rejected'):reserved+=3*parsed.package_bytes+65536
                except Exception:unreadable_imports+=1
            uses.update(retained_imports=import_total,pending_imports=None if unreadable_imports else sum(i.state not in ('accepted','rejected') for i in imports))
            for key,kind in [('datasets','dataset'),('versions','version'),('notes','review_note'),('corrections','review_correction'),('decisions','review_decision')]:
                uses[key]=con.execute('SELECT count(*) FROM objects WHERE kind=?',(kind,)).fetchone()[0]
            checks['inputs']=Check(key='inputs',state='unavailable' if unreadable_imports else 'ok',code='input_database_unavailable' if unreadable_imports else 'input_database_readable')
    except Exception:
        imports=[];import_total=unreadable_imports=None
        for key in ('retained_imports','pending_imports','datasets','versions','notes','corrections','decisions'):uses.pop(key,None)
        checks['inputs']=Check(key='inputs',state='unavailable',code='input_database_unavailable')
    try:
        manifest=session.catalog.load()
        if manifest.schema_version!=3 or manifest.workspace_id!=session.inputs.descriptor['id']:raise ValueError('Inventory mismatch')
        report_total=len(manifest.runs)
        for run in manifest.runs:
            try:session.source_version(run)
            except Exception:held_reports.append(run.id)
        checks['reports']=Check(key='reports',state='attention' if held_reports else 'ok',code='report_sources_held' if held_reports else 'report_sources_checked')
    except Exception:
        report_total=None;held_reports=[]
        checks['reports']=Check(key='reports',state='unavailable',code='report_inventory_unavailable')
    running=session.worker_enabled
    checks['worker']=Check(key='worker',state='ok' if running else 'attention' if session.worker_requested or any(j.status in ('queued','running') for j in jobs) else 'disabled',
        code='worker_process_running' if running else 'worker_process_stopped' if session.worker_requested else 'worker_queue_waiting' if any(j.status in ('queued','running') for j in jobs) else 'worker_not_enabled')
    try:
        private_member(session.inputs.root,directory=True)
        usage=shutil.disk_usage(session.inputs.root)
        if not 0<=usage.free<=usage.total or usage.total<=0:raise ValueError('Invalid disk observation')
        disk_free,disk_total=usage.free,usage.total
        # Directory space is observed separately from ledger admission reservations.
        input_bytes=sum(tree_usage([session.inputs.root/'inputs',session.inputs.root/'staging']))
        uses['input_storage']=None if unreadable_imports is None or unreadable_imports else input_bytes+reserved
        roots=[session.store.root/'jobs',session.store.root/'operations',session.catalog.root]
        evidence_bytes=sum(tree_usage([p for p in roots if p.exists() or p.is_symlink()]))
        uses['analysis_evidence']=None if unreadable_jobs is None or unreadable_jobs else evidence_bytes+analysis_reserved
        for key,path in [('input_ledger',session.inputs.path),('job_ledger',session.store.path)]:
            private_member(path);uses[key]=path.stat().st_size
        near=disk_free<max(100_000_000,disk_total//20)
        checks['storage']=Check(key='storage',state='attention' if near else 'ok',code='storage_near_limit' if near else 'storage_observed')
    except Exception:
        for key in ('input_storage','analysis_evidence','input_ledger','job_ledger'):uses.pop(key,None)
        checks['storage']=Check(key='storage',state='unavailable',code='storage_unavailable')
    limits=dict(pending_jobs=MAX_PENDING_JOBS,retained_jobs=MAX_RETAINED_JOBS,pending_imports=c.MAX_PENDING,retained_imports=c.MAX_ATTEMPTS,
        datasets=c.MAX_DATASETS,versions=c.MAX_VERSIONS,notes=MAX_WORKSPACE_NOTES,corrections=MAX_CORRECTIONS,decisions=MAX_WORKSPACE_DECISIONS,
        input_ledger=INPUT_LEDGER_LIMIT,job_ledger=MAX_STORE_BYTES,input_storage=c.MAX_INPUT_BYTES,analysis_evidence=MAX_ANALYSIS_BYTES)
    capacities=[Capacity(key=key,used=uses.get(key),limit=limit,state='unavailable' if uses.get(key) is None else 'attention' if uses[key]*5>=limit*4 else 'ok') for key,limit in limits.items()]
    levels=[check.state for check in checks.values()]+[x.state for x in capacities]
    state='unavailable' if 'unavailable' in levels else 'attention' if 'attention' in levels else 'ok'
    value=Snapshot(schema_version=1,kind='keystone.operations',workspace_id=session.inputs.descriptor['id'],observed_at=now(),state=state,
        checks=[checks[k] for k in COMPONENTS],capacities=capacities,jobs=jobs,job_total=job_total,unreadable_jobs=unreadable_jobs,job_counts=job_counts,
        imports=imports,import_total=import_total,unreadable_imports=unreadable_imports,report_total=report_total,held_reports=held_reports,
        disk_free_bytes=disk_free,disk_total_bytes=disk_total,live_data_enabled=False,paid_models_enabled=False,financial_approval=False,production_release_approved=False).model_dump()
    if len(c.canonical(value))>MAX_RESPONSE_BYTES:raise c.InputError('input_unavailable',503)
    return value
