"""New supplied-input workflows: independent outcomes, boundaries and one-attempt delivery."""
from copy import deepcopy
from pathlib import Path
import json
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient
import pytest

from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog
from keystone.workspace.job_contract import JobError,LocalWorkflowJobRecord,LocalWorkflowRequest
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.onboarding.local_workflows.contracts import FORMATS,PROFILES,processing_plan,semantic,producer,Result
from keystone.workspace.onboarding.local_workflows.calculate import calculate
from keystone.workspace.onboarding.service import binding
from keystone.workspace.worker import run_one,recover_delivery
from test_workspace_onboarding import session,headers,ORIGIN
from test_workspace_fresh_close import worker

ROOT=Path(__file__).resolve().parents[1]


def sample(w):return json.loads((ROOT/'fixtures/local_workflows'/f'{w}.json').read_text())


def entity(w):return dict(id='entity-example',name='Northstar Components',kind='group' if w=='events' else 'company',ticker=None if w=='events' else 'NSTAR',members=['NSTAR'] if w=='events' else [])


def request(v):
    w=v['contract']['metadata']['workflow']
    return dict(schema_version=4,workflow=w,source=dict(kind='dataset_version',dataset_id=v['dataset_id'],version_id=v['id'],contract_sha256=v['contract_sha256']),timeout_seconds=120,processing_plan=processing_plan(w))


def ingest(session,w,edit=None):
    e=entity(w);e.pop('id');e=session.inputs.create_entity(e)
    d=session.inputs.create_dataset(dict(entity_id=e['id'],title='Fictional '+w,workflow=w,payload_format=FORMATS[w]))
    value=sample(w);value['dataset']['entity_id']=value['payload']['entity_id']=e['id']
    if edit:edit(value)
    evidence=b'Fictional test permission. No real sources or data rights claimed.'
    policy=dict(schema_version=1,id='permission-'+uuid.uuid4().hex,workspace_id=session.inputs.descriptor['id'],entity_id=e['id'],payload_sha256=c.fingerprint(value['payload']),
        category='synthetic',provider_or_owner=value['sources'][0]['provider_or_owner'],intended_use='private_personal_evaluation',evidence_sha256=c.sha(evidence),reviewed_by='Test operator',reviewed_at='2026-01-01T00:00:00Z',expires_at=None,
        rights=dict(local_retention='allowed',local_processing='allowed',local_backup='allowed',model_transfer='denied',sharing='denied'))
    session.inputs.install_permission(policy,evidence)
    for s in value['sources']:s['permission_record_id']=policy['id']
    raw=c.canonical(value);key='local-import-'+uuid.uuid4().hex
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    r=api.post('/api/datasets/'+d['id']+'/inspect',content=raw,headers=headers(session));assert r.status_code==200,r.text
    r=api.post('/api/imports',json=r.json()['descriptor'],headers=headers(session,key));assert r.status_code==201,r.text
    r=api.put('/api/imports/'+r.json()['import_attempt']['id']+'/package',content=raw,headers=headers(session,key));assert r.status_code==200,r.text
    return session.inputs.version(r.json()['version_id']),policy


def pure(w,edit=None):
    package=sample(w)
    if edit:edit(package['payload'])
    source=dict(workspace_id='workspace-example',dataset_id='dataset-example',version_id='version-example',classification='synthetic',
        **{k:'a'*64 for k in ('contract_sha256','receipt_sha256','entity_sha256','policy_sha256')},payload_sha256=c.fingerprint(package['payload']))
    req=dict(schema_version=4,workflow=w,source=dict(kind='dataset_version',dataset_id=source['dataset_id'],version_id=source['version_id'],contract_sha256=source['contract_sha256']),timeout_seconds=120,processing_plan=processing_plan(w))
    job=LocalWorkflowJobRecord(job_id='job-'+'1'*32,operation_id='web-'+'1'*32,request=LocalWorkflowRequest.model_validate(req),request_sha256=c.fingerprint(req),created_at='2026-01-01T00:00:00Z',profile=PROFILES[w],source=source,producer_sha256=c.fingerprint(producer()))
    result=calculate(package,entity(w),job);Result.model_validate(result)
    return result


@pytest.mark.parametrize('w',FORMATS)
def test_import_job_native_and_delivery_only(session,w,monkeypatch):
    version,_=ingest(session,w)
    assert version['contract']['validation']['analytical_execution']=='not_started'
    assert not Catalog(session.catalog.root).load().runs
    body=request(version);job,replayed=session.submit(body,'new-local-workflow-0001');assert not replayed
    assert session.submit(body,'new-local-workflow-0001')[1]
    assert job['max_requests']==job['max_output_tokens']==0
    assert job['admission_schema_version']==4
    with worker(session) as store:
        assert run_one(store)==(True,False)
        saved=store.get(job['job_id'])['job'];assert saved['status']=='review_required',saved
        assert saved['execution']['attempt']==1 and saved['execution']['analysis_commit_sha256']
        from keystone.workspace.onboarding.local_workflows import calculate as engine
        monkeypatch.setattr(engine,'calculate',lambda *_a,**_k:pytest.fail('Delivery recovery recalculated'))
        assert recover_delivery(store,job['job_id'])['job']['status']=='review_required'
        assert run_one(store)==(False,False)
    run=Catalog(session.catalog.root).load().runs[0]
    with TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN) as api:
        assert api.get('/api/runs/'+run.id+'/report-view').status_code==403
        r=api.get('/api/runs/'+run.id+'/report-view',headers=headers(session));assert r.status_code==200,r.text
        view=r.json();assert view['summary']['template_id']=='local-workflow-summary-v1'
        assert view['state']['financial_approval'] is False
        assert view['state']['evidence_gate']=='held_for_review'
        assert any(ch['availability']=='available' for ch in view['charts'])
        assert all(m['availability']=='available' and m['value'] is not None for m in view['metrics'] if m['unit']=='count')


def test_monitoring_independent_policy_outcomes_and_missingness():
    result=pure('monitoring');m={m['id']:m for m in result['metrics']}
    assert m['breaches']['value']=='1' and m['missing']['value']=='1' and m['assessed']['value']=='1'
    rows=result['details']['items'][0]['rows']
    assert [r['status'] for r in rows]==['BASELINE','NEW_BREACH','KNOWN_STABLE']
    assert result['rows'][1]['status']=='MISSING_OBSERVATION'
    assert result['charts'][1]['points'][-1]['value'] is None


def test_event_arithmetic_independent_of_gate():
    result=pure('events');study=result['details']['study']
    # Constructed stock returns = .0005 + 1.2*market + [.01,.02,.03].
    assert study['per_event'][0]['alpha']==pytest.approx(.0005)
    assert study['per_event'][0]['beta']==pytest.approx(1.2)
    assert study['caar']==pytest.approx(.06)
    assert study['p_value'] is None and result['details']['scenario']['distribution'] is None


def test_news_filter_dedup_actual_word_counts_and_no_match():
    result=pure('news');d=result['details']
    assert d['funnel']==dict(raw=5,ingested=4,relevant=3,clusters=2)
    assert len(d['exclusions'])==2
    stories=d['scored_items'];first=next(s for s in stories if s['cluster_size']==2)
    assert first['score_evidence']['positive_count']==2 and first['score_evidence']['negative_count']==0
    assert first['sentiment']==pytest.approx(2/6)
    assert next(s for s in stories if s['cluster_size']==1)['sentiment'] is None
    assert all(s['level'] is None for s in d['signals'])


@pytest.mark.parametrize('w',FORMATS)
def test_new_format_cannot_impersonate_saved_job(session,w):
    v,_=ingest(session,w);body=request(v);body.pop('processing_plan');body['schema_version']=2
    with pytest.raises(JobError):session.submit(body,'wrong-job-family-0001')


@pytest.mark.parametrize('w',FORMATS)
def test_policy_revocation_after_admission_holds_job(session,w):
    v,p=ingest(session,w);job,_=session.submit(request(v),'source-revocation-0001')
    session.inputs.revoke_permission(p['id'],'Fictional authorisation revoked in test')
    with worker(session) as store:
        run_one(store);assert store.get(job['job_id'])['job']['status']=='source_changed'
    assert not Catalog(session.catalog.root).load().runs


@pytest.mark.parametrize('w',FORMATS)
def test_closed_payload_rejects_extra_fields(w):
    p=sample(w);p['payload']['arbitrary_path']='/tmp/private'
    with pytest.raises(ValueError):semantic(p,entity(w))


@pytest.mark.parametrize('case',['duplicate_date','future','unit','threshold_bool','duplicate_item','source','missing_minimum'])
def test_monitoring_invalid_inputs(case):
    p=sample('monitoring');i=p['payload']['items'][0]
    if case=='duplicate_date':i['observations'][1]['date']=i['observations'][0]['date']
    elif case=='future':p['payload']['as_of']='2999-01-01'
    elif case=='unit':i['currency']='EUR'
    elif case=='threshold_bool':i['threshold']=True
    elif case=='duplicate_item':p['payload']['items'].append(deepcopy(i))
    elif case=='source':i['observations'][0]['source_id']='not-retained'
    else:p['payload']['items']=[]
    with pytest.raises((ValueError,KeyError)):semantic(p,entity('monitoring'))


@pytest.mark.parametrize('case',['future','return_bool','return_nan','wrong_size','duplicate_control','ticker','review_spoof'])
def test_event_invalid_inputs(case):
    p=sample('events');e=p['payload']['events'][0]
    if case=='future':e['window_dates']=['2999-01-01','2999-01-02','2999-01-03'];e['anchor_date']='2999-01-02'
    elif case=='return_bool':e['evt_stock'][0]=True
    elif case=='return_nan':e['evt_stock'][0]=float('nan')
    elif case=='wrong_size':e['est_stock'].pop()
    elif case=='duplicate_control':p['payload']['controls']=[deepcopy(e)]
    elif case=='ticker':e['ticker']='OTHER'
    else:e['date_status']='reviewed'
    with pytest.raises(ValueError):semantic(p,entity('events'))


@pytest.mark.parametrize('case',['future','word_overlap','word_pattern','body_scope','bad_url','duplicate_id','alias','source_dates'])
def test_news_invalid_inputs(case):
    p=sample('news');n=p['payload'];a=n['articles'][0]
    if case=='future':n['as_of']='2999-01-01T00:00:00Z'
    elif case=='word_overlap':n['word_list']['negative'].append('growth')
    elif case=='word_pattern':n['word_list']['positive'][0]='two words'
    elif case=='body_scope':a['text_scope']='headline_only'
    elif case=='bad_url':a['url']='javascript:alert(1)'
    elif case=='duplicate_id':n['articles'][1]['id']=a['id']
    elif case=='alias':n['aliases']=['A']
    else:p['sources'][0]['period_end']='2024-02-01'
    with pytest.raises(ValueError):semantic(p,entity('news'))


def test_empty_news_has_no_fabricated_tone():
    result=pure('news',lambda p:p.update(articles=[]))
    assert not result['rows'] and not result['charts'][0]['points']
    assert all(m['value']=='0' for m in result['metrics'])


def test_decimal_threshold_crossing_survives_float_rounding():
    def edit(p):
        p['items']=p['items'][:1];i=p['items'][0];i['threshold']='999999999999'
        i['observations']=[dict(date='2026-01-31',value='999999999999',source_id='observations'),dict(date='2026-04-30',value='999999999999.00000001',source_id='observations')]
    r=pure('monitoring',edit)
    assert r['details']['items'][0]['rows'][-1]['status']=='NEW_BREACH'
    assert next(m for m in r['metrics'] if m['id']=='breaches')['value']=='1'


def test_degenerate_event_windows_are_excluded_with_no_fake_mean():
    r=pure('events',lambda p:p['events'][0].update(est_market=[0.]*250))
    assert r['details']['study']['n_events']==0
    assert len(r['details']['study']['rejected_events'])==1
    assert next(m for m in r['metrics'] if m['id']=='mean-car')['value'] is None


@pytest.mark.parametrize('w',FORMATS)
def test_no_acquisition_or_default_scorer(w,monkeypatch):
    import socket
    import agent3.track_a,agent3.sentiment,monitoring.live_data
    def refuse(*_a,**_k):pytest.fail('Unexpected acquisition or model scorer')
    monkeypatch.setattr(socket,'create_connection',refuse)
    monkeypatch.setattr(agent3.track_a,'load_event_set',refuse)
    monkeypatch.setattr(agent3.sentiment,'get_scorer',refuse)
    monkeypatch.setattr(monitoring.live_data,'prepare',refuse)
    assert pure(w)['financial_approval'] is False


@pytest.mark.parametrize('w',FORMATS)
def test_delivery_failure_and_orphan_recover_without_calculation(session,w,monkeypatch):
    v,_=ingest(session,w);job,_=session.submit(request(v),'orphaned-local-proof-0001')
    from keystone.workspace import worker as runtime
    execute=runtime.operation.execute
    def orphan(*args,**kwargs):
        execute(*args,**kwargs)
        path=session.store.root/'operations'/job['operation_id']/'operation.json'
        saved=json.loads(path.read_text());saved.update(status='running',exit_code=None);path.write_bytes(c.canonical(saved))
        raise KeyboardInterrupt()
    monkeypatch.setattr(runtime.operation,'execute',orphan)
    with worker(session) as store:
        assert run_one(store)==(True,True)
        assert store.get(job['job_id'])['job']['status']=='outcome_unknown'
        from keystone.workspace.onboarding.local_workflows import calculate as engine
        monkeypatch.setattr(engine,'calculate',lambda *_a,**_k:pytest.fail('Recovery recalculated'))
        for _ in range(2):
            recovered=recover_delivery(store,job['job_id'])['job']
            assert recovered['status']=='review_required' and recovered['execution']['operation_status']=='outcome_unknown'
            assert recovered['execution']['attempt']==1
        assert len(Catalog(session.catalog.root).load().runs)==1


@pytest.mark.parametrize('w',FORMATS)
def test_new_format_snapshot_restores_lineage_and_holds_queue(session,tmp_path,w):
    from test_workspace_private_recovery import capture
    from keystone.workspace.onboarding.recovery import restore_private,release_restored_job
    from keystone.workspace.onboarding.service import PrivateAdmission
    v,_=ingest(session,w)
    done,_=session.submit(request(v),'restore-local-done-0001')
    with worker(session) as store:run_one(store);assert store.get(done['job_id'])['job']['status']=='review_required'
    queued,_=session.submit(request(v),'restore-local-queued-0002')
    restored=restore_private(capture(session,tmp_path),tmp_path/'restored-local')
    replacement=PrivateAdmission(restored,ORIGIN,enable_jobs=True)
    try:
        assert replacement.get(queued['job_id'])['job']['restoration_hold'] is True
        run=Catalog(replacement.catalog.root).load().runs[0];assert run.input_origin.version_id==v['id']
        with worker(replacement) as store:
            assert run_one(store)==(False,False)
            release_restored_job(store,queued['job_id'],'Rechecked the exact fictional local-workflow request')
            assert run_one(store)==(True,False)
            assert store.get(queued['job_id'])['job']['execution']['attempt']==1
    finally:replacement.close()


@pytest.mark.parametrize('w',FORMATS)
def test_idempotency_conflict_and_fixed_plan(session,w):
    v,_=ingest(session,w);body=request(v);session.submit(body,'local-plan-key-0001')
    changed=deepcopy(body);changed['timeout_seconds']=100
    with pytest.raises(JobError,match='job_request_conflict'):session.submit(changed,'local-plan-key-0001')
    changed=deepcopy(body);changed['processing_plan']['method']='arbitrary-method'
    with pytest.raises(JobError,match='job_request_invalid'):session.submit(changed,'local-plan-key-0002')


def test_result_capacity_preserves_existing_evidence(session,monkeypatch):
    v,_=ingest(session,'news');body=request(v)
    from keystone.workspace import job_store
    original=job_store.private_member
    # Inspect the actual bounded reservation rather than creating a large file.
    session.store.root.joinpath('jobs').mkdir(exist_ok=True,mode=0o700)
    path=session.store.root/'jobs'/'oversized-evidence';path.write_bytes(b'x');path.chmod(0o600)
    real=Path.stat
    def stat(p,*args,**kwargs):
        if p==path:
            s=real(p,*args,**kwargs);return type(s)((s.st_mode,s.st_ino,s.st_dev,s.st_nlink,s.st_uid,s.st_gid,90_000_000,s.st_atime,s.st_mtime,s.st_ctime))
        return real(p,*args,**kwargs)
    monkeypatch.setattr(Path,'stat',stat)
    with pytest.raises(JobError,match='job_capacity_reached'):session.submit(body,'capacity-local-0001')
    assert path.read_bytes()==b'x'
