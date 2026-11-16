"""HTTP-to-worker acceptance with real supervised output and delivery-only recovery."""
import json
import time

from fastapi.testclient import TestClient
import pytest

from keystone.workspace.catalog import Catalog
from keystone.workspace.job_contract import JobError
from keystone.workspace.job_store import JobStore
from keystone.workspace.worker import recover_delivery, run_one
from keystone.workspace.jobs import Admission
from test_native_reports import legacy, native, hashes
from workspace_execution_scenarios import prepare, read_root, scenario_app, verify

ORIGIN = 'http://127.0.0.1:8765'


@pytest.fixture
def isolated(native, tmp_path):
    return prepare(native, tmp_path / 'acceptance')


def submit(api, service, family='close', key='acceptance-one', timeout=30):
    return api.post('/api/jobs', json=dict(workflow=family, source_run_id=family+'-example', timeout_seconds=timeout),
        headers={'Origin': ORIGIN, 'Authorization': 'Bearer '+service.token, 'Idempotency-Key':key})


def wait(service, ident, statuses, timeout=25):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        saved = service.get(ident)
        if saved['job']['status'] in statuses: return saved
        time.sleep(.04)
    pytest.fail('Expected job outcome did not arrive: '+saved['job']['status'])


def recovery(root, ident):
    store = JobStore(root/'control', root/'workspace', worker=True)
    try: return recover_delivery(store, ident)
    finally: store.close()


def test_acceptance_preparation_is_private_bounded_and_preserves_sources(native, tmp_path):
    before = hashes(native)
    root = prepare(native, tmp_path/'acceptance')
    assert hashes(native) == before and read_root(root) == root
    assert len(Catalog(root/'workspace').load().runs) == 5
    with pytest.raises(FileExistsError): prepare(native, root)
    with pytest.raises(ValueError): prepare(native, native/'inside')
    with pytest.raises(Exception): read_root(native)
    link = tmp_path/'alias'; link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError): read_root(link)


def test_real_http_profiles_keep_identity_downloads_and_review_gates_across_restart(isolated):
    app, service = scenario_app(isolated, ORIGIN)
    saved = []
    with TestClient(app, base_url=ORIGIN) as api:
        for family in ('research','monitoring','events','news','close'):
            response = submit(api, service, family, 'profile-'+family)
            assert response.status_code == 202
            ident = response.json()['job']['job_id']
            finished = wait(service, ident, {'review_required','failed','outcome_unknown'})
            assert finished['job']['status'] == 'review_required'
            replay = submit(api, service, family, 'profile-'+family)
            assert replay.status_code == 200 and replay.json()['job']['job_id'] == ident
            assert finished['job']['execution']['attempt'] == 1
            result = finished['job']['execution']['result']['run_id']
            view = api.get('/api/runs/'+result+'/report-view')
            assert view.status_code == 200 and view.json()['state']['financial_approval'] is False
            run = api.get('/api/runs/'+result).json()
            import hashlib
            for artifact in run['artifacts']:
                response = api.get(artifact['url'])
                assert response.status_code == 200
                assert hashlib.sha256(response.content).hexdigest() == artifact['sha256']
            saved.append(ident)
    restarted = Admission(isolated/'workspace', isolated/'control', ORIGIN)
    try:
        assert [restarted.get(i)['job']['execution']['attempt'] for i in saved] == [1]*5
        assert verify(isolated)['registered_runs'] == 10
        from keystone.workspace.api import create_app
        with TestClient(create_app(isolated/'workspace',admission=restarted),base_url=ORIGIN) as api:
            replay = submit(api,restarted,'research','profile-research')
            assert replay.status_code == 200 and replay.json()['job']['status'] == 'review_required'
            assert replay.json()['worker_enabled'] is False
            assert not replay.json()['next_action'].startswith('Queued')
    finally: restarted.close()


def test_lost_http_acknowledgement_keeps_one_admission_and_processing_attempt(isolated):
    app, service = scenario_app(isolated, ORIGIN, 'lost_ack')
    with TestClient(app, base_url=ORIGIN) as api:
        assert submit(api, service).status_code == 502
        assert len(service.store.list(25,None)['jobs']) == 1
        replay = submit(api, service)
        assert replay.status_code == 200 and replay.json()['replayed'] is True
        ident = replay.json()['job']['job_id']
        assert wait(service,ident,{'review_required','failed'})['job']['status'] == 'review_required'
        assert len(service.store.list(25,None)['jobs']) == 1
    receipt = verify(isolated)
    assert receipt['registered_runs'] == 6 and receipt['jobs'][0]['attempt'] == 1


@pytest.mark.parametrize('fault', ['delivery_before','delivery_after','crash_after_registration'])
def test_http_delivery_interruptions_recover_once_without_processing_again(isolated, fault, monkeypatch):
    app, service = scenario_app(isolated, ORIGIN, fault)
    with TestClient(app, base_url=ORIGIN) as api:
        ident = submit(api,service).json()['job']['job_id']
        if fault == 'crash_after_registration':
            until = time.monotonic()+25
            while service.worker_enabled and time.monotonic()<until: time.sleep(.04)
            assert not service.worker_enabled
            public = api.get('/api/jobs/'+ident,headers={'Authorization':'Bearer '+service.token}).json()['job']
            assert public['status'] == 'running' and public['recovery_required'] and public['result_url'] is None
            assert api.get('/api/execution').json()['worker_status'] == 'stopped'
        else:
            public = wait(service,ident,{'delivery_failed','failed'})['job']
            assert public['status'] == 'delivery_failed' and public['result_url'] is None
        assert len(Catalog(isolated/'workspace').load().runs) == (5 if fault=='delivery_before' else 6)
    from keystone.workspace import worker
    monkeypatch.setattr(worker.operation,'execute',lambda *a,**k:pytest.fail('Recovery repeated processing'))
    result = recovery(isolated, ident)
    assert result['job']['status'] == 'review_required' and result['job']['execution']['attempt'] == 1
    assert recovery(isolated, ident) == result
    assert verify(isolated)['registered_runs'] == 6


@pytest.mark.parametrize(('fault','status'), [('source_changed','source_changed'),('processing_failed','failed'),('timeout','outcome_unknown')])
def test_http_failures_remain_held_without_automatic_processing_retry(isolated, fault, status):
    app, service = scenario_app(isolated, ORIGIN, fault)
    with TestClient(app, base_url=ORIGIN) as api:
        response = submit(api,service,timeout=1 if fault=='timeout' else 30)
        ident = response.json()['job']['job_id']
        result = wait(service,ident,{status})['job']
        assert result['execution']['attempt'] == 1 and result['result_url'] is None
        replay = submit(api,service,timeout=1 if fault=='timeout' else 30)
        assert replay.status_code == 200 and replay.json()['job']['status'] == status
    with pytest.raises(Exception): recovery(isolated,ident)
    store = JobStore(isolated/'control',isolated/'workspace',worker=True)
    try:
        store.interrupt_running()
        assert run_one(store) == (False,False)
    finally: store.close()
    assert verify(isolated)['registered_runs'] == 5


def test_recovery_refuses_tampered_staging_then_recovers_the_preserved_original(isolated):
    app, service = scenario_app(isolated,ORIGIN,'delivery_before')
    with TestClient(app,base_url=ORIGIN) as api:
        ident = submit(api,service).json()['job']['job_id']
        assert wait(service,ident,{'delivery_failed'})['job']['execution']['attempt'] == 1
    path = isolated/'control/jobs'/ident/'result/catalog.json'
    original = path.read_bytes(); path.write_bytes(original+b'\n')
    with pytest.raises(JobError): recovery(isolated,ident)
    assert verify(isolated)['registered_runs'] == 5
    path.write_bytes(original)
    assert recovery(isolated,ident)['job']['status'] == 'review_required'
    assert verify(isolated)['registered_runs'] == 6


def test_recovery_marks_unfinished_orphan_unknown_and_refuses_missing_output(isolated, monkeypatch):
    service = Admission(isolated/'workspace',isolated/'control',ORIGIN)
    try:
        admitted, _ = service.submit(dict(workflow='close',source_run_id='close-example'),'orphan-one')
        store = JobStore(isolated/'control',isolated/'workspace',worker=True)
        try: store.claim_next()
        finally: store.close()
    finally: service.close()
    from keystone.workspace import worker
    monkeypatch.setattr(worker.operation,'execute',lambda *a,**k:pytest.fail('Orphan was reexecuted'))
    with pytest.raises(Exception): recovery(isolated,admitted['job_id'])
    receipt = verify(isolated)
    assert receipt['jobs'][0]['status'] == 'outcome_unknown'
    assert receipt['jobs'][0]['attempt'] == 1 and receipt['registered_runs'] == 5


def test_http_history_pages_cover_more_than_one_page_without_loss_or_overlap(isolated):
    app, service = scenario_app(isolated,ORIGIN,'processing_failed')
    with TestClient(app,base_url=ORIGIN) as api:
        identities = []
        for i in range(30):
            response = submit(api,service,key='history-'+str(i).zfill(3))
            assert response.status_code == 202
            ident = response.json()['job']['job_id']; identities.append(ident)
            assert wait(service,ident,{'failed'})['job']['execution']['attempt'] == 1
        headers = {'Authorization':'Bearer '+service.token}
        first = api.get('/api/jobs?limit=25',headers=headers).json()
        second = api.get('/api/jobs?limit=25&before='+first['next_cursor'],headers=headers).json()
        assert [j['job_id'] for j in first['jobs']+second['jobs']] == list(reversed(identities))
        assert second['next_cursor'] is None
        assert all(j['status']=='failed' for j in first['jobs']+second['jobs'])
    receipt = verify(isolated)
    assert len(receipt['jobs']) == 30 and receipt['registered_runs'] == 5


def test_job_read_survives_a_journal_removed_by_a_committing_worker(isolated, monkeypatch):
    from contextlib import contextmanager
    import threading
    import keystone.workspace.job_store as ledger
    service=Admission(isolated/'workspace',isolated/'control',ORIGIN)
    writer=JobStore(isolated/'control',isolated/'workspace',worker=True)
    committing,allow_commit,finished=threading.Event(),threading.Event(),threading.Event()
    real_connect=writer._connect;real_member=ledger.private_member
    reader_thread=threading.get_ident();errors=[];observed=[]
    journal=writer.path.with_name(writer.path.name+'-journal')
    @contextmanager
    def traced(*args,**kwargs):
        with real_connect(*args,**kwargs) as con:
            def trace(sql):
                if sql=='COMMIT':
                    committing.set()
                    allow_commit.wait(5)
            con.set_trace_callback(trace)
            yield con
    def probe(path,**kwargs):
        if path==journal and threading.get_ident()==reader_thread and committing.is_set():
            assert journal.exists()
            allow_commit.set()
            assert finished.wait(3) and not errors
            assert not journal.exists()
            observed.append('journal_removed_at_probe')
        return real_member(path,**kwargs)
    def advance():
        try:writer.claim_next()
        except Exception as error:errors.append(error)
        finally:finished.set()
    thread=None
    try:
        admitted,_=service.submit(dict(workflow='close',source_run_id='close-example'),'journal-removal-read')
        monkeypatch.setattr(writer,'_connect',traced)
        monkeypatch.setattr(ledger,'private_member',probe)
        thread=threading.Thread(target=advance);thread.start()
        assert committing.wait(3)
        result=service.get(admitted['job_id'])
        assert observed==['journal_removed_at_probe']
        assert result['job']['status']=='running' and result['job']['execution']['attempt']==1
        assert result['events'][-1]['event']=='claimed'
    finally:
        allow_commit.set()
        if thread is not None:thread.join(timeout=5)
        writer.close();service.close()


@pytest.mark.parametrize('suffix',['-journal','-wal','-shm'])
@pytest.mark.parametrize('fault',['mode','link','hardlink','directory','unreadable'])
def test_transient_companion_handling_still_refuses_unsafe_files(isolated,monkeypatch,suffix,fault):
    import os
    import keystone.workspace.job_store as ledger
    service=Admission(isolated/'workspace',isolated/'control',ORIGIN)
    try:
        admitted,_=service.submit(dict(workflow='close',source_run_id='close-example'),'unsafe-companion')
        member=service.store.path.with_name(service.store.path.name+suffix)
        if fault=='directory':member.mkdir(mode=0o700)
        elif fault=='link':member.symlink_to(isolated/'missing-target')
        else:
            member.write_bytes(b'Fictional unsafe companion');member.chmod(0o600)
            if fault=='mode':member.chmod(0o644)
            elif fault=='hardlink':os.link(member,isolated/'retained-link')
            else:
                real=ledger.private_member
                def unreadable(path,**kwargs):
                    if path==member:raise PermissionError('Fictional unreadable transaction file')
                    return real(path,**kwargs)
                monkeypatch.setattr(ledger,'private_member',unreadable)
        with pytest.raises(JobError,match='job_store_unavailable'):service.get(admitted['job_id'])
    finally:service.close()


def test_job_reads_keep_state_and_events_on_one_snapshot_during_a_worker_commit(isolated, monkeypatch):
    from contextlib import contextmanager
    import threading
    service = Admission(isolated/'workspace',isolated/'control',ORIGIN)
    writer = JobStore(isolated/'control',isolated/'workspace',worker=True)
    committing, finished = threading.Event(), threading.Event()
    original_connect = writer._connect
    errors = []
    @contextmanager
    def traced(*args, **kwargs):
        with original_connect(*args, **kwargs) as con:
            con.set_trace_callback(lambda sql: committing.set() if sql == 'COMMIT' else None)
            yield con
    monkeypatch.setattr(writer,'_connect',traced)
    def advance():
        try: writer.claim_next()
        except Exception as error: errors.append(error)
        finally: finished.set()
    thread = None
    try:
        admitted, _ = service.submit(dict(workflow='close',source_run_id='close-example'),'snapshot-read')
        ident = admitted['job_id']
        with service.store._connect(write=False) as read:
            assert read.execute('SELECT status FROM executions WHERE job_id=?',(ident,)).fetchone()[0] == 'queued'
            thread = threading.Thread(target=advance); thread.start()
            assert committing.wait(2)
            assert not finished.wait(.1)  # DELETE-journal commit waits for the reader's snapshot.
            assert read.execute('SELECT event FROM events WHERE job_id=? ORDER BY event_id DESC LIMIT 1',(ident,)).fetchone()[0] == 'admitted'
            assert service.store._execution(read,ident).status == 'queued'
        assert finished.wait(2) and not errors
        current = service.get(ident)
        assert current['job']['status'] == 'running' and current['events'][-1]['event'] == 'claimed'
    finally:
        if thread is not None: thread.join(timeout=3)
        writer.close(); service.close()


def test_worker_exit_cannot_mix_liveness_and_recovery_flags_in_one_response(isolated, monkeypatch):
    from starlette.datastructures import QueryParams
    service = Admission(isolated/'workspace',isolated/'control',ORIGIN)
    try:
        first, _ = service.submit(dict(workflow='close',source_run_id='close-example'),'liveness-first')
        service.submit(dict(workflow='close',source_run_id='close-example'),'liveness-second')
        store = JobStore(isolated/'control',isolated/'workspace',worker=True)
        try: store.claim_next()
        finally: store.close()
        service.worker_requested = True
        samples = [iter([True]+[False]*20)]
        monkeypatch.setattr(Admission,'worker_enabled',property(lambda self: next(samples[0])))
        result = service.list(QueryParams())
        assert result['worker_enabled'] is True
        assert all(job['worker_enabled'] is True and not job['recovery_required'] for job in result['jobs'])
        samples[0] = iter([True]+[False]*20)
        running = service.get(first['job_id'])['job']
        assert running['worker_enabled'] is True and running['recovery_required'] is False
        stopped = service.get(first['job_id'])['job']
        assert stopped['worker_enabled'] is False and stopped['recovery_required'] is True
    finally: service.close()
