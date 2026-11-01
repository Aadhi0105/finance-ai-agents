"""Real HTTP admission, durable duplicate control, source pins and safe local storage."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3

from fastapi.testclient import TestClient
import pytest

from keystone.maintenance import gate, control_write_gate
from keystone.workspace.api import create_app
from keystone.workspace.job_contract import JobError
from keystone.workspace.jobs import Admission
from test_native_reports import legacy, native, hashes

ORIGIN = 'http://127.0.0.1:8765'
REQUEST = dict(schema_version=1, workflow='research', source_run_id='research-example', timeout_seconds=120)


@pytest.fixture
def admission(native, tmp_path):
    service = Admission(native, tmp_path / 'controls', ORIGIN)
    yield service
    service.close()


@pytest.fixture
def client(native, admission):
    with TestClient(create_app(native, admission=admission), base_url=ORIGIN) as client:
        yield client


def headers(service, key='request-one'):
    return {'Origin': ORIGIN, 'Authorization': 'Bearer ' + service.token,
            'Idempotency-Key': key, 'Sec-Fetch-Site': 'same-origin'}


def submit(client, service, request=None, key='request-one'):
    return client.post('/api/jobs', json=REQUEST if request is None else request, headers=headers(service, key))


def test_default_server_stays_read_only_without_creating_control_state(native, tmp_path):
    before = hashes(native)
    with TestClient(create_app(native), base_url=ORIGIN) as client:
        capability = client.get('/api/execution').json()
        assert not capability['admission_enabled'] and not capability['worker_enabled']
        assert capability['workflows'] == []
        assert client.post('/api/jobs', json=REQUEST).status_code == 405
        assert client.get('/api/jobs').status_code == 404
        assert client.get('/api/workspace').json()['read_only']
    assert hashes(native) == before


def test_all_five_profiles_are_pinned_and_never_execute(client, admission, native, monkeypatch):
    import keystone.operation
    def forbidden(*a, **k):
        pytest.fail('Admission executed an agent or acquired external data')
    monkeypatch.setattr(keystone.operation, 'execute', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    before = hashes(native)
    runs = client.get('/api/runs').json()['runs']
    for run in runs:
        response = submit(client, admission, dict(workflow=run['workflow'], source_run_id=run['id']), 'profile-' + run['workflow'])
        assert response.status_code == 202, response.text
        body = response.json(); job = body['job']
        assert not body['replayed'] and job['status'] == 'queued'
        assert not any(job[k] for k in ('worker_enabled', 'live_data_enabled', 'paid_models_enabled', 'financial_approval'))
        assert job['max_requests'] == 12 and job['max_output_tokens'] == 48000
        assert job['source']['artifacts'] == [{k:v for k,v in a.items() if k != 'url'} for a in run['artifacts']]
        assert job['source']['primary_artifact_id'] == run['native_view']['source_artifact_ids'][0]
        assert job['input_validation'] == 'matched_at_admission'
        saved = client.get(response.headers['location'], headers=headers(admission))
        assert saved.status_code == 200 and saved.json()['job'] == job
        assert saved.json()['events'] == [{'event': 'admitted', 'created_at': job['created_at']}]
        assert str(native) not in response.text and str(admission.store.root) not in response.text
        assert admission.token not in response.text
    assert hashes(native) == before
    assert len(client.get('/api/jobs', headers=headers(admission)).json()['jobs']) == 5
    assert not (admission.store.root/'operations').exists()


@pytest.mark.parametrize('change', [
    {'command':'anything'}, {'arguments':['--live']}, {'input_path':'/private/input'},
    {'output_dir':'/tmp/output'}, {'allow_live_data':True}, {'allow_paid':True},
    {'financial_approval':True}, {'profile':'other'}, {'operation_id':'reuse'},
    {'max_requests':100}, {'schema_version':True}, {'schema_version':2},
    {'timeout_seconds':True}, {'timeout_seconds':'60'}, {'timeout_seconds':0},
    {'timeout_seconds':601}, {'workflow':'agent1'}, {'source_run_id':'../source'},
])
def test_request_cannot_expand_execution_scope(client, admission, change):
    request = {**REQUEST, **change}
    response = submit(client, admission, request)
    assert response.status_code == 422 and response.json()['error']['code'] == 'job_request_invalid'
    assert client.get('/api/jobs', headers=headers(admission)).json()['jobs'] == []


@pytest.mark.parametrize('payload', [[], None, 'command', {}, {'workflow':'news','source_run_id':'research-example'},
                                         {'workflow':'research','source_run_id':'missing'}])
def test_unknown_or_mismatched_source_is_refused(client, admission, payload):
    response = client.post('/api/jobs', content=json.dumps(payload),
                           headers={**headers(admission), 'Content-Type':'application/json'})
    assert response.status_code in (422,503)
    assert not client.get('/api/jobs', headers=headers(admission)).json()['jobs']


@pytest.mark.parametrize('change', [
    {'Authorization':None}, {'Authorization':'Bearer invalid'}, {'Origin':None},
    {'Origin':'null'}, {'Origin':'http://localhost:8765'}, {'Origin':'https://attacker.example'},
    {'Host':'localhost:8765'}, {'Host':'127.0.0.1:9999'},
    {'Sec-Fetch-Site':'cross-site'}, {'Sec-Fetch-Site':'same-site'}, {'Sec-Fetch-Site':'none'},
])
def test_write_requires_exact_origin_and_private_token(client, admission, change):
    values=headers(admission)
    for key,value in change.items():
        if value is None: values.pop(key,None)
        else: values[key]=value
    response=client.post('/api/jobs',json=REQUEST,headers=values)
    assert response.status_code==403
    assert admission.token not in response.text
    assert not client.get('/api/jobs',headers=headers(admission)).json()['jobs']


def test_jobs_and_reads_require_token_and_never_serve_control_files(client, admission):
    created=submit(client,admission); location=created.headers['location']
    for url in ['/api/jobs',location]:
        assert client.get(url).status_code==403
        assert client.head(url).status_code==403
        assert client.get(url,headers={'Authorization':'Bearer '+admission.token}).status_code==200
        head=client.head(url,headers=headers(admission));assert head.status_code==200 and not head.content
        assert head.headers['cache-control']=='no-store'
    for url in ['/access-token.key','/jobs.sqlite3','/api/runs/research-example/files/access-token.key']:
        assert client.get(url).status_code==404
    for method in ['put','patch','delete','options']:
        assert getattr(client,method)('/api/jobs',headers=headers(admission)).status_code==405
    assert client.post(location,headers=headers(admission)).status_code==405
    assert client.post('/api/runs',headers=headers(admission)).status_code==405


def test_body_bounds_duplicate_json_and_headers_are_checked_before_admission(client, admission):
    values={**headers(admission),'Content-Type':'application/json'}
    for raw in [b'{"workflow":"research","workflow":"news"}',b'{"timeout_seconds":NaN}',b'{bad',b'']:
        assert client.post('/api/jobs',content=raw,headers=values).status_code==422
    assert client.post('/api/jobs',content=b'x'*4097,headers=values).status_code==413
    assert client.post('/api/jobs',content=iter([b'x'*2048,b'x'*2049]),headers=values).status_code==413
    for content_type in ['text/plain','application/x-www-form-urlencoded']:
        assert client.post('/api/jobs',content=b'{}',headers={**values,'Content-Type':content_type}).status_code==415
    assert client.post('/api/jobs',content=b'{}',headers={**values,'Content-Encoding':'gzip'}).status_code==415
    for duplicated in ['Authorization','Origin','Idempotency-Key','Content-Type','Content-Length']:
        pairs=list(values.items())+[(duplicated, values.get(duplicated,'2'))]
        assert client.post('/api/jobs',content=b'{}',headers=pairs).status_code in (403,415,422)
    assert client.post('/api/jobs?command=hidden',json=REQUEST,headers=values).status_code==422
    assert client.post('/api/jobs',json=REQUEST,headers={k:v for k,v in headers(admission).items() if k!='Idempotency-Key'}).status_code==422


def test_idempotent_replay_is_stable_and_changed_request_conflicts(client, admission):
    first=submit(client,admission); second=submit(client,admission)
    assert first.status_code==202 and second.status_code==200
    assert second.json()['replayed'] and first.json()['job']==second.json()['job']
    assert first.headers['location']==second.headers['location']
    assert submit(client,admission,{**REQUEST,'timeout_seconds':119}).status_code==409
    with sqlite3.connect(admission.store.path) as con:
        assert con.execute('SELECT count(*) FROM jobs').fetchone()[0]==1
        assert con.execute('SELECT count(*) FROM events').fetchone()[0]==1


def test_concurrent_same_key_has_one_durable_job_and_operation(client, admission):
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses=list(pool.map(lambda _:submit(client,admission),range(6)))
    assert [r.status_code for r in responses].count(202)==1
    assert all(r.status_code in (200,202) for r in responses)
    assert len({r.json()['job']['operation_id'] for r in responses})==1
    assert len(client.get('/api/jobs',headers=headers(admission)).json()['jobs'])==1


def test_restart_preserves_identity_and_rotates_access(native, admission):
    original_root=admission.store.root;old_token=admission.token
    with TestClient(create_app(native,admission=admission),base_url=ORIGIN) as client:
        first=submit(client,admission).json()['job']
    replacement=Admission(native,original_root,ORIGIN)
    with TestClient(create_app(native,admission=replacement),base_url=ORIGIN) as client:
        assert replacement.token!=old_token
        assert client.get('/api/jobs',headers={'Authorization':'Bearer '+old_token}).status_code==403
        replay=submit(client,replacement)
        assert replay.status_code==200 and replay.json()['job']==first
        assert client.get('/api/jobs/'+first['job_id'],headers=headers(replacement)).json()['events'][0]['event']=='admitted'


def test_capacity_is_bounded_but_replay_remains_available(client, admission, monkeypatch):
    import keystone.workspace.job_store as module
    monkeypatch.setattr(module,'MAX_PENDING_JOBS',2)
    assert submit(client,admission,key='capacity-1').status_code==202
    assert submit(client,admission,key='capacity-2').status_code==202
    assert submit(client,admission,key='capacity-3').status_code==409
    assert submit(client,admission,key='capacity-1').status_code==200


def test_job_pagination_has_no_duplicate_or_missing_rows(client, admission):
    ids=[submit(client,admission,key='page-key-'+str(i)).json()['job']['job_id'] for i in range(3)]
    page=client.get('/api/jobs?limit=2',headers=headers(admission)).json()
    assert [j['job_id'] for j in page['jobs']]==list(reversed(ids[1:]))
    tail=client.get('/api/jobs?limit=2&before='+page['next_cursor'],headers=headers(admission)).json()
    assert [j['job_id'] for j in tail['jobs']]==ids[:1] and tail['next_cursor'] is None
    for query in ['limit=0','limit=101','limit=1&limit=2','status=running','before=bad']:
        assert client.get('/api/jobs?'+query,headers=headers(admission)).status_code==422


def test_admission_participates_in_backup_and_cli_mutation_gates(client, admission):
    for exclusive in [True,False]:
        with gate(exclusive=exclusive):
            response=submit(client,admission)
            assert response.status_code==503 and response.json()['error']['code']=='job_control_busy'
    assert submit(client,admission).status_code==202


def test_audit_and_job_commit_atomically_or_both_roll_back(client, admission):
    with admission.store._write() as con:
        con.execute("CREATE TRIGGER refuse_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'private-disk-failure'); END;")
    refused=submit(client,admission)
    assert refused.status_code==503 and 'private-disk-failure' not in refused.text
    with sqlite3.connect(admission.store.path) as con:
        assert con.execute('SELECT count(*) FROM jobs').fetchone()[0]==0
        assert con.execute('SELECT count(*) FROM events').fetchone()[0]==0
    with admission.store._write() as con:con.execute('DROP TRIGGER refuse_event')
    assert submit(client,admission).status_code==202


def test_private_files_and_same_store_second_server_refusal(native, admission):
    before=admission.token_file.read_bytes()
    assert not admission.store.root.stat().st_mode&0o077
    for p in [admission.store.path,admission.token_file,admission.store.root/'session.lock']:
        assert not p.stat().st_mode&0o077
    with pytest.raises(JobError):Admission(native,admission.store.root,ORIGIN)
    assert admission.token_file.read_bytes()==before


@pytest.mark.parametrize('unsafe',['inside','ancestor','directory-link','public-directory','database-link','token-link','hardlink'])
def test_unsafe_control_paths_are_refused_without_touching_targets(native,tmp_path,unsafe):
    directory=tmp_path/'controls';directory.mkdir(mode=0o700)
    target=tmp_path/'preserve';target.write_text('preserve');target.chmod(0o600)
    if unsafe=='inside':directory=Path(native)/'must-not-create'
    elif unsafe=='ancestor':directory=Path(native).parent
    elif unsafe=='directory-link':
        directory.rmdir();directory.symlink_to(target)
    elif unsafe=='public-directory':directory.chmod(0o755)
    elif unsafe=='database-link':(directory/'jobs.sqlite3').symlink_to(target)
    elif unsafe=='token-link':(directory/'access-token.key').symlink_to(target)
    elif unsafe=='hardlink':(directory/'jobs.sqlite3').hardlink_to(target)
    with pytest.raises(JobError):Admission(native,directory,ORIGIN)
    assert target.read_text()=='preserve'
    assert not (Path(native)/'must-not-create').exists()


def test_existing_ledger_cannot_be_silently_bound_to_another_workspace(native,admission,tmp_path):
    directory=admission.store.root;token=admission.token_file.read_bytes();admission.close()
    other=tmp_path/'different';shutil.copytree(native,other)
    with pytest.raises(JobError):Admission(other,directory,ORIGIN)
    assert (directory/'access-token.key').read_bytes()==token


def test_changed_source_blocks_new_job_but_preserves_prior_receipt(native,tmp_path):
    workspace=tmp_path/'saved';shutil.copytree(native,workspace)
    service=Admission(workspace,tmp_path/'controls',ORIGIN)
    with TestClient(create_app(workspace,admission=service),base_url=ORIGIN) as client:
        original=submit(client,service).json()['job']
        model=workspace/'runs/research-example/model.json';model.write_bytes(model.read_bytes()+b'\n')
        refused=submit(client,service,key='changed-source')
        assert refused.status_code==503 and refused.json()['error']['code']=='job_source_unavailable'
        replay=submit(client,service)
        assert replay.status_code==200 and replay.json()['job']==original
        assert replay.json()['job']['input_validation']=='matched_at_admission'
        assert client.get('/api/jobs/'+original['job_id'],headers=headers(service)).status_code==200


def test_inconsistent_ledger_is_refused_without_raw_state(client,admission):
    first=submit(client,admission).json()['job']
    with admission.store._write() as con:
        con.execute('UPDATE jobs SET record_json=?',(json.dumps({'secret':'PRIVATE_DETAIL'}),))
    response=client.get('/api/jobs/'+first['job_id'],headers=headers(admission))
    assert response.status_code==503 and 'PRIVATE_DETAIL' not in response.text
    assert str(admission.store.root) not in response.text


def test_sqlite_snapshot_and_restore_keep_duplicate_history(native,admission,tmp_path):
    from keystone.storage import snapshot,restore,verify
    from test_production_storage import plan_for,entry
    original,_=admission.submit(REQUEST,'backup-request')
    plan=plan_for([entry(admission.store.path,'jobs.sqlite3','file','logs')])
    saved=snapshot(plan,tmp_path/'snapshots',quiescent=True)
    assert set(verify(saved)['files'])=={'jobs.sqlite3'}
    restored=restore(saved,tmp_path/'restored')
    admission.close()
    replacement=Admission(native,restored,ORIGIN)
    try:
        replay,replayed=replacement.submit(REQUEST,'backup-request')
        assert replayed and replay==original
        assert replacement.get(original['job_id'])['events'][0]['event']=='admitted'
    finally:replacement.close()


def test_threaded_control_gate_does_not_change_environment_or_umask():
    before=dict(os.environ)
    mask=os.umask(0o022);os.umask(mask)
    with control_write_gate():assert dict(os.environ)==before
    after=os.umask(mask);os.umask(mask)
    assert after==mask and dict(os.environ)==before


def test_read_requests_do_not_change_job_ledger(client,admission):
    submit(client,admission)
    before=admission.store.path.read_bytes()
    result=client.get('/api/jobs',headers=headers(admission)).json()
    client.head('/api/jobs',headers=headers(admission))
    client.get('/api/jobs/'+result['jobs'][0]['job_id'],headers=headers(admission))
    assert admission.store.path.read_bytes()==before
    assert not admission.store.path.with_name('jobs.sqlite3-wal').exists()
    assert not admission.store.path.with_name('jobs.sqlite3-journal').exists()


def test_malformed_foreign_database_is_preserved_and_never_reinitialized(native,tmp_path):
    root=tmp_path/'foreign';root.mkdir(mode=0o700)
    database=root/'jobs.sqlite3'
    with sqlite3.connect(database) as con:
        con.execute('CREATE TABLE preserve (value TEXT)')
        con.execute('INSERT INTO preserve VALUES (?)',('keep',))
    database.chmod(0o600);before=database.read_bytes()
    with pytest.raises(JobError):Admission(native,root,ORIGIN)
    assert database.read_bytes()==before
    assert not (root/'access-token.key').exists()


def test_control_tree_backup_refuses_token_and_ledger_only_backup_is_explicit(admission,tmp_path):
    from keystone.storage import snapshot
    from test_production_storage import plan_for,entry
    with pytest.raises(ValueError,match='Secret/environment'):
        snapshot(plan_for([entry(admission.store.root)]),tmp_path/'snapshots',quiescent=True)
    assert admission.token_file.exists()


def test_cli_default_does_not_enable_admission_and_opt_in_stays_loopback(native,tmp_path,monkeypatch,capsys):
    import uvicorn
    from keystone.workspace.__main__ import main
    calls=[]
    def serve(app,**kwargs):
        calls.append(kwargs)
        with TestClient(app,base_url=ORIGIN) as client:
            caps=client.get('/api/execution').json()
            assert caps['admission_enabled']==(len(calls)==2)
            assert not caps['worker_enabled']
    monkeypatch.setattr(uvicorn,'run',serve)
    main(['serve','--workspace',str(native),'--port','8765'])
    assert not capsys.readouterr().out
    main(['serve','--workspace',str(native),'--port','8765','--enable-job-admission',
          '--jobs-dir',str(tmp_path/'controls')])
    output=json.loads(capsys.readouterr().out)
    assert output['job_admission_enabled'] and not output['job_worker_enabled']
    assert 'token' not in output and Path(output['token_file']).stat().st_mode&0o077==0
    assert all(c['host']=='127.0.0.1' and not c['proxy_headers'] and not c['access_log'] for c in calls)
    with pytest.raises(SystemExit):
        main(['serve','--workspace',str(native),'--jobs-dir',str(tmp_path/'unenabled')])
    assert not (tmp_path/'unenabled').exists()


def test_missing_used_ledger_is_not_recreated_as_an_empty_queue(native,admission):
    admission.submit(REQUEST,'preserve-history')
    directory=admission.store.root;token=admission.token_file.read_bytes()
    admission.close();(directory/'jobs.sqlite3').unlink()
    with pytest.raises(JobError):Admission(native,directory,ORIGIN)
    assert not (directory/'jobs.sqlite3').exists()
    assert (directory/'access-token.key').read_bytes()==token
