"""Bounded storage accounting and stopped-workspace evidence checks.

Observation never removes files, releases reservations, repairs a ledger, or
grants permission. A filesystem inventory is distinct from reference validation
and from an independently recoverable backup.
"""
from contextlib import ExitStack, contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import stat
from typing import Literal

from pydantic import Field

from keystone.maintenance import gate
from .catalog import Catalog, Record, ID, read_json, run_identity
from .job_contract import now, parse_job_record, fingerprint
from .job_store import JobStore, private_member
from .onboarding import contracts as c

MAX_MEMBERS = 60_000
MAX_HASH_BYTES = 1_000_000_000
MAX_RESPONSE_BYTES = 32_000
AREAS = ('configuration', 'input_ledger', 'inputs', 'staging', 'permissions',
         'reports', 'job_ledger', 'job_evidence', 'operation_evidence',
         'accounting', 'recovery', 'runtime', 'unrecognised')
REQUIRED = ('workspace.json', 'inputs.sqlite3', 'inputs', 'staging', 'permissions',
            'reports', 'reports/runs', 'reports/catalog.json', 'control', 'control/jobs.sqlite3')


class Area(Record):
    key: Literal['configuration','input_ledger','inputs','staging','permissions','reports',
                 'job_ledger','job_evidence','operation_evidence','accounting','recovery','runtime','unrecognised']
    files: int | None = Field(ge=0)
    bytes: int | None = Field(ge=0)
    state: Literal['observed','attention','unavailable']


class Inventory(Record):
    schema_version: Literal[1]
    kind: Literal['keystone.storage']
    workspace_id: str = Field(pattern=ID)
    observed_at: str
    state: Literal['observed','attention','unavailable']
    areas: list[Area] = Field(min_length=13,max_length=13)
    total_files: int | None = Field(ge=0)
    total_bytes: int | None = Field(ge=0)
    disk_free_bytes: int | None = Field(ge=0)
    disk_total_bytes: int | None = Field(ge=1)
    retention_policy: Literal['preserve_until_operator_review']
    automatic_deletion: Literal[False]
    deletion_supported: Literal[False]
    document_intake_supported: Literal[False]
    reference_check: Literal['requires_stopped_audit']
    backup_protection: Literal['not_established_by_inventory']
    financial_approval: Literal[False]
    production_release_approved: Literal[False]


def area_for(parts):
    if parts == ('validation.lock',): return 'runtime'
    if parts == ('restore-receipt.json',) or parts[0]=='recovery': return 'recovery'
    if parts == ('workspace.json',): return 'configuration'
    if parts == ('inputs.sqlite3',): return 'input_ledger'
    if parts[0] in {'inputs','staging','permissions','reports','accounting'}: return parts[0]
    if parts[0] == 'control' and len(parts)>1:
        name=parts[1]
        if name == 'jobs.sqlite3': return 'job_ledger' if len(parts)==2 else 'unrecognised'
        if name in {'jobs','operations'}: return 'job_evidence' if name=='jobs' else 'operation_evidence'
        if name == 'runtime': return 'runtime'
        if name == 'restore-history.json' and len(parts)==2: return 'recovery'
        if name in {'session.lock','worker.lock','access-token.key'} and len(parts)==2: return 'runtime'
        if name.startswith('jobs.sqlite3-') and name in {'jobs.sqlite3-journal','jobs.sqlite3-wal','jobs.sqlite3-shm'} and len(parts)==2: return 'runtime'
    if parts in {('inputs.sqlite3-journal',),('inputs.sqlite3-wal',),('inputs.sqlite3-shm',)}: return 'runtime'
    return 'unrecognised'


def scan(root, *, hashes=False):
    """Count the entire private root, including runtime/unrecognised members.

    Never follow links or open credential contents. Hashing has an additional
    byte bound and is used only during stopped-workspace maintenance.
    """
    root=Path(root);private_member(root,directory=True)
    totals={key:[0,0] for key in AREAS};bad=set();members=0;hashed=0;proof={};unknown=False
    pending=[root]
    while pending:
        folder=pending.pop()
        try:
            private_member(folder,directory=True)
            with os.scandir(folder) as entries:
                for entry in entries:
                    members+=1
                    if members>MAX_MEMBERS: raise OverflowError('Inventory bound')
                    path=folder/entry.name;parts=path.relative_to(root).parts;key=area_for(parts)
                    try:
                        info=entry.stat(follow_symlinks=False);directory=stat.S_ISDIR(info.st_mode)
                        private_member(path,directory=directory)
                        if directory:
                            if key=='unrecognised' and parts!=('control',):unknown=True
                            pending.append(path)
                        else:
                            totals[key][0]+=1;totals[key][1]+=info.st_size
                            if hashes and key!='runtime':
                                hashed+=info.st_size
                                if hashed>MAX_HASH_BYTES:raise OverflowError('Hash bound')
                                digest=hashlib.sha256()
                                fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
                                with os.fdopen(fd,'rb') as stream:
                                    before=os.fstat(stream.fileno())
                                    if (before.st_dev,before.st_ino)!=(info.st_dev,info.st_ino):raise ValueError()
                                    read=0
                                    while block:=stream.read(1024*1024):
                                        read+=len(block)
                                        if read>info.st_size:raise ValueError()
                                        digest.update(block)
                                    after=os.fstat(stream.fileno())
                                if (read,after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=(info.st_size,info.st_size,info.st_mtime_ns,info.st_ctime_ns):raise ValueError()
                                proof['/'.join(parts)]=dict(bytes=read,sha256=digest.hexdigest())
                    except OverflowError:raise
                    except Exception:bad.add(key)
        except OverflowError:raise
        except Exception:bad.add(area_for(folder.relative_to(root).parts) if folder!=root else 'configuration')
    for relative in REQUIRED:
        path=root/relative
        try:private_member(path,directory=relative in {'inputs','staging','permissions','reports','reports/runs','control'})
        except Exception:bad.add(area_for(tuple(relative.split('/'))))
    areas=[Area(key=k,files=None if k in bad else totals[k][0],bytes=None if k in bad else totals[k][1],
                state='unavailable' if k in bad else 'attention' if k=='unrecognised' and (totals[k][0] or unknown) else 'observed') for k in AREAS]
    return areas,proof


def observe_storage(inputs):
    def bound_root():
        if (private_member(inputs.root,directory=True)!=inputs._root_identity
                or inputs.read('workspace.json',65536)!=c.canonical(inputs.descriptor)):raise ValueError()
    try:
        bound_root();areas,_=scan(inputs.root);bound_root()
    except Exception:areas=[Area(key=k,files=None,bytes=None,state='unavailable') for k in AREAS]
    free=total=None
    try:
        disk=shutil.disk_usage(inputs.root)
        if not 0<=disk.free<=disk.total or disk.total<=0:raise ValueError()
        free,total=disk.free,disk.total
    except Exception:pass
    state='unavailable' if free is None or any(a.state=='unavailable' for a in areas) else 'attention' if any(a.state=='attention' for a in areas) or free<max(100_000_000,total//20) else 'observed'
    value=Inventory(schema_version=1,kind='keystone.storage',workspace_id=inputs.descriptor['id'],observed_at=now(),state=state,areas=areas,
        total_files=None if any(a.files is None for a in areas) else sum(a.files for a in areas),
        total_bytes=None if any(a.bytes is None for a in areas) else sum(a.bytes for a in areas),
        disk_free_bytes=free,disk_total_bytes=total,retention_policy='preserve_until_operator_review',automatic_deletion=False,
        deletion_supported=False,document_intake_supported=False,reference_check='requires_stopped_audit',
        backup_protection='not_established_by_inventory',financial_approval=False,production_release_approved=False).model_dump()
    if len(c.canonical(value))>MAX_RESPONSE_BYTES:raise c.InputError('input_unavailable',503)
    return value


def audit_evidence(inputs, store):
    """Caller owns stopped session/worker leases and exclusive maintenance.

    Checks current reference semantics, not source authenticity. A permission
    hold is explicit and does not authorise deletion of the underlying evidence.
    """
    checks=[]
    def check(key, fn):
        try:
            fn();state='verified'
        except c.InputError as error:
            state='held' if error.code=='input_policy_refused' else 'unavailable'
        except Exception:state='unavailable'
        checks.append(dict(key=key,state=state))
    areas,before=scan(inputs.root,hashes=True)
    physical_ok=all(a.state=='observed' for a in areas)
    checks.append(dict(key='inventory',state='verified' if physical_ok else 'unavailable'))
    def all_inputs():
        with inputs.connect() as con:
            rows=con.execute('SELECT kind,id FROM objects').fetchall()
            if len(rows)>10_000:raise ValueError()
            versions={};permissions=[]
            for kind,ident in rows:
                value=inputs._object(con,kind,ident)
                if kind=='version':versions[value['id']]=value
                if kind=='permission':permissions.append(value['id'])
            imports=[row[0] for row in con.execute('SELECT id FROM imports').fetchall()]
            attempts={ident:inputs._attempt(con,ident) for ident in imports}
        if {p.name for p in (inputs.root/'inputs').iterdir()}!=set(versions):raise ValueError()
        if {p.name for p in (inputs.root/'staging').iterdir()}-set(imports):raise ValueError()
        if {p.name for p in (inputs.root/'permissions').iterdir()}!=set(permissions):raise ValueError()
        # Continue checking all versions even if one has a permission hold.
        held=False;unavailable=False
        for ident in versions:
            try:
                version=versions[ident]
                if {p.name for p in (inputs.root/'inputs'/ident).iterdir()}!=set(version['files']):raise ValueError()
                descriptor,receipt=attempts[version['import_id']]
                c.Preflight.model_validate(descriptor)
                if receipt['state']!='accepted' or receipt['version_id']!=ident or descriptor['dataset_id']!=version['dataset_id']:raise ValueError()
                inputs.version(ident)
            except c.InputError as error:
                if error.code=='input_policy_refused':held=True
                else:unavailable=True
            except Exception:unavailable=True
        if unavailable:raise ValueError()
        if any(receipt['state']=='accepted' and receipt.get('version_id') not in versions for _,receipt in attempts.values()):raise ValueError()
        if held:raise c.InputError('input_policy_refused',403)
    check('inputs',all_inputs)
    def permission_files():
        with inputs.connect() as con:
            policies=[inputs._object(con,'permission',row[0]) for row in con.execute("SELECT id FROM objects WHERE kind='permission'")]
        for raw in policies:
            policy=c.Permission.model_validate(raw)
            if (inputs.read('permissions/'+policy.id+'/record.json',65536)!=c.canonical(raw)
                    or c.sha(inputs.read('permissions/'+policy.id+'/evidence'))!=policy.evidence_sha256):raise ValueError()
    check('permission_evidence',permission_files)
    def reviews():
        from .review.notes import validate_notes
        from .review.corrections import validate_corrections
        from .review.decisions import validate_decisions
        validate_notes(inputs);validate_corrections(inputs);validate_decisions(inputs)
    check('review_records',reviews)
    def jobs_and_reports():
        from .onboarding.service import binding
        from .onboarding.execution import verified_result
        from .job_files import read_job
        from .onboarding.close_state import registry_proof
        manifest=Catalog(inputs.root/'reports').load()
        if manifest.schema_version!=3 or manifest.workspace_id!=inputs.descriptor['id']:raise ValueError()
        registered={r.input_origin.job_id:r for r in manifest.runs}
        if len(registered)!=len(manifest.runs):raise ValueError()
        records={}
        with store._connect(write=False) as con:
            rows=con.execute('SELECT * FROM jobs ORDER BY sequence').fetchall()
            if len(rows)>1000:raise ValueError()
            for row in rows:
                public=store._public(con,row);record=parse_job_record(store._record(row))
                if record.schema_version not in {2,3,4,5} or record.source.workspace_id!=inputs.descriptor['id']:raise ValueError()
                version=inputs.version(record.source.version_id)
                if binding(inputs,version)!=record.source:raise ValueError()
                execution=store._execution(con,record.job_id)
                events=con.execute('SELECT event,created_at FROM events WHERE job_id=? ORDER BY event_id',(record.job_id,)).fetchall()
                allowed={'admitted','claimed','inputs_verified','prepared','registered','failed','source_changed','interrupted','delivery_failed','recovered'}
                if not 1<=len(events)<=50 or events[0]!=('admitted',record.created_at) or sum(e=='admitted' for e,_ in events)!=1:raise ValueError()
                for event,created_at in events:
                    if event not in allowed:raise ValueError()
                    c.instant(created_at)
                folder=store.root/'jobs'/record.job_id
                if folder.exists():
                    if read_job(folder)!=record:raise ValueError()
                elif execution.result is not None or execution.status in {'completed','review_required'} or any(e in {'inputs_verified','prepared','registered','recovered'} for e,_ in events):raise ValueError()
                if execution.result is not None:
                    result,run,_=verified_result(store,record,execution.result)
                    registered_run=registered.get(record.job_id)
                    if public['status'] in {'completed','review_required'} and (registered_run is None or fingerprint(run_identity(registered_run))!=result.run_sha256):raise ValueError()
                elif record.job_id in registered:raise ValueError()
                if record.schema_version==3 and execution.accounting_commit_sha256:
                    if c.fingerprint(registry_proof(inputs,record))!=execution.accounting_commit_sha256:raise ValueError()
                records[record.job_id]=record
        catalog=Catalog(inputs.root/'reports')
        for run in manifest.runs:
            if run.input_origin.job_id not in records:raise ValueError()
            for artifact in run.artifacts:catalog.read(run.id,artifact)
        # Working evidence without an admission is preserved for investigation.
        jobs=store.root/'jobs'
        if jobs.exists() and any(p.name not in records for p in jobs.iterdir()):raise ValueError()
        operations=store.root/'operations';known={r.operation_id for r in records.values()}
        if operations.exists() and any(p.name not in known for p in operations.iterdir()):raise ValueError()
    check('jobs_and_reports',jobs_and_reports)
    def accounting():
        from .onboarding.close_state import inspect
        root=inputs.root/'accounting'
        if root.exists():
            for entity in root.iterdir():inspect(inputs,entity.name)
    check('accounting',accounting)
    check('snapshot_permission',inputs.backup_plan)
    after_areas,after=scan(inputs.root,hashes=True)
    unchanged=before==after and areas==after_areas
    checks.append(dict(key='unchanged_evidence',state='verified' if unchanged else 'unavailable'))
    state='unavailable' if any(c['state']=='unavailable' for c in checks) else 'held' if any(c['state']=='held' for c in checks) else 'verified'
    return dict(schema_version=1,kind='keystone.evidence-audit',workspace_id=inputs.descriptor['id'],observed_at=now(),state=state,
        checks=checks,evidence_files=len(after),evidence_bytes=sum(v['bytes'] for v in after.values()),
        evidence_sha256=c.fingerprint(after) if unchanged and physical_ok else None,
        runtime_files_excluded=True,consistent_backup=False,financial_approval=False,production_release_approved=False)


@contextmanager
def stopped_workspace(root):
    """Existing lock files only: refuse a live server/worker, create no workspace files."""
    root=Path(root).absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError()
    with gate(exclusive=True),ExitStack() as stack:
        for name in ('session.lock','worker.lock'):
            path=root/'control'/name
            if name=='worker.lock' and not path.exists() and not path.is_symlink():continue
            identity=private_member(path)
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW);stack.callback(os.close,fd)
            if (os.fstat(fd).st_dev,os.fstat(fd).st_ino)!=identity:raise ValueError()
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def audit_private(root):
    from .onboarding.store import InputStore
    with stopped_workspace(root):
        inputs=InputStore(root)
        store=JobStore.reader(inputs.root/'control',inputs.root/'reports')
        try:return audit_evidence(inputs,store)
        finally:store.close()
