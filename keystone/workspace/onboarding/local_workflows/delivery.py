"""Atomic calculated evidence and explicit delivery-only recovery for local workflows."""
from html import escape
import os
from pathlib import Path
import uuid

from ...catalog import Catalog,DatasetOrigin,ManifestV3,RunV3,read_confined,read_json,run_identity
from ...job_contract import JobError,now,fingerprint
from ...job_execution import PreparedResult
from ...job_files import write_new,flush_tree
from ...saved_job import artifact_for
from ...report_views.publish import register_views
from .. import contracts as c
from ..execution import read_inputs,current_version
from ..store import InputStore
from .contracts import semantic,producer,Result


def evidence(result,payload,record):
    Result.model_validate(result)
    if (result['source']!=record.source.model_dump() or result['request_sha256']!=record.request_sha256
            or result['job_id']!=record.job_id or result['workflow']!=record.request.workflow
            or result['producer_sha256']!=record.producer_sha256 or c.fingerprint(payload)!=record.source.payload_sha256):
        raise ValueError('Calculated evidence changed')


def export_html(result,entity):
    rows=''.join('<tr><th>'+escape(m['label'])+'</th><td>'+escape(m['value'] if m['value'] is not None else 'Unavailable: '+m['reason'])+'</td><td>'+escape(m['unit'])+'</td><td>'+escape(m['period'])+'</td></tr>' for m in result['metrics'])
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>'+escape(entity)+' · Local '+result['workflow']+'</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:30px auto;padding:24px;color:#244437;background:#faf9f3}table{width:100%;border-collapse:collapse}td,th{text-align:left;border-bottom:1px solid #ddd;padding:12px}h1{font:40px Georgia}</style>'
        '<h1>'+escape(entity)+' · '+result['workflow'].title()+'</h1><p>New calculations from supplied local evidence · Review required · No financial approval.</p>'
        '<p>No provider retrieval or language-model inference.</p><table><caption>Retained calculated values</caption><thead><tr><th>Measure</th><th>Value / hold</th><th>Unit</th><th>Period</th></tr></thead><tbody>'+rows+'</tbody></table><ul>'+
        ''.join('<li>'+escape(s)+'</li>' for s in result['limitations'])+'</ul></html>').encode()


def render(folder,record):
    from .calculate import calculate
    folder=Path(folder);payload,contract,entity=read_inputs(folder,record)
    inputs=InputStore(folder.parents[2]);probe=type('Probe',(),dict(workspace=inputs.root/'reports'))()
    current_version(probe,record,executing=True)
    result=calculate({**contract['metadata'],'payload':payload},entity,record)
    evidence(result,payload,record)
    stage=folder/('.local-workflows-'+uuid.uuid4().hex);target=stage/'runs'/result['result_id'];target.mkdir(parents=True,mode=0o700)
    items=[('payload.json',c.canonical(result),'local-result','New local calculation evidence','evidence'),
        ('supplied-input.json',c.canonical(payload),'supplied-input','Exact supplied observations and parameters','evidence'),
        ('analysis-request.json',c.canonical(record.request.model_dump()),'analysis-request','Exact confirmed processing request','evidence'),
        ('input-contract.json',c.canonical(contract),'input-contract','Source-use contract and validation','evidence'),
        ('report_REVIEW.html',export_html(result,entity['name']),'local-report','Local workflow review export','report')]
    artifacts=[]
    for name,data,id_,label,kind in items:
        write_new(target/name,data);artifacts.append(artifact_for(target/name,target,id_,label,kind))
    origin=DatasetOrigin(**{k:getattr(record.source,k) for k in ('dataset_id','version_id','contract_sha256','payload_sha256','receipt_sha256','entity_sha256','classification')},job_id=record.job_id,request_sha256=record.request_sha256,profile=record.profile)
    run=RunV3(id=result['result_id'],agent='agent2' if record.request.workflow=='monitoring' else 'agent3',workflow=record.request.workflow,
        title=('Local '+record.request.workflow+' · '+entity['name'])[:160],entity=entity['name'],period=result['period'],prepared_at=now(),execution_status='held',
        review_status='review_required',summary='New calculations from supplied local evidence. Financial review remains required.',
        limitations=result['limitations'],checks=['Exact input, source-use scope and fixed method verified.'],metrics=[],artifacts=artifacts,
        report_id='local-report',source_run_id=result['result_id'],input_origin=origin)
    pr=producer()
    manifest=ManifestV3(schema_version=3,kind='keystone.private-workspace-reports',classification='private',workspace_id=record.source.workspace_id,
        prepared_at=now(),code_commit=pr['code_commit'],code_worktree_dirty=pr['code_worktree_dirty'],preparer_sha256=c.sha(Path(__file__).read_bytes()),production_release_approved=False,runs=[run])
    manifest=register_views(stage,manifest)
    proof=dict(schema_version=1,kind='keystone.local-workflow-commit',job_id=record.job_id,request_sha256=record.request_sha256,
        source=record.source.model_dump(),producer_sha256=record.producer_sha256,
        artifacts={a.name:dict(sha256=a.sha256,bytes=a.bytes) for a in manifest.runs[0].artifacts})
    write_new(target/'analysis-commit.json',c.canonical(proof))
    raw=manifest.model_dump();raw['runs'][0]['artifacts'].append(artifact_for(target/'analysis-commit.json',target,'analysis-commit','Atomic analytical completion proof','evidence').model_dump())
    temp=stage/'catalog.complete.json';write_new(temp,c.canonical(raw));os.replace(temp,stage/'catalog.json')
    if sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())*2>16_000_000:raise ValueError('Result byte budget')
    Catalog(stage).load();flush_tree(stage);current_version(probe,record,executing=True)
    os.rename(stage,folder/'result');flush_tree(folder)
    return 3


def verified_result(store,record,expected=None):
    current_version(store,record)
    folder=store.root/'jobs'/record.job_id;payload,contract,entity=read_inputs(folder,record)
    catalog=Catalog(folder/'result');manifest=catalog.load()
    if len(manifest.runs)!=1 or manifest.workspace_id!=record.source.workspace_id:raise JobError('job_recovery_unavailable',409)
    run=manifest.runs[0];artifacts={a.id:a for a in run.artifacts}
    result=read_json(catalog.read(run.id,artifacts['local-result']));evidence(result,payload,record)
    proof=read_json(catalog.read(run.id,artifacts['analysis-commit']))
    desired=dict(schema_version=1,kind='keystone.local-workflow-commit',job_id=record.job_id,request_sha256=record.request_sha256,
        source=record.source.model_dump(),producer_sha256=record.producer_sha256,
        artifacts={a.name:dict(sha256=a.sha256,bytes=a.bytes) for a in run.artifacts if a.id!='analysis-commit'})
    if (proof!=desired or run.id!=result['result_id'] or run.source_run_id!=run.id or run.review_status!='review_required'
            or run.entity!=entity['name'] or run.workflow!=record.request.workflow or run.execution_status!='held'
            or run.period!=result['period']):raise JobError('job_recovery_unavailable',409)
    actual={str(p.relative_to(catalog.root/'runs'/run.id)) for p in (catalog.root/'runs'/run.id).rglob('*') if not p.is_dir()}
    if actual!={a.name for a in run.artifacts}:raise JobError('job_recovery_unavailable',409)
    for a in run.artifacts:catalog.read(run.id,a)
    for id_,value in [('supplied-input',payload),('input-contract',contract),('analysis-request',record.request.model_dump())]:
        if read_json(catalog.read(run.id,artifacts[id_]))!=value:raise JobError('job_recovery_unavailable',409)
    expected_origin=DatasetOrigin(**{k:getattr(record.source,k) for k in ('dataset_id','version_id','contract_sha256','payload_sha256','receipt_sha256','entity_sha256','classification')},job_id=record.job_id,request_sha256=record.request_sha256,profile=record.profile)
    if run.input_origin!=expected_origin:raise JobError('job_recovery_unavailable',409)
    from ...job_delivery import operation_proof
    saved,receipt_sha=operation_proof(store,record,committed_local=True)
    prepared=PreparedResult(run_id=run.id,manifest_sha256=c.sha(read_confined(catalog.root,'catalog.json',2_000_000)),run_sha256=fingerprint(run_identity(run)),operation_receipt_sha256=receipt_sha)
    if expected is not None and expected!=prepared:raise JobError('job_recovery_unavailable',409)
    return prepared,run,saved


def commit_hash(store,record):
    catalog=Catalog(store.root/'jobs'/record.job_id/'result');run=catalog.load().runs[0]
    return c.sha(catalog.read(run.id,next(a for a in run.artifacts if a.id=='analysis-commit')))
