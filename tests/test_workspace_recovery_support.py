"""Recovery triage is not recovery authority; stopped CLI recovery is explicit."""
from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from keystone.workspace.api import create_app
from keystone.workspace import recovery_support as support,operations
from keystone.workspace.__main__ import main
from keystone.workspace.job_store import JobStore
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.onboarding.store import InputStore
from keystone.workspace.worker import run_one
from test_workspace_onboarding import session,headers,ORIGIN,prepare
from test_workspace_local_research import ingest,request
from test_workspace_fresh_close import worker
from test_native_reports import hashes,native,legacy


def api(session):return TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)


def test_protected_readonly_guidance_is_redacted_and_does_not_establish_backup(session):
    before=hashes(session.inputs.root);client=api(session)
    assert client.get('/api/recovery').status_code==403
    assert client.get('/api/recovery',headers={**headers(session),'Origin':'https://foreign.example'}).status_code==403
    response=client.get('/api/recovery',headers=headers(session));assert response.status_code==200,response.text
    value=response.json();support.Recovery.model_validate(value)
    assert value['state']=='observed' and value['job_total']==value['import_total']==0
    assert value['jobs']==value['imports']==[]
    assert value['protection']['independent_backup']=='not_verified_here'
    assert value['protection']['local_restore']=='requires_separate_receipt'
    assert all(value[k] is False for k in ('automatic_recovery','automatic_retry','financial_approval','production_release_approved'))
    assert session.token not in response.text and str(session.inputs.root) not in response.text
    assert response.headers['cache-control']=='no-store'
    assert client.head('/api/recovery',headers=headers(session)).content==b''
    assert client.get('/api/recovery?command=retry',headers=headers(session)).status_code==422
    for method in ('POST','PUT','PATCH','DELETE'):assert client.request(method,'/api/recovery',headers=headers(session)).status_code==405
    assert hashes(session.inputs.root)==before


def test_schema_matches_runtime():
    schema=json.loads((Path(__file__).parents[1]/'keystone/workspace/recovery.schema.json').read_text())
    assert schema==support.Recovery.model_json_schema()


def test_fresh_restore_can_be_audited_before_server_start_or_key_creation(session,tmp_path):
    from test_workspace_private_recovery import capture
    from keystone.workspace.onboarding.recovery import restore_private
    from keystone.workspace.lifecycle import audit_private
    snapshot=capture(session,tmp_path)
    root=restore_private(snapshot,tmp_path/'offline-restored')
    assert (root/'control/session.lock').read_bytes()==b''
    assert not (root/'control/access-token.key').exists()
    before=hashes(root)
    assert audit_private(root)['state']=='verified'
    assert hashes(root)==before and not (root/'control/access-token.key').exists()


@pytest.mark.parametrize('status,held,workflow,running,code',[
 ('queued',True,'research',False,'restored_queue_held'),('queued',False,'news',False,'queued_waiting'),
 ('running',False,'research',True,'work_in_progress'),('running',False,'events',False,'worker_interrupted'),
 ('delivery_failed',False,'research',False,'delivery_inspection'),('outcome_unknown',False,'close',False,'unknown_outcome'),
 ('source_changed',False,'monitoring',False,'source_hold'),('failed',False,'close',False,'close_state_inspection'),
 ('failed',False,'research',False,'failed_attempt'),('review_required',False,'research',False,None),('completed',False,'close',False,None),
])
def test_guidance_distinguishes_never_started_uncertain_committed_and_historical_work(session,monkeypatch,status,held,workflow,running,code):
    raw=operations.observe(session);raw['job_total']=1
    raw['jobs']=[dict(id='job-'+'a'*32,workflow=workflow,status=status,created_at=raw['observed_at'],started_at=None,finished_at=None,
        stage='admitted',timeout_seconds=120,restoration_hold=held,recovery_required=held)]
    if running:next(x for x in raw['checks'] if x['key']=='worker').update(code='worker_process_running',state='ok')
    monkeypatch.setattr(operations,'observe',lambda _:raw)
    before=hashes(session.inputs.root);value=support.observe(session)
    assert ([j['guidance'] for j in value['jobs']])==([] if code is None else [code])
    assert not value['automatic_recovery'] and not value['automatic_retry']
    assert hashes(session.inputs.root)==before


@pytest.mark.parametrize('state,code',[('reserved','import_in_progress'),('receiving','import_in_progress'),('validating','import_in_progress'),('interrupted','import_inspection'),('delivery_failed','import_inspection'),('rejected','import_rejected'),('accepted',None)])
def test_import_guidance_does_not_mean_financial_execution(session,monkeypatch,state,code):
    raw=operations.observe(session);raw['import_total']=1
    raw['imports']=[dict(id='import-'+'b'*32,state=state,created_at=raw['observed_at'])]
    monkeypatch.setattr(operations,'observe',lambda _:raw)
    value=support.observe(session)
    assert [i['guidance'] for i in value['imports']]==([] if code is None else [code])


def test_unknown_inventory_is_not_a_healthy_empty_recovery_list(session,monkeypatch):
    raw=operations.observe(session);raw.update(job_total=None,unreadable_jobs=None)
    monkeypatch.setattr(operations,'observe',lambda _:raw)
    value=support.observe(session)
    assert value['state']=='unavailable' and value['job_total'] is None
    assert value['jobs']==[]


def test_unreadable_case_stays_counted_as_unknown(session,monkeypatch):
    raw=operations.observe(session);raw.update(job_total=2,unreadable_jobs=1)
    raw['jobs']=[dict(id='job-'+'a'*32,workflow='news',status='delivery_failed',created_at=raw['observed_at'],started_at=None,finished_at=None,stage='delivery_failed',timeout_seconds=120,restoration_hold=False,recovery_required=True)]
    monkeypatch.setattr(operations,'observe',lambda _:raw)
    value=support.observe(session)
    assert value['state']=='unavailable' and value['unreadable_jobs']==1 and len(value['jobs'])==1


@pytest.mark.parametrize('command,extra',[
 ('recover-private-job',['--job-id','job-'+'a'*32]),('recover-import',['--import-id','import-'+'b'*32]),
 ('release-restored-job',['--job-id','job-'+'a'*32,'--reason','Fictional review']),
 ('release-uncommitted-close',['--job-id','job-'+'a'*32]),
])
def test_private_cli_refuses_live_server_before_journal_recovery_or_any_change(session,monkeypatch,capsys,command,extra):
    import keystone.workspace.onboarding.store as inputs
    before=hashes(session.inputs.root);called=[]
    monkeypatch.setattr(inputs.InputStore,'__init__',lambda *a,**k:called.append(True))
    assert main([command,'--workspace',str(session.inputs.root),*extra])==2
    assert called==[] and hashes(session.inputs.root)==before
    output=capsys.readouterr();assert session.token not in output.err and str(session.inputs.root) not in output.err


def test_private_legacy_reports_spelling_cannot_bypass_stopped_server_guard(session):
    before=hashes(session.inputs.root)
    assert main(['recover-job','--workspace',str(session.catalog.root),'--jobs-dir',str(session.store.root),'--job-id','job-'+'a'*32])==2
    assert hashes(session.inputs.root)==before


def test_private_cli_refuses_live_worker_before_input_journal_recovery(session,monkeypatch):
    import keystone.workspace.onboarding.store as inputs
    root=session.inputs.root;session.close();store=JobStore(root/'control',root/'reports',worker=True)
    before=hashes(root);called=[]
    monkeypatch.setattr(inputs.InputStore,'__init__',lambda *a,**k:called.append(True))
    try:assert main(['recover-private-job','--workspace',str(root),'--job-id','job-'+'a'*32])==2
    finally:store.close()
    assert called==[] and hashes(root)==before


def test_surviving_mutator_lease_blocks_recovery_before_input_open(session,monkeypatch):
    from keystone.maintenance import control_write_gate
    import keystone.workspace.onboarding.store as inputs
    root=session.inputs.root;session.close();before=hashes(root);called=[]
    monkeypatch.setattr(inputs.InputStore,'__init__',lambda *a,**k:called.append(True))
    with control_write_gate():
        assert main(['recover-private-job','--workspace',str(root),'--job-id','job-'+'a'*32])==2
    assert called==[] and hashes(root)==before


def test_root_based_cli_recovers_saved_delivery_twice_without_recalculation(session,monkeypatch,capsys):
    *_,version=ingest(session);job,_=session.submit(request(version),'support-delivery-0001')
    from keystone.workspace import worker as runtime
    with worker(session) as store:
        with monkeypatch.context() as patch:
            patch.setattr(runtime,'publish_result',lambda *_:(_ for _ in ()).throw(OSError('Fictional publication failure')))
            assert run_one(store)==(True,False)
        assert store.get(job['job_id'])['job']['status']=='delivery_failed'
    operation=session.inputs.root/'control/operations'/job['operation_id']/'operation.json';original=operation.read_bytes()
    session.close()
    from keystone.workspace.onboarding.research import calculate as maths
    monkeypatch.setattr(maths,'calculate',lambda *_a,**_k:pytest.fail('Recovery recalculated'))
    monkeypatch.setattr(runtime.operation,'execute',lambda *_a,**_k:pytest.fail('Recovery dispatched'))
    first=None
    for _ in range(2):
        assert main(['recover-private-job','--workspace',str(session.inputs.root),'--job-id',job['job_id']])==0
        value=json.loads(capsys.readouterr().out)
        assert value['status']=='review_required' and not value['financial_execution_started']
        if first is None:first=value
        else:assert value==first
    assert operation.read_bytes()==original
    reader=JobStore.reader(session.store.root,session.catalog.root)
    try:assert reader.get(job['job_id'])['job']['execution']['attempt']==1
    finally:reader.close()


def test_missing_proof_stays_unknown_without_a_second_attempt(session,monkeypatch):
    *_,version=ingest(session);job,_=session.submit(request(version),'unknown-attempt-0001')
    with worker(session) as store:assert store.claim_next().job_id==job['job_id']
    session.close()
    from keystone.workspace import worker as runtime
    monkeypatch.setattr(runtime.operation,'execute',lambda *_a,**_k:pytest.fail('Unknown attempt dispatched'))
    assert main(['recover-private-job','--workspace',str(session.inputs.root),'--job-id',job['job_id']])==2
    reader=JobStore.reader(session.store.root,session.catalog.root)
    try:
        saved=reader.get(job['job_id'])['job']
        assert saved['status']=='outcome_unknown' and saved['execution']['attempt']==1
    finally:reader.close()


def test_prepared_import_cli_accepts_once_without_validation_or_execution(session,native,monkeypatch,capsys):
    _,data,descriptor,_=prepare(session,native,'close');client=api(session);key='support-import-0001'
    reserved=client.post('/api/imports',json=descriptor,headers=headers(session,key));ident=reserved.json()['import_attempt']['id']
    with monkeypatch.context() as patch:
        patch.setattr(session.inputs,'_promote',lambda *_:(_ for _ in ()).throw(OSError('Fictional interrupted promotion')))
        assert client.put('/api/imports/'+ident+'/package',content=data,headers=headers(session,key)).status_code==503
    assert session.inputs.attempt(ident)[1]['state']=='delivery_failed'
    session.close()
    import keystone.workspace.onboarding.service as service
    monkeypatch.setattr(service.subprocess,'run',lambda *_a,**_k:pytest.fail('Recovery repeated validation'))
    first=None
    for _ in range(2):
        assert main(['recover-import','--workspace',str(session.inputs.root),'--import-id',ident])==0
        value=json.loads(capsys.readouterr().out);assert value['state']=='accepted'
        if first is None:first=value
        else:assert value==first
    assert len(InputStore(session.inputs.root).versions(descriptor['dataset_id'])['items'])==1
