"""Mutable execution receipts are separate from the immutable v1 admission."""
from typing import Literal
from datetime import datetime

from pydantic import Field, model_validator

from .catalog import Record
from .job_contract import now

STATES = Literal['queued', 'running', 'completed', 'review_required', 'source_changed',
                 'failed', 'outcome_unknown', 'delivery_failed']
TERMINAL = {'completed', 'review_required', 'source_changed', 'failed', 'outcome_unknown', 'delivery_failed'}


class PreparedResult(Record):
    run_id: str = Field(pattern=r'^result-[a-f0-9]{32}$')
    manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    run_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    operation_receipt_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class JobExecution(Record):
    schema_version: int = Field(default=1, ge=1, le=1)
    status: STATES = 'queued'
    attempt: int = Field(default=0, ge=0, le=1)
    started_at: str | None = Field(default=None, max_length=80)
    inputs_verified_at: str | None = Field(default=None, max_length=80)
    finished_at: str | None = Field(default=None, max_length=80)
    operation_status: Literal['not_started', 'running', 'completed', 'review_required', 'failed_inspect_state', 'outcome_unknown'] = 'not_started'
    reason: Literal['waiting', 'processing', 'registered', 'source_changed', 'execution_failed',
                    'interrupted', 'delivery_failed', 'recovered'] = 'waiting'
    result: PreparedResult | None = None

    @model_validator(mode='after')
    def phase(self):
        for value in (self.started_at,self.inputs_verified_at,self.finished_at):
            if value is not None and datetime.fromisoformat(value).utcoffset() is None:
                raise ValueError('Execution timestamps require a timezone.')
        expected_reason = {'queued':{'waiting'},'running':{'processing'},'completed':{'registered','recovered'},
            'review_required':{'registered','recovered'},'source_changed':{'source_changed'},
            'failed':{'execution_failed'},'outcome_unknown':{'interrupted'},'delivery_failed':{'delivery_failed'}}
        if (self.reason not in expected_reason[self.status]
                or self.status == 'queued' and (self.attempt != 0 or self.started_at is not None or self.result is not None
                    or self.inputs_verified_at is not None or self.operation_status != 'not_started')
                or self.status != 'queued' and (self.attempt != 1 or self.started_at is None)
                or self.status in TERMINAL and self.finished_at is None
                or self.status in {'queued', 'running'} and self.finished_at is not None
                or self.status in {'completed', 'review_required', 'delivery_failed'} and
                    (self.result is None or self.operation_status not in {'completed', 'review_required'})
                or self.result is not None and self.inputs_verified_at is None):
            raise ValueError('Execution phase disagrees.')
        return self


def claimed():
    return JobExecution(status='running', attempt=1, started_at=now(), reason='processing')


def changed(execution, **values):
    return JobExecution.model_validate({**execution.model_dump(), **values})
