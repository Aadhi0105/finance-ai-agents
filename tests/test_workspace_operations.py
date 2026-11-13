"""Bounded, protected operating observations, with isolated component failures."""
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from keystone.workspace.api import create_app
from keystone.workspace.job_contract import now
from keystone.workspace.operations import observe,Snapshot,tree_usage
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.worker import run_one
from test_workspace_onboarding import session,headers,ORIGIN
from test_workspace_local_research import ingest,request
from test_workspace_fresh_close import worker
from test_native_reports import hashes,native,legacy

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def api(session):
    return TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)

def get(api,session):
    r=api.get('/api/operations',headers=headers(session));assert r.status_code==200,r.text
    return r.json()

def check(value,key):return next(c for c in value['checks'] if c['key']==key)
def capacity(value,key):return next(c for c in value['capacities'] if c['key']==key)

def test_empty_observation_is_exact_readonly_and_not_production_or_financial_approval(session,api):
    before=hashes(session.inputs.root)
    value=get(api,session);Snapshot.model_validate(value)
    assert value['state']=='ok' and value['job_total']==value['import_total']==value['report_total']==0
    assert check(value,'worker')['state']=='disabled'
    assert capacity(value,'input_storage')['used']==0 and capacity(value,'input_ledger')['used']>0
    assert value['financial_approval'] is value['production_release_approved'] is False
    assert not value['live_data_enabled'] and not value['paid_models_enabled']
    assert api.head('/api/operations',headers=headers(session)).status_code==200
    assert hashes(session.inputs.root)==before
    assert session.token not in json.dumps(value) and str(session.inputs.root) not in json.dumps(value)

def test_schema_matches_runtime(session,api):
    schema=json.loads((ROOT/'keystone/workspace/operations.schema.json').read_text())
    assert schema==Snapshot.model_json_schema();Draft202012Validator(schema).validate(get(api,session))

def test_access_origin_queries_and_all_mutations_are_refused(session,api):
    assert api.get('/api/operations').status_code==403
    assert api.get('/api/operations',headers={**headers(session),'Origin':'https://example.com'}).status_code==403
    assert api.get('/api/operations?command=repair',headers=headers(session)).status_code==422
    assert api.get('/api/operations',headers={**headers(session),'Host':'attacker.example'}).status_code==403
    for method in ('post','put','patch','delete'):
        assert api.request(method,'/api/operations',headers=headers(session),json={}).status_code==405

def test_supplied_inputs_and_queued_work_are_counted_without_execution(session,api):
    *_,version=ingest(session)
    job,_=session.submit(request(version),'ops-queued-original')
    before=hashes(session.inputs.root)
    value=get(api,session)
    assert value['job_counts']['queued']==1 and len(value['jobs'])==1
    assert value['jobs'][0]['id']==job['job_id'] and value['jobs'][0]['stage']=='admitted'
    assert value['jobs'][0]['started_at'] is None
    assert check(value,'worker')['code']=='worker_queue_waiting' and value['state']=='attention'
    assert value['import_total']==1 and value['imports'][0]['state']=='accepted'
    assert capacity(value,'versions')['used']==1 and capacity(value,'input_storage')['used']>0
    assert hashes(session.inputs.root)==before and value['report_total']==0

def test_capacity_advisory_uses_the_full_queue_and_reports_limits(session,api,native):
    from test_workspace_onboarding import ingest as saved_ingest,submit
    version,*_=saved_ingest(session,native,'research')
    for n in range(20):submit(session,version,'ops-capacity-'+str(n))
    value=get(api,session)
    assert len(value['jobs'])==20 and value['job_counts']['queued']==20
    assert capacity(value,'pending_jobs')==dict(key='pending_jobs',used=20,limit=20,state='attention')
    assert capacity(value,'retained_jobs')['used']==20

def test_analysis_reservations_are_visible_before_job_count_capacity_is_reached(session,api):
    *_,version=ingest(session)
    for n in range(5):session.submit(request(version),'ops-analysis-capacity-'+str(n))
    value=get(api,session)
    assert capacity(value,'pending_jobs')['state']=='ok'
    measured=capacity(value,'analysis_evidence')
    assert measured['used']>=80_000_000 and measured['limit']==100_000_000 and measured['state']=='attention'

@pytest.mark.parametrize('running',[True,False])
def test_owned_process_availability_does_not_invent_heartbeat_or_execution(session,api,running):
    session.worker_requested=True;session.worker=SimpleNamespace(running=running,close=lambda:None)
    value=get(api,session)
    assert check(value,'worker')['code']==('worker_process_running' if running else 'worker_process_stopped')
    assert value['job_total']==0

def test_running_stage_and_interrupted_outcome_use_saved_receipts(session,api):
    *_,version=ingest(session);job,_=session.submit(request(version),'ops-running-original')
    with worker(session) as store:
        assert store.claim_next().job_id==job['job_id']
        value=get(api,session);assert value['jobs'][0]['stage']=='claimed' and value['jobs'][0]['status']=='running'
        store.update_execution(job['job_id'],event='inputs_verified',inputs_verified_at=now())
        assert get(api,session)['jobs'][0]['stage']=='inputs_verified'
        store.interrupt_running()
    value=get(api,session)
    assert value['jobs'][0]['status']=='outcome_unknown' and value['jobs'][0]['recovery_required'] is True
    assert check(value,'jobs')['code']=='recovery_inspection_required'

def test_historical_failures_do_not_falsely_claim_current_system_failure(session,api):
    *_,version=ingest(session);job,_=session.submit(request(version),'ops-failure-original')
    with worker(session) as store:
        store.claim_next();store.update_execution(job['job_id'],event='failed',status='failed',reason='execution_failed',finished_at=now(),operation_status='failed_inspect_state')
    value=get(api,session)
    assert value['job_counts']['failed']==1 and value['state']=='ok'
    assert check(value,'jobs')['code']=='job_records_checked'

def test_completed_report_remains_financially_unapproved_and_withdrawal_is_visible(session,api):
    _,_,policy,version=ingest(session);job,_=session.submit(request(version),'ops-report-original')
    with worker(session) as store:assert run_one(store)==(True,False)
    value=get(api,session)
    assert value['report_total']==1 and value['job_counts']['review_required']==1
    assert value['state']=='ok' and not value['financial_approval']
    session.inputs.revoke_permission(policy['id'],'Fictional permission withdrawn')
    assert api.get('/api/workspace',headers=headers(session)).status_code==403
    value=get(api,session)
    assert check(value,'reports')['code']=='report_sources_held'
    assert value['held_reports']==['result-'+job['job_id'][4:]] and value['state']=='attention'
    assert 'Northstar' not in json.dumps(value)  # Operational references do not disclose source contents.

def test_catalog_failure_does_not_hide_other_components_or_invent_zero_reports(session,api):
    path=session.catalog.root/'catalog.json';path.write_bytes(b'broken inventory with /private/secret sk-ant-not-a-real-key')
    assert api.get('/api/workspace',headers=headers(session)).status_code==503
    value=get(api,session)
    assert value['report_total'] is None and check(value,'reports')['state']=='unavailable'
    assert check(value,'jobs')['state']=='ok' and check(value,'inputs')['state']=='ok'
    assert 'secret' not in json.dumps(value) and 'sk-ant' not in json.dumps(value)

def test_corrupt_individual_job_is_counted_as_unknown_not_zero_pending(session,api):
    *_,version=ingest(session);session.submit(request(version),'ops-corrupt-original')
    with session.store._write() as con:con.execute("UPDATE jobs SET record_sha256=?",('0'*64,))
    value=get(api,session)
    assert value['job_total']==1 and value['unreadable_jobs']==1 and not value['jobs']
    assert capacity(value,'pending_jobs')['used'] is None and value['state']=='unavailable'

def test_unreadable_ledger_isolated_and_failed_reads_never_create_control_files(session,api,monkeypatch):
    def broken(*a,**k):raise OSError('/private/secret token')
    monkeypatch.setattr(session.store,'_connect',broken)
    before=hashes(session.inputs.root);value=get(api,session)
    assert value['job_total'] is None and value['job_counts'] is None and value['unreadable_jobs'] is None
    assert capacity(value,'pending_jobs')['used'] is None and capacity(value,'retained_jobs')['used'] is None
    assert check(value,'inputs')['state']=='ok' and 'secret' not in json.dumps(value)
    assert hashes(session.inputs.root)==before

def test_corrupt_import_does_not_claim_available_reserved_space(session,api):
    ingest(session)
    with session.inputs.write() as con:con.execute("UPDATE imports SET receipt_sha=?",('0'*64,))
    value=get(api,session)
    assert value['import_total']==1 and value['unreadable_imports']==1 and value['imports']==[]
    assert capacity(value,'pending_imports')['used'] is None and capacity(value,'input_storage')['used'] is None

def test_import_reservations_include_recovery_held_attempts(session,api):
    _,dataset,_,version=ingest(session)
    raw=(session.inputs.root/'inputs'/version['id']/'package.json').read_bytes()
    preview=session.inputs.inspect_package(dataset['id'],raw)
    session.inputs.reserve(preview['descriptor'],'ops-reserved-import')
    value=get(api,session)
    actual=sum(tree_usage([session.inputs.root/'inputs',session.inputs.root/'staging']))
    assert capacity(value,'pending_imports')['used']==1
    assert capacity(value,'input_storage')['used']==actual+3*len(raw)+65536

def test_private_bounded_storage_scan_handles_files_and_refuses_links_or_overrun(session,api,monkeypatch):
    ingest(session)
    roots=[session.inputs.root/'inputs',session.inputs.root/'staging']
    assert sum(tree_usage(roots))>0
    import keystone.workspace.operations as module
    monkeypatch.setattr(module,'MAX_SCAN_MEMBERS',1)
    value=get(api,session);assert check(value,'storage')['code']=='storage_unavailable'
    assert capacity(value,'input_storage')['used'] is None

def test_storage_symlink_does_not_follow_or_disclose_target(session,api,tmp_path):
    target=tmp_path/'outside';target.write_text('PRIVATE CONTENT')
    (session.inputs.root/'staging/forbidden').symlink_to(target)
    value=get(api,session)
    assert check(value,'storage')['state']=='unavailable' and 'PRIVATE' not in json.dumps(value)

def test_low_disk_space_is_advisory_and_does_not_mutate_or_change_limits(session,api,monkeypatch):
    import keystone.workspace.operations as module
    monkeypatch.setattr(module.shutil,'disk_usage',lambda _:SimpleNamespace(free=99,total=10_000_000_000))
    before=hashes(session.inputs.root);value=get(api,session)
    assert check(value,'storage')['code']=='storage_near_limit' and value['disk_free_bytes']==99
    assert capacity(value,'input_storage')['limit']==c.MAX_INPUT_BYTES and hashes(session.inputs.root)==before

def test_oversized_response_is_refused_and_read_does_not_repair_or_execute(session,api,monkeypatch):
    import keystone.workspace.operations as module
    import socket
    import keystone.operation
    def forbidden(*a,**k):pytest.fail('Operations attempted execution, acquisition or a control write')
    monkeypatch.setattr(socket.socket,'connect',forbidden);monkeypatch.setattr(keystone.operation,'execute',forbidden)
    monkeypatch.setattr(session.inputs,'write',forbidden);monkeypatch.setattr(session.store,'_write',forbidden)
    assert get(api,session)['state']=='ok'
    monkeypatch.setattr(module,'MAX_RESPONSE_BYTES',100)
    assert api.get('/api/operations',headers=headers(session)).status_code==503

def test_synthetic_catalog_does_not_expose_operator_observations(native):
    api=TestClient(create_app(native),base_url=ORIGIN)
    assert api.get('/api/workspace').status_code==200
    assert api.get('/api/operations').status_code==404

@pytest.mark.parametrize('workflow',['research','monitoring','events','news','close'])
def test_all_saved_report_families_have_operational_outcomes_without_financial_approval(session,api,native,workflow):
    from test_workspace_onboarding import ingest as saved_ingest,submit
    version,*_=saved_ingest(session,native,workflow);job=submit(session,version)
    with worker(session) as store:assert run_one(store)==(True,False)
    value=get(api,session)
    assert value['jobs'][0]['workflow']==workflow and value['jobs'][0]['id']==job['job_id']
    assert value['job_counts']['review_required']==1 and value['report_total']==1
    assert not value['held_reports'] and value['state']=='ok' and value['financial_approval'] is False

def test_restored_queue_is_visible_without_releasing_or_processing_it(session,tmp_path):
    from test_workspace_private_recovery import capture
    from keystone.workspace.onboarding.recovery import restore_private
    from keystone.workspace.onboarding.service import PrivateAdmission
    *_,version=ingest(session);job,_=session.submit(request(version),'ops-restored-original')
    restored=PrivateAdmission(restore_private(capture(session,tmp_path),tmp_path/'restored-ops'),ORIGIN)
    try:
        before=hashes(restored.inputs.root);value=observe(restored)
        assert value['jobs'][0]['id']==job['job_id'] and value['jobs'][0]['restoration_hold'] is True
        assert value['jobs'][0]['status']=='queued' and value['jobs'][0]['started_at'] is None
        assert value['jobs'][0]['recovery_required'] is True and value['report_total']==0
        assert hashes(restored.inputs.root)==before
    finally:restored.close()

def test_reads_remain_coherent_while_a_worker_updates_a_receipt(session,api):
    from concurrent.futures import ThreadPoolExecutor
    *_,version=ingest(session);session.submit(request(version),'ops-concurrent-original')
    with worker(session) as store,ThreadPoolExecutor(max_workers=2) as pool:
        values=[pool.submit(get,api,session) for _ in range(8)]
        store.claim_next();store.interrupt_running()
        for task in values:
            value=task.result();Snapshot.model_validate(value)
            if value['job_total'] is not None:
                assert sum(value['job_counts'].values())+value['unreadable_jobs']==1
    assert get(api,session)['jobs'][0]['status']=='outcome_unknown'

def test_report_observation_checks_the_catalog_once(session,api,monkeypatch):
    *_,version=ingest(session);session.submit(request(version),'ops-catalog-once')
    with worker(session) as store:assert run_one(store)==(True,False)
    original=session.catalog.load;calls=[]
    def counted():calls.append(True);return original()
    monkeypatch.setattr(session.catalog,'load',counted)
    assert get(api,session)['report_total']==1 and len(calls)==1

def test_fresh_close_observation_preserves_committed_accounting_state(session,api):
    from test_workspace_fresh_close import ingest as close_ingest
    from test_workspace_onboarding import submit
    *_,version=close_ingest(session);submit(session,version,'ops-fresh-accounting')
    with worker(session) as store:assert run_one(store)==(True,False)
    before=hashes(session.inputs.root)
    value=get(api,session)
    assert value['jobs'][0]['workflow']=='close' and value['job_counts']['review_required']==1
    assert value['report_total']==1 and value['state']=='ok' and not value['financial_approval']
    assert hashes(session.inputs.root)==before
