"""Supervised saved-job execution, source preservation and delivery-only recovery."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest

from keystone.maintenance import ROOT
from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog, read_json
from keystone.workspace.jobs import Admission
from keystone.workspace.job_store import JobStore
from keystone.workspace.worker import run_one, recover_delivery
from test_native_reports import legacy, native, hashes

ORIGIN = 'http://127.0.0.1:8765'


@pytest.fixture
def working(native, tmp_path):
    workspace = tmp_path / 'workspace'
    shutil.copytree(native, workspace)
    service = Admission(workspace, tmp_path / 'control', ORIGIN)
    yield workspace, service
    service.close()


def admit(service, workflow, key=None):
    return service.submit(dict(workflow=workflow,source_run_id=workflow+'-example',timeout_seconds=60),
                          key or 'worker-'+workflow)[0]


def worker_store(service):
    return JobStore(service.store.root, service.catalog.root, worker=True)


def diagnostics(service, job):
    folder=service.store.root/'jobs'/job['job_id']
    return (folder/'failure.json').read_text() if (folder/'failure.json').exists() else service.get(job['job_id'])


@pytest.mark.parametrize('workflow',['research','monitoring','events','news','close'])
def test_real_offline_profiles_register_new_native_reports_without_changing_sources(working,workflow):
    workspace,service=working
    before=hashes(workspace);old=read_json((workspace/'catalog.json').read_bytes())
    job=admit(service,workflow)
    store=worker_store(service)
    try:
        assert run_one(store)==(True,False)
        saved=service.get(job['job_id']);current=saved['job']
        assert current['status']=='review_required',diagnostics(service,job)
        assert current['execution']['attempt']==1 and current['execution']['inputs_verified_at']
        assert not current['financial_approval'] and not current['paid_models_enabled']
        ident='result-'+job['job_id'][4:]
        assert current['result_url']=='#/runs/'+ident
        with TestClient(create_app(workspace),base_url=ORIGIN) as api:
            result=api.get('/api/runs/'+ident);assert result.status_code==200
            view=api.get('/api/runs/'+ident+'/report-view');assert view.status_code==200
            assert view.json()['state']['financial_approval'] is False
            assert view.json()['state']['evidence_gate']=='held_for_review'
            assert result.json()['job_origin']['job_id']==job['job_id']
            assert result.json()['job_origin']['source_catalog_run_id']==workflow+'-example'
        after=read_json((workspace/'catalog.json').read_bytes())
        assert after['runs'][:-1]==old['runs'] and len(after['runs'])==len(old['runs'])+1
        assert {p:h for p,h in hashes(workspace).items() if p in before and p!='catalog.json'}=={p:h for p,h in before.items() if p!='catalog.json'}
        assert run_one(store)==(False,False)
        receipt=json.loads((service.store.root/'operations'/job['operation_id']/'operation.json').read_text())
        assert receipt['status']=='review_required' and receipt['model_control']['requests_reserved']==0
    finally:store.close()


def test_source_change_after_admission_is_refused_without_starting_operation(working):
    workspace,service=working
    job=admit(service,'close')
    target=workspace/'runs/close-example/close-june.json'
    original=target.read_bytes();target.write_bytes(original+b'\n')
    store=worker_store(service)
    try:
        assert run_one(store)==(True,False)
        assert service.get(job['job_id'])['job']['status']=='source_changed'
        assert not (store.root/'operations'/job['operation_id']).exists()
        target.write_bytes(original)
        assert run_one(store)==(False,False)
        replay,replayed=service.submit(job['request'],'worker-close')
        assert replayed and replay['status']=='source_changed'
    finally:store.close()


def test_even_valid_overview_metadata_changes_do_not_bypass_source_pins(working):
    workspace,service=working
    job=admit(service,'monitoring')
    path=workspace/'catalog.json';raw=read_json(path.read_bytes())
    next(r for r in raw['runs'] if r['id']=='monitoring-example')['summary']='New legitimate saved overview metadata.'
    path.write_text(json.dumps(raw))
    Catalog(workspace).load()  # The inventory is valid, but it is a different admitted source.
    store=worker_store(service)
    try:
        run_one(store)
        assert service.get(job['job_id'])['job']['status']=='source_changed'
        assert not (store.root/'operations'/job['operation_id']).exists()
    finally:store.close()


@pytest.mark.parametrize('after_replace',[False,True])
def test_failed_registration_recovers_saved_delivery_without_reexecuting(working,monkeypatch,after_replace):
    import keystone.workspace.job_delivery as delivery
    import keystone.workspace.worker as worker
    workspace,service=working
    original=read_json((workspace/'catalog.json').read_bytes())
    job=admit(service,'close');replace=delivery._replace_inventory
    def fail(*args):
        if after_replace:replace(*args)
        raise OSError('PRIVATE-delivery-error')
    store=worker_store(service)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(delivery,'_replace_inventory',fail)
            run_one(store)
        failed=service.get(job['job_id'])['job']
        assert failed['status']=='delivery_failed' and failed['execution']['result']
        current=Catalog(workspace).load()
        assert len(current.runs)==len(original['runs'])+int(after_replace)
        with monkeypatch.context() as patch:
            patch.setattr(worker.operation,'execute',lambda *a,**k:pytest.fail('Recovery reran an operation'))
            recovered=recover_delivery(store,job['job_id'])
            again=recover_delivery(store,job['job_id'])
        assert recovered['job']['status']=='review_required'
        assert recovered==again
        assert len(Catalog(workspace).load().runs)==len(original['runs'])+1
        assert [e['event'] for e in recovered['events']].count('recovered')==1
        assert 'PRIVATE-delivery-error' not in json.dumps(recovered)
        assert read_json((workspace/'catalog.json').read_bytes())['runs'][:-1]==original['runs']
    finally:store.close()


def test_recovery_refuses_changed_prepared_output(working,monkeypatch):
    import keystone.workspace.job_delivery as delivery
    workspace,service=working;job=admit(service,'close');store=worker_store(service)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(delivery,'_replace_inventory',lambda *a:(_ for _ in ()).throw(OSError('disk')))
            run_one(store)
        assert service.get(job['job_id'])['job']['status']=='delivery_failed'
        stage=store.root/'jobs'/job['job_id']/'result/catalog.json'
        stage.write_bytes(stage.read_bytes()+b'\n')
        with pytest.raises(Exception):recover_delivery(store,job['job_id'])
        assert service.get(job['job_id'])['job']['status']=='delivery_failed'
        assert len(Catalog(workspace).load().runs)==5
    finally:store.close()


def test_worker_lease_excludes_another_worker_and_does_not_reclaim_running_jobs(working):
    _,service=working;job=admit(service,'monitoring');store=worker_store(service)
    try:
        store.claim_next()
        with pytest.raises(Exception):worker_store(service)
    finally:store.close()
    replacement=worker_store(service)
    try:
        replacement.interrupt_running()
        assert service.get(job['job_id'])['job']['status']=='outcome_unknown'
        assert run_one(replacement)==(False,False)
        assert not (replacement.root/'operations'/job['operation_id']).exists()
        with pytest.raises(Exception):recover_delivery(replacement,job['job_id'])
    finally:replacement.close()


def test_used_working_directory_never_causes_an_automatic_second_execution(working):
    _,service=working;job=admit(service,'close')
    folder=service.store.root/'jobs'/job['job_id'];folder.mkdir(parents=True,mode=0o700)
    marker=folder/'preserve';marker.write_text('prior partial work')
    store=worker_store(service)
    try:
        run_one(store)
        assert service.get(job['job_id'])['job']['status']=='outcome_unknown'
        assert marker.read_text()=='prior partial work'
        assert not (store.root/'operations'/job['operation_id']).exists()
    finally:store.close()


def test_existing_v1_ledger_migrates_without_losing_admission_or_idempotency(working):
    import sqlite3
    workspace,service=working;job=admit(service,'news');root=service.store.root
    original=service.store.immutable(job['job_id']).model_dump()
    service.close()
    with sqlite3.connect(root/'jobs.sqlite3') as con:
        events=con.execute('SELECT job_id,event,created_at FROM events').fetchall()
        con.execute('DROP TABLE executions');con.execute('DROP TABLE events')
        con.execute("CREATE TABLE events(job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),event TEXT NOT NULL CHECK(event='admitted'),created_at TEXT NOT NULL)")
        con.executemany('INSERT INTO events VALUES (?,?,?)',events)
        con.execute('PRAGMA user_version=1')
    migrated=Admission(workspace,root,ORIGIN)
    try:
        replay,replayed=migrated.submit(job['request'],'worker-news')
        assert replayed and replay['job_id']==job['job_id'] and replay['status']=='queued'
        assert migrated.store.immutable(job['job_id']).model_dump()==original
        assert migrated.get(job['job_id'])['events']==[{'event':'admitted','created_at':job['created_at']}]
        with sqlite3.connect(root/'jobs.sqlite3') as con:assert con.execute('PRAGMA user_version').fetchone()[0]==2
    finally:migrated.close()


def test_pending_capacity_is_released_after_delivery_but_history_is_retained(working,monkeypatch):
    import keystone.workspace.job_store as module
    _,service=working;monkeypatch.setattr(module,'MAX_PENDING_JOBS',1)
    first=admit(service,'close')
    with pytest.raises(Exception):admit(service,'monitoring')
    store=worker_store(service)
    try:
        run_one(store)
        second=admit(service,'monitoring')
        assert second['status']=='queued' and service.get(first['job_id'])['job']['status']=='review_required'
        monkeypatch.setattr(module,'MAX_RETAINED_JOBS',2)
        run_one(store)
        with pytest.raises(Exception):admit(service,'events')
        assert len(service.store.list(100,None)['jobs'])==2
    finally:store.close()


def test_private_working_copy_must_match_source_before_child_can_render(working,monkeypatch):
    import keystone.workspace.worker as worker
    workspace,service=working;job=admit(service,'monitoring');execute=worker.operation.execute
    def tamper(agent,args,*a,**k):
        target=Path(args[0])/'inputs/runs/monitoring-example/snapshot.json'
        target.write_bytes(target.read_bytes()+b'\n')
        return execute(agent,args,*a,**k)
    store=worker_store(service)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(worker.operation,'execute',tamper)
            run_one(store)
        assert service.get(job['job_id'])['job']['status']=='failed'
        assert len(Catalog(workspace).load().runs)==5
    finally:store.close()


def test_valid_native_projection_cannot_publish_changed_financial_evidence(working,monkeypatch):
    import hashlib
    import keystone.workspace.worker as worker
    from keystone.workspace.report_views.publish import register_views
    from keystone.workspace.catalog import ManifestV2
    workspace,service=working;job=admit(service,'monitoring');verify=worker.verified_result
    checked={'valid_native':False}
    def replace_financial_source(store,record):
        stage=store.root/'jobs'/record.job_id/'result'
        manifest=Catalog(stage).load();raw=manifest.model_dump();run=raw['runs'][0]
        registration=run.pop('native_view');excluded={registration['artifact_id'],registration['source_artifact_ids'][1]}
        run['artifacts']=[a for a in run['artifacts'] if a['id'] not in excluded]
        primary=next(a for a in run['artifacts'] if a['name']=='snapshot.json')
        path=stage/'runs'/run['id']/'snapshot.json';source=read_json(path.read_bytes())
        source['current'][0]['value']+=.01
        data=(json.dumps(source,allow_nan=False)+'\n').encode();path.write_bytes(data)
        primary.update(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
        for name in ['native-series.json','native-report.json']:(stage/'runs'/run['id']/name).unlink()
        (stage/'catalog.json').unlink()
        register_views(stage,ManifestV2.model_validate(raw))
        Catalog(stage).load()  # Valid-looking, internally source-bound output still differs from admitted financial evidence.
        checked['valid_native']=True
        return verify(store,record)
    store=worker_store(service)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(worker,'verified_result',replace_financial_source)
            run_one(store)
        assert checked['valid_native']
        assert service.get(job['job_id'])['job']['status']=='failed'
        assert len(Catalog(workspace).load().runs)==5
    finally:store.close()


def wait_for_job(service,job_id,statuses,timeout=30):
    import time
    until=time.monotonic()+timeout
    last=None
    while time.monotonic()<until:
        last=service.get(job_id)['job']
        if last['status'] in statuses:return last
        time.sleep(.05)
    pytest.fail('Job did not reach expected state: '+str(last))


def test_managed_background_worker_runs_via_existing_protected_api(native,tmp_path):
    workspace=tmp_path/'managed';shutil.copytree(native,workspace)
    service=Admission(workspace,tmp_path/'control',ORIGIN,enable_worker=True)
    first=None
    with TestClient(create_app(workspace,admission=service),base_url=ORIGIN) as api:
        caps=api.get('/api/execution').json()
        assert caps['worker_enabled'] and not caps['paid_models_enabled'] and not caps['live_data_enabled']
        headers={'Authorization':'Bearer '+service.token,'Origin':ORIGIN,'Idempotency-Key':'background-one'}
        response=api.post('/api/jobs',json={'workflow':'close','source_run_id':'close-example'},headers=headers)
        assert response.status_code==202
        first=response.json()['job'];finished=wait_for_job(service,first['job_id'],{'review_required','failed','outcome_unknown'})
        assert first['schema_version']==2 and first['admission_schema_version']==1
        assert finished['status']=='review_required',diagnostics(service,first)
        assert finished['worker_enabled'] and finished['result_url']
        ident=finished['execution']['result']['run_id']
        assert api.get('/api/runs/'+ident+'/report-view').status_code==200
        replay=api.post('/api/jobs',json={'workflow':'close','source_run_id':'close-example'},headers=headers)
        assert replay.status_code==200 and replay.json()['job']['job_id']==first['job_id']
        assert replay.json()['job']['status']=='review_required'
        assert api.get('/api/jobs/'+first['job_id']).status_code==403
    assert not service.worker_enabled
    restarted=Admission(workspace,tmp_path/'control',ORIGIN)
    try:
        saved=restarted.get(first['job_id'])['job']
        assert saved['status']=='review_required' and saved['execution']['attempt']==1
        assert len(Catalog(workspace).load().runs)==6
    finally:restarted.close()


def test_enabled_queue_admission_can_continue_while_worker_owns_mutator(native,tmp_path):
    from keystone.maintenance import gate
    workspace=tmp_path/'queue';shutil.copytree(native,workspace)
    service=Admission(workspace,tmp_path/'control',ORIGIN,enable_worker=True)
    try:
        with gate():
            job=admit(service,'monitoring')
            assert job['status']=='queued'
        with gate(exclusive=True):
            with pytest.raises(Exception):admit(service,'close')
        assert service.get(job['job_id'])['job']['status']=='queued'
    finally:service.close()


def test_no_browser_can_enable_worker_or_inject_transition(working):
    workspace,service=working
    with TestClient(create_app(workspace,admission=service),base_url=ORIGIN) as api:
        headers={'Authorization':'Bearer '+service.token,'Origin':ORIGIN,'Idempotency-Key':'no-transition'}
        for extra in [{'worker_enabled':True},{'status':'completed'},{'execute':True}]:
            response=api.post('/api/jobs',json={'workflow':'close','source_run_id':'close-example',**extra},headers=headers)
            assert response.status_code==422
        job=api.post('/api/jobs',json={'workflow':'close','source_run_id':'close-example'},headers=headers).json()['job']
        assert api.post('/api/jobs/'+job['job_id']+'/recover',headers=headers).status_code==405
        assert api.post('/api/jobs/'+job['job_id']+'/start',headers=headers).status_code==405
        assert not api.get('/api/execution').json()['worker_enabled']


def test_worker_deadline_marks_unknown_and_never_retries_claimed_job(working,monkeypatch,tmp_path):
    import keystone.operation as operation
    workspace,service=working
    job=service.submit({'workflow':'close','source_run_id':'close-example','timeout_seconds':1},'timeout-request')[0]
    ready=tmp_path/'partial';script=tmp_path/'stall.py'
    script.write_text('from pathlib import Path\nimport time\nPath('+repr(str(ready))+').write_text("private output")\ntime.sleep(60)\n')
    store=worker_store(service)
    try:
        with monkeypatch.context() as patch:
            patch.setitem(operation.ENTRYPOINTS,'workspace-saved',[str(script)])
            run_one(store)
        assert ready.exists()
        assert service.get(job['job_id'])['job']['status']=='outcome_unknown'
        assert run_one(store)==(False,False) and len(Catalog(workspace).load().runs)==5
        assert service.get(job['job_id'])['job']['execution']['attempt']==1
    finally:store.close()


def test_supervised_child_has_no_provider_secrets_and_live_defaults_are_overridden(working,monkeypatch,tmp_path):
    import keystone.operation as operation
    _,service=working;job=admit(service,'close')
    result=tmp_path/'environment.json';script=tmp_path/'environment.py'
    script.write_text('import os,json\nfrom pathlib import Path\nPath('+repr(str(result))+').write_text(json.dumps({k:os.environ.get(k) for k in ["ANTHROPIC_API_KEY","AGENT_DATA_SOURCE","AGENT_STATS_VIA_MCP","KEYSTONE_SUPERVISED"]}))\n')
    store=worker_store(service)
    try:
        with monkeypatch.context() as patch:
            patch.setenv('ANTHROPIC_API_KEY','NEVER-PASS-THIS')
            patch.setenv('AGENT_DATA_SOURCE','yfinance');patch.setenv('AGENT_STATS_VIA_MCP','1')
            patch.setitem(operation.ENTRYPOINTS,'workspace-saved',[str(script)])
            run_one(store)
        values=json.loads(result.read_text())
        assert values=={'ANTHROPIC_API_KEY':None,'AGENT_DATA_SOURCE':'fixture','AGENT_STATS_VIA_MCP':'0','KEYSTONE_SUPERVISED':'1'}
        assert 'NEVER-PASS-THIS' not in json.dumps(service.get(job['job_id']))
    finally:store.close()


def test_offline_renderer_refuses_unsupervised_execution(working):
    import subprocess,sys
    workspace,service=working;job=admit(service,'close')
    result=subprocess.run([sys.executable,'-m','keystone.workspace.saved_job',str(service.store.root/'jobs'/job['job_id'])],capture_output=True)
    assert result.returncode==2
    assert not (service.store.root/'jobs').exists()
    assert len(Catalog(workspace).load().runs)==5


def test_supervised_saved_runtime_blocks_real_socket_entrypoint(working,monkeypatch,tmp_path):
    import keystone.operation as operation
    _,service=working;job=admit(service,'close')
    script=tmp_path/'network_attempt.py'
    script.write_text('import socket,sys\nsys.path.insert(0,'+repr(str(ROOT))+')\nfrom keystone.workspace import saved_job\nsaved_job.render=lambda folder:socket.create_connection(("127.0.0.1",9))\nraise SystemExit(saved_job.main())\n')
    store=worker_store(service)
    try:
        with monkeypatch.context() as patch:
            patch.setitem(operation.ENTRYPOINTS,'workspace-saved',[str(script)])
            run_one(store)
        failure=json.loads((store.root/'jobs'/job['job_id']/'failure.json').read_text())
        assert failure['error_type']=='PermissionError'
        assert service.get(job['job_id'])['job']['status']=='failed'
    finally:store.close()


def test_shutdown_of_running_worker_records_interruption_without_report(native,tmp_path):
    import time
    from keystone.workspace.worker_process import WorkerProcess
    workspace=tmp_path/'stopped';shutil.copytree(native,workspace)
    service=Admission(workspace,tmp_path/'control',ORIGIN,enable_worker=True)
    service.start_worker()
    try:
        job=admit(service,'research')
        wait_for_job(service,job['job_id'],{'running','review_required'})
        # Only assert interruption if shutdown reaches a genuinely in-flight operation.
        if service.get(job['job_id'])['job']['status']=='running':
            service.worker.close()
            state=service.get(job['job_id'])['job']['status']
            assert state in {'outcome_unknown','review_required'}
            if state=='outcome_unknown':assert len(Catalog(workspace).load().runs)==5
        else:assert len(Catalog(workspace).load().runs)==6
    finally:service.close()


def test_verified_delivery_survives_local_control_backup_restore(working,monkeypatch,tmp_path):
    from keystone.storage import snapshot,restore
    from test_production_storage import plan_for,entry
    import keystone.workspace.job_delivery as delivery
    import keystone.workspace.worker as worker
    workspace,service=working;job=admit(service,'close');store=worker_store(service)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(delivery,'_replace_inventory',lambda *a:(_ for _ in ()).throw(OSError('disk')))
            run_one(store)
        assert service.get(job['job_id'])['job']['status']=='delivery_failed'
    finally:store.close()
    plan=plan_for([entry(service.store.path,'jobs.sqlite3','file','logs'),
        entry(service.store.root/'jobs','jobs','tree','logs'),
        entry(service.store.root/'operations','operations','tree','logs')])
    saved=snapshot(plan,tmp_path/'backup',quiescent=True)
    restored=restore(saved,tmp_path/'restored-control')
    service.close()
    opened=Admission(workspace,restored,ORIGIN);recovery=worker_store(opened)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(worker.operation,'execute',lambda *a,**k:pytest.fail('Restore recovery reran financial work'))
            result=recover_delivery(recovery,job['job_id'])
        assert result['job']['status']=='review_required'
        assert result['job']['operation_id']==job['operation_id']
        assert len(Catalog(workspace).load().runs)==6
    finally:recovery.close();opened.close()


def test_hard_worker_exit_keeps_child_lease_and_never_reexecutes(working,tmp_path):
    import fcntl,os,subprocess,sys,time
    _,service=working;job=admit(service,'close');ready=tmp_path/'child-ready'
    script=tmp_path/'short_child.py'
    script.write_text('from pathlib import Path\nimport time\nPath('+repr(str(ready))+').write_text("started")\ntime.sleep(2)\n')
    code=('from keystone import operation\n'
          'operation.ENTRYPOINTS["workspace-saved"]=['+repr(str(script))+']\n'
          'from keystone.workspace.worker import main\n'
          'raise SystemExit(main(["--workspace",'+repr(str(service.catalog.root))+',"--jobs-dir",'+repr(str(service.store.root))+',"--once"]))')
    process=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        until=time.monotonic()+15
        while not ready.exists() and process.poll() is None and time.monotonic()<until:time.sleep(.03)
        assert ready.exists()
        process.kill();process.wait(timeout=5)
        fd=os.open(service.store.root/'worker.lock',os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(fd)
        until=time.monotonic()+10
        replacement=None
        while time.monotonic()<until:
            try:
                replacement=worker_store(service);break
            except Exception:time.sleep(.05)
        assert replacement is not None
        try:
            replacement.interrupt_running()
            assert service.get(job['job_id'])['job']['status']=='outcome_unknown'
            assert run_one(replacement)==(False,False)
            assert ready.read_text()=='started'
        finally:replacement.close()
    finally:
        if process.poll() is None:process.kill();process.wait()


def test_old_queued_snapshot_does_not_rerun_an_already_registered_identity(working,tmp_path,monkeypatch):
    import keystone.workspace.worker as worker
    workspace,service=working;job=admit(service,'close')
    old=service.store.path.read_bytes();store=worker_store(service)
    try:
        run_one(store)
        assert service.get(job['job_id'])['job']['status']=='review_required'
    finally:store.close()
    service.close()
    restored=tmp_path/'old-control';restored.mkdir(mode=0o700)
    ledger=restored/'jobs.sqlite3';ledger.write_bytes(old);ledger.chmod(0o600)
    opened=Admission(workspace,restored,ORIGIN);replacement=worker_store(opened)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(worker.operation,'execute',lambda *a,**k:pytest.fail('Already registered work was repeated'))
            run_one(replacement)
        assert opened.get(job['job_id'])['job']['status']=='outcome_unknown'
        assert len(Catalog(workspace).load().runs)==6
        assert not (restored/'operations').exists()
    finally:replacement.close();opened.close()
