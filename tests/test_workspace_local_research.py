"""New local research: independent arithmetic, private boundaries and delivery recovery."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
import json
import uuid

from fastapi.testclient import TestClient
import pytest

from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog
from keystone.workspace.job_contract import JobError
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.onboarding.research.contracts import semantic,plan,today,producer
from keystone.workspace.onboarding.research.calculate import calculate
from keystone.workspace.worker import run_one,recover_delivery
from test_workspace_onboarding import session,headers,ORIGIN
from test_workspace_fresh_close import worker

ROOT=Path(__file__).resolve().parents[1]


def example():
    value=json.loads((ROOT/'docs/webapp/fresh-analysis/examples/complete-kit.json').read_text())
    # Quote is a fictional dated observation, never refresh a real source.
    d=(today()-timedelta(days=1)).isoformat()
    value['payload']['quote']['as_of']=d
    value['sources'][1].update(period_start=d,period_end=d)
    return value


def request(version,valuation=True):
    body=json.loads((ROOT/'docs/webapp/fresh-analysis/examples/valuation-request.json').read_text())
    body['source']=dict(kind='dataset_version',dataset_id=version['dataset_id'],version_id=version['id'],contract_sha256=version['contract_sha256'])
    if valuation:body['assumption_review']=dict(acknowledged=True,source_reference_sha256=c.fingerprint(body['source']),analysis_plan_sha256=c.fingerprint(body['analysis_plan']))
    else:body['analysis_plan']['valuation']=None;body['assumption_review']=None
    return body


def ingest(session,edit=None,entity=None,dataset=None):
    value=example()
    entity=entity or session.inputs.create_entity(dict(name='Northstar Components',kind='company',ticker='NSTAR',members=[]))
    dataset=dataset or session.inputs.create_dataset(dict(entity_id=entity['id'],title='Northstar financial kit',workflow='research',payload_format=c.FRESH_RESEARCH))
    value['payload']['entity_id']=value['dataset']['entity_id']=entity['id']
    if edit:edit(value)
    evidence=b'Fictional operator authorisation for local engineering tests only.'
    policy=dict(schema_version=1,id='permission-'+uuid.uuid4().hex,workspace_id=session.inputs.descriptor['id'],entity_id=entity['id'],payload_sha256=c.fingerprint(value['payload']),
        category='synthetic',provider_or_owner=value['sources'][0]['provider_or_owner'],intended_use='private_personal_evaluation',evidence_sha256=c.sha(evidence),reviewed_by='Test operator',reviewed_at='2026-01-01T00:00:00Z',expires_at=None,
        rights=dict(local_retention='allowed',local_processing='allowed',local_backup='allowed',model_transfer='denied',sharing='denied'))
    session.inputs.install_permission(policy,evidence)
    for s in value['sources']:s['permission_record_id']=policy['id']
    raw=c.canonical(value)
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    inspection=api.post('/api/datasets/'+dataset['id']+'/inspect',content=raw,headers=headers(session));assert inspection.status_code==200,inspection.text
    descriptor=inspection.json()['descriptor'];key='research-'+uuid.uuid4().hex
    reserved=api.post('/api/imports',json=descriptor,headers=headers(session,key));assert reserved.status_code==201,reserved.text
    receipt=api.put('/api/imports/'+reserved.json()['import_attempt']['id']+'/package',content=raw,headers=headers(session,key));assert receipt.status_code==200,receipt.text
    return entity,dataset,policy,session.inputs.version(receipt.json()['version_id'])


def test_local_research_http_worker_native_and_delivery_only_recovery(session,monkeypatch):
    entity,dataset,policy,version=ingest(session)
    assert version['contract']['validation']['analytical_execution']=='not_started'
    assert not Catalog(session.catalog.root).load().runs
    body=request(version)
    job,replay=session.submit(body,'local-research-0001');assert not replay
    assert session.submit(body,'local-research-0001')[1]
    assert job['max_requests']==job['max_output_tokens']==0
    with worker(session) as store:
        assert run_one(store)==(True,False)
        saved=store.get(job['job_id'])['job'];assert saved['status']=='review_required',saved
        assert saved['execution']['attempt']==1
        run=Catalog(session.catalog.root).load().runs[0]
        evidence=json.loads(Catalog(session.catalog.root).read(run.id,next(a for a in run.artifacts if a.id=='local-result')))
        metrics={m['id']:m for m in evidence['metrics']}
        assert metrics['base-fcff']['value']=='80000000.0'
        assert float(metrics['operating-margin']['value'])==.12
        assert float(metrics['base-equity']['value'])==1_000_000_000
        assert float(metrics['weighted-per-share']['value'])==100
        assert float(metrics['model-value-gap']['value'])==.25
        from keystone.workspace.onboarding.research import calculate as maths
        monkeypatch.setattr(maths,'calculate',lambda *_a,**_k:pytest.fail('Recovery recalculated'))
        assert recover_delivery(store,job['job_id'])['job']['status']=='review_required'
        assert run_one(store)==(False,False)
    with TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN) as api:
        assert api.get('/api/runs/'+run.id+'/report-view').status_code==403
        response=api.get('/api/runs/'+run.id+'/report-view',headers=headers(session));assert response.status_code==200,response.text
        view=response.json();assert view['state']['financial_approval'] is False
        assert view['summary']['template_id']=='local-research-summary-v1'
        assert any(ch['availability']=='available' for ch in view['charts'])


def test_missing_cash_retains_summary_and_holds_valuation(session):
    def edit(v):v['payload']['periods'][-1]['observations']['cash_and_equivalents']=dict(value=None,source_id=None,locator=None,missing_reason='not_provided')
    _,_,_,version=ingest(session,edit)
    job,_=session.submit(request(version),'missing-cash-0001')
    with worker(session) as store:
        run_one(store);saved=store.get(job['job_id'])['job'];assert saved['status']=='review_required',saved
    run=Catalog(session.catalog.root).load().runs[0]
    data=json.loads(Catalog(session.catalog.root).read(run.id,next(a for a in run.artifacts if a.id=='local-result')))
    assert next(s for s in data['sections'] if s['id']=='valuation')['availability']=='withheld'
    assert next(m for m in data['metrics'] if m['id']=='weighted-per-share')['value'] is None
    assert next(m for m in data['metrics'] if m['id']=='revenue-2025')['value']=='1000000000'


def test_summary_only_and_changed_review(session):
    *_,version=ingest(session)
    changed=request(version);changed['analysis_plan']['valuation']['high_growth']='0.2'
    with pytest.raises(JobError):session.submit(changed,'changed-review-0001')
    job,_=session.submit(request(version,False),'summary-only-0001')
    with worker(session) as store:
        run_one(store);assert store.get(job['job_id'])['job']['status']=='review_required'


@pytest.mark.parametrize('field,bad',[('revenue','-1'),('capex','-1'),('depreciation_amortization','-1'),('total_debt','-1'),('cash_and_equivalents','-1')])
def test_semantic_sign_refusals(field,bad):
    value=example();value['payload']['periods'][-1]['observations'][field]['value']=bad
    with pytest.raises(ValueError):semantic(value,dict(id='entity-northstar',kind='company',ticker='NSTAR'))


@pytest.mark.parametrize('key,bad',[('discount_rate','0'),('discount_rate','0.01'),('high_growth','-0.96'),('terminal_growth','-1'),('tax_rate','1.1'),('horizon_years',True)])
def test_plan_refuses_unsuitable_parameters(key,bad):
    body=json.loads((ROOT/'docs/webapp/fresh-analysis/examples/valuation-request.json').read_text());body['analysis_plan']['valuation'][key]=bad
    body['assumption_review']['analysis_plan_sha256']=c.fingerprint(body['analysis_plan'])
    with pytest.raises(ValueError):plan(body)


def pure(edit=None,valuation=True,plan_edit=None,monkeypatch=None):
    value=example()
    if edit:edit(value)
    semantic(value,dict(id='entity-northstar',kind='company',ticker='NSTAR'))
    body=json.loads((ROOT/'docs/webapp/fresh-analysis/examples/valuation-request.json').read_text())
    if not valuation:body['analysis_plan']['valuation']=None;body['assumption_review']=None
    if plan_edit:plan_edit(body['analysis_plan']['valuation'])
    if body['assumption_review']:body['assumption_review']['analysis_plan_sha256']=c.fingerprint(body['analysis_plan'])
    binding=dict(workspace_id='workspace-test',dataset_id=body['source']['dataset_id'],version_id=body['source']['version_id'],classification='synthetic',
        **{k:'a'*64 for k in ('contract_sha256','receipt_sha256','entity_sha256','policy_sha256')},payload_sha256=c.fingerprint(value['payload']))
    result=calculate(value,body,binding,'job-'+'1'*32,producer(),today().isoformat())
    return {m['id']:m for m in result['metrics']},result


def set_obs(v,key,value):
    obs=v['payload']['periods'][-1]['observations'][key]
    if value is None:obs.update(value=None,source_id=None,locator=None,missing_reason='not_provided')
    else:obs['value']=str(value)


@pytest.mark.parametrize('wc,expected',[('5000000',80_000_000),('-5000000',90_000_000),('0',85_000_000)])
def test_independent_fcff_absorption_release_zero(wc,expected):
    m,_=pure(lambda v:set_obs(v,'change_in_working_capital',wc))
    assert float(m['base-fcff']['value'])==expected


@pytest.mark.parametrize('field',['change_in_working_capital','depreciation_amortization','capex','cash_and_equivalents','total_debt'])
def test_missing_valuation_component_does_not_fall_back(field):
    m,r=pure(lambda v:set_obs(v,field,None))
    assert m['weighted-per-share']['value'] is None
    assert m['revenue-2025']['value']=='1000000000'
    assert next(s for s in r['sections'] if s['id']=='valuation')['availability']=='withheld'


@pytest.mark.parametrize('tax,expected',[('0',110_000_000),('0.25',80_000_000),('1',None)])
def test_explicit_tax_endpoints_and_nonpositive_fcff(tax,expected):
    m,_=pure(plan_edit=lambda p:p.update(tax_rate=tax))
    assert (float(m['base-fcff']['value']) if m['base-fcff']['value'] is not None else None)==expected
    if expected is None:assert m['base-fcff']['reason_codes']==['nonpositive_fcff']


def test_effective_tax_and_unsuitable_effective_rate():
    plan_edit=lambda p:p.update(tax_basis='effective_rate',tax_rate=None)
    m,_=pure(plan_edit=plan_edit);assert float(m['base-fcff']['value'])==80_000_000
    m,_=pure(lambda v:set_obs(v,'pretax_income','-1'),plan_edit=plan_edit)
    assert m['base-fcff']['reason_codes']==['tax_basis_unavailable']


@pytest.mark.parametrize('field',['net_income','operating_income'])
def test_zero_profit_preserved_and_multiple_not_applicable(field):
    m,_=pure(lambda v:set_obs(v,field,'0'))
    assert float(m[field.replace('_','-')]['value'])==0
    multiple=m['annual-pe' if field=='net_income' else 'ev-operating-income']
    assert multiple['value'] is None and multiple['availability']=='not_applicable'


def test_zero_and_distressed_equity_remain_distinct():
    m,_=pure(lambda v:set_obs(v,'total_debt','1160000000'))
    assert float(m['bear-equity']['value'])==0 and float(m['bear-per-share']['value'])==0
    m,_=pure(lambda v:set_obs(v,'total_debt','1500000000'))
    assert float(m['base-equity']['value'])<0 and m['base-per-share']['value'] is None
    assert m['weighted-per-share']['reason_codes']==['distressed_equity']


def test_nonzero_other_claims_hold_bridge_without_losing_pe():
    m,_=pure(lambda v:set_obs(v,'noncontrolling_interests','1'))
    assert m['weighted-per-share']['reason_codes']==['unsupported_equity_claims']
    assert m['annual-pe']['availability']=='available'


@pytest.mark.parametrize('age',[7,8])
def test_quote_freshness_exact_day_boundary(age):
    def edit(v):
        d=(today()-timedelta(days=age)).isoformat();v['payload']['quote']['as_of']=d;v['sources'][1].update(period_start=d,period_end=d)
    m,_=pure(edit)
    assert m['annual-pe']['availability']==('available' if age==7 else 'withheld')
    assert m['base-equity']['availability']=='available'
    assert (m['weighted-per-share']['value'] is not None)==(age==7)


@pytest.mark.parametrize('cap,valid',[('760000000',True),('759999999',False)])
def test_quote_reconciliation_exact_five_percent(cap,valid):
    value=example();value['payload']['quote']['observations']['market_cap']['value']=cap
    if valid:semantic(value,dict(id='entity-northstar',kind='company',ticker='NSTAR'))
    else:
        with pytest.raises(ValueError):semantic(value,dict(id='entity-northstar',kind='company',ticker='NSTAR'))


def test_no_acquisition_network_or_dcf_for_summary(monkeypatch):
    import socket
    from tools import data
    from keystone.workspace.onboarding.research import calculate as maths
    def forbidden(*a,**kw):pytest.fail('Forbidden acquisition, network or valuation call')
    for name in ('get_financials','get_prices','get_consensus','get_historical_trend'):monkeypatch.setattr(data,name,forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden);monkeypatch.setattr(maths,'run_dcf',forbidden)
    m,r=pure(valuation=False)
    assert m['operating-margin']['value']=='0.12' and r['execution']['model_calls']==r['execution']['provider_requests']==0


def test_three_year_fade_matches_independent_equations():
    from decimal import Decimal,localcontext
    m,_=pure(plan_edit=lambda p:p.update(horizon_years=3))
    with localcontext() as ctx:
        ctx.prec=50;fcf=Decimal('80000000');pv=Decimal(0);r=Decimal('.1');g=Decimal('.02')
        for t,growth in enumerate(map(Decimal,['.1','.06','.02']),1):
            fcf*=1+growth;pv+=fcf/(1+r)**t
        ev=pv+fcf*(1+g)/(r-g)/(1+r)**3
        assert abs(Decimal(m['base-ev']['value'])-ev)<1


def test_delivery_failure_recovers_once_without_calculation(session,monkeypatch):
    *_,version=ingest(session);job,_=session.submit(request(version),'delivery-fault-0001')
    from keystone.workspace import worker as runtime
    real=runtime.publish_result
    def fail(*_a,**_k):raise OSError('Injected delivery failure')
    monkeypatch.setattr(runtime,'publish_result',fail)
    with worker(session) as store:
        run_one(store);assert store.get(job['job_id'])['job']['status']=='delivery_failed'
        monkeypatch.setattr(runtime,'publish_result',real)
        from keystone.workspace.onboarding.research import calculate as maths
        monkeypatch.setattr(maths,'calculate',lambda *_a,**_k:pytest.fail('Delivery recovery recalculated'))
        for _ in range(2):assert recover_delivery(store,job['job_id'])['job']['status']=='review_required'
        assert len(Catalog(session.catalog.root).load().runs)==1


def test_orphaned_complete_proof_recovers_preserving_unknown_operation(session,monkeypatch):
    *_,version=ingest(session);job,_=session.submit(request(version),'orphan-proof-0001')
    from keystone.workspace import worker as runtime
    execute=runtime.operation.execute
    def stop_after_saved(*a,**kw):
        execute(*a,**kw)
        path=session.store.root/'operations'/job['operation_id']/'operation.json'
        raw=json.loads(path.read_text());raw.update(status='running',exit_code=None);path.write_bytes(c.canonical(raw))
        raise KeyboardInterrupt()
    monkeypatch.setattr(runtime.operation,'execute',stop_after_saved)
    with worker(session) as store:
        assert run_one(store)==(True,True)
        assert store.get(job['job_id'])['job']['status']=='outcome_unknown'
        recovered=recover_delivery(store,job['job_id'])['job']
        assert recovered['status']=='review_required' and recovered['execution']['operation_status']=='outcome_unknown'
        assert recovered['execution']['analysis_commit_sha256'] and recovered['execution']['attempt']==1


def test_revoked_queued_source_is_never_calculated(session):
    _,_,policy,version=ingest(session);job,_=session.submit(request(version),'revoked-local-0001')
    session.inputs.revoke_permission(policy['id'],'Fictional permission withdrawn')
    with worker(session) as store:
        run_one(store);saved=store.get(job['job_id'])['job']
        assert saved['status']=='source_changed' and saved['execution']['attempt']==1
    assert not Catalog(session.catalog.root).load().runs


def test_new_format_snapshot_restore_retains_lineage_and_holds_queue(session,tmp_path):
    from test_workspace_private_recovery import capture
    from keystone.workspace.onboarding.recovery import restore_private
    from keystone.workspace.onboarding.service import PrivateAdmission
    *_,version=ingest(session)
    completed,_=session.submit(request(version),'restore-local-0001')
    with worker(session) as store:run_one(store)
    queued,_=session.submit(request(version,False),'restore-local-0002')
    snapshot=capture(session,tmp_path);restored=restore_private(snapshot,tmp_path/'restored-local')
    replacement=PrivateAdmission(restored,ORIGIN,enable_jobs=True)
    try:
        assert replacement.get(queued['job_id'])['job']['restoration_hold'] is True
        run=Catalog(replacement.catalog.root).load().runs[0]
        assert run.input_origin.version_id==version['id']
        from keystone.workspace.onboarding.recovery import release_restored_job
        with worker(replacement) as store:
            assert run_one(store)==(False,False)
            release_restored_job(store,queued['job_id'],'Reviewed exact restored fictional research request')
            assert run_one(store)==(True,False)
            assert store.get(queued['job_id'])['job']['execution']['attempt']==1
        from keystone.workspace.report_views.delivery import load_view
        assert load_view(Catalog(replacement.catalog.root),run)['state']['financial_approval'] is False
    finally:replacement.close()


def test_new_request_idempotency_and_changed_plan_conflict(session):
    *_,version=ingest(session);body=request(version)
    job,_=session.submit(body,'local-key-conflict-0001')
    changed=deepcopy(body);changed['analysis_plan']['valuation']['high_growth']='0.2'
    changed['assumption_review']['analysis_plan_sha256']=c.fingerprint(changed['analysis_plan'])
    with pytest.raises(JobError,match='job_request_conflict'):session.submit(changed,'local-key-conflict-0001')
    assert session.submit(body,'local-key-conflict-0001')[0]['job_id']==job['job_id']
    assert len(session.store.list(25,None)['jobs'])==1


def test_result_reservations_refuse_capacity_without_deletion(session):
    *_,version=ingest(session);body=request(version,False)
    for i in range(6):session.submit(body,f'local-reservation-{i:04}')
    with pytest.raises(JobError,match='job_capacity_reached'):session.submit(body,'local-reservation-0007')
    assert len(session.store.list(25,None)['jobs'])==6
    assert not Catalog(session.catalog.root).load().runs
