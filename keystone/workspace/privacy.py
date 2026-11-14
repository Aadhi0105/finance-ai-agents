"""Bounded private access observations and an identifier-free diagnostic export.

These observations do not grant rights, modify permissions or read payload prose.
The local bearer key represents possession, not an authenticated analyst identity.
"""
from datetime import datetime,timezone
from typing import Literal

from pydantic import Field,model_validator

from .catalog import Record,ID
from .job_contract import now
from .job_store import private_member
from .lifecycle import scan
from .onboarding import contracts as c

MAX_PERMISSIONS=1000
MAX_RESPONSE_BYTES=16_000
MAX_SOURCE_BYTES=50_000_000
State=Literal['checked','attention','unavailable']
RIGHTS=('local_retention','local_processing','local_backup','model_transfer','sharing')


class Counts(Record):
    allowed: int=Field(ge=0,le=MAX_PERMISSIONS)
    denied: int=Field(ge=0,le=MAX_PERMISSIONS)
    pending: int=Field(ge=0,le=MAX_PERMISSIONS)


class Rights(Record):
    local_retention: Counts
    local_processing: Counts
    local_backup: Counts
    model_transfer: Counts
    sharing: Counts


class Sources(Record):
    state: State
    records: int|None=Field(ge=0,le=MAX_PERMISSIONS)
    held_records: int|None=Field(ge=0,le=MAX_PERMISSIONS)
    versions: int|None=Field(ge=0,le=c.MAX_VERSIONS)
    held_versions: int|None=Field(ge=0,le=c.MAX_VERSIONS)
    rights: Rights|None

    @model_validator(mode='after')
    def consistency(self):
        values=(self.records,self.held_records,self.versions,self.held_versions,self.rights)
        if self.state=='unavailable':
            if any(v is not None for v in values): raise ValueError('Unknown counts')
        else:
            if any(v is None for v in values): raise ValueError('Missing counts')
            if self.held_records>self.records or self.held_versions>self.versions: raise ValueError('Counts')
            for name in RIGHTS:
                row=getattr(self.rights,name)
                if row.allowed+row.denied+row.pending!=self.records: raise ValueError('Rights counts')
            attention=bool(self.held_records or self.held_versions or self.rights.local_backup.denied or self.rights.local_backup.pending)
            if self.state!=('attention' if attention else 'checked'): raise ValueError('State')
        return self


class Controls(Record):
    local_key: Literal['checked','unavailable']
    workspace_files: State
    browser_credentials: Literal['tab_memory_only']='tab_memory_only'
    delivery: Literal['protected_no_store']='protected_no_store'
    diagnostic_export: Literal['allowlisted_no_identifiers']='allowlisted_no_identifiers'
    token_rotation: Literal['stop_and_restart']='stop_and_restart'
    analyst_identity: Literal['not_authenticated']='not_authenticated'
    automatic_session_expiry: Literal[False]=False
    live_data_enabled: Literal[False]=False
    paid_models_enabled: Literal[False]=False
    external_sharing_enabled: Literal[False]=False
    financial_approval: Literal[False]=False
    production_release_approved: Literal[False]=False


class Diagnostic(Record):
    schema_version: Literal[1]=1
    kind: Literal['keystone.privacy-diagnostic']='keystone.privacy-diagnostic'
    observed_at: str=Field(max_length=80)
    state: State
    controls: Controls
    source_use: State

    @model_validator(mode='after')
    def consistency(self):
        c.instant(self.observed_at)
        levels=(self.controls.local_key,self.controls.workspace_files,self.source_use)
        expected='unavailable' if 'unavailable' in levels else 'attention' if 'attention' in levels else 'checked'
        if self.state!=expected:raise ValueError('State')
        return self


class Privacy(Record):
    schema_version: Literal[1]=1
    kind: Literal['keystone.privacy']='keystone.privacy'
    workspace_id: str=Field(pattern=ID)
    observed_at: str=Field(max_length=80)
    state: State
    controls: Controls
    sources: Sources

    @model_validator(mode='after')
    def consistency(self):
        Diagnostic(observed_at=self.observed_at,state=self.state,controls=self.controls,source_use=self.sources.state)
        return self


def source_summary(inputs):
    try:
        read_bytes=0;budget_failed=False
        def read(name,limit=131072):
            nonlocal read_bytes,budget_failed
            remaining=MAX_SOURCE_BYTES-read_bytes
            if remaining<=0:budget_failed=True;raise ValueError()
            try:data=inputs.read(name,min(limit,remaining))
            except Exception:
                if remaining<limit:budget_failed=True
                raise
            read_bytes+=len(data)
            return data
        with inputs.connect() as con:
            ids=[r[0] for r in con.execute("SELECT id FROM objects WHERE kind='permission' LIMIT ?",(MAX_PERMISSIONS+1,))]
            versions=[r[0] for r in con.execute("SELECT id FROM objects WHERE kind='version' LIMIT ?",(c.MAX_VERSIONS+1,))]
            if len(ids)>MAX_PERMISSIONS or len(versions)>c.MAX_VERSIONS:raise ValueError()
            rows={key:dict(allowed=0,denied=0,pending=0) for key in RIGHTS};held=0
            for id_ in ids:
                raw=inputs._object(con,'permission',id_);policy=c.Permission.model_validate(raw)
                if (policy.workspace_id!=inputs.descriptor['id'] or policy.id!=id_
                        or read('permissions/'+id_+'/record.json',65536)!=c.canonical(raw)
                        or c.sha(read('permissions/'+id_+'/evidence',c.MAX_PACKAGE))!=policy.evidence_sha256):raise ValueError()
                inputs._object(con,'entity',policy.entity_id)
                revoked=con.execute('SELECT 1 FROM objects WHERE id=?',('revoked-'+c.sha(id_.encode())[:32],)).fetchone()
                held+=bool(revoked or policy.expires_at and c.instant(policy.expires_at)<=datetime.now(timezone.utc)
                           or policy.rights.local_retention!='allowed' or policy.rights.local_processing!='allowed')
                for key in RIGHTS:rows[key][getattr(policy.rights,key)]+=1
        held_versions=0
        # Reuse the action gate's policy semantics while bounding *all* its file
        # reads too. This checks source-use contracts, not financial payloads.
        from copy import copy
        reader=copy(inputs);reader.read=read
        for id_ in versions:
            version=inputs.object('version',id_);contract=version['contract']
            if (read('inputs/'+id_+'/contract.json')!=c.canonical(contract)
                    or c.fingerprint(contract)!=version['contract_sha256']):raise ValueError()
            entity=inputs.object('entity',contract['metadata']['dataset']['entity_id'])
            if c.fingerprint(entity)!=contract['entity_sha256']:raise ValueError()
            try:
                if reader.policies(contract['metadata'],contract['payload_sha256'],entity)!=contract['policy']:
                    held_versions+=1
            except c.InputError as error:
                if error.code!='input_policy_refused':raise
                if budget_failed:raise ValueError()
                held_versions+=1
        attention=held or held_versions or rows['local_backup']['pending'] or rows['local_backup']['denied']
        return Sources(state='attention' if attention else 'checked',records=len(ids),held_records=held,
            versions=len(versions),held_versions=held_versions,rights=Rights(**rows))
    except Exception:
        return Sources(state='unavailable',records=None,held_records=None,versions=None,held_versions=None,rights=None)


def observe(session):
    files='unavailable'
    try:
        inputs=session.inputs
        def bound():
            if (private_member(inputs.root,directory=True)!=inputs._root_identity
                    or inputs.read('workspace.json',65536)!=c.canonical(inputs.descriptor)):raise ValueError()
        bound();areas,_=scan(inputs.root);bound()
        files='checked' if all(a.state=='observed' for a in areas) else 'attention'
    except Exception:pass
    sources=source_summary(session.inputs)
    controls=Controls(local_key='checked' if session.access_key_current() else 'unavailable',workspace_files=files)
    levels=(controls.local_key,files,sources.state)
    value=Privacy(workspace_id=session.inputs.descriptor['id'],observed_at=now(),
        state='unavailable' if 'unavailable' in levels else 'attention' if 'attention' in levels else 'checked',
        controls=controls,sources=sources).model_dump()
    if len(c.canonical(value))>MAX_RESPONSE_BYTES:raise c.InputError('input_unavailable',503)
    return value


def diagnostic(session):
    view=Privacy.model_validate(observe(session))
    return Diagnostic(observed_at=view.observed_at,state=view.state,controls=view.controls,source_use=view.sources.state).model_dump()
