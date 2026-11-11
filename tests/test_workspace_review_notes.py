"""Durable analyst notes: exact source scope, retries, atomicity and restoration."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.onboarding.service import PrivateAdmission
from keystone.workspace.onboarding.store import InputStore
from keystone.workspace.onboarding.recovery import restore_private
from keystone.workspace.review.notes import NoteRequest,Note,NotesStore,validate_notes
from keystone.workspace.review.contracts import Snapshot
from keystone.workspace.report_views.values import digest
from keystone.workspace.worker import run_one
from test_workspace_onboarding import session,headers,ORIGIN
from test_workspace_local_research import ingest,request
from test_workspace_fresh_close import worker
from test_workspace_private_recovery import capture
from test_native_reports import hashes,legacy,native

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(session):
    session.review_notes_enabled=True
    _,_,permission,version=ingest(session)
    job,_=session.submit(request(version),'note-test-source')
    with worker(session) as store:assert run_one(store)==(True,False)
    run_id='result-'+job['job_id'][4:]
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    snapshot=api.get(f'/api/runs/{run_id}/review',headers=headers(session)).json()['snapshot']
    return session,api,snapshot,permission


def body(snapshot,**updates):
    target=next(t for t in snapshot['targets'] if t['kind']=='review_issue')
    return dict(schema_version=1,snapshot_id=snapshot['snapshot_id'],target_id=target['id'],target_sha256=target['scope_sha256'],
        reviewer_label='Fictional analyst',note_type='question',text='Which source establishes this financial definition?',
        evidence_refs=target['evidence_refs'][:1],**updates)


def url(snapshot):return '/api/runs/'+snapshot['binding']['run_id']+'/review-notes'


def post(ready,value=None,key='note-request-0001'):
    session,api,snapshot,_=ready
    return api.post(url(snapshot),json=value or body(snapshot),headers=headers(session,key))


def test_notes_are_immutable_source_bound_and_retry_exactly_once(ready):
    session,api,snapshot,_=ready
    before=hashes(session.catalog.root);inputs=hashes(session.inputs.root/'inputs')
    first=post(ready);assert first.status_code==201,first.text
    saved=first.json()['note'];assert saved['request']['snapshot_id']==snapshot['snapshot_id']
    assert saved['binding']==snapshot['binding'] and saved['identity_assurance']=='local_operator_unverified'
    assert saved['financial_approval'] is False and saved['sequence']==1
    replay=post(ready);assert replay.status_code==200 and replay.json()['replayed'] is True
    assert replay.json()['note']==saved
    value=body(snapshot);value['text']='Changed request under the original key'
    assert post(ready,value).status_code==409
    book=api.get(url(snapshot),headers=headers(session));assert book.status_code==200
    assert book.json()['notes']==[saved] and book.json()['analyst_review']=='in_review'
    assert book.json()['decision_count']==0 and book.json()['financial_approval'] is False
    assert api.get('/api/runs/'+snapshot['binding']['run_id']+'/review',headers=headers(session)).json()['snapshot']==snapshot
    assert hashes(session.catalog.root)==before and hashes(session.inputs.root/'inputs')==inputs
    head=api.head(url(snapshot),headers=headers(session));assert not head.content and head.status_code==200
    assert head.headers['content-length']==str(len(book.content)) and head.headers['cache-control']=='no-store'
    for method in ('put','patch','delete'):
        assert getattr(api,method)(url(snapshot),headers=headers(session)).status_code==405


def test_invalid_stale_or_approval_promoting_requests_never_persist(ready):
    session,api,snapshot,_=ready
    cases=[('schema_version',True),('financial_approval',True),('identity_assurance','authenticated'),
        ('snapshot_id','review-'+'0'*64),('target_id','missing'),('target_sha256','0'*64),
        ('reviewer_label',' '),('text','\t'),('text','x'*2001),('note_type','approved'),
        ('evidence_refs',['unknown-source']),('evidence_refs',[snapshot['targets'][0]['evidence_refs'][0]]*2),
        ('recorded_at','2020-01-01T00:00:00Z'),('id','note-'+'1'*32)]
    for index,(field,value) in enumerate(cases):
        data=body(snapshot);data[field]=value
        response=post(ready,data,'invalid-note-'+str(index))
        assert response.status_code in {409,422},(field,response.text)
    assert api.get(url(snapshot),headers=headers(session)).json()['notes']==[]


def test_note_reads_and_writes_require_current_access_and_permissions(ready):
    session,api,snapshot,permission=ready
    assert api.get(url(snapshot)).status_code==403
    assert api.post(url(snapshot),json=body(snapshot)).status_code==403
    assert api.get(url(snapshot),headers={**headers(session),'Origin':'https://example.com'}).status_code==403
    assert post(ready).status_code==201
    session.inputs.revoke_permission(permission['id'],'Fictional source permission withdrawn')
    assert api.get(url(snapshot),headers=headers(session)).status_code==403
    assert post(ready).status_code==403


def test_notes_can_be_read_without_enabling_new_writes(ready):
    session,api,snapshot,_=ready
    assert post(ready).status_code==201
    session.review_notes_enabled=False
    readonly=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    book=readonly.get(url(snapshot),headers=headers(session)).json()
    assert book['notes_enabled'] is False and len(book['notes'])==1
    assert readonly.post(url(snapshot),json=body(snapshot),headers=headers(session,'disabled-note')).status_code==405


def test_missing_receipt_write_rolls_back_the_note_and_preserves_retry(ready,monkeypatch):
    session,api,snapshot,_=ready;original=session.inputs._put
    def fail_receipt(con,kind,ident,value):
        if kind=='review_note_receipt':raise OSError('Injected receipt write failure')
        return original(con,kind,ident,value)
    with monkeypatch.context() as patch:
        patch.setattr(session.inputs,'_put',fail_receipt)
        assert post(ready).status_code==503
    assert api.get(url(snapshot),headers=headers(session)).json()['notes']==[]
    assert post(ready).status_code==201
    assert len(api.get(url(snapshot),headers=headers(session)).json()['notes'])==1


def test_concurrent_same_key_requests_share_one_note(ready):
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda _:post(ready),range(4)))
    assert all(r.status_code in {200,201} for r in responses)
    assert sum(r.status_code==201 for r in responses)==1
    assert len({r.json()['note']['id'] for r in responses})==1


def test_capacity_does_not_remove_existing_notes(ready,monkeypatch):
    import keystone.workspace.review.notes as notes
    session,api,snapshot,_=ready;monkeypatch.setattr(notes,'MAX_RUN_NOTES',1)
    assert post(ready).status_code==201
    second=post(ready,key='note-request-0002');assert second.status_code==409
    assert len(api.get(url(snapshot),headers=headers(session)).json()['notes'])==1


def test_transport_bounds_and_duplicate_headers_fail_before_storage(ready):
    session,api,snapshot,_=ready
    assert api.get(url(snapshot)+'?approve=true',headers=headers(session)).status_code==422
    assert api.post(url(snapshot),json=body(snapshot),headers=headers(session)).status_code==422
    assert api.post(url(snapshot),content=b'x'*16385,headers=headers(session,'oversized-note')).status_code==413
    assert api.post(url(snapshot),content=b'{}',headers={**headers(session,'wrong-media'),'Content-Type':'text/plain'}).status_code==415
    repeated=list(headers(session,'repeated-header').items())+[('Idempotency-Key','another-key')]
    assert api.post(url(snapshot),json=body(snapshot),headers=repeated).status_code==422
    assert api.get(url(snapshot),headers=headers(session)).json()['notes']==[]


def test_changed_review_scope_keeps_old_notes_separate(ready):
    session,api,snapshot,_=ready;assert post(ready).status_code==201
    changed=deepcopy(snapshot);changed['targets'][0]['detail']='A newly defined review subject.'
    target=changed['targets'][0];target['scope_sha256']=digest({k:v for k,v in target.items() if k!='scope_sha256'})
    changed['snapshot_id']='review-'+digest({k:v for k,v in changed.items() if k!='snapshot_id'})
    Snapshot.model_validate(changed)
    book=NotesStore(session.inputs).notebook(changed,enabled=True)
    assert book['notes']==[] and len(book['earlier_scope_notes'])==1
    assert book['analyst_review']=='not_started' and book['financial_approval'] is False
    replay,replayed=NotesStore(session.inputs).append(lambda:{'snapshot':changed},body(snapshot),'note-request-0001')
    assert replayed and replay['request']['snapshot_id']==snapshot['snapshot_id']
    with pytest.raises(c.InputError):NotesStore(session.inputs).append(lambda:{'snapshot':changed},body(snapshot),'old-scope-key')


def test_corrupt_receipts_block_read_and_backup_even_after_hash_replacement(ready):
    session,api,snapshot,_=ready;assert post(ready).status_code==201
    with session.inputs.write() as con:
        ident,raw=con.execute("SELECT id,value FROM objects WHERE kind='review_note_receipt'").fetchone()
        value=json.loads(raw);value['request_sha256']='0'*64;data=c.canonical(value)
        con.execute('UPDATE objects SET value=?,sha256=? WHERE id=?',(data.decode(),c.sha(data),ident))
    assert api.get(url(snapshot),headers=headers(session)).status_code==503
    with pytest.raises(c.InputError):session.inputs.backup_plan()


def test_notes_restore_with_their_original_bindings_and_replay_receipts(ready,tmp_path):
    session,api,snapshot,_=ready;original=post(ready).json()['note']
    before=hashes(session.catalog.root);snapshot_path=capture(session,tmp_path)
    restored=restore_private(snapshot_path,tmp_path/'restored')
    replacement=PrivateAdmission(restored,ORIGIN,enable_review_notes=True)
    try:
        restored_api=TestClient(create_app(replacement.catalog.root,admission=replacement,private=replacement),base_url=ORIGIN)
        book=restored_api.get(url(snapshot),headers=headers(replacement));assert book.status_code==200,book.text
        assert book.json()['notes']==[original]
        replay=restored_api.post(url(snapshot),json=body(snapshot),headers=headers(replacement,'note-request-0001'))
        assert replay.status_code==200 and replay.json()['note']==original
        assert hashes(replacement.catalog.root)==before
        validate_notes(InputStore(restored))
    finally:replacement.close()


def test_note_runtime_schemas_are_versioned_and_match_models(ready):
    saved=post(ready).json()['note']
    for name,model,value in [('note-request',NoteRequest,body(ready[2])),('note',Note,saved)]:
        schema=json.loads((ROOT/'keystone/workspace/review'/(name+'.schema.json')).read_text())
        assert schema==model.model_json_schema();Draft202012Validator(schema).validate(value)


def test_note_actions_never_execute_analysis_or_acquire_data(ready,monkeypatch):
    import socket
    from keystone.workspace.onboarding.research import calculate
    from keystone import operation
    def forbidden(*_a,**_k):pytest.fail('Note action attempted analysis or acquisition')
    monkeypatch.setattr(calculate,'calculate',forbidden)
    monkeypatch.setattr(operation,'execute',forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    session,api,snapshot,_=ready
    assert post(ready).status_code==201
    assert api.get(url(snapshot),headers=headers(session)).json()['decision_count']==0


@pytest.mark.parametrize('workflow',['research','monitoring','events','news','close'])
def test_private_saved_report_families_accept_only_notes_not_decisions(session,native,workflow):
    from test_workspace_onboarding import ingest as saved_ingest,submit
    session.review_notes_enabled=True
    version,*_=saved_ingest(session,native,workflow)
    job=submit(session,version)
    with worker(session) as store:assert run_one(store)==(True,False)
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    snapshot=api.get('/api/runs/result-'+job['job_id'][4:]+'/review',headers=headers(session)).json()['snapshot']
    response=api.post(url(snapshot),json=body(snapshot),headers=headers(session,'family-note-0001'))
    assert response.status_code==201,response.text
    assert api.get(url(snapshot),headers=headers(session)).json()['analyst_review']=='in_review'
    view=api.get('/api/runs/'+snapshot['binding']['run_id']+'/report-view',headers=headers(session)).json()
    assert view['state']['financial_approval'] is False and view['state']['evidence_gate']=='held_for_review'


def test_synthetic_catalogues_have_read_only_notebooks(native):
    api=TestClient(create_app(native),base_url=ORIGIN)
    for run in Catalog(native).load().runs:
        response=api.get('/api/runs/'+run.id+'/review-notes');assert response.status_code==200,response.text
        assert response.json()['notes_enabled'] is False and response.json()['notes']==[]
        assert api.post('/api/runs/'+run.id+'/review-notes',json={}).status_code==405
