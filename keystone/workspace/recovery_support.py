"""Read-only recovery triage, using verified operating records, never dispatch.

Guidance identifies an inspection route, not proof that recovery is possible.
Protection claims require independent evidence, not an operating observation.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from typing import Literal

from pydantic import Field,model_validator

from .catalog import Record,ID
from .job_contract import JOB_ID,JobError
from .job_execution import STATES
from .job_store import JobStore,private_member
from . import operations

MAX_RESPONSE_BYTES=700_000
Worker=Literal['worker_process_running','worker_not_enabled','worker_queue_waiting','worker_process_stopped']
JobGuidance=Literal['restored_queue_held','queued_waiting','work_in_progress','worker_interrupted',
    'delivery_inspection','unknown_outcome','source_hold','failed_attempt','close_state_inspection']
ImportGuidance=Literal['import_in_progress','import_inspection','import_rejected']


def job_guidance(status,held,workflow,worker):
    if held:return 'restored_queue_held'
    if status=='queued':return 'queued_waiting'
    if status=='running':return 'work_in_progress' if worker=='worker_process_running' else 'worker_interrupted'
    if status=='delivery_failed':return 'delivery_inspection'
    if status=='outcome_unknown':return 'unknown_outcome'
    if status=='source_changed':return 'source_hold'
    if status=='failed':return 'close_state_inspection' if workflow=='close' else 'failed_attempt'
    return None


def import_guidance(state):
    if state in {'interrupted','delivery_failed'}:return 'import_inspection'
    if state=='rejected':return 'import_rejected'
    if state in {'reserved','receiving','validating'}:return 'import_in_progress'
    return None


class Job(Record):
    id: str=Field(pattern=JOB_ID)
    workflow: Literal['research','monitoring','events','news','close']
    status: STATES
    restoration_hold: bool
    guidance: JobGuidance


class Import(Record):
    id: str=Field(pattern=r'^import-[a-f0-9]{32}$')
    state: Literal['reserved','receiving','validating','rejected','interrupted','delivery_failed']
    guidance: ImportGuidance


class Protection(Record):
    independent_backup: Literal['not_verified_here']='not_verified_here'
    encryption_key_recovery: Literal['not_verified_here']='not_verified_here'
    clean_machine_recovery: Literal['not_verified_here']='not_verified_here'
    local_restore: Literal['requires_separate_receipt']='requires_separate_receipt'


class Recovery(Record):
    schema_version: Literal[1]=1
    kind: Literal['keystone.recovery-support']='keystone.recovery-support'
    workspace_id: str=Field(pattern=ID)
    observed_at: str=Field(max_length=80)
    state: Literal['observed','attention','unavailable']
    worker: Worker
    source_checks: Literal['checked','held','unavailable']
    job_total: int|None=Field(ge=0,le=1000)
    unreadable_jobs: int|None=Field(ge=0,le=1000)
    import_total: int|None=Field(ge=0,le=1000)
    unreadable_imports: int|None=Field(ge=0,le=1000)
    jobs: list[Job]=Field(max_length=1000)
    imports: list[Import]=Field(max_length=1000)
    protection: Protection=Protection()
    automatic_recovery: Literal[False]=False
    automatic_retry: Literal[False]=False
    financial_approval: Literal[False]=False
    production_release_approved: Literal[False]=False

    @model_validator(mode='after')
    def consistent(self):
        from .onboarding import contracts as c
        c.instant(self.observed_at)
        for total,unreadable,items in ((self.job_total,self.unreadable_jobs,self.jobs),(self.import_total,self.unreadable_imports,self.imports)):
            if (total is None)!=(unreadable is None):raise ValueError('Unknown totals')
            if total is None:
                if items:raise ValueError('Unknown inventory')
            elif unreadable>total or len(items)>total-unreadable:raise ValueError('Counts')
            if len({i.id for i in items})!=len(items):raise ValueError('Duplicate identity')
        for j in self.jobs:
            if (j.restoration_hold and j.status!='queued'
                    or j.guidance!=job_guidance(j.status,j.restoration_hold,j.workflow,self.worker)):raise ValueError('Job guidance')
        for i in self.imports:
            if i.guidance!=import_guidance(i.state):raise ValueError('Import guidance')
        unknown=self.job_total is None or self.import_total is None or bool(self.unreadable_jobs or self.unreadable_imports) or self.source_checks=='unavailable'
        attention=(any(j.guidance not in {'queued_waiting','work_in_progress'} for j in self.jobs)
                   or any(i.guidance!='import_in_progress' for i in self.imports)
                   or self.worker=='worker_process_stopped' or self.source_checks=='held')
        if self.state!=('unavailable' if unknown else 'attention' if attention else 'observed'):raise ValueError('Recovery state')
        return self


def observe(session):
    from .onboarding import contracts as c
    op=operations.Snapshot.model_validate(operations.observe(session))
    worker=next(x.code for x in op.checks if x.key=='worker')
    reports=next(x.code for x in op.checks if x.key=='reports')
    source='checked' if reports=='report_sources_checked' else 'held' if reports=='report_sources_held' else 'unavailable'
    jobs=[Job(id=j.id,workflow=j.workflow,status=j.status,restoration_hold=j.restoration_hold,guidance=code)
          for j in op.jobs if (code:=job_guidance(j.status,j.restoration_hold,j.workflow,worker)) is not None]
    imports=[Import(id=i.id,state=i.state,guidance=code) for i in op.imports if (code:=import_guidance(i.state)) is not None]
    unknown=op.job_total is None or op.import_total is None or bool(op.unreadable_jobs or op.unreadable_imports) or source=='unavailable'
    attention=(any(j.guidance not in {'queued_waiting','work_in_progress'} for j in jobs)
               or any(i.guidance!='import_in_progress' for i in imports) or worker=='worker_process_stopped' or source=='held')
    value=Recovery(workspace_id=op.workspace_id,observed_at=op.observed_at,state='unavailable' if unknown else 'attention' if attention else 'observed',
        worker=worker,source_checks=source,job_total=op.job_total,unreadable_jobs=op.unreadable_jobs,
        import_total=op.import_total,unreadable_imports=op.unreadable_imports,jobs=jobs,imports=imports).model_dump()
    if len(c.canonical(value))>MAX_RESPONSE_BYTES:raise c.InputError('input_unavailable',503)
    return value


@contextmanager
def operator_store(root):
    """Stop-before-recovery CLI guard; take the existing server lease first.

    The worker store then takes its own exclusive worker lease before any input
    journal recovery. No browser capability or background worker is enabled.
    """
    root=Path(root).absolute();fd=None;store=None
    try:
        if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError()
        root_id=private_member(root,directory=True)
        control=root/'control';control_id=private_member(control,directory=True)
        path=control/'session.lock';identity=private_member(path)
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        if (os.fstat(fd).st_dev,os.fstat(fd).st_ino)!=identity:raise ValueError()
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (private_member(path)!=identity or private_member(root,directory=True)!=root_id
                or private_member(control,directory=True)!=control_id):raise ValueError()
        store=JobStore(control,root/'reports',worker=True)
        yield store
    finally:
        if store is not None:store.close()
        if fd is not None:os.close(fd)
