"""3D recovery preserves financial evidence and never restarts queued work."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

from keystone import storage
from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog
from keystone.workspace.job_store import JobStore
from keystone.workspace.worker import run_one,recover_delivery
from keystone.workspace.onboarding import contracts as c,close_state
from keystone.workspace.onboarding.service import PrivateAdmission
from keystone.workspace.onboarding.store import InputStore
from keystone.workspace.onboarding.recovery import restore_private,release_restored_job,path_binding
from test_native_reports import legacy,native,hashes
from test_workspace_onboarding import session,ingest,submit,headers,ORIGIN
from test_workspace_fresh_close import ingest as fresh_ingest,correction,worker


def capture(session,tmp_path):
    session.close()
    inputs=InputStore(session.inputs.root)
    lease=JobStore(inputs.root/'control',inputs.root/'reports')
    try:
        plan=inputs.backup_plan()
        return storage.snapshot(plan,tmp_path/'snapshots',quiescent=True,
            verify_source=lambda: inputs.backup_plan()==plan or (_ for _ in ()).throw(ValueError('changed')))
    finally:lease.close()


def test_relocated_workspace_retains_report_and_holds_exact_queued_request(session,native,tmp_path):
    version,*_=ingest(session,native,'close')
    completed=submit(session,version)
    with worker(session) as store:assert run_one(store)==(True,False)
    queued=submit(session,version)
    immutable=session.store.immutable(queued['job_id']).model_dump()
    old_token=session.token
    original_inputs=hashes(session.inputs.root/'inputs');original_reports=hashes(session.catalog.root)
    snapshot=capture(session,tmp_path);before=storage.verify(snapshot)
    restored=restore_private(snapshot,tmp_path/'relocated')
    assert not (restored/'control/access-token.key').exists()
    assert hashes(restored/'inputs')==original_inputs and hashes(restored/'reports')==original_reports
    replacement=PrivateAdmission(restored,ORIGIN,enable_jobs=True)
    try:
        assert replacement.token!=old_token
        assert replacement.store.immutable(queued['job_id']).model_dump()==immutable
        assert replacement.get(queued['job_id'])['job']['restoration_hold'] is True
        with JobWorker(replacement) as store:
            assert run_one(store)==(False,False)
            assert store.get(queued['job_id'])['job']['execution']['attempt']==0
            record=release_restored_job(store,queued['job_id'],'Reviewed the exact restored synthetic version')
            assert record['processing_started'] is False
            assert run_one(store)==(True,False)
            assert run_one(store)==(False,False)
            assert store.get(queued['job_id'])['job']['execution']['attempt']==1
        with TestClient(create_app(replacement.catalog.root,admission=replacement,private=replacement),base_url=ORIGIN) as api:
            run='result-'+completed['job_id'][4:]
            assert api.get('/api/runs/'+run+'/report-view',headers=headers(replacement)).status_code==200
            assert api.get('/api/workspace',headers={'Authorization':'Bearer '+old_token}).status_code==403
        history=json.loads((restored/'control/restore-history.json').read_text())
        assert history[-1]['queued_jobs_held']==[queued['job_id']]
        assert history[-1]['workspace_id']==replacement.inputs.descriptor['id']
    finally:replacement.close()
    assert storage.verify(snapshot)==before
    assert hashes(session.inputs.root/'inputs')==original_inputs and hashes(session.catalog.root)==original_reports


class JobWorker:
    def __init__(self,session):self.session=session
    def __enter__(self):
        self.store=JobStore(self.session.store.root,self.session.catalog.root,worker=True)
        return self.store
    def __exit__(self,*args):self.store.close()


def test_empty_private_workspace_restores_fixed_empty_directories(session,tmp_path):
    snapshot=capture(session,tmp_path)
    restored=restore_private(snapshot,tmp_path/'empty-restored')
    with_session=PrivateAdmission(restored,ORIGIN)
    try:
        assert with_session.inputs.list('entity')['items']==[]
        assert with_session.catalog.load().runs==[]
        assert with_session.store.list(25,None)['jobs']==[]
    finally:with_session.close()


def test_running_request_becomes_unknown_without_being_dispatched(session,native,tmp_path):
    version,*_=ingest(session,native,'close');job=submit(session,version)
    with worker(session) as store:assert store.claim_next().job_id==job['job_id']
    snapshot=capture(session,tmp_path)
    restored=restore_private(snapshot,tmp_path/'interrupted')
    replacement=PrivateAdmission(restored,ORIGIN,enable_jobs=True)
    try:
        saved=replacement.get(job['job_id'])['job']
        assert saved['status']=='outcome_unknown' and saved['execution']['attempt']==1
        with JobWorker(replacement) as store:
            assert run_one(store)==(False,False)
            with pytest.raises(Exception):release_restored_job(store,job['job_id'],'Must not requeue an attempted operation')
        assert not (restored/'control/jobs'/job['job_id']).exists()
    finally:replacement.close()


def test_restored_fresh_close_and_correction_preserve_accounting_proofs(session,tmp_path,monkeypatch):
    entity,dataset,_,first=fresh_ingest(session)
    original=submit(session,first)
    with worker(session) as store:run_one(store)
    _,_,_,second=fresh_ingest(session,correction(),entity=entity,dataset=dataset)
    corrected=submit(session,second)
    with worker(session) as store:run_one(store)
    before=close_state.inspect(session.inputs,entity['id'])
    proof=session.inputs.object('close_commit','commit-'+original['job_id'])
    snapshot=capture(session,tmp_path)
    target=restore_private(snapshot,tmp_path/'restored-close')
    replacement=PrivateAdmission(target,ORIGIN,enable_jobs=True)
    try:
        assert close_state.inspect(replacement.inputs,entity['id'])==before
        import agent4.close
        monkeypatch.setattr(agent4.close,'execute_close',lambda *_a,**_k:pytest.fail('Restore recalculated accounting'))
        with JobWorker(replacement) as store:
            for job in (original,corrected):
                assert recover_delivery(store,job['job_id'])['job']['status']=='review_required'
            assert run_one(store)==(False,False)
        assert replacement.inputs.object('close_commit','commit-'+original['job_id'])==proof
        with close_state.open_state(close_state.state_path(replacement.inputs,entity['id'])) as state:
            assert state.con.execute('SELECT count(*) FROM a4_runs').fetchone()[0]==2
            assert state.get_run('close-june')['bundle']['bound_tree']['actual_cents']==6500
            assert state.get_run('close-june-corrected')['bundle']['bound_tree']['actual_cents']==7500
    finally:replacement.close()


@pytest.mark.parametrize('mutation',['corrupt','missing','extra','symlink','binding','report','permission'])
def test_incomplete_corrupt_or_semantically_wrong_snapshot_is_never_published(session,native,tmp_path,mutation):
    version,*_=ingest(session,native,'close');job=submit(session,version)
    with worker(session) as store:run_one(store)
    snapshot=capture(session,tmp_path)
    if mutation=='corrupt':(snapshot/'data/inputs.sqlite3').write_bytes(b'bad')
    elif mutation=='missing':(snapshot/'data/reports/catalog.json').unlink()
    elif mutation=='extra':(snapshot/'data/unlisted.json').write_text('{}')
    elif mutation=='symlink':
        p=snapshot/'data/reports/catalog.json';p.unlink();p.symlink_to(session.catalog.root/'catalog.json')
    else:
        # Resealed snapshots still need semantic identity/policy checks.
        manifest=storage.verify(snapshot)
        if mutation=='binding':
            name='control/jobs.sqlite3'
            with sqlite3.connect(snapshot/'data'/name) as con:
                con.execute("UPDATE metadata SET value='wrong' WHERE key='workspace'")
        elif mutation=='report':
            name='reports/catalog.json';raw=json.loads((snapshot/'data'/name).read_text());raw['runs'][0]['summary']='Changed registration'
            (snapshot/'data'/name).write_bytes(c.canonical(raw))
        else:
            name=next(n for n in manifest['files'] if n.startswith('permissions/') and n.endswith('/evidence'))
            (snapshot/'data'/name).write_bytes(b'Changed permission evidence')
        p=snapshot/'data'/name
        manifest['files'][name]={'size':p.stat().st_size,'sha256':storage.digest(p)}
        (snapshot/'manifest.json').write_text(storage.canonical(manifest))
        (snapshot/'manifest.sha256').write_text(storage.digest(snapshot/'manifest.json')+'\n')
    before=hashes(session.inputs.root)
    with pytest.raises(Exception):restore_private(snapshot,tmp_path/'refused')
    assert not (tmp_path/'refused').exists() and hashes(session.inputs.root)==before


def test_repeated_relocation_keeps_history_and_queued_holds(session,native,tmp_path):
    version,*_=ingest(session,native,'close');job=submit(session,version)
    first=restore_private(capture(session,tmp_path),tmp_path/'first')
    s=PrivateAdmission(first,ORIGIN)
    try:
        second_snapshot=capture(s,tmp_path/'second-snapshot')
        assert 'control/restore-history.json' in storage.verify(second_snapshot)['files']
    finally:s.close()
    second=restore_private(second_snapshot,tmp_path/'second')
    s=PrivateAdmission(second,ORIGIN)
    try:
        assert s.get(job['job_id'])['job']['restoration_hold']
        assert len(json.loads((second/'control/restore-history.json').read_text()))==2
    finally:s.close()


def test_queue_release_rechecks_permission_without_starting_or_replacing_job(session,native,tmp_path):
    version,_,_,_,policy,*_=ingest(session,native,'close');job=submit(session,version)
    target=restore_private(capture(session,tmp_path),tmp_path/'revoked')
    s=PrivateAdmission(target,ORIGIN)
    try:
        s.inputs.revoke_permission(policy['id'],'Fictional revocation after recovery')
        with JobWorker(s) as store:
            with pytest.raises(Exception):release_restored_job(store,job['job_id'],'Review after revocation')
            assert store.get(job['job_id'])['job']['restoration_hold']
            assert run_one(store)==(False,False)
    finally:s.close()


def test_queued_close_cannot_be_released_against_a_changed_accounting_predecessor(session,tmp_path):
    _,_,_,version=fresh_ingest(session)
    first=submit(session,version);second=submit(session,version)
    with worker(session) as store:
        # Only the first request executes; the second retains its original pin.
        assert run_one(store)==(True,False)
    restored=restore_private(capture(session,tmp_path),tmp_path/'stale-close')
    s=PrivateAdmission(restored,ORIGIN)
    try:
        with JobWorker(s) as store:
            with pytest.raises(Exception):release_restored_job(store,second['job_id'],'Inspect stale predecessor')
            assert store.get(second['job_id'])['job']['restoration_hold']
            assert run_one(store)==(False,False)
        assert s.get(first['job_id'])['job']['status']=='review_required'
    finally:s.close()


@pytest.mark.parametrize('fault',['copy','prepare','receipt','publish'])
def test_private_restore_failure_keeps_snapshot_and_existing_workspace_intact(session,tmp_path,monkeypatch,fault):
    snapshot=capture(session,tmp_path);before=storage.verify(snapshot)
    original=hashes(session.inputs.root)
    import keystone.workspace.onboarding.recovery as recovery
    def fail(*_a,**_k):raise OSError('Simulated destination failure')
    with monkeypatch.context() as patch:
        if fault=='copy':patch.setattr(storage,'copy_file',fail)
        if fault=='prepare':patch.setattr(recovery,'prepare_restore',fail)
        if fault=='receipt':patch.setattr(storage,'write_json',fail)
        if fault=='publish':patch.setattr(storage.os,'rename',fail)
        with pytest.raises(OSError):restore_private(snapshot,tmp_path/'failed-destination')
    assert not (tmp_path/'failed-destination').exists()
    assert hashes(session.inputs.root)==original and storage.verify(snapshot)==before


@pytest.mark.parametrize('after_registration',[False,True])
def test_committed_but_interrupted_close_restores_held_and_recovers_delivery_once(session,tmp_path,monkeypatch,after_registration):
    import keystone.workspace.job_delivery as delivery
    _,_,_,version=fresh_ingest(session);job=submit(session,version)
    replace=delivery._replace_inventory
    def interrupt(*args):
        if after_registration:replace(*args)
        raise OSError('Fictional delivery interruption')
    with worker(session) as store:
        with monkeypatch.context() as patch:
            patch.setattr(delivery,'_replace_inventory',interrupt)
            assert run_one(store)==(True,False)
        assert store.get(job['job_id'])['job']['status']=='delivery_failed'
    operation=session.inputs.root/'control/operations'/job['operation_id']/'operation.json'
    original_receipt=operation.read_bytes()
    snapshot=capture(session,tmp_path)
    import agent4.close
    monkeypatch.setattr(agent4.close,'execute_close',lambda *_a,**_k:pytest.fail('Recovery recalculated a committed close'))
    root=restore_private(snapshot,tmp_path/'interrupted-close')
    s=PrivateAdmission(root,ORIGIN,enable_jobs=True)
    try:
        assert s.get(job['job_id'])['job']['status']=='delivery_failed'
        with JobWorker(s) as store:
            assert run_one(store)==(False,False)
            first=recover_delivery(store,job['job_id'])
            second=recover_delivery(store,job['job_id'])
            assert first['job']==second['job']
            assert first['job']['status']=='review_required' and first['job']['execution']['attempt']==1
        assert len(s.catalog.load().runs)==1
        assert (root/'control/operations'/job['operation_id']/'operation.json').read_bytes()==original_receipt
    finally:s.close()
