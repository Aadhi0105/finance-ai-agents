"""Atomic local analytical evidence and delivery-only recovery; no shared ledger writes."""
import os
from pathlib import Path
import uuid
from html import escape

from ...catalog import Catalog,ManifestV3,RunV3,DatasetOrigin,read_confined,read_json,run_identity
from ...job_contract import JobError,now,fingerprint
from ...job_execution import PreparedResult
from ...job_files import write_new,flush_tree
from ...saved_job import artifact_for
from ...report_views.publish import register_views
from ...report_views.values import resolve
from .. import contracts as c
from ..execution import read_inputs,current_version
from ..store import InputStore
from .contracts import semantic,producer,validate_shape


def evidence(result,payload,request,record):
    validate_shape('result',result)
    if result['analysis_plan']!=request['analysis_plan'] or result['lineage']['request_sha256']!=record.request_sha256:
        raise ValueError('Plan mismatch')
    lineage=result['lineage']
    if (any(lineage[k]!=getattr(record.source,k) for k in ('workspace_id','dataset_id','version_id','contract_sha256','payload_sha256','receipt_sha256','entity_sha256','policy_sha256'))
            or lineage['job_id']!=record.job_id or lineage['operation_id']!=record.operation_id
            or lineage['payload_sha256']!=c.fingerprint(payload) or lineage['analysis_plan_sha256']!=c.fingerprint(request['analysis_plan'])
            or lineage['source_reference_sha256']!=c.fingerprint(request['source'])
            or lineage['assumption_review_sha256']!=(c.fingerprint(request['assumption_review']) if request['assumption_review'] else None)):
        raise ValueError('Input or plan mismatch')
    for name in ('metrics','derivations','sections','checks','series'):
        if len({r['id'] for r in result[name]})!=len(result[name]):raise ValueError('Repeated identity')
    from .contracts import SECTIONS
    if {s['id'] for s in result['sections']}!=set(SECTIONS):raise ValueError('Section scope')
    if c.fingerprint({k:v for k,v in result['provenance']['producer'].items() if k not in {'recipe','validator_version'}})!=record.producer_sha256:
        raise ValueError('Producer mismatch')
    metrics={m['id']:m for m in result['metrics']};derivations={d['id']:d for d in result['derivations']}
    if len(metrics)!=len(result['metrics']) or len(derivations)!=len(result['derivations']):raise ValueError('Duplicate identity')
    for metric in metrics.values():
        if metric['value'] is not None and metric['id'] not in derivations[metric['derivation_id']]['metric_ids']:raise ValueError('Derivation mismatch')
    for item in derivations.values():
        if any(resolve(payload,p) is None for p in item['input_pointers']):raise ValueError('Missing input reference')
        for p in item['parameter_pointers']:resolve(result,p)
        if not set(item['metric_ids'])<=metrics.keys():raise ValueError('Missing metric')
    for section in result['sections']:
        if not set(section['metric_ids'])<=metrics.keys():raise ValueError('Missing section metric')
    for series in result['series']:
        for point in series['points']:
            if point['value'] is not None and (metrics[point['metric_id']]['value']!=point['value'] or metrics[point['metric_id']]['period_end']!=point['date']):raise ValueError('Series mismatch')


def export_html(result,entity):
    rows=''.join('<tr><th>'+escape(m['label'])+'</th><td>'+escape(m['value'] if m['value'] is not None else m['availability']+' / '+', '.join(m['reason_codes']))+'</td><td>'+escape((m['currency'] or '')+' '+m['unit'])+'</td><td>'+escape((m['period_end'] or '')+(' / quote '+m['as_of'] if m['as_of'] else ''))+'</td></tr>' for m in result['metrics'])
    import json
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>'+escape(entity)+' · Local research</title><style>body{font:16px/1.6 system-ui;background:#f7f6f0;color:#183c35;max-width:1100px;margin:40px auto;padding:24px}h1{font:42px Georgia}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #ccc}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        '<h1>'+escape(entity)+' · Company analysis</h1><p>Calculated from supplied local evidence · '+escape(result['provenance']['classification'])+'</p>'
        '<p><strong>Review required. No financial approval.</strong> No provider retrieval or model inference. Source authenticity is not independently established.</p>'
        '<p>Statement period '+escape(result['identity']['period_end'])+' · evaluated '+escape(result['execution']['evaluated_on'])+'</p>'
        '<table><caption>Retained calculated figures and section restrictions</caption><thead><tr><th>Measure</th><th>Value / hold</th><th>Unit</th><th>Period / date</th></tr></thead><tbody>'+rows+'</tbody></table>'
        '<h2>Exact selected plan</h2><pre>'+escape(json.dumps(result['analysis_plan'],indent=2,ensure_ascii=False))+'</pre>'
        '<h2>Checks and section availability</h2><pre>'+escape(json.dumps(dict(sections=result['sections'],checks=result['checks']),indent=2,ensure_ascii=False))+'</pre></html>').encode()


def render(folder,record):
    from .calculate import calculate
    folder=Path(folder);source,contract,entity=read_inputs(folder,record)
    inputs=InputStore(folder.parents[2]);probe=type('Probe',(),dict(workspace=inputs.root/'reports'))()
    current_version(probe,record,executing=True)
    package={**contract['metadata'],'payload':source};semantic(package,entity)
    result=calculate(package,record.request.model_dump(),record.source.model_dump(),record.job_id,producer(),record.evaluated_on)
    evidence(result,source,record.request.model_dump(),record)
    stage=folder/('.research-'+uuid.uuid4().hex);target=stage/'runs'/result['result_id'];target.mkdir(parents=True,mode=0o700)
    items=[('payload.json',c.canonical(result),'local-result','Calculated local research','evidence'),
           ('financial-kit.json',c.canonical(source),'financial-kit','Supplied financial observations','evidence'),
           ('analysis-request.json',c.canonical(record.request.model_dump()),'analysis-request','Exact plan and acknowledgement','evidence'),
           ('input-contract.json',c.canonical(contract),'input-contract','Source contract and validation','evidence'),
           ('report_REVIEW.html',export_html(result,entity['name']),'research-report','Local research review export','report')]
    artifacts=[]
    for name,data,id_,label,kind in items:
        write_new(target/name,data);artifacts.append(artifact_for(target/name,target,id_,label,kind))
    origin=DatasetOrigin(**{k:getattr(record.source,k) for k in ('dataset_id','version_id','contract_sha256','payload_sha256','receipt_sha256','entity_sha256','classification')},job_id=record.job_id,request_sha256=record.request_sha256,profile=record.profile)
    run=RunV3(id=result['result_id'],agent='agent1',workflow='research',title=('Company analysis · '+entity['name'])[:160],entity=entity['name'],period=source['periods'][-1]['period_end'],
        prepared_at=now(),execution_status='completed',review_status='review_required',summary='Calculated from supplied local financial observations. Financial review remains required.',
        limitations=['Source permissions and matching files do not establish authenticity.','No provider retrieval, model inference or investment recommendation.'],
        checks=['Exact source, plan and review binding verified.'],metrics=[],artifacts=artifacts,report_id='research-report',source_run_id=result['result_id'],input_origin=origin)
    pr=producer()
    manifest=ManifestV3(schema_version=3,kind='keystone.private-workspace-reports',classification='private',workspace_id=record.source.workspace_id,
        prepared_at=now(),code_commit=pr['code_commit'],code_worktree_dirty=pr['code_worktree_dirty'],preparer_sha256=c.sha(Path(__file__).read_bytes()),production_release_approved=False,runs=[run])
    manifest=register_views(stage,manifest)
    inventory={a.name:dict(sha256=a.sha256,bytes=a.bytes) for a in manifest.runs[0].artifacts}
    proof=dict(schema_version=1,kind='keystone.local-analysis-commit',job_id=record.job_id,request_sha256=record.request_sha256,
        source=record.source.model_dump(),analysis_plan_sha256=c.fingerprint(record.request.analysis_plan),producer_sha256=record.producer_sha256,artifacts=inventory)
    write_new(target/'analysis-commit.json',c.canonical(proof))
    raw=manifest.model_dump();raw['runs'][0]['artifacts'].append(artifact_for(target/'analysis-commit.json',target,'analysis-commit','Atomic analytical result proof','evidence').model_dump())
    temp=stage/'catalog.complete.json';write_new(temp,c.canonical(raw));os.replace(temp,stage/'catalog.json')
    if sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())*2>16_000_000:raise ValueError('Result byte budget')
    Catalog(stage).load();flush_tree(stage)
    current_version(probe,record,executing=True)
    os.rename(stage,folder/'result');flush_tree(folder)
    return 3


def verified_result(store,record,expected=None):
    current_version(store,record)
    folder=store.root/'jobs'/record.job_id;before,contract,entity=read_inputs(folder,record)
    catalog=Catalog(folder/'result');manifest=catalog.load()
    if len(manifest.runs)!=1 or manifest.workspace_id!=record.source.workspace_id:raise JobError('job_recovery_unavailable',409)
    run=manifest.runs[0];artifacts={a.id:a for a in run.artifacts}
    source=read_json(catalog.read(run.id,artifacts['local-result']))
    proof=read_json(catalog.read(run.id,artifacts['analysis-commit']))
    expected_proof=dict(schema_version=1,kind='keystone.local-analysis-commit',job_id=record.job_id,request_sha256=record.request_sha256,
        source=record.source.model_dump(),analysis_plan_sha256=c.fingerprint(record.request.analysis_plan),producer_sha256=record.producer_sha256,
        artifacts={a.name:dict(sha256=a.sha256,bytes=a.bytes) for a in run.artifacts if a.id!='analysis-commit'})
    if proof!=expected_proof or run.source_run_id!=run.id or run.review_status!='review_required' or run.entity!=entity['name']:raise JobError('job_recovery_unavailable',409)
    actual={str(p.relative_to(catalog.root/'runs'/run.id)) for p in (catalog.root/'runs'/run.id).rglob('*') if not p.is_dir()}
    if actual!={a.name for a in run.artifacts}:raise JobError('job_recovery_unavailable',409)
    for artifact in run.artifacts:catalog.read(run.id,artifact)
    if read_json(catalog.read(run.id,artifacts['financial-kit']))!=before or read_json(catalog.read(run.id,artifacts['input-contract']))!=contract or read_json(catalog.read(run.id,artifacts['analysis-request']))!=record.request.model_dump():raise JobError('job_recovery_unavailable',409)
    evidence(source,before,record.request.model_dump(),record)
    origin=run.input_origin
    if any(getattr(origin,k)!=getattr(record.source,k) for k in ('dataset_id','version_id','contract_sha256','payload_sha256','receipt_sha256','entity_sha256','classification')) or origin.job_id!=record.job_id or origin.request_sha256!=record.request_sha256 or origin.profile!=record.profile:raise JobError('job_recovery_unavailable',409)
    from ...job_delivery import operation_proof
    saved,receipt_sha=operation_proof(store,record,committed_local=True)
    prepared=PreparedResult(run_id=run.id,manifest_sha256=c.sha(read_confined(catalog.root,'catalog.json',2_000_000)),run_sha256=fingerprint(run_identity(run)),operation_receipt_sha256=receipt_sha)
    if expected is not None and expected!=prepared:raise JobError('job_recovery_unavailable',409)
    return prepared,run,saved


def commit_hash(store,record):
    catalog=Catalog(store.root/'jobs'/record.job_id/'result');run=catalog.load().runs[0]
    artifact=next(a for a in run.artifacts if a.id=='analysis-commit')
    return c.sha(catalog.read(run.id,artifact))
