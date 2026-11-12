"""Closed input/control contracts, independent of financial execution state."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Literal

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from pydantic import Field, model_validator

from ..catalog import ID, Record, read_json

MAX_PACKAGE = 20_000_000
MAX_INPUT_BYTES = 200_000_000
MAX_ATTEMPTS = 1000
MAX_PENDING = 5
MAX_DATASETS = 100
MAX_VERSIONS = 200
VALIDATION_SECONDS = 60
TRANSFER_SECONDS = 60
FORMATS = {'research': 'agent1.model/2', 'monitoring': 'agent2.snapshot/legacy-1',
           'events': 'agent3.events-bundle/1', 'news': 'agent3.news-bundle/1', 'close': 'agent4.close/1'}
FRESH_CLOSE = 'agent4.close-request/1'
FRESH_RESEARCH = 'agent1.financial-kit/1'
LOCAL_FORMATS = {'monitoring':'agent2.observations/1','events':'agent3.event-windows/1','news':'agent3.news-text/1'}
SUPPORTED_FORMATS = {k: [v] + ([FRESH_CLOSE] if k == 'close' else [FRESH_RESEARCH] if k == 'research' else [LOCAL_FORMATS[k]]) for k, v in FORMATS.items()}
CLASSIFICATIONS = {'synthetic': 'synthetic', 'public_provider': 'provider', 'issuer': 'issuer', 'confidential': 'internal'}
SCHEMA = json.loads(Path(__file__).with_name('package.schema.json').read_text())
Draft202012Validator.check_schema(SCHEMA)
ENVELOPE = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
SHA = r'^[a-f0-9]{64}$'


class InputError(ValueError):
    def __init__(self, code='input_invalid', status=422):
        self.code, self.status = code, status
        super().__init__(code)

    def envelope(self):
        messages = {
            'input_invalid': 'Use the supported JSON input format and matching declared metadata.',
            'input_policy_refused': 'Current source-use evidence does not permit this local action.',
            'input_capacity': 'Input capacity is full; preserve existing evidence and inspect locally.',
            'input_not_found': 'The selected private record is unavailable.',
            'input_conflict': 'This identity already refers to different input or metadata.',
            'input_busy': 'Private workspace control is busy; inspect or retry the same identity.',
            'input_unavailable': 'Private input evidence is missing, changed or inaccessible; preserve it.',
            'input_interrupted': 'Input validation or transfer stopped; inspect its saved receipt.',
            'input_disabled': 'Input admission is disabled for this server.',
            'input_too_large': 'The input exceeds the supported size or structure limits.',
            'input_media_refused': 'Inputs require uncompressed UTF-8 application/json.',
        }
        messages.update({
            'review_scope_changed': 'The selected review scope changed or this source does not belong to the item. Recheck the report.',
            'review_note_invalid': 'Check the note text, attribution, source references and exact review scope.',
            'review_note_conflict': 'This submission identity belongs to a different note. Preserve the original request.',
            'review_note_capacity': 'The review-note limit has been reached. Existing notes and reports are preserved.',
            'review_notes_unavailable': 'Saved review notes could not be verified. Preserve the workspace and ask the operator to inspect it.',
            'review_correction_unsupported': 'Corrections require a private report with an accepted input version.',
            'review_correction_invalid': 'Select a validated successor in the same dataset and recheck its exact change comparison.',
            'review_correction_conflict': 'This submission identity belongs to another correction. Preserve the original request.',
            'review_correction_already_linked': 'This input already has a recorded correction. Inspect its replacement and continue from that version.',
            'review_correction_unchanged': 'The successor contains no source or input changes beyond its lineage pointer.',
            'review_correction_diff_limit': 'This replacement exceeds the 200-change comparison limit. Its accepted input is preserved; inspect it separately.',
            'review_correction_capacity': 'The correction record limit has been reached. Existing inputs and reports are preserved.',
            'review_corrections_unavailable': 'Correction history could not be verified. Preserve the workspace and inspect its saved evidence.',
            'review_decision_invalid': 'Check the review item, decision, explanation and exact history version.',
            'review_decision_stale': 'Review history changed. Recheck saved decisions before recording a new one; preserve any unconfirmed submission.',
            'review_decision_transition': 'This action would repeat the current decision or reopen an item already awaiting review.',
            'review_decision_reference': 'Attached notes or corrections must belong to this exact report, review scope and item.',
            'review_decision_conflict': 'This submission identity belongs to another decision. Preserve the original request.',
            'review_decision_capacity': 'The decision or storage limit was reached. Existing review history is preserved.',
            'review_decisions_unavailable': 'Saved review decisions could not be verified. Preserve the workspace and inspect its records.',
        })
        return {'error': {'code': self.code, 'message': messages[self.code]}}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(value):
    return sha(canonical(value))


def code_identity():
    import subprocess
    import sys
    from keystone.maintenance import ROOT
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,timeout=5)
    dirty=subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True,timeout=5)
    sources={str(p.relative_to(ROOT)):sha(p.read_bytes()) for part in ('keystone/workspace','validation','agent4','agent3','tools')
             for p in sorted((ROOT/part).rglob('*.py'))}
    sources['keystone/workspace/onboarding/package.schema.json']=sha(Path(__file__).with_name('package.schema.json').read_bytes())
    sources['composer.py']=sha((ROOT/'composer.py').read_bytes())
    return dict(code_commit=commit.stdout.strip() if commit.returncode==0 else None,
                code_worktree_dirty=dirty.returncode!=0 or bool(dirty.stdout),python=sys.version.split()[0],source_sha256=sources)


def instant(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.utcoffset() is None:
        raise ValueError('Timezone required')
    return dt.astimezone(timezone.utc)


def bounded_json(data):
    if not 0 < len(data) <= MAX_PACKAGE:
        raise InputError('input_too_large', 413)
    try:
        text = data.decode('utf-8', errors='strict')
        depth, quoted, escaped = 0, False, False
        for c in text:
            if quoted:
                if escaped: escaped = False
                elif c == '\\': escaped = True
                elif c == '"': quoted = False
            elif c == '"': quoted = True
            elif c in '{[':
                depth += 1
                if depth > 64: raise InputError('input_too_large', 413)
            elif c in '}]': depth -= 1
        value = read_json(text.encode('utf-8'))
        stack, values, rows, chars = [value], 0, 0, 0
        while stack:
            x = stack.pop(); values += 1
            if values > 1_000_000: raise InputError('input_too_large', 413)
            if isinstance(x, dict):
                stack.extend(x.keys()); stack.extend(x.values())
            elif isinstance(x, list):
                rows += sum(isinstance(y, dict) for y in x)
                if rows > 50_000: raise InputError('input_too_large', 413)
                stack.extend(x)
            elif isinstance(x, str):
                chars += len(x)
                if len(x) > 100_000 or chars > 2_000_000:
                    raise InputError('input_too_large', 413)
        return value
    except InputError:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError, OverflowError):
        raise InputError() from None


def envelope(value):
    try:
        if not isinstance(value,dict):raise ValueError('Object required')
        if value.get('schema_version') == 3:
            from .local_workflows.contracts import envelope as local_envelope
            return local_envelope(value)
        if value.get('schema_version') == 2:
            from .research.contracts import envelope as local_envelope
            return local_envelope(value)
        ENVELOPE.validate(value)
        if type(value['schema_version']) is not int or value['payload_format'] not in SUPPORTED_FORMATS[value['workflow']]:
            raise ValueError('Unsupported saved input')
        sources = value['sources']
        if len({s['source_id'] for s in sources}) != len(sources):
            raise ValueError('Repeated source')
        for s in sources:
            if s['period_start'] and s['period_end'] and s['period_start'] > s['period_end']:
                raise ValueError('Period order')
        return value
    except (ValueError, TypeError, KeyError, ValidationError):
        raise InputError() from None


class EntityRequest(Record):
    name: str = Field(min_length=1, max_length=160)
    kind: Literal['company', 'group'] = 'company'
    ticker: str | None = Field(default=None, min_length=1, max_length=32)
    members: list[str] = Field(default_factory=list, max_length=1000)

    @model_validator(mode='after')
    def scope(self):
        if (not self.name.strip() or self.kind == 'company' and self.members
                or self.kind == 'group' and (not self.members or self.ticker is not None)
                or len(set(self.members)) != len(self.members)
                or any(not isinstance(x, str) or not x.strip() or len(x)>160 for x in self.members)):
            raise ValueError('Invalid entity scope')
        if self.ticker is not None:
            from tools.event_contracts import ticker
            if ticker(self.ticker) != self.ticker: raise ValueError('Canonical ticker required')
        return self


class Entity(EntityRequest):
    id: str = Field(pattern=ID)
    created_at: str


class DatasetRequest(Record):
    entity_id: str = Field(pattern=ID)
    title: str = Field(min_length=1, max_length=160)
    workflow: Literal['research', 'monitoring', 'events', 'news', 'close']
    payload_format: str

    @model_validator(mode='after')
    def format(self):
        if self.payload_format not in SUPPORTED_FORMATS[self.workflow] or not self.title.strip():
            raise ValueError('Unsupported dataset')
        return self


class Rights(Record):
    local_retention: Literal['allowed', 'denied', 'pending']
    local_processing: Literal['allowed', 'denied', 'pending']
    local_backup: Literal['allowed', 'denied', 'pending']
    model_transfer: Literal['allowed', 'denied', 'pending']
    sharing: Literal['allowed', 'denied', 'pending']


class Permission(Record):
    schema_version: int = Field(ge=1, le=1)
    id: str = Field(pattern=ID)
    workspace_id: str = Field(pattern=ID)
    entity_id: str = Field(pattern=ID)
    payload_sha256: str = Field(pattern=SHA)
    category: Literal['synthetic', 'public_provider', 'issuer', 'confidential']
    provider_or_owner: str = Field(min_length=1, max_length=200)
    intended_use: Literal['private_personal_evaluation']
    evidence_sha256: str = Field(pattern=SHA)
    reviewed_by: str = Field(min_length=1, max_length=160)
    reviewed_at: str = Field(max_length=80)
    expires_at: str | None = Field(max_length=80)
    rights: Rights

    @model_validator(mode='after')
    def dates(self):
        reviewed = instant(self.reviewed_at)
        if reviewed > datetime.now(timezone.utc) or self.expires_at and instant(self.expires_at) <= reviewed:
            raise ValueError('Invalid review dates')
        return self


class Preflight(Record):
    schema_version: int = Field(ge=1, le=3)
    dataset_id: str = Field(pattern=ID)
    package_bytes: int = Field(ge=1, le=MAX_PACKAGE)
    package_sha256: str = Field(pattern=SHA)
    payload_sha256: str = Field(pattern=SHA)
    metadata: dict

    @model_validator(mode='after')
    def metadata_shape(self):
        # Preflight never carries the financial payload.
        if 'payload' in self.metadata: raise ValueError('Payload prohibited in preflight')
        envelope({**self.metadata, 'payload': {'preflight': True}})
        if self.schema_version != self.metadata['schema_version']:
            raise ValueError('Preflight version mismatch')
        if self.schema_version in {2,3} and self.package_bytes > 1_000_000:
            raise ValueError('Local kit size')
        return self


class Producer(Record):
    code_commit: str | None = Field(pattern=r'^[a-f0-9]{40}$')
    code_worktree_dirty: bool
    python: str = Field(min_length=1,max_length=80)
    source_sha256: dict[str,str] = Field(min_length=1,max_length=500)

    @model_validator(mode='after')
    def hashes(self):
        import re
        if any(len(k)>240 or re.fullmatch(SHA,v) is None for k,v in self.source_sha256.items()):
            raise ValueError('Invalid producer evidence')
        return self


class ValidationReceipt(Record):
    schema_version: int = Field(ge=1,le=1)
    validator_version: Literal['1.0.0']
    producer: Producer
    payload_sha256: str = Field(pattern=SHA)
    upstream_id: str = Field(min_length=1,max_length=200)
    period: str = Field(min_length=1,max_length=120)
    execution_status: Literal['completed','held','refused','unavailable','failed']
    eligible: bool
    reasons: list[str] = Field(max_length=30)


class AccountingSource(Record):
    workspace_id: str = Field(pattern=ID)
    entity_id: str = Field(pattern=ID)
    generation_sha256: str = Field(pattern=SHA)
    lineage_versions: list[str] = Field(max_length=MAX_VERSIONS)


class CloseValidationReceipt(ValidationReceipt):
    schema_version: int = Field(ge=2, le=2)
    accounting_source: AccountingSource


def validation_receipt(raw):
    if raw.get('schema_version') == 4:
        from .local_workflows.contracts import LocalValidation
        return LocalValidation.model_validate(raw)
    if raw.get('schema_version') == 3:
        from .research.receipt import LocalReceipt
        return LocalReceipt.model_validate(raw)
    model = CloseValidationReceipt if raw.get('schema_version') == 2 else ValidationReceipt
    return model.model_validate(raw)


def request_key(value):
    import re
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{7,95}', value):
        raise InputError()
    return sha(value.encode())
