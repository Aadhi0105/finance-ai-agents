"""Closed offline admission contract. No browser-provided commands or paths."""
from datetime import datetime, timezone
import hashlib
import json
from typing import Literal

from pydantic import Field, field_validator, model_validator

from keystone.operation import MAX_TIMEOUT_SECONDS, MAX_REQUESTS, MAX_OUTPUT_TOKENS
from .catalog import ArtifactV2, ID, NativeViewRegistration, Record

WORKFLOWS = Literal['research', 'monitoring', 'events', 'news', 'close']
PROFILES = {
    'research': 'rebuild-saved-research',
    'monitoring': 'render-saved-monitoring',
    'events': 'replay-saved-events',
    'news': 'replay-saved-news',
    'close': 'render-saved-close',
}
JOB_ID = r'^job-[a-f0-9]{32}$'
MAX_REQUEST_BYTES = 4096
MAX_PENDING_JOBS = 20
MAX_RETAINED_JOBS = 1000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False,
                      ensure_ascii=not (isinstance(value,dict) and value.get('schema_version')==3 and 'analysis_plan' in value))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


class JobError(ValueError):
    def __init__(self, code, status=503):
        self.code, self.status = code, status
        super().__init__(code)

    def envelope(self):
        messages = {
            'job_access_required': 'A valid local job-access token is required.',
            'job_origin_refused': 'Job requests require the configured local origin.',
            'job_request_invalid': 'Use the supported offline job request and request key.',
            'job_request_too_large': 'The job request exceeds the supported size.',
            'job_media_type_refused': 'Job requests require application/json without compression.',
            'job_source_unavailable': 'The registered synthetic source is unavailable or unsupported.',
            'job_request_conflict': 'This request key already identifies a different request.',
            'job_capacity_reached': 'Job admission is full. Preserve existing jobs and inspect their status.',
            'job_control_busy': 'Another Keystone session or recovery task is using this workspace. Use its existing window, or stop that session before restarting. Preserve the request key and lock files.',
            'job_not_found': 'The saved job was not found.',
            'job_store_unavailable': 'Job control state is unavailable. Preserve it and inspect locally.',
            'job_worker_unavailable': 'The local worker could not start. Preserve the job ledger and inspect locally.',
            'job_recovery_unavailable': 'Verified saved delivery is not available for this job. Do not rerun it blindly.',
        }
        return {'error': {'code': self.code, 'message': messages[self.code]}}


class JobRequest(Record):
    schema_version: int = Field(default=1, ge=1, le=1)
    workflow: WORKFLOWS
    source_run_id: str = Field(pattern=ID)
    timeout_seconds: int = Field(default=MAX_TIMEOUT_SECONDS, ge=1, le=MAX_TIMEOUT_SECONDS)


class SourceBinding(Record):
    run_id: str = Field(pattern=ID)
    workflow: WORKFLOWS
    run_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    primary_artifact_id: str = Field(pattern=ID)
    native_view: NativeViewRegistration
    artifacts: list[ArtifactV2] = Field(min_length=2, max_length=40)


class JobRecord(Record):
    schema_version: int = Field(default=1, ge=1, le=1)
    job_id: str = Field(pattern=JOB_ID)
    operation_id: str = Field(pattern=r'^web-[a-f0-9]{32}$')
    request: JobRequest
    request_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    created_at: str = Field(min_length=20, max_length=80)
    profile: str = Field(min_length=1, max_length=60)
    profile_version: int = Field(default=1, ge=1, le=1)
    status: Literal['queued'] = 'queued'
    source: SourceBinding
    input_validation: Literal['matched_at_admission'] = 'matched_at_admission'
    worker_enabled: Literal[False] = False
    live_data_enabled: Literal[False] = False
    paid_models_enabled: Literal[False] = False
    financial_approval: Literal[False] = False
    max_requests: int = Field(default=MAX_REQUESTS, ge=MAX_REQUESTS, le=MAX_REQUESTS)
    max_output_tokens: int = Field(default=MAX_OUTPUT_TOKENS, ge=MAX_OUTPUT_TOKENS, le=MAX_OUTPUT_TOKENS)

    @field_validator('worker_enabled', 'live_data_enabled', 'paid_models_enabled', 'financial_approval', mode='before')
    @classmethod
    def only_false(cls, value):
        if value is not False:
            raise ValueError('This capability is disabled.')
        return value

    @model_validator(mode='after')
    def bound_identity(self):
        if (self.operation_id != 'web-' + self.job_id[4:]
                or self.request_sha256 != fingerprint(self.request.model_dump())
                or self.profile != PROFILES[self.request.workflow]
                or self.source.workflow != self.request.workflow
                or self.source.run_id != self.request.source_run_id
                or self.source.primary_artifact_id != self.source.native_view.source_artifact_ids[0]
                or self.source.primary_artifact_id not in {a.id for a in self.source.artifacts}
                or datetime.fromisoformat(self.created_at).utcoffset() is None):
            raise ValueError('Job identities disagree.')
        return self


class DatasetReference(Record):
    kind: Literal['dataset_version']
    dataset_id: str = Field(pattern=ID)
    version_id: str = Field(pattern=ID)
    contract_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class DatasetJobRequest(Record):
    schema_version: int = Field(default=2, ge=2, le=2)
    workflow: WORKFLOWS
    source: DatasetReference
    timeout_seconds: int = Field(default=MAX_TIMEOUT_SECONDS, ge=1, le=MAX_TIMEOUT_SECONDS)


DATASET_PROFILES = {key:value.replace('saved','imported') for key,value in PROFILES.items()}


class DatasetBinding(Record):
    workspace_id: str = Field(pattern=ID)
    dataset_id: str = Field(pattern=ID)
    version_id: str = Field(pattern=ID)
    contract_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    payload_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    receipt_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    entity_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    policy_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    classification: Literal['synthetic','provider','issuer','internal','mixed','unknown']


class DatasetJobRecord(JobRecord):
    schema_version: int = Field(default=2, ge=2, le=2)
    request: DatasetJobRequest
    source: DatasetBinding

    @model_validator(mode='after')
    def bound_identity(self):
        if (self.operation_id != 'web-'+self.job_id[4:]
                or self.request_sha256 != fingerprint(self.request.model_dump())
                or self.profile != DATASET_PROFILES[self.request.workflow]
                or (self.source.dataset_id,self.source.version_id,self.source.contract_sha256) !=
                   (self.request.source.dataset_id,self.request.source.version_id,self.request.source.contract_sha256)
                or datetime.fromisoformat(self.created_at).utcoffset() is None):
            raise ValueError('Dataset job identities disagree.')
        return self


class FreshCloseJobRecord(DatasetJobRecord):
    schema_version: int = Field(default=3, ge=3, le=3)
    # Import here would create a contracts/catalogue cycle; the pin has a small
    # standalone strict model in the onboarding contract and is checked below.
    accounting_source: dict

    @model_validator(mode='after')
    def bound_identity(self):
        from .onboarding.contracts import AccountingSource
        pin = AccountingSource.model_validate(self.accounting_source)
        if (self.request.workflow != 'close' or self.profile != 'calculate-imported-close'
                or self.operation_id != 'web-'+self.job_id[4:]
                or self.request_sha256 != fingerprint(self.request.model_dump())
                or pin.workspace_id != self.source.workspace_id
                or (self.source.dataset_id,self.source.version_id,self.source.contract_sha256) !=
                   (self.request.source.dataset_id,self.request.source.version_id,self.request.source.contract_sha256)
                or datetime.fromisoformat(self.created_at).utcoffset() is None):
            raise ValueError('Fresh close identities disagree.')
        return self


def parse_job_record(raw):
    if not isinstance(raw,dict) or type(raw.get('schema_version')) is not int:
        raise ValueError('Unsupported job record.')
    model = {1:JobRecord,2:DatasetJobRecord,3:FreshCloseJobRecord,4:LocalResearchJobRecord,5:LocalWorkflowJobRecord}.get(raw['schema_version'])
    if model is None: raise ValueError('Unsupported job record.')
    return model.model_validate(raw)


def capabilities(enabled, worker=False, worker_requested=False):
    return dict(schema_version=1, admission_enabled=enabled, worker_enabled=worker,
                worker_status='running' if worker else 'stopped' if worker_requested else 'not_enabled',
                local_token_required=enabled, classification='synthetic',
                live_data_enabled=False, paid_models_enabled=False, financial_approval=False,
                workflows=list(PROFILES) if enabled else [],
                profiles=PROFILES if enabled else {}, timeout_seconds_max=MAX_TIMEOUT_SECONDS,
                max_requests=MAX_REQUESTS, max_output_tokens=MAX_OUTPUT_TOKENS,
                max_pending_jobs=MAX_PENDING_JOBS, max_retained_jobs=MAX_RETAINED_JOBS,
                scope='Supervised offline saved-evidence execution.' if worker else 'Admission only; the local worker is disabled.')


class LocalResearchRequest(DatasetJobRequest):
    schema_version: Literal[3] = 3
    workflow: Literal['research']
    timeout_seconds: int = Field(default=120,ge=1,le=120)
    analysis_plan: dict
    assumption_review: dict | None

    @model_validator(mode='after')
    def local_plan(self):
        from .onboarding.research.contracts import plan
        plan(self.model_dump())
        return self


class LocalResearchJobRecord(DatasetJobRecord):
    schema_version: Literal[4] = 4
    request: LocalResearchRequest
    max_requests: Literal[0] = 0
    max_output_tokens: Literal[0] = 0
    evaluated_on: str
    admission_readiness_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    producer_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def bound_identity(self):
        from datetime import date
        if (self.profile!='calculate-local-research' or self.operation_id!='web-'+self.job_id[4:]
                or self.request_sha256!=fingerprint(self.request.model_dump())
                or (self.source.dataset_id,self.source.version_id,self.source.contract_sha256)!=
                   (self.request.source.dataset_id,self.request.source.version_id,self.request.source.contract_sha256)):
            raise ValueError('Local research identity changed')
        date.fromisoformat(self.evaluated_on)
        return self


class LocalWorkflowRequest(DatasetJobRequest):
    schema_version: Literal[4] = 4
    workflow: Literal['monitoring','events','news']
    timeout_seconds: int = Field(default=120,ge=1,le=120)
    processing_plan: dict

    @model_validator(mode='after')
    def fixed_method(self):
        from .onboarding.local_workflows.contracts import processing_plan
        if self.processing_plan!=processing_plan(self.workflow):raise ValueError('Unsupported processing plan')
        if type(self.schema_version) is not int or type(self.processing_plan['schema_version']) is not int or self.processing_plan['financial_approval'] is not False:
            raise ValueError('Strict processing plan required')
        return self


class LocalWorkflowJobRecord(DatasetJobRecord):
    schema_version: Literal[5] = 5
    request: LocalWorkflowRequest
    max_requests: Literal[0] = 0
    max_output_tokens: Literal[0] = 0
    producer_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def bound_identity(self):
        from .onboarding.local_workflows.contracts import PROFILES
        if (self.profile!=PROFILES[self.request.workflow] or self.operation_id!='web-'+self.job_id[4:]
                or self.request_sha256!=fingerprint(self.request.model_dump())
                or (self.source.dataset_id,self.source.version_id,self.source.contract_sha256)!=
                   (self.request.source.dataset_id,self.request.source.version_id,self.request.source.contract_sha256)
                or datetime.fromisoformat(self.created_at).utcoffset() is None):raise ValueError('Local workflow binding changed')
        return self
