"""Saved dispositions: independent states, retries, history and complete review flow."""
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
from keystone.workspace.onboarding.recovery import restore_private
from keystone.workspace.onboarding.service import PrivateAdmission
from keystone.workspace.review.contracts import Snapshot
from keystone.workspace.review.decisions import DecisionRequest, DecisionRecord, DecisionsStore, journal
from keystone.workspace.report_views.values import digest
from keystone.workspace.worker import run_one
from test_workspace_onboarding import session, headers, ORIGIN
from test_workspace_review_notes import ready, body as note_body
from test_workspace_review_corrections import ready as corrections_ready, body as correction_body, post as post_correction
from test_workspace_local_research import request
from test_workspace_fresh_close import worker
from test_workspace_private_recovery import capture
from test_native_reports import hashes, native, legacy

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def scope(ready):
    session,_,snapshot,permission=ready
    session.review_decisions_enabled=True
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    return session,api,snapshot,permission


def url(scope):return '/api/runs/'+scope[2]['binding']['run_id']+'/review-decisions'


def body(scope,disposition='acknowledged',sequence=0,target=None,**updates):
    snapshot=scope[2];target=target or snapshot['targets'][0]
    return {**dict(schema_version=1,snapshot_id=snapshot['snapshot_id'],target_id=target['id'],target_sha256=target['scope_sha256'],
        expected_sequence=sequence,disposition=disposition,reviewer_label='Fictional analyst',reason='Reviewed the retained evidence and its limitations.',
        note_ids=[],correction_ids=[]),**updates}


def post(scope,value=None,key='decision-request-0001'):
    return scope[1].post(url(scope),json=body(scope) if value is None else value,headers=headers(scope[0],key))


def history(scope,**query):return scope[1].get(url(scope),params=query,headers=headers(scope[0]))


def test_all_dispositions_and_all_acknowledged_keep_financial_restrictions(scope):
    session,api,snapshot,_=scope;before=hashes(session.catalog.root);inputs=hashes(session.inputs.root/'inputs')
    first=post(scope);assert first.status_code==201,first.text
    record=first.json()['record'];assert record['ordinal']==record['decision']['sequence']==1
    assert record['decision']['identity_assurance']=='local_operator_unverified' and record['financial_approval'] is False
    assert history(scope).json()['progress']['analyst_review']=='in_review'
    assert post(scope,body(scope,'changes_requested',1),'request-changes-key').status_code==201
    h=history(scope).json();assert h['progress']['analyst_review']=='changes_requested'
    assert post(scope,body(scope,'reopened',2),'reopen-item-key').status_code==201
    assert history(scope).json()['progress']['targets'][snapshot['targets'][0]['id']]=='pending'
    seq=3
    for target in snapshot['targets']:
        if target['availability']=='available':
            response=post(scope,body(scope,sequence=seq,target=target),'acknowledge-'+str(seq))
            assert response.status_code==201,response.text
            seq+=1
    h=history(scope).json()
    assert h['progress']['analyst_review']=='reviewed_with_limitations' and h['last_sequence']==seq
    assert h['progress']['financial_approval'] is False and h['progress']['evidence_gate']==snapshot['evidence_gate']
    assert post(scope,body(scope,'reopened',seq),'reopen-completed-review').status_code==201
    assert history(scope).json()['progress']['analyst_review']=='in_review'
    assert hashes(session.catalog.root)==before and hashes(session.inputs.root/'inputs')==inputs
    original=api.get('/api/runs/'+snapshot['binding']['run_id']+'/review',headers=headers(session)).json()
    assert original['snapshot']==snapshot and original['snapshot']['decisions_enabled'] is False
    assert original['progress']['decision_count']==0  # 5A remains a scope-only protocol.
    view=api.get('/api/runs/'+snapshot['binding']['run_id']+'/report-view',headers=headers(session)).json()
    assert view['state']['financial_approval'] is False and view['state']['evidence_gate']==snapshot['evidence_gate']


def test_same_request_replays_after_later_decisions_and_conflicts_if_changed(scope):
    original=post(scope).json()['record']
    assert post(scope,body(scope,'reopened',1),'later-reopen-key').status_code==201
    replay=post(scope);assert replay.status_code==200 and replay.json()['replayed'] is True
    assert replay.json()['record']==original and history(scope).json()['last_sequence']==2
    value=body(scope);value['reason']='Changed explanation'
    assert post(scope,value).status_code==409
    assert post(scope,body(scope,'changes_requested',0),'stale-new-tab-key').status_code==409
    assert history(scope).json()['last_sequence']==2


def test_repeated_states_and_unrecorded_or_initial_reopen_are_refused(scope):
    assert post(scope,body(scope,'reopened')).status_code==409
    assert post(scope).status_code==201
    assert post(scope,body(scope,sequence=1),'repeated-ack-key').status_code==409
    missing=next((t for t in scope[2]['targets'] if t['availability']=='not_recorded'),None)
    if missing:assert post(scope,body(scope,target=missing,sequence=1),'missing-subject-key').status_code==409


def test_invalid_stale_and_approval_promoting_bodies_never_persist(scope):
    cases=[('schema_version',True),('expected_sequence',True),('expected_sequence',1.0),('expected_sequence',-1),
        ('disposition','approved'),('reason',' '),('reason','x'*1601),('reviewer_label',''),('financial_approval',True),
        ('recorded_at','2020-01-01T00:00:00Z'),('identity_assurance','authenticated'),('snapshot_id','review-'+'0'*64),
        ('target_id','unknown'),('target_sha256','0'*64),('note_ids',['bad']),('correction_ids',['bad']),
        ('note_ids',['note-'+'a'*32]*2)]
    for i,(key,value) in enumerate(cases):
        request=body(scope);request[key]=value
        result=post(scope,request,'invalid-decision-'+str(i))
        assert result.status_code in {409,422},(key,result.text)
    assert history(scope).json()['last_sequence']==0


def test_decisions_require_access_origin_and_current_source_permission(scope):
    session,api,snapshot,permission=scope
    assert api.get(url(scope)).status_code==403
    assert api.post(url(scope),json=body(scope)).status_code==403
    assert api.get(url(scope),headers={**headers(session),'Origin':'https://example.com'}).status_code==403
    assert post(scope).status_code==201
    session.inputs.revoke_permission(permission['id'],'Fictional permission withdrawn')
    assert history(scope).status_code==403 and post(scope).status_code==403


def test_readonly_profile_preserves_decisions_without_enabling_writes(scope):
    assert post(scope).status_code==201
    session,_,_,_=scope;session.review_decisions_enabled=False
    readonly=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    h=readonly.get(url(scope),headers=headers(session)).json()
    assert h['decisions_enabled'] is False and h['last_sequence']==1
    assert readonly.post(url(scope),json=body(scope),headers=headers(session,'disabled-decision')).status_code==405


def test_atomic_receipt_rollback_and_same_key_concurrency(scope,monkeypatch):
    original=scope[0].inputs._put
    def fail(con,kind,ident,value):
        if kind=='review_decision_receipt':raise OSError('Injected receipt failure')
        return original(con,kind,ident,value)
    with monkeypatch.context() as patch:
        patch.setattr(scope[0].inputs,'_put',fail)
        assert post(scope).status_code==503
    assert history(scope).json()['last_sequence']==0
    with ThreadPoolExecutor(max_workers=3) as pool:responses=list(pool.map(lambda _:post(scope),range(3)))
    assert sorted(r.status_code for r in responses)==[200,200,201]
    assert len({r.json()['record']['id'] for r in responses})==1


def test_concurrent_new_keys_require_rechecking_the_history(scope):
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda key:post(scope,key=key),['concurrent-decision-one','concurrent-decision-two']))
    assert sorted(r.status_code for r in responses)==[201,409]
    assert history(scope).json()['last_sequence']==1


def test_saved_notes_and_corrections_attach_only_to_exact_review_item(corrections_ready):
    from keystone.workspace.review.notes import NotesStore
    session,_,snapshot,*_=corrections_ready;session.review_decisions_enabled=True
    note_request=note_body(snapshot)
    note,_=NotesStore(session.inputs).append(lambda:{'snapshot':snapshot},note_request,'decision-linked-note')
    target=next(t for t in snapshot['targets'] if t['id']==note_request['target_id'])
    value=correction_body(corrections_ready);value.update(target_id=target['id'],target_sha256=target['scope_sha256'])
    correction=post_correction(corrections_ready,value).json()['correction']
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    scope=(session,api,snapshot,None)
    value=body(scope,'changes_requested',target=target,note_ids=[note['id']],correction_ids=[correction['id']])
    assert post(scope,value).status_code==201
    h=history(scope).json();assert h['latest_events'][0]['note_ids']==[note['id']]
    assert h['latest_events'][0]['correction_ids']==[correction['id']]
    wrong=body(scope,sequence=1,note_ids=[note['id']]);assert post(scope,wrong,'wrong-item-link').status_code==409
    # Linking a correction is review evidence, not execution or an automatic resolution.
    assert len(session.catalog.load().runs)==1 and h['progress']['analyst_review']=='changes_requested'
    replacement_permission=corrections_ready[6]
    session.inputs.revoke_permission(replacement_permission['id'],'Fictional replacement permission withdrawn')
    assert history(scope).status_code==403


def test_changed_review_definition_retains_earlier_history_and_replay(scope):
    session,_,snapshot,_=scope;original=post(scope).json()['record']
    changed=deepcopy(snapshot);target=changed['targets'][0];target['detail']='A newly worded review subject.'
    target['scope_sha256']=digest({k:v for k,v in target.items() if k!='scope_sha256'})
    changed['snapshot_id']='review-'+digest({k:v for k,v in changed.items() if k!='snapshot_id'})
    Snapshot.model_validate(changed)
    store=DecisionsStore(session.inputs);context=lambda _:{'snapshot':changed}
    h=store.journal(changed,context,enabled=True)
    assert h['current_count']==0 and h['earlier_scope_count']==1
    assert h['progress']['analyst_review']=='not_started' and h['latest_events']==[]
    assert store.append(context,snapshot['binding']['run_id'],body(scope),'decision-request-0001')==(original,True)
    with pytest.raises(c.InputError):store.append(context,snapshot['binding']['run_id'],body(scope),'stale-scope-new-key')
    request=body(scope,sequence=1);request.update(snapshot_id=changed['snapshot_id'],target_sha256=target['scope_sha256'])
    saved,_=store.append(context,snapshot['binding']['run_id'],request,'new-scope-decision-key')
    assert saved['ordinal']==2 and saved['decision']['sequence']==1


def test_paginated_complete_history_has_stable_revision_and_no_silent_truncation(scope,monkeypatch):
    import keystone.workspace.review.decisions as module
    monkeypatch.setattr(module,'PAGE_SIZE',2)
    for i,action in enumerate(['acknowledged','reopened','changes_requested','acknowledged','reopened']):
        response=post(scope,body(scope,action,i),'paged-decision-'+str(i));assert response.status_code==201,response.text
    first=history(scope).json();assert [r['ordinal'] for r in first['records']]==[5,4]
    second=history(scope,before=first['page']['next_cursor'],revision=5).json()
    third=history(scope,before=second['page']['next_cursor'],revision=5).json()
    assert [r['ordinal'] for r in second['records']+third['records']]==[3,2,1]
    assert third['page']['next_cursor'] is None
    assert post(scope,body(scope,sequence=5),'sixth-decision-key').status_code==201
    assert history(scope,before=first['page']['next_cursor'],revision=5).status_code==409


def test_transport_and_capacity_bounds_preserve_existing_history(scope,monkeypatch):
    import keystone.workspace.review.decisions as module
    session,api,*_=scope
    assert history(scope,approve='yes').status_code==422
    assert api.post(url(scope),json=body(scope),headers=headers(session)).status_code==422
    assert api.post(url(scope),content=b'x'*16385,headers=headers(session,'oversized-decision')).status_code==413
    repeated=list(headers(session,'repeated-header-decision').items())+[('Idempotency-Key','second-header-key')]
    assert api.post(url(scope),json=body(scope),headers=repeated).status_code==422
    assert post(scope).status_code==201
    monkeypatch.setattr(module,'MAX_RUN_DECISIONS',1)
    assert post(scope,body(scope,'reopened',1),'capacity-decision-key').status_code==409
    assert history(scope).json()['last_sequence']==1
    head=api.head(url(scope),headers=headers(session));assert head.status_code==200 and not head.content
    for method in ('put','patch','delete'):assert getattr(api,method)(url(scope),headers=headers(session)).status_code==405


@pytest.mark.parametrize('kind',['review_decision','review_decision_receipt'])
def test_corrupt_records_refuse_delivery_and_backup_even_if_row_hash_replaced(scope,kind):
    assert post(scope).status_code==201
    session=scope[0]
    with session.inputs.write() as con:
        ident,raw=con.execute('SELECT id,value FROM objects WHERE kind=?',(kind,)).fetchone()
        value=json.loads(raw)
        if kind=='review_decision':value['decision']['disposition']='changes_requested'
        else:value['request_sha256']='0'*64
        data=c.canonical(value);con.execute('UPDATE objects SET value=?,sha256=? WHERE id=?',(data.decode(),c.sha(data),ident))
    assert history(scope).status_code==503
    with pytest.raises(c.InputError):session.inputs.backup_plan()


def test_restore_preserves_decisions_retries_and_reduced_states_without_execution(scope,tmp_path):
    first=post(scope).json()['record'];assert post(scope,body(scope,'changes_requested',1),'restored-changes-key').status_code==201
    path=capture(scope[0],tmp_path);root=restore_private(path,tmp_path/'restored')
    restored=PrivateAdmission(root,ORIGIN,enable_review_decisions=True)
    try:
        api=TestClient(create_app(restored.catalog.root,admission=restored,private=restored),base_url=ORIGIN)
        h=api.get(url(scope),headers=headers(restored)).json();assert h['progress']['analyst_review']=='changes_requested'
        replay=api.post(url(scope),json=body(scope),headers=headers(restored,'decision-request-0001'))
        assert replay.status_code==200 and replay.json()['record']==first
        assert len(restored.catalog.load().runs)==1 and h['last_sequence']==2
    finally:restored.close()


def test_full_correction_and_rerun_starts_a_separate_review(corrections_ready):
    session,_,snapshot,_,replacement,*_=corrections_ready;session.review_decisions_enabled=True
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    scope=(session,api,snapshot,None)
    assert post(scope,body(scope,'changes_requested')).status_code==201
    assert post_correction(corrections_ready).status_code==201
    assert history(scope).json()['progress']['analyst_review']=='changes_requested'
    job,_=session.submit(request(replacement),'decision-corrected-report')
    with worker(session) as store:assert run_one(store)==(True,False)
    h=api.get('/api/runs/result-'+job['job_id'][4:]+'/review-decisions',headers=headers(session)).json()
    assert h['last_sequence']==0 and h['progress']['analyst_review']=='not_started'
    assert h['financial_approval'] is False and history(scope).json()['last_sequence']==1


def test_schemas_match_runtime_and_decisions_do_not_execute_agents(scope,monkeypatch):
    saved=post(scope).json()['record']
    for name,model,value in [('disposition-request',DecisionRequest,body(scope)),('disposition-record',DecisionRecord,saved)]:
        schema=json.loads((ROOT/'keystone/workspace/review'/(name+'.schema.json')).read_text())
        assert schema==model.model_json_schema();Draft202012Validator(schema).validate(value)
    import socket
    from keystone import operation
    from keystone.workspace.onboarding.research import calculate
    def forbidden(*_a,**_k):pytest.fail('Review decision attempted acquisition or financial execution')
    monkeypatch.setattr(socket.socket,'connect',forbidden);monkeypatch.setattr(operation,'execute',forbidden);monkeypatch.setattr(calculate,'calculate',forbidden)
    assert post(scope,body(scope,'reopened',1),'offline-review-key').status_code==201
    assert history(scope).json()['financial_approval'] is False


@pytest.mark.parametrize('workflow',['research','monitoring','events','news','close'])
def test_saved_workflow_families_record_dispositions_without_promoting_gates(session,native,workflow):
    from test_workspace_onboarding import ingest,submit
    session.review_decisions_enabled=True
    version,*_=ingest(session,native,workflow);job=submit(session,version)
    with worker(session) as store:assert run_one(store)==(True,False)
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    root='/api/runs/result-'+job['job_id'][4:]
    snapshot=api.get(root+'/review',headers=headers(session)).json()['snapshot']
    scope=(session,api,snapshot,None);assert post(scope).status_code==201
    h=history(scope).json();assert h['progress']['analyst_review']=='in_review' and h['financial_approval'] is False
    assert api.get(root+'/report-view',headers=headers(session)).json()['state']['evidence_gate']=='held_for_review'


def test_synthetic_catalogues_have_explicit_readonly_journals(native):
    api=TestClient(create_app(native),base_url=ORIGIN)
    for run in Catalog(native).load().runs:
        path='/api/runs/'+run.id+'/review-decisions'
        h=api.get(path);assert h.status_code==200,h.text
        assert h.json()['decisions_enabled'] is False and h.json()['current_count']==0
        assert api.post(path,json={}).status_code==405 and api.get(path+'?revision=0').status_code==422


@pytest.mark.parametrize('workflow',['monitoring','events','news','close'])
def test_fresh_workflows_review_without_rewriting_calculations_or_accounting(session,workflow):
    if workflow=='close':
        from test_workspace_fresh_close import ingest
        from test_workspace_onboarding import submit
        *_,version=ingest(session)
        job=submit(session,version)
    else:
        from test_workspace_local_workflows import ingest,request
        version,_=ingest(session,workflow)
        job,_=session.submit(request(version),'fresh-decision-'+workflow)
    with worker(session) as store:assert run_one(store)==(True,False)
    session.review_decisions_enabled=True
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    root='/api/runs/result-'+job['job_id'][4:]
    snapshot=api.get(root+'/review',headers=headers(session)).json()['snapshot']
    scope=(session,api,snapshot,None)
    reports=hashes(session.catalog.root);accounting=hashes(session.inputs.root/'accounting')
    assert post(scope,body(scope,'changes_requested')).status_code==201
    assert post(scope,body(scope,sequence=1),'fresh-reviewed-key').status_code==201
    assert post(scope,body(scope,'reopened',2),'fresh-reopened-key').status_code==201
    assert history(scope).json()['progress']['analyst_review']=='in_review'
    assert hashes(session.catalog.root)==reports and hashes(session.inputs.root/'accounting')==accounting
    assert api.get(root+'/report-view',headers=headers(session)).json()['state']['financial_approval'] is False


def test_same_input_second_report_and_unknown_attachments_cannot_inherit_or_rebind(scope):
    assert post(scope).status_code==201
    for field,prefix in [('note_ids','note'),('correction_ids','correction')]:
        response=post(scope,body(scope,'changes_requested',1,**{field:[prefix+'-'+'f'*32]}),'missing-'+prefix+'-reference')
        assert response.status_code==409,response.text
    session,api,snapshot,_=scope
    version=session.inputs.version(snapshot['binding']['version_id'])
    job,_=session.submit(request(version),'same-input-separate-report')
    with worker(session) as store:assert run_one(store)==(True,False)
    root='/api/runs/result-'+job['job_id'][4:]
    changed=api.get(root+'/review',headers=headers(session)).json()['snapshot']
    assert changed['snapshot_id']!=snapshot['snapshot_id']
    assert api.get(root+'/review-decisions',headers=headers(session)).json()['last_sequence']==0
    assert api.post(root+'/review-decisions',json=body(scope),headers=headers(session,'wrong-report-request')).status_code==409
    assert history(scope).json()['last_sequence']==1


def test_oversized_journal_is_unavailable_without_erasing_saved_history(scope,monkeypatch):
    import keystone.workspace.review.decisions as module
    assert post(scope).status_code==201
    with monkeypatch.context() as patch:
        patch.setattr(module,'MAX_JOURNAL_BYTES',100)
        assert history(scope).status_code==503
    assert history(scope).json()['last_sequence']==1


def test_restore_retains_exact_note_and_correction_attachments(corrections_ready,tmp_path):
    from keystone.workspace.review.notes import NotesStore
    session,_,snapshot,*_=corrections_ready;session.review_decisions_enabled=True
    note,_=NotesStore(session.inputs).append(lambda:{'snapshot':snapshot},note_body(snapshot),'restored-reference-note')
    target=next(t for t in snapshot['targets'] if t['id']==note['request']['target_id'])
    value=correction_body(corrections_ready);value.update(target_id=target['id'],target_sha256=target['scope_sha256'])
    correction=post_correction(corrections_ready,value).json()['correction']
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    scope=(session,api,snapshot,None)
    request=body(scope,'changes_requested',target=target,note_ids=[note['id']],correction_ids=[correction['id']])
    saved=post(scope,request,'restored-reference-decision').json()['record']
    root=restore_private(capture(session,tmp_path),tmp_path/'restored-linked-review')
    restored=PrivateAdmission(root,ORIGIN,enable_review_decisions=True)
    try:
        api=TestClient(create_app(restored.catalog.root,admission=restored,private=restored),base_url=ORIGIN)
        h=api.get(url(scope),headers=headers(restored));assert h.status_code==200,h.text
        assert h.json()['records']==[saved] and h.json()['progress']['analyst_review']=='changes_requested'
        event=h.json()['latest_events'][0]
        assert event['note_ids']==[note['id']] and event['correction_ids']==[correction['id']]
        response=api.post(url(scope),json=request,headers=headers(restored,'restored-reference-decision'))
        assert response.status_code==200 and response.json()['record']==saved
        assert len(restored.catalog.load().runs)==1
    finally:restored.close()
