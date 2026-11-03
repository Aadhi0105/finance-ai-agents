"""Dataset-pinned offline jobs; accepted inputs are never bootstrap reports."""
from pathlib import Path
import os
import uuid

from ..catalog import (Catalog,DatasetOrigin,ManifestV3,RunV3,read_confined,read_json,run_identity)
from ..job_contract import JobError,fingerprint,now
from ..job_execution import PreparedResult
from ..job_files import write_new,flush_tree,digest_bytes
from . import contracts as c
from .store import InputStore
from .service import binding


def current_version(store,record,*,executing=False):
    try:
        inputs=InputStore(store.workspace.parent)
        version=inputs.version(record.source.version_id,processing=True)
        if binding(inputs,version)!=record.source:raise ValueError()
        if record.schema_version==4 and executing:
            from .research.contracts import readiness,producer
            payload=read_json(inputs.read('inputs/'+version['id']+'/payload.json'))
            if c.fingerprint(readiness(payload))!=record.admission_readiness_sha256 or c.fingerprint(producer())!=record.producer_sha256:
                raise ValueError('Local readiness or producer changed')
        return inputs,version
    except Exception:raise JobError('job_source_unavailable',409) from None


def prepare_inputs(store,record):
    inputs,version=current_version(store,record,executing=True)
    manifest=Catalog(store.workspace).load()
    if manifest.schema_version!=3 or manifest.workspace_id!=record.source.workspace_id:raise JobError('job_source_unavailable')
    if any(r.id=='result-'+record.job_id[4:] for r in manifest.runs):raise JobError('job_recovery_unavailable',409)
    if len(manifest.runs)>=100:raise JobError('job_capacity_reached',409)
    if record.schema_version == 3:
        from .close_state import begin
        try: begin(inputs,record)
        except Exception: raise JobError('job_source_unavailable',409) from None
    folder=store.root/'jobs'/record.job_id
    folder.mkdir(parents=True,mode=0o700,exist_ok=False)
    write_new(folder/'job.json',c.canonical(record.model_dump()))
    working=folder/'inputs';working.mkdir(mode=0o700)
    for name in ('payload.json','validation.json','contract.json'):
        write_new(working/name,inputs.read('inputs/'+version['id']+'/'+name))
    entity=inputs.object('entity',version['contract']['metadata']['dataset']['entity_id'])
    write_new(working/'entity.json',c.canonical(entity))
    read_inputs(folder,record)
    current_version(store,record,executing=True)
    flush_tree(folder)
    return folder


def read_inputs(folder,record):
    inputs=Path(folder)/'inputs'
    raw={name:read_confined(inputs,name) for name in ('payload.json','validation.json','contract.json','entity.json')}
    contract=read_json(raw['contract.json']);validation=read_json(raw['validation.json']);entity=read_json(raw['entity.json'])
    if (c.sha(raw['payload.json'])!=record.source.payload_sha256
            or c.sha(raw['validation.json'])!=record.source.receipt_sha256
            or c.fingerprint(contract)!=record.source.contract_sha256
            or c.fingerprint(entity)!=record.source.entity_sha256
            or c.fingerprint(contract['policy'])!=record.source.policy_sha256
            or contract['policy']['classification']!=record.source.classification
            or contract['metadata']['workflow']!=record.request.workflow
            or contract['dataset_id']!=record.source.dataset_id
            or contract['validation']!=validation or not validation['eligible']):
        raise JobError('job_source_unavailable')
    if record.schema_version == 3 and (contract['metadata']['payload_format'] != c.FRESH_CLOSE
            or validation.get('accounting_source') != record.accounting_source):
        raise JobError('job_source_unavailable')
    if record.schema_version==4 and contract['metadata']['payload_format']!=c.FRESH_RESEARCH:raise JobError('job_source_unavailable')
    return read_json(raw['payload.json']),contract,entity


def render(folder,record, *, saved_close=None):
    if record.schema_version==4:
        from .research.delivery import render as render_local
        return render_local(folder,record)
    source,contract,entity=read_inputs(folder,record)
    description=contract['validation'];workflow=record.request.workflow
    fresh = record.schema_version == 3
    accounting = None
    if fresh:
        from .close_state import calculate, remember
        inputs = InputStore(Path(folder).parents[2])
        version = inputs.version(record.source.version_id,processing=True)
        if binding(inputs,version) != record.source: raise JobError('job_source_unavailable',409)
        saved,proof = saved_close if saved_close is not None else calculate(inputs,record,source)
        accounting = dict(commit_sha256=remember(inputs,proof), bundle_sha256=proof['bundle_digest'],
                          classification=proof['classification'], lineage_versions=proof['lineage_versions'])
        source = saved['bundle']
    stage=Path(folder)/('.close-delivery-'+uuid.uuid4().hex if fresh else 'result');stage.mkdir(mode=0o700,exist_ok=False)
    id_='result-'+record.job_id[4:]
    target=stage/'runs'/id_;target.mkdir(parents=True,mode=0o700)
    primary=target/'payload.json'
    write_new(primary,c.canonical(source) if fresh else read_confined(Path(folder)/'inputs','payload.json'))
    from ..saved_job import artifact_for
    from ..report_views.publish import register_views
    artifacts=[]
    if workflow=='research':
        import composer
        report=Path(composer.build_report(str(primary)))
        artifacts += [artifact_for(p,target,'chart-'+str(i),'Rebuilt saved chart','chart')
                      for i,p in enumerate(sorted((target/'charts').glob('*.png')))]
    elif workflow=='monitoring':
        from monitoring.reporting import render_report
        report=target/'report.html';write_new(report,render_report(source).encode())
    elif workflow in {'events','news'}:
        from agent3.bundles import read_bundle,replay,export_html
        bundle=read_bundle(primary);rebuilt=replay(bundle)
        if rebuilt['verification']!='matched':raise ValueError('Replay did not match')
        report=target/'report.html';write_new(report,export_html(bundle,rebuilt).encode())
    else:
        from agent4.report import render_report
        from agent4.state import digest
        saved=dict(bundle=source,bundle_digest=digest(source))
        report=target/'report.html';write_new(report,render_report(saved,[saved]).encode())
    artifacts += [artifact_for(primary,target,'imported-source','Imported saved evidence','evidence'),
                  artifact_for(report,target,'rebuilt-report','Rebuilt saved report','report')]
    if fresh:
        for name,data,label in [('close-request.json',read_confined(Path(folder)/'inputs','payload.json'),'Submitted close request'),
                                ('accounting-commit.json',c.canonical(proof),'Atomic accounting commit proof')]:
            write_new(target/name,data)
            artifacts.append(artifact_for(target/name,target,name.split('.')[0],label,'evidence'))
    # Make lineage and the policy/validation basis inspectable beside the report.
    write_new(target/'input-contract.json',c.canonical(contract))
    artifacts.append(artifact_for(target/'input-contract.json',target,'input-contract','Input contract and validation basis','evidence'))
    origin=DatasetOrigin(**{k:getattr(record.source,k) for k in ('dataset_id','version_id','contract_sha256','payload_sha256','receipt_sha256','entity_sha256','classification')},
                         job_id=record.job_id,request_sha256=record.request_sha256,profile=record.profile)
    run=RunV3(id=id_,agent={'research':'agent1','monitoring':'agent2','events':'agent3','news':'agent3','close':'agent4'}[workflow],
        workflow=workflow,title=(('Calculated close · ' if fresh else 'Imported saved run · ')+contract['metadata']['dataset']['title'])[:160],
        entity=entity['name'],period=description['period'],prepared_at=now(),execution_status=description['execution_status'],
        review_status='review_required',summary='Budget and actuals calculated offline. Financial review remains required.' if fresh else 'Saved evidence processed offline. Financial review remains required.',
        limitations=['Imported source-use records are local attestations; file integrity is not source authenticity.',
                     'No fresh provider data, model inference or authenticated financial approval.'],
        checks=['Input version and source-use scope matched before processing.'],metrics=[],artifacts=artifacts,
        report_id='rebuilt-report',source_run_id=description['upstream_id'],input_origin=origin,accounting_origin=accounting)
    producer=c.code_identity()
    manifest=ManifestV3(schema_version=3,kind='keystone.private-workspace-reports',classification='private',
        workspace_id=record.source.workspace_id,prepared_at=now(),code_commit=producer['code_commit'],code_worktree_dirty=producer['code_worktree_dirty'],
        preparer_sha256=c.sha(Path(__file__).read_bytes()),production_release_approved=False,runs=[run])
    register_views(stage,manifest)
    Catalog(stage).load();flush_tree(stage)
    if fresh:
        if (Path(folder)/'result').exists(): raise JobError('job_recovery_unavailable',409)
        os.rename(stage,Path(folder)/'result');flush_tree(Path(folder))
    return 3


def verified_result(store,record,expected=None):
    if record.schema_version==4:
        from .research.delivery import verified_result as verify_local
        return verify_local(store,record,expected)
    inputs,_ = current_version(store,record)
    folder=store.root/'jobs'/record.job_id
    before,contract,entity=read_inputs(folder,record)
    stage=folder/'result';catalog=Catalog(stage);manifest=catalog.load()
    if manifest.schema_version!=3 or manifest.workspace_id!=record.source.workspace_id or len(manifest.runs)!=1:
        raise JobError('job_recovery_unavailable',409)
    run=manifest.runs[0];origin=run.input_origin
    desired=DatasetOrigin(**{k:getattr(record.source,k) for k in ('dataset_id','version_id','contract_sha256','payload_sha256','receipt_sha256','entity_sha256','classification')},
        job_id=record.job_id,request_sha256=record.request_sha256,profile=record.profile)
    description=contract['validation']
    if (origin!=desired or run.workflow!=record.request.workflow or run.entity!=entity['name']
            or run.source_run_id!=description['upstream_id'] or run.period!=description['period']
            or run.execution_status!=description['execution_status'] or run.review_status!='review_required'):
        raise JobError('job_recovery_unavailable',409)
    primary=next(a for a in run.artifacts if a.id==run.native_view.source_artifact_ids[0])
    rebuilt=read_json(catalog.read(run.id,primary))
    fresh = record.schema_version == 3
    if fresh:
        from .close_state import registry_proof
        from agent4.state import digest
        from agent4.report import validate_bundle
        proof = registry_proof(inputs,record)
        validate_bundle(dict(bundle=rebuilt,bundle_digest=proof['bundle_digest']))
        requested=next(a for a in run.artifacts if a.id=='close-request')
        committed=next(a for a in run.artifacts if a.id=='accounting-commit')
        if (run.accounting_origin is None or run.accounting_origin.model_dump() !=
                dict(commit_sha256=c.fingerprint(proof),bundle_sha256=proof['bundle_digest'],
                     classification=proof['classification'],lineage_versions=proof['lineage_versions'])
                or read_json(catalog.read(run.id,requested)) != before or read_json(catalog.read(run.id,committed)) != proof
                or rebuilt['request'] != before or digest(before) != proof['native_request_sha256']):
            raise JobError('job_recovery_unavailable',409)
    excluded={'artifacts','validation','note'} if run.workflow=='research' else set()
    if not fresh and {k:v for k,v in before.items() if k not in excluded}!={k:v for k,v in rebuilt.items() if k not in excluded}:
        raise JobError('job_recovery_unavailable',409)
    lineage=next(a for a in run.artifacts if a.id=='input-contract')
    if read_json(catalog.read(run.id,lineage))!=contract:raise JobError('job_recovery_unavailable',409)
    from ..job_delivery import operation_proof
    saved,receipt_sha=operation_proof(store,record,committed_close=fresh)
    result=PreparedResult(run_id=run.id,manifest_sha256=digest_bytes(read_confined(stage,'catalog.json',2_000_000)),
                          run_sha256=fingerprint(run_identity(run)),operation_receipt_sha256=receipt_sha)
    if expected is not None and expected!=result:raise JobError('job_recovery_unavailable',409)
    return result,run,saved
