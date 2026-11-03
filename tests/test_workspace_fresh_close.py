"""Fresh close acceptance: exact accounting, state pins and delivery-only recovery."""
from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path
import uuid

from fastapi.testclient import TestClient
import pytest

from agent4.state import VarianceStore
from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog
from keystone.workspace.job_contract import JobError
from keystone.workspace.job_store import JobStore
from keystone.workspace.onboarding import contracts as c, close_state
from keystone.workspace.worker import run_one, recover_delivery, release_uncommitted_close
from test_workspace_onboarding import session, headers, submit, ORIGIN

ROOT = Path(__file__).resolve().parents[1]


def request():
    return json.loads((ROOT/'fixtures/agent4/close-june.json').read_text())


def package(session, source=None, *, entity=None, dataset=None, category='synthetic', edit=None, expires_at=None):
    source = deepcopy(source or request())
    entity = entity or session.inputs.create_entity(dict(name=source['entity'],kind='company',ticker=None,members=[]))
    dataset = dataset or session.inputs.create_dataset(dict(entity_id=entity['id'],title='Fictional close request',
                                                          workflow='close',payload_format=c.FRESH_CLOSE))
    value = json.loads((ROOT/'docs/webapp/data-onboarding/examples/synthetic-close-request.json').read_text())
    value['payload'] = source
    value['dataset'].update(entity_id=entity['id'],title=dataset['title'],upstream_id=source['run_id'])
    evidence=b'Fictional test operator permission; no real-company data rights claimed.'
    policy=dict(schema_version=1,id='permission-'+uuid.uuid4().hex,workspace_id=session.inputs.descriptor['id'],entity_id=entity['id'],
        payload_sha256=c.fingerprint(source),category=category,provider_or_owner='Fictional test operator',
        intended_use='private_personal_evaluation',evidence_sha256=c.sha(evidence),reviewed_by='Test operator',
        reviewed_at='2026-01-01T00:00:00Z',expires_at=expires_at,
        rights=dict(local_retention='allowed',local_processing='allowed',local_backup='allowed',model_transfer='denied',sharing='denied'))
    session.inputs.install_permission(policy,evidence)
    for declaration in value['sources']:
        declaration.update(category=category,provider_or_owner=policy['provider_or_owner'],permission_record_id=policy['id'])
        periods=[r['period'] for r in source[declaration['role']]['rows']]
        declaration.update(period_start=min(periods) if periods else None,period_end=max(periods) if periods else None)
    if edit: edit(value)
    raw=c.canonical(value)
    descriptor=dict(schema_version=1,dataset_id=dataset['id'],package_bytes=len(raw),package_sha256=c.sha(raw),
                    payload_sha256=c.fingerprint(source),metadata={k:v for k,v in value.items() if k!='payload'})
    return entity,dataset,policy,raw,descriptor


def ingest(session, source=None, *, expected=200, **kwargs):
    entity,dataset,policy,raw,descriptor=package(session,source,**kwargs)
    key='import-'+uuid.uuid4().hex
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    try:
        reserved=api.post('/api/imports',json=descriptor,headers=headers(session,key))
        assert reserved.status_code==201,reserved.text
        attempt=reserved.json()['import_attempt']['id']
        response=api.put('/api/imports/'+attempt+'/package',content=raw,headers=headers(session,key))
        assert response.status_code==expected,response.text
        if expected!=200:return entity,dataset,policy,response
        version=session.inputs.version(response.json()['version_id'])
    finally:api.close()
    return entity,dataset,policy,version


@contextmanager
def worker(session):
    store=JobStore(session.store.root,session.catalog.root,worker=True)
    try:yield store
    finally:store.close()


def test_fresh_close_exact_totals_no_financial_write_on_upload_and_native_delivery(session,monkeypatch):
    entity,dataset,policy,version=ingest(session)
    assert not (session.inputs.root/'accounting').exists()
    assert version['contract']['validation']['schema_version']==2
    job=submit(session,version)
    assert job['profile']=='calculate-imported-close' and job['financial_approval'] is False
    with worker(session) as store:
        assert run_one(store)==(True,False)
        saved=store.get(job['job_id'])['job']
        assert saved['status']=='review_required',saved
        assert saved['execution']['accounting_commit_sha256']
        assert run_one(store)==(False,False)
        result=Catalog(session.catalog.root).load().runs[0]
        assert result.accounting_origin.classification=='synthetic'
        proof=session.inputs.object('close_commit','commit-'+job['job_id'])
        with close_state.open_state(close_state.state_path(session.inputs,entity['id'])) as state:
            bundle=state.get_run('close-june')['bundle']
            assert state.con.execute('SELECT count(*) FROM a4_runs').fetchone()[0]==1
            root=bundle['report']['full_hierarchy']
            # Independent arithmetic: (11000-4500)-(10000-4000) = +500 cents.
            assert bundle['bound_tree']['budget_cents']==6000
            assert bundle['bound_tree']['actual_cents']==6500
            assert root['total_variance_cents']==500
            assert bundle['report']['reforecasts']['profit']['inputs']['ytd_cents']==39000
            from agent4.output import waterfall_rows
            bridge=waterfall_rows(root)
            assert bridge[0]['end_cents']==6000 and bridge[-1]['end_cents']==6500
            assert sum(r['value_cents'] for r in bridge if r['kind']=='step')==500
            assert bundle['report']['reconciles'] is True
        import agent4.close
        monkeypatch.setattr(agent4.close,'execute_close',lambda *_a,**_k:pytest.fail('Recovery recalculated'))
        assert recover_delivery(store,job['job_id'])['job']['status']=='review_required'
        assert proof==session.inputs.object('close_commit','commit-'+job['job_id'])
    with TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN) as api:
        view=api.get('/api/runs/'+result.id+'/report-view',headers=headers(session))
        assert view.status_code==200,view.text
        assert view.json()['state']['financial_approval'] is False


@pytest.mark.parametrize('change',[
    lambda r:r['budget']['rows'].pop(),
    lambda r:r['actuals']['rows'].pop(),
    lambda r:r['actuals']['rows'].append(deepcopy(r['actuals']['rows'][0])),
    lambda r:r['actuals']['rows'][0].update(amount_cents=True),
    lambda r:r['actuals']['rows'][0].update(amount_cents=1.5),
    lambda r:r['actuals']['rows'][0].update(period='2026-07-31'),
    lambda r:r.update(close_period='2026-06-29'),
    lambda r:r.update(frequency='weekly'),
    lambda r:r['tree']['children'][0].update(sign='wrong'),
    lambda r:r['tree'].update(root_measure='wrong'),
    lambda r:r.update(supersedes='nonexistent'),
    lambda r:r['budget'].update(approved=False),
])
def test_invalid_new_close_refused_without_canonical_state(session,change):
    source=request();change(source)
    entity,_,_,_=ingest(session,source,expected=422)
    assert not close_state.state_path(session.inputs,entity['id']).exists()
    assert Catalog(session.catalog.root).load().runs==[]


@pytest.mark.parametrize('edit',[
    lambda p:p['sources'][0].update(currency='USD'),
    lambda p:p['sources'][1].update(units='EUR millions'),
    lambda p:p['sources'][1].update(role='budget'),
    lambda p:p['dataset'].update(upstream_id='different-run'),
])
def test_explicit_close_declarations_refused(session,edit):
    ingest(session,edit=edit,expected=422)


def test_two_queued_jobs_pin_same_predecessor_second_never_executes(session):
    entity,dataset,_,v1=ingest(session)
    other=request();other['run_id']='close-second';other['actuals']['version']='a-second'
    _,_,_,v2=ingest(session,other,entity=entity,dataset=dataset)
    first,second=submit(session,v1),submit(session,v2)
    with worker(session) as store:
        run_one(store);run_one(store)
        assert store.get(first['job_id'])['job']['status']=='review_required'
        assert store.get(second['job_id'])['job']['status']=='source_changed'
        assert not (store.root/'operations'/second['operation_id']).exists()
    with pytest.raises(JobError):submit(session,v2)


def correction():
    source=request();source.update(run_id='close-june-corrected',supersedes='close-june')
    source['actuals'].update(version='actuals-correction',rows=[dict(line='sales',period='2026-06-30',amount_cents=12000)])
    return source


def run_first(session,**kwargs):
    entity,dataset,policy,version=ingest(session,**kwargs)
    job=submit(session,version)
    with worker(session) as store:
        run_one(store)
        assert store.get(job['job_id'])['job']['status']=='review_required'
    return entity,dataset,policy,job


def test_delta_correction_uses_predecessor_and_preserves_prior_close(session):
    entity,dataset,_,first=run_first(session)
    before=close_state.inspect(session.inputs,entity['id'])
    _,_,_,version=ingest(session,correction(),entity=entity,dataset=dataset)
    assert version['contract']['validation']['accounting_source']==before
    assert close_state.inspect(session.inputs,entity['id'])==before
    job=submit(session,version)
    with worker(session) as store:
        run_one(store)
        assert store.get(job['job_id'])['job']['status']=='review_required'
        assert recover_delivery(store,first['job_id'])['job']['status']=='review_required'
    with close_state.open_state(close_state.state_path(session.inputs,entity['id'])) as state:
        previous=state.get_run('close-june')['bundle'];corrected=state.get_run('close-june-corrected')['bundle']
        assert previous['bound_tree']['actual_cents']==6500
        assert corrected['bound_tree']['actual_cents']==7500
        assert corrected['report']['full_hierarchy']['total_variance_cents']==1500
        assert corrected['report']['reforecasts']['profit']['inputs']['ytd_cents']==40000
        assert len(state.actuals_snapshot('actuals-correction'))==12
        assert len(close_state.summary(session.inputs,entity['id'],state)['lineage_versions'])==2


def test_later_period_delta_uses_retained_ytd_without_supersedes(session):
    entity,dataset,_,_=run_first(session)
    source=request();source.update(run_id='close-july',close_period='2026-07-31')
    source['actuals'].update(version='actual-july',rows=[dict(line='sales',period='2026-07-31',amount_cents=12000),
                                                     dict(line='cost',period='2026-07-31',amount_cents=4500)])
    _,_,_,version=ingest(session,source,entity=entity,dataset=dataset)
    job=submit(session,version)
    with worker(session) as store:
        run_one(store);assert store.get(job['job_id'])['job']['status']=='review_required'
    with close_state.open_state(close_state.state_path(session.inputs,entity['id'])) as state:
        bundle=state.get_run('close-july')['bundle']
        assert bundle['bound_tree']['actual_cents']==7500
        assert bundle['report']['reforecasts']['profit']['inputs']['ytd_cents']==46500
        assert len(bundle['sources']['effective_actuals'])==14


@pytest.mark.parametrize('change',[
    lambda r:r.pop('supersedes'),
    lambda r:r.update(supersedes='wrong-head'),
    lambda r:r.update(close_period='2026-05-31'),
    lambda r:r.update(run_id='close-june'),
    lambda r:r['budget']['rows'][0].update(amount_cents=999),
    lambda r:r['actuals'].update(version=request()['actuals']['version']),
    lambda r:r.update(entity='Wrong company'),
    lambda r:r.update(frequency='quarterly'),
])
def test_stale_conflicting_or_wrong_company_corrections_refused(session,change):
    entity,dataset,_,_=run_first(session)
    before=close_state.inspect(session.inputs,entity['id'])
    source=correction();change(source)
    ingest(session,source,entity=entity,dataset=dataset,expected=422)
    assert close_state.inspect(session.inputs,entity['id'])==before


def test_inherited_permission_revocation_blocks_claim_and_report_reads(session):
    entity,dataset,policy,first=run_first(session)
    _,_,_,version=ingest(session,correction(),entity=entity,dataset=dataset)
    job=submit(session,version)
    session.inputs.revoke_permission(policy['id'],'Fictional permission withdrawn')
    with worker(session) as store:
        run_one(store)
        assert store.get(job['job_id'])['job']['status']=='source_changed'
        assert not (store.root/'operations'/job['operation_id']).exists()
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    try:
        assert api.get('/api/runs/result-'+first['job_id'][4:]+'/report-view',headers=headers(session)).status_code in {403,503}
    finally:api.close()


@pytest.mark.parametrize('crash',['after_commit','before_commit','during_report'])
def test_real_supervised_failure_requires_explicit_commit_or_no_commit_recovery(session,monkeypatch,crash):
    from keystone import operation
    entity,dataset,_,version=ingest(session)
    job=submit(session,version)
    if crash=='during_report':
        code="import agent4.report\ndef fail(*a,**k): raise RuntimeError('test delivery failure')\nagent4.report.render_report=fail\n"
    elif crash=='after_commit':
        code="import os,agent4.close\noriginal=agent4.close.execute_close\ndef stop(*a,**k):\n original(*a,**k)\n os._exit(91)\nagent4.close.execute_close=stop\n"
    else:
        code="import os,agent4.close\noriginal=agent4.close.execute_close\ndef stop(*a,**k):\n hook=k['commit_hook']\n def before(*x):\n  hook(*x)\n  os._exit(91)\n k['commit_hook']=before\n return original(*a,**k)\nagent4.close.execute_close=stop\n"
    code+="from keystone.workspace.saved_job import main\nraise SystemExit(main())\n"
    with worker(session) as store:
        with monkeypatch.context() as patch:
            patch.setitem(operation.ENTRYPOINTS,'workspace-saved',['-c',code])
            assert run_one(store)==(True,False)
        saved=store.get(job['job_id'])['job'];assert saved['status']=='failed',saved
        opfile=store.root/'operations'/job['operation_id']/'operation.json'
        original_receipt=opfile.read_bytes()
        assert run_one(store)==(False,False)
        with pytest.raises(JobError):submit(session,version)
        import agent4.close
        monkeypatch.setattr(agent4.close,'execute_close',lambda *_a,**_k:pytest.fail('Recovery recalculated'))
        monkeypatch.setattr(agent4.close,'reforecast',lambda *_a,**_k:pytest.fail('Recovery recalculated forecast'))
        if crash=='before_commit':
            with pytest.raises(Exception):recover_delivery(store,job['job_id'])
            result=release_uncommitted_close(store,job['job_id'])
            assert result['resolution']=='no_commit_verified'
            assert close_state.inspect(session.inputs,entity['id'])==version['contract']['validation']['accounting_source']
            assert Catalog(session.catalog.root).load().runs==[]
        else:
            with pytest.raises(Exception):release_uncommitted_close(store,job['job_id'])
            recovered=recover_delivery(store,job['job_id'])['job']
            assert recovered['status']=='review_required'
            assert recovered['execution']['operation_status']=='failed_inspect_state'
            assert recovered['execution']['reason']=='recovered'
            assert recovered['execution']['attempt']==1
            assert recover_delivery(store,job['job_id'])['job']==recovered
            with close_state.open_state(close_state.state_path(session.inputs,entity['id'])) as state:
                assert state.con.execute('SELECT count(*) FROM a4_runs').fetchone()[0]==1
                assert state.con.execute('SELECT count(*) FROM keystone_close_commits').fetchone()[0]==1
        assert opfile.read_bytes()==original_receipt


@pytest.mark.parametrize('after_replace',[False,True])
def test_catalogue_delivery_failure_recovers_exact_commit_once(session,monkeypatch,after_replace):
    import keystone.workspace.job_delivery as delivery
    entity,_,_,version=ingest(session);job=submit(session,version)
    replace=delivery._replace_inventory
    def fail(*args):
        if after_replace:replace(*args)
        raise OSError('Fictional catalogue interruption')
    with worker(session) as store:
        with monkeypatch.context() as patch:
            patch.setattr(delivery,'_replace_inventory',fail);run_one(store)
        old=store.get(job['job_id'])['job']['execution']
        assert old['status']=='delivery_failed'
        proof=session.inputs.object('close_commit','commit-'+job['job_id'])
        import agent4.close
        monkeypatch.setattr(agent4.close,'execute_close',lambda *_a,**_k:pytest.fail('Recovery recalculated'))
        recovered=recover_delivery(store,job['job_id'])['job']['execution']
        assert recovered['result']==old['result']
        assert recovered['accounting_commit_sha256']==c.fingerprint(proof)
        assert len(Catalog(session.catalog.root).load().runs)==1


def test_atomic_attribution_failure_rolls_back_financial_commit(tmp_path):
    from agent4.close import execute_close
    def fail(state,saved):raise OSError('Fictional atomic attribution failure')
    with VarianceStore(tmp_path/'a.duckdb') as state:
        with pytest.raises(OSError):execute_close(state,request(),commit_hook=fail)
        assert state.get_run('close-june') is None
        assert state.versions('budget')==state.versions('actuals')==state.versions('reforecast')==[]
        assert state.con.execute('SELECT count(*) FROM a4_heads').fetchone()[0]==0
        assert len(state.attempt_history('close-june'))==2


def test_orphaned_supervisor_receipt_recovery_preserves_original_bytes(session,monkeypatch):
    from keystone import operation
    _,_,_,version=ingest(session);job=submit(session,version)
    write=operation.write_record
    def lose_final(path,record):
        if Path(path).name=='operation.json' and record.get('status')=='review_required':
            raise OSError('Fictional supervisor final-write loss')
        return write(path,record)
    with worker(session) as store:
        with monkeypatch.context() as patch:
            patch.setattr(operation,'write_record',lose_final);run_one(store)
        assert store.get(job['job_id'])['job']['status']=='outcome_unknown'
        path=store.root/'operations'/job['operation_id']/'operation.json';before=path.read_bytes()
        assert json.loads(before)['status']=='running'
        import agent4.close
        monkeypatch.setattr(agent4.close,'execute_close',lambda *_a,**_k:pytest.fail('Recovery recalculated'))
        recovered=recover_delivery(store,job['job_id'])['job']['execution']
        assert recovered['operation_status']=='outcome_unknown' and recovered['status']=='review_required'
        assert path.read_bytes()==before


def test_mixed_history_classification_and_revoked_inherited_evidence(session):
    entity,dataset,policy,_=run_first(session)
    source=correction();source['data_kind']='unverified'
    _,_,_,version=ingest(session,source,entity=entity,dataset=dataset,category='confidential')
    job=submit(session,version)
    with worker(session) as store:
        run_one(store);assert store.get(job['job_id'])['job']['status']=='review_required'
    run=next(r for r in Catalog(session.catalog.root).load().runs if r.input_origin.job_id==job['job_id'])
    assert run.accounting_origin.classification=='mixed'
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    try:
        response=api.get('/api/runs/'+run.id+'/report-view',headers=headers(session))
        assert response.status_code==200,response.text
        assert response.json()['state']['data_classification']=='mixed'
        session.inputs.revoke_permission(policy['id'],'Fictional inherited permission withdrawn')
        assert api.get('/api/runs/'+run.id+'/report-view',headers=headers(session)).status_code in {403,503}
    finally:api.close()


def test_expired_inherited_permission_refuses_new_close(session,monkeypatch):
    from datetime import datetime,timezone
    import keystone.workspace.onboarding.store as storage
    entity,dataset,_,_=run_first(session,expires_at='2027-01-01T00:00:00Z')
    _,_,_,version=ingest(session,correction(),entity=entity,dataset=dataset)
    class Future(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2028,1,1,tzinfo=timezone.utc)
    monkeypatch.setattr(storage,'datetime',Future)
    with pytest.raises(JobError):submit(session,version)


def test_lost_accounting_database_is_not_treated_as_an_empty_predecessor(session,tmp_path):
    entity,_,_,_=run_first(session)
    path=close_state.state_path(session.inputs,entity['id'])
    path.rename(tmp_path/'preserved.duckdb')
    with pytest.raises(c.InputError):close_state.inspect(session.inputs,entity['id'],recovery=True)


def test_report_read_refuses_a_job_receipt_bound_to_a_different_commit(session):
    from keystone.workspace.job_contract import canonical,fingerprint
    _,_,_,job=run_first(session)
    run=Catalog(session.catalog.root).load().runs[0]
    assert session.source_version(run)['id']==run.input_origin.version_id
    with session.store._write() as con:
        raw=json.loads(con.execute('SELECT record_json FROM executions WHERE job_id=?',(job['job_id'],)).fetchone()[0])
        raw['accounting_commit_sha256']='0'*64
        con.execute('UPDATE executions SET record_json=?,record_sha256=? WHERE job_id=?',
                    (canonical(raw),fingerprint(raw),job['job_id']))
    with pytest.raises(c.InputError):session.source_version(run)


def test_workspace_and_entity_accounting_are_isolated(session,tmp_path):
    from keystone.workspace.onboarding.store import create_workspace
    from keystone.workspace.onboarding.service import PrivateAdmission
    from test_native_reports import hashes
    entity,_,_,_=run_first(session)
    before=hashes(session.inputs.root)
    other=PrivateAdmission(create_workspace(tmp_path/'other','Other fictional workspace'),ORIGIN,enable_imports=True,enable_jobs=True)
    try:
        other_entity,_,_,_=run_first(other)
        assert hashes(session.inputs.root)==before
        assert close_state.inspect(session.inputs,entity['id'])['workspace_id']!=close_state.inspect(other.inputs,other_entity['id'])['workspace_id']
    finally:other.close()
    second_entity=session.inputs.create_entity(dict(name='Second company',kind='company',ticker=None,members=[]))
    source=request();source['entity']=second_entity['name']
    _,_,_,version=ingest(session,source,entity=second_entity)
    job=submit(session,version)
    with worker(session) as store:
        run_one(store);assert store.get(job['job_id'])['job']['status']=='review_required'
    assert close_state.state_path(session.inputs,entity['id'])!=close_state.state_path(session.inputs,second_entity['id'])


def test_private_backup_declares_accounting_database_and_restores_exact_state(session,tmp_path):
    from keystone.storage import snapshot,restore
    from keystone.workspace.onboarding.store import InputStore
    entity,_,_,_=run_first(session)
    before=close_state.inspect(session.inputs,entity['id'])
    session.close()
    plan=session.inputs.backup_plan()
    assert [s['role'] for s in plan['sources'] if s['kind']=='database']==['agent4_state']
    def recheck():assert session.inputs.backup_plan()==plan
    saved=snapshot(plan,tmp_path/'snapshots',quiescent=True,verify_source=recheck)
    target=tmp_path/'restored';restore(saved,target)
    restored=InputStore(target)
    assert close_state.inspect(restored,entity['id'])==before
    assert not (target/'control/access-token.key').exists()
    # Absolute JobStore ownership binding remains deliberately held for 3D.
    with pytest.raises(Exception):JobStore(target/'control',target/'reports')
