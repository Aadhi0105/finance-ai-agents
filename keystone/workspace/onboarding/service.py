"""One private server session, protected intake and explicit v2 job admission."""
import asyncio
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

from starlette.concurrency import run_in_threadpool

from keystone.maintenance import ROOT, control_write_gate
from ..catalog import read_confined, read_json,run_identity
from ..jobs import Admission
from ..job_contract import (JobError,DatasetJobRequest,DatasetJobRecord,FreshCloseJobRecord,DatasetBinding,LocalResearchRequest,LocalResearchJobRecord,
                            DATASET_PROFILES,MAX_PENDING_JOBS,MAX_RETAINED_JOBS,MAX_REQUESTS,MAX_OUTPUT_TOKENS,
                            MAX_TIMEOUT_SECONDS,fingerprint as job_fingerprint,now)
from ..job_files import write_new
from ..job_store import exclusive_file,private_member
from ..worker import offline_environment
from . import contracts as c
from .store import InputStore,ident
from ..job_contract import LocalWorkflowRequest,LocalWorkflowJobRecord
from .local_workflows.contracts import PROFILES as LOCAL_PROFILES


def binding(inputs,version):
    contract=version['contract']
    return DatasetBinding(workspace_id=inputs.descriptor['id'],dataset_id=version['dataset_id'],version_id=version['id'],
        contract_sha256=version['contract_sha256'],payload_sha256=contract['payload_sha256'],
        receipt_sha256=version['files']['validation.json']['sha256'],entity_sha256=contract['entity_sha256'],
        policy_sha256=c.fingerprint(contract['policy']),classification=contract['policy']['classification'])


class PrivateAdmission(Admission):
    def __init__(self,root,origin,*,enable_imports=False,enable_jobs=False,enable_worker=False,enable_review_notes=False,enable_review_corrections=False,enable_review_decisions=False):
        if enable_worker and not enable_jobs: raise c.InputError()
        self.inputs=InputStore(root,recover=True)
        self.imports_enabled=enable_imports
        self.jobs_enabled=enable_jobs
        self.review_notes_enabled=enable_review_notes
        self.review_corrections_enabled=enable_review_corrections
        self.review_decisions_enabled=enable_review_decisions
        self._intake_lock=threading.Lock()
        super().__init__(self.inputs.root/'reports',self.inputs.root/'control',origin,enable_worker=enable_worker)
        try:
            if self.catalog.load().workspace_id!=self.inputs.descriptor['id']:raise c.InputError('input_unavailable',503)
            self.inputs.interrupt_imports()
        except Exception:
            self.close();raise

    def capabilities(self):
        return dict(schema_version=2,classification='private',local_token_required=True,
                    operations_supported=True,storage_supported=True,installation_supported=True,
                    admission_enabled=self.jobs_enabled,imports_enabled=self.imports_enabled,
                    review_notes_enabled=self.review_notes_enabled,
                    review_corrections_enabled=self.review_corrections_enabled,
                    review_decisions_enabled=self.review_decisions_enabled,
                    worker_enabled=self.worker_enabled,worker_status='running' if self.worker_enabled else
                       'stopped' if self.worker_requested else 'not_enabled',
                    workflows=list(c.FORMATS) if self.jobs_enabled else [],
                    profiles=DATASET_PROFILES if self.jobs_enabled else {},timeout_seconds_max=MAX_TIMEOUT_SECONDS,
                    max_requests=MAX_REQUESTS,max_output_tokens=MAX_OUTPUT_TOKENS,
                    max_pending_jobs=MAX_PENDING_JOBS,max_retained_jobs=MAX_RETAINED_JOBS,
                    input_formats=c.FORMATS if self.imports_enabled else {},
                    supported_input_formats=c.SUPPORTED_FORMATS if self.imports_enabled else {},
                    fresh_research_supported=True,fresh_research_profile='calculate-local-research' if self.jobs_enabled else None,
                    fresh_research_limits=dict(timeout_seconds=120,max_package_bytes=1_000_000,max_requests=0,max_output_tokens=0),
                    local_workflows_supported=True,local_workflow_profiles=LOCAL_PROFILES if self.jobs_enabled else {},
                    local_workflow_limits=dict(timeout_seconds=120,max_package_bytes=1_000_000,max_requests=0,max_output_tokens=0),
                    fresh_close_profile='calculate-imported-close' if self.jobs_enabled else None,
                    live_data_enabled=False,paid_models_enabled=False,financial_approval=False,
                    scope='Private local input onboarding and supervised offline processing.',
                    max_package_bytes=c.MAX_PACKAGE,max_input_bytes=c.MAX_INPUT_BYTES)

    def public_job(self,job,*,worker_enabled=None):
        value=super().public_job(job,worker_enabled=worker_enabled)
        if job.get('restoration_hold'):
            value['next_action']='Restored request held. A local operator must recheck and release this exact never-started job.'
        if job.get('profile') == 'calculate-imported-close' and job['status'] == 'failed':
            value['recovery_required'] = True
        return {**value,'schema_version':3,'admission_schema_version':4 if job.get('profile') in LOCAL_PROFILES.values() else 3 if job.get('profile')=='calculate-local-research' else 2}

    def submit(self,value,key):
        if not self.jobs_enabled: raise JobError('job_request_invalid',405)
        try:
            model=LocalWorkflowRequest if isinstance(value,dict) and value.get('schema_version')==4 else LocalResearchRequest if isinstance(value,dict) and value.get('schema_version')==3 else DatasetJobRequest
            if model is LocalResearchRequest:
                from .research.contracts import plan
                plan(value)
            request=model.model_validate(value);kh=c.request_key(key)
        except (ValueError,TypeError): raise JobError('job_request_invalid',422) from None
        fp=job_fingerprint(request.model_dump())
        old=self._safe(lambda:self.store.existing(kh,fp))
        if old is not None:return self.public_job(old),True
        try:
            version=self.inputs.version(request.source.version_id,processing=True)
            if (version['dataset_id']!=request.source.dataset_id or version['contract_sha256']!=request.source.contract_sha256
                    or version['contract']['metadata']['workflow']!=request.workflow): raise ValueError()
            source=binding(self.inputs,version)
        except Exception: raise JobError('job_source_unavailable',409) from None
        id_=uuid.uuid4().hex
        local=version['contract']['metadata']['payload_format']==c.FRESH_RESEARCH
        if local != isinstance(request,LocalResearchRequest):raise JobError('job_request_invalid',422)
        other=version['contract']['metadata']['payload_format'] in c.LOCAL_FORMATS.values()
        if other != isinstance(request,LocalWorkflowRequest):raise JobError('job_request_invalid',422)
        fresh = version['contract']['metadata']['payload_format'] == c.FRESH_CLOSE
        extra = {}
        if fresh:
            from .close_state import current
            try: extra['accounting_source'] = current(self.inputs,version['contract']['validation']['accounting_source'])
            except Exception: raise JobError('job_source_unavailable',409) from None
        if local:
            from .research.contracts import readiness,producer
            payload=read_json(self.inputs.read('inputs/'+version['id']+'/payload.json'))
            ready=readiness(payload)
            extra.update(evaluated_on=ready['evaluated_on'],admission_readiness_sha256=c.fingerprint(ready),producer_sha256=c.fingerprint(producer()))
        if other:
            from .local_workflows.contracts import producer
            extra['producer_sha256']=c.fingerprint(producer())
        model = LocalWorkflowJobRecord if other else LocalResearchJobRecord if local else FreshCloseJobRecord if fresh else DatasetJobRecord
        record=model(job_id='job-'+id_,operation_id='web-'+id_,request=request,request_sha256=fp,
                     created_at=now(),profile=LOCAL_PROFILES[request.workflow] if other else 'calculate-local-research' if local else 'calculate-imported-close' if fresh else DATASET_PROFILES[request.workflow],source=source,**extra)
        job,replayed=self._safe(lambda:self.store.admit(kh,record))
        return self.public_job(job),replayed

    def source_version(self,run):
        version=self.inputs.version(run.input_origin.version_id)
        origin=run.input_origin
        source=binding(self.inputs,version)
        for name in ('dataset_id','version_id','contract_sha256','payload_sha256','receipt_sha256','entity_sha256','classification'):
            if getattr(origin,name)!=getattr(source,name): raise c.InputError('input_unavailable',503)
        record=self.store.immutable(origin.job_id)
        public=self.store.get(origin.job_id)['job']
        if (record.schema_version not in {2,3,4,5} or record.source!=source or record.request_sha256!=origin.request_sha256
                or record.profile!=origin.profile or public['status'] not in {'completed','review_required'}
                or public['execution']['result'] is None
                or public['execution']['result']['run_sha256']!=job_fingerprint(run_identity(run))):
            raise c.InputError('input_unavailable',503)
        if record.schema_version == 3:
            from .close_state import registry_proof
            proof = registry_proof(self.inputs,record)
            if (run.accounting_origin is None or run.accounting_origin.commit_sha256 != c.fingerprint(proof)
                    or public['execution']['accounting_commit_sha256'] != c.fingerprint(proof)):
                raise c.InputError('input_unavailable',503)
        return version

    def authorize_transfer(self,id_,key):
        if not self.imports_enabled: raise c.InputError('input_disabled',405)
        kh=c.request_key(key)
        with self.inputs.connect() as con:
            row=con.execute('SELECT key_hash FROM imports WHERE id=?',(ident(id_),)).fetchone()
            if row is None: raise c.InputError('input_not_found',404)
            if row[0]!=kh: raise c.InputError('input_conflict',409)
        descriptor,receipt=self.inputs.attempt(id_)
        entity=self.inputs.object('entity',descriptor['metadata']['dataset']['entity_id'])
        policy=self.inputs.policies(descriptor['metadata'],descriptor['payload_sha256'],entity)
        context=dict(entity=entity,policy=policy)
        if descriptor['metadata']['payload_format']==c.FRESH_RESEARCH:
            context['research_candidate_version_id']='version-'+uuid.uuid4().hex
            context['research_scope']=self.inputs.research_scope(entity['id'])
        return descriptor,receipt,context

    async def transfer(self,id_,request,key):
        descriptor,receipt,context=await run_in_threadpool(self.authorize_transfer,id_,key)
        if receipt['state'] not in {'reserved','interrupted','accepted'}: raise c.InputError('input_conflict',409)
        if not self._intake_lock.acquire(blocking=False):raise c.InputError('input_busy',409)
        stream=None;folder=None
        try:
            with control_write_gate(queue_only=True):
                if receipt['state']!='accepted':
                    transfer='transfer-'+uuid.uuid4().hex
                    self.inputs.transition(id_,'receiving',transfer_id=transfer,reason=None)
                import hashlib
                hash_=hashlib.sha256();total=0;buffer=bytearray()
                async with asyncio.timeout(c.TRANSFER_SECONDS):
                    async for chunk in request.stream():
                        total+=len(chunk)
                        if total>descriptor['package_bytes'] or total>c.MAX_PACKAGE: raise c.InputError('input_too_large',413)
                        hash_.update(chunk)
                        buffer.extend(chunk)
                if total!=descriptor['package_bytes'] or hash_.hexdigest()!=descriptor['package_sha256']: raise c.InputError()
                if receipt['state']=='accepted':return receipt
                # Policy is scoped to actual payload content, not a client hash
                # assertion. Do not persist arbitrary rejected/unpermitted bytes.
                def verify_content():
                    package=c.envelope(c.bounded_json(bytes(buffer)))
                    if ({k:v for k,v in package.items() if k!='payload'}!=descriptor['metadata']
                            or c.fingerprint(package['payload'])!=descriptor['payload_sha256']):raise c.InputError()
                await run_in_threadpool(verify_content)
                _,_,context=await run_in_threadpool(self.authorize_transfer,id_,key)
                parent=self.inputs.root/'staging'/id_
                parent.mkdir(mode=0o700,exist_ok=True);private_member(parent,directory=True)
                folder=parent/transfer;folder.mkdir(mode=0o700)
                write_new(folder/'package.json',bytes(buffer))
                buffer.clear()
                write_new(folder/'preflight.json',c.canonical(descriptor))
                write_new(folder/'context.json',c.canonical(context))
                self.inputs.transition(id_,'validating')
            return await run_in_threadpool(self.validate_and_accept,id_,folder)
        except BaseException as error:
            if stream:stream.close()
            try:
                _,current=self.inputs.attempt(id_)
                if current['state'] in {'receiving','validating'}:
                    state='rejected' if isinstance(error,c.InputError) and error.code in {'input_invalid','input_too_large'} else 'interrupted'
                    self.inputs.transition(id_,state,reason=error.code if isinstance(error,c.InputError) else 'input_interrupted')
            except Exception:pass
            if isinstance(error,c.InputError):raise
            if isinstance(error,(KeyboardInterrupt,SystemExit,asyncio.CancelledError)):raise
            raise c.InputError('input_interrupted',409) from None
        finally:self._intake_lock.release()

    def validate_and_accept(self,id_,folder):
        lease=self.inputs.root/'validation.lock'
        try:exclusive_file(lease)
        except FileExistsError:pass
        private_member(lease)
        fd=os.open(lease,os.O_RDWR|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with control_write_gate() as inherited:
                descriptor,_ = self.inputs.attempt(id_)
                fresh = descriptor['metadata']['payload_format'] == c.FRESH_CLOSE
                if fresh:
                    from .close_state import validation_copy
                    context = read_json(read_confined(folder,'context.json',65536))
                    context['accounting_source'] = validation_copy(self.inputs,context['entity']['id'],folder)
                    # This context has not been accepted or hashed yet.
                    (folder/'context.json').unlink()
                    write_new(folder/'context.json',c.canonical(context))
                try:
                    result=subprocess.run([sys.executable,'-m','keystone.workspace.onboarding.validate',str(folder)],
                        cwd=ROOT,env=offline_environment(self.store.root),pass_fds=(*inherited,fd),
                        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                        timeout=c.VALIDATION_SECONDS)
                finally:
                    if fresh:
                        for suffix in ('','.wal'):
                            (folder/('predecessor.duckdb'+suffix)).unlink(missing_ok=True)
                if result.returncode<0:
                    self.inputs.transition(id_,'interrupted',reason='input_interrupted')
                    raise c.InputError('input_interrupted',409)
                if result.returncode!=0:
                    self.inputs.transition(id_,'rejected',reason='input_invalid')
                    raise c.InputError()
                try:
                    if fresh:
                        from .close_state import current
                        current(self.inputs,read_json(read_confined(folder,'validation.json',65536))['accounting_source'])
                    return self.inputs.accept(id_,folder)
                except Exception:
                    self.inputs.transition(id_,'delivery_failed',reason='input_unavailable')
                    raise c.InputError('input_unavailable',503) from None
        except (BlockingIOError,RuntimeError):raise c.InputError('input_busy',409) from None
        finally:os.close(fd)
