"""Correction lineage preserves evidence and delegates execution to existing jobs."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.onboarding.service import PrivateAdmission
from keystone.workspace.onboarding.recovery import restore_private
from keystone.workspace.review.corrections import Correction, CorrectionRequest, changes, pin
from keystone.workspace.worker import run_one
from test_workspace_onboarding import session, headers, ORIGIN
from test_workspace_local_research import ingest, request
from test_workspace_fresh_close import worker
from test_workspace_private_recovery import capture
from test_native_reports import hashes
from test_native_reports import native, legacy

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(session):
    session.review_corrections_enabled = True
    entity, dataset, permission, version = ingest(session)
    job, _ = session.submit(request(version), 'correction-original')
    with worker(session) as store:
        assert run_one(store) == (True, False)
    def edit(value):
        value['dataset']['supersedes_version_id'] = version['id']
        value['payload']['periods'][-1]['observations']['operating_income']['value'] = '130000000'
    _, _, replacement_permission, replacement = ingest(session, edit, entity, dataset)
    api = TestClient(create_app(session.catalog.root, admission=session, private=session), base_url=ORIGIN)
    run = 'result-' + job['job_id'][4:]
    snapshot = api.get('/api/runs/' + run + '/review', headers=headers(session)).json()['snapshot']
    return session, api, snapshot, version, replacement, permission, replacement_permission


def url(ready):
    return '/api/runs/' + ready[2]['binding']['run_id'] + '/review-corrections'


def comparison(ready):
    response = ready[1].get(url(ready), params={'replacement_version_id': ready[4]['id']}, headers=headers(ready[0]))
    assert response.status_code == 200, response.text
    return response.json()['comparison']


def body(ready):
    snapshot = ready[2]; target = snapshot['targets'][0]; delta = comparison(ready)
    return dict(schema_version=1, snapshot_id=snapshot['snapshot_id'], target_id=target['id'],
        target_sha256=target['scope_sha256'], replacement=delta['replacement'], change_sha256=delta['change_sha256'],
        reviewer_label='Fictional analyst', reason='Correct the supplied operating-income observation using the revised source package.')


def post(ready, value=None, key='correction-key-0001'):
    return ready[1].post(url(ready), json=body(ready) if value is None else value, headers=headers(ready[0], key))


def test_correction_compares_inputs_records_once_and_preserves_old_evidence(ready):
    session, api, snapshot, old, new, *_ = ready
    before, inputs = hashes(session.catalog.root), hashes(session.inputs.root/'inputs')
    delta = comparison(ready)
    field = next(d for d in delta['changes'] if d['path'].endswith('/operating_income/value'))
    assert field['before']['text'] == '"120000000"' and field['after']['text'] == '"130000000"'
    result = post(ready); assert result.status_code == 201, result.text
    record = result.json()['correction']
    assert record['binding'] == snapshot['binding'] and record['request']['replacement'] == pin(new)
    assert record['financial_approval'] is False and record['identity_assurance'] == 'local_operator_unverified'
    replay = post(ready); assert replay.status_code == 200 and replay.json()['correction'] == record
    assert replay.json()['replayed'] is True
    assert post(ready, key='second-link-0001').status_code == 409
    value = body(ready); value['reason'] = 'Changed explanation'
    assert post(ready, value).status_code == 409
    lineage = api.get(url(ready), headers=headers(session)).json()
    assert lineage['candidates'] == [] and len(lineage['outgoing']) == 1
    assert lineage['outgoing'][0]['replacement_reports'] == []
    assert lineage['outgoing'][0]['affected_reports'][0]['id'] == snapshot['binding']['run_id']
    assert hashes(session.catalog.root) == before and hashes(session.inputs.root/'inputs') == inputs
    assert len(session.catalog.load().runs) == 1
    assert api.get('/api/runs/'+snapshot['binding']['run_id']+'/review',headers=headers(session)).json()['progress']['analyst_review'] == 'not_started'
    head = api.head(url(ready), headers=headers(session)); assert head.status_code == 200 and not head.content
    for method in ('put', 'patch', 'delete'):
        assert getattr(api, method)(url(ready), headers=headers(session)).status_code == 405


def test_explicit_rerun_has_new_numbers_new_review_and_bidirectional_lineage(ready):
    session, api, snapshot, old, new, *_ = ready
    assert post(ready).status_code == 201
    before = hashes(session.catalog.root)
    job, _ = session.submit(request(new), 'correction-explicit-rerun')
    with worker(session) as store:
        assert run_one(store) == (True, False)
    new_run = 'result-' + job['job_id'][4:]
    new_review = api.get('/api/runs/'+new_run+'/review', headers=headers(session)).json()
    assert new_review['snapshot']['binding']['version_id'] == new['id']
    assert new_review['snapshot']['snapshot_id'] != snapshot['snapshot_id']
    assert new_review['progress']['analyst_review'] == 'not_started' and new_review['progress']['financial_approval'] is False
    view = api.get('/api/runs/'+new_run+'/report-view', headers=headers(session)).json()
    metric = next(m for m in view['metrics'] if m['id'] == 'operating-margin')
    assert float(metric['value']) == .13
    assert all(hashes(session.catalog.root)[path] == sha for path, sha in before.items() if path != 'catalog.json')
    lineage = api.get('/api/runs/'+new_run+'/review-corrections', headers=headers(session)).json()
    assert len(lineage['incoming']) == 1 and lineage['outgoing'] == []
    assert lineage['incoming'][0]['replacement_reports'][0]['id'] == new_run
    assert api.get(url(ready),headers=headers(session)).json()['outgoing'][0]['replacement_reports'][0]['id'] == new_run
    assert api.get('/api/runs/'+new_run+'/review-notes',headers=headers(session)).json()['notes'] == []


@pytest.mark.parametrize('field,value', [
    ('schema_version', True), ('financial_approval', True), ('reviewer_label',' '), ('reason',''),
    ('reason','x'*2001), ('snapshot_id','review-'+'0'*64), ('target_id','unknown'), ('target_sha256','0'*64),
    ('change_sha256','0'*64), ('identity_assurance','authenticated'), ('recorded_at','2026-01-01T00:00:00Z')])
def test_invalid_or_stale_corrections_do_not_persist(ready, field, value):
    data = body(ready); data[field] = value
    assert post(ready,data).status_code in {409,422}
    assert ready[1].get(url(ready),headers=headers(ready[0])).json()['outgoing'] == []


def test_wrong_version_contract_dataset_and_lineage_are_refused(ready):
    for name, value in [('version_id',ready[3]['id']), ('contract_sha256','0'*64), ('dataset_id','dataset-other'), ('payload_sha256','0'*64)]:
        data = body(ready); data['replacement'][name] = value
        assert post(ready,data).status_code == 409
    session,api,snapshot,old,new,*_ = ready
    entity = session.inputs.object('entity',new['contract']['metadata']['dataset']['entity_id'])
    dataset = session.inputs.object('dataset',new['dataset_id'])
    _,_,_,unrelated = ingest(session,lambda v:v['payload']['periods'][-1]['observations']['revenue'].update(value='850000000'),entity,dataset)
    assert api.get(url(ready),params={'replacement_version_id':unrelated['id']},headers=headers(session)).status_code == 409


@pytest.mark.parametrize('which',[5,6])
def test_current_source_and_replacement_permissions_are_required_for_reads_and_retries(ready,which):
    assert post(ready).status_code == 201
    session,api,*_ = ready
    session.inputs.revoke_permission(ready[which]['id'],'Fictional source-use withdrawal')
    assert api.get(url(ready),headers=headers(session)).status_code == 403
    assert post(ready,body_value(ready)).status_code == 403


def body_value(ready):
    # Used after permissions are revoked; preserve the original request without a new preview.
    with ready[0].inputs.connect() as con:
        value=json.loads(con.execute("SELECT value FROM objects WHERE kind='review_correction'").fetchone()[0])
    return value['request']


def test_transport_capabilities_and_same_origin_boundaries(ready):
    session,api,*_ = ready
    value=body(ready)
    assert api.get(url(ready)).status_code == 403
    assert api.post(url(ready),json=value).status_code == 403
    assert api.post(url(ready),json=value,headers={**headers(session,'cross-origin-key'),'Origin':'https://example.com'}).status_code == 403
    assert api.get(url(ready)+'?approval=true',headers=headers(session)).status_code == 422
    assert api.post(url(ready),json=value,headers=headers(session)).status_code == 422
    assert api.post(url(ready),content=b'x'*16385,headers=headers(session,'large-correction')).status_code == 413
    repeated=list(headers(session,'repeat-header-0001').items())+[('Idempotency-Key','another-key')]
    assert api.post(url(ready),json=value,headers=repeated).status_code == 422
    assert post(ready).status_code == 201
    session.review_corrections_enabled=False
    readonly=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    assert readonly.get(url(ready),headers=headers(session)).json()['corrections_enabled'] is False
    assert readonly.post(url(ready),json=value,headers=headers(session,'disabled-correction')).status_code == 405


def test_concurrent_links_and_rollback_preserve_single_record(ready,monkeypatch):
    session=ready[0];value=body(ready);original=session.inputs._put
    def fail(con,kind,ident,value):
        if kind=='review_correction_receipt':raise OSError('Injected write failure')
        return original(con,kind,ident,value)
    with monkeypatch.context() as patch:
        patch.setattr(session.inputs,'_put',fail)
        assert post(ready,value).status_code == 503
    assert ready[1].get(url(ready),headers=headers(session)).json()['outgoing'] == []
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda _:post(ready,value),range(3)))
    assert all(r.status_code in {200,201} for r in results)
    assert sum(r.status_code==201 for r in results)==1
    assert len({r.json()['correction']['id'] for r in results})==1


def test_changed_payload_cannot_borrow_previous_payload_permission(ready):
    session,api,_,old,new,*_ = ready
    package=json.loads(session.inputs.read('inputs/'+old['id']+'/package.json'))
    package['dataset']['supersedes_version_id']=old['id']
    package['payload']['periods'][-1]['observations']['operating_income']['value']='110000000'
    assert api.post('/api/datasets/'+old['dataset_id']+'/inspect',content=c.canonical(package),headers=headers(session)).status_code == 403


def test_correction_receipt_corruption_refuses_reads_and_snapshot(ready):
    assert post(ready).status_code==201
    session,api,*_=ready
    with session.inputs.write() as con:
        ident,raw=con.execute("SELECT id,value FROM objects WHERE kind='review_correction_receipt'").fetchone()
        value=json.loads(raw);value['request_sha256']='0'*64;data=c.canonical(value)
        con.execute('UPDATE objects SET value=?,sha256=? WHERE id=?',(data.decode(),c.sha(data),ident))
    assert api.get(url(ready),headers=headers(session)).status_code==503
    with pytest.raises(c.InputError):session.inputs.backup_plan()


def test_restore_retains_correction_identity_and_retry_without_execution(ready,tmp_path):
    original=post(ready).json()['correction'];saved_body=body(ready)
    folder=capture(ready[0],tmp_path)
    restored=restore_private(folder,tmp_path/'restored')
    replacement=PrivateAdmission(restored,ORIGIN,enable_review_corrections=True)
    try:
        api=TestClient(create_app(replacement.catalog.root,admission=replacement,private=replacement),base_url=ORIGIN)
        assert api.get(url(ready),headers=headers(replacement)).json()['outgoing'][0]['record']==original
        replay=api.post(url(ready),json=saved_body,headers=headers(replacement,'correction-key-0001'))
        assert replay.status_code==200 and replay.json()['correction']==original
        assert len(replacement.catalog.load().runs)==1
    finally:replacement.close()


def test_correction_schemas_match_runtime_and_diff_preserves_null_and_missing(ready):
    saved=post(ready).json()['correction']
    for name,model,value in [('correction-request',CorrectionRequest,body(ready)),('correction',Correction,saved)]:
        schema=json.loads((ROOT/'keystone/workspace/review'/(name+'.schema.json')).read_text())
        assert schema==model.model_json_schema();Draft202012Validator(schema).validate(value)
    delta=changes({'a':None,'slash/key':1},{'tilde~key':None,'slash/key':2})
    assert next(d for d in delta if d['path']=='/a')['after']['present'] is False
    assert next(d for d in delta if d['path']=='/tilde~0key')['after']['text']=='null'
    assert any(d['path']=='/slash~1key' for d in delta)
    with pytest.raises(c.InputError):changes({}, {})
    with pytest.raises(c.InputError):changes({'rows':list(range(201))},{'rows':list(range(1,202))})


def test_correction_linking_never_calculates_or_acquires_data(ready,monkeypatch):
    import socket
    from keystone.workspace.onboarding.research import calculate
    from keystone import operation
    value=body(ready)
    def forbidden(*_a,**_k):pytest.fail('Correction link attempted execution/acquisition')
    monkeypatch.setattr(calculate,'calculate',forbidden);monkeypatch.setattr(operation,'execute',forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    assert post(ready,value).status_code==201
    assert ready[1].get(url(ready),headers=headers(ready[0])).json()['outgoing'][0]['replacement_reports']==[]


@pytest.mark.parametrize('workflow',['research','monitoring','events','news','close'])
def test_saved_workflows_can_link_validated_source_metadata_replacements(session,native,workflow):
    from test_workspace_onboarding import ingest as saved_ingest, submit
    session.review_corrections_enabled=True
    old,package,*_=saved_ingest(session,native,workflow)
    job=submit(session,old)
    with worker(session) as store:assert run_one(store)==(True,False)
    package['dataset']['supersedes_version_id']=old['id']
    package['sources'][0]['reference']='Fictional revised retained-source description'
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    descriptor=api.post('/api/datasets/'+old['dataset_id']+'/inspect',content=c.canonical(package),headers=headers(session)).json()['descriptor']
    reserved=api.post('/api/imports',json=descriptor,headers=headers(session,'family-correction-input')).json()['import_attempt']
    receipt=api.put('/api/imports/'+reserved['id']+'/package',content=c.canonical(package),headers=headers(session,'family-correction-input'))
    assert receipt.status_code==200 and receipt.json()['state']=='accepted',receipt.text
    run_id='result-'+job['job_id'][4:];path='/api/runs/'+run_id+'/review-corrections'
    snapshot=api.get('/api/runs/'+run_id+'/review',headers=headers(session)).json()['snapshot']
    preview=api.get(path,params={'replacement_version_id':receipt.json()['version_id']},headers=headers(session))
    assert preview.status_code==200,preview.text
    delta=preview.json()['comparison'];assert [d['path'] for d in delta['changes']]==['/sources/0/reference']
    target=snapshot['targets'][0]
    value=dict(schema_version=1,snapshot_id=snapshot['snapshot_id'],target_id=target['id'],target_sha256=target['scope_sha256'],
        replacement=delta['replacement'],change_sha256=delta['change_sha256'],reviewer_label='Fictional analyst',reason='Clarify the retained source description.')
    response=api.post(path,json=value,headers=headers(session,'family-correction-link'))
    assert response.status_code==201,response.text
    assert api.get(path,headers=headers(session)).json()['financial_approval'] is False
    assert len(session.catalog.load().runs)==1


def test_new_input_cannot_inherit_prior_notes_and_alternative_successors_cannot_overwrite_link(ready):
    from keystone.workspace.review.notes import NotesStore
    from test_workspace_review_notes import body as note_body
    session,api,snapshot,old,new,*_=ready
    session.review_notes_enabled=True
    NotesStore(session.inputs).append(lambda:{'snapshot':snapshot},note_body(snapshot),'original-review-note')
    assert post(ready).status_code==201
    entity=session.inputs.object('entity',old['contract']['metadata']['dataset']['entity_id'])
    dataset=session.inputs.object('dataset',old['dataset_id'])
    def edit(value):
        value['dataset']['supersedes_version_id']=old['id']
        value['payload']['periods'][-1]['observations']['operating_income']['value']='140000000'
    _,_,_,alternative=ingest(session,edit,entity,dataset)
    delta=api.get(url(ready),params={'replacement_version_id':alternative['id']},headers=headers(session)).json()['comparison']
    value=body(ready);value.update(replacement=delta['replacement'],change_sha256=delta['change_sha256'])
    assert post(ready,value,'alternative-correction-key').status_code==409
    job,_=session.submit(request(new),'new-input-no-inherited-notes')
    with worker(session) as store:assert run_one(store)==(True,False)
    fresh='/api/runs/result-'+job['job_id'][4:]
    assert api.get(fresh+'/review-notes',headers=headers(session)).json()['notes']==[]
    assert api.get('/api/runs/'+snapshot['binding']['run_id']+'/review-notes',headers=headers(session)).json()['notes'][0]['request']['text']==note_body(snapshot)['text']


def test_other_reports_using_the_original_version_are_visible_without_inheriting_review(ready):
    session,api,snapshot,old,*_=ready
    job,_=session.submit(request(old,valuation=False),'another-original-report')
    with worker(session) as store:assert run_one(store)==(True,False)
    assert post(ready).status_code==201
    other='result-'+job['job_id'][4:]
    history=api.get('/api/runs/'+other+'/review-corrections',headers=headers(session)).json()
    assert {r['id'] for r in history['outgoing'][0]['affected_reports']}=={other,snapshot['binding']['run_id']}
    assert history['outgoing'][0]['record']['binding']['run_id']==snapshot['binding']['run_id']
    assert api.get('/api/runs/'+other+'/review',headers=headers(session)).json()['progress']['analyst_review']=='not_started'


def test_linked_report_delivery_verifies_inventory_once_and_still_checks_each_source(ready,monkeypatch):
    session,api,snapshot,old,new,*_=ready
    assert post(ready).status_code==201
    job,_=session.submit(request(new),'lineage-inventory-read')
    with worker(session) as store:assert run_one(store)==(True,False)
    original=Catalog.load;loads=[];sources=[];source=session.source_version
    def load(catalog):
        loads.append(True);return original(catalog)
    def authorise(run):
        sources.append(run.id);return source(run)
    monkeypatch.setattr(Catalog,'load',load);monkeypatch.setattr(session,'source_version',authorise)
    response=api.get(url(ready),headers=headers(session));assert response.status_code==200,response.text
    assert len(loads)==1
    assert set(sources)=={snapshot['binding']['run_id'],'result-'+job['job_id'][4:]}


def test_competing_submission_keys_record_one_successor_and_capacity_preserves_history(ready,monkeypatch):
    import keystone.workspace.review.corrections as module
    value=body(ready)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda key:post(ready,value,key),['first-correction-key','competing-correction-key']))
    assert sorted(r.status_code for r in results)==[201,409]
    monkeypatch.setattr(module,'MAX_CORRECTIONS',1)
    assert len(ready[1].get(url(ready),headers=headers(ready[0])).json()['outgoing'])==1


def test_synthetic_catalogues_refuse_correction_writes_and_explain_unsupported_input(native):
    api=TestClient(create_app(native),base_url=ORIGIN)
    for run in Catalog(native).load().runs:
        path='/api/runs/'+run.id+'/review-corrections'
        assert api.get(path).status_code==409
        assert api.get(path+'?unexpected=true').status_code==422
        assert api.post(path,json={}).status_code==405


def test_fresh_close_correction_link_does_not_apply_the_accounting_change(session):
    from test_workspace_fresh_close import ingest as close_ingest, correction as close_correction
    from test_workspace_onboarding import submit
    from keystone.workspace.onboarding import close_state
    session.review_corrections_enabled=True
    entity,dataset,_,old=close_ingest(session)
    original=submit(session,old)
    with worker(session) as store:assert run_one(store)==(True,False)
    basis=close_state.inspect(session.inputs,entity['id'])
    _,_,_,new=close_ingest(session,close_correction(),entity=entity,dataset=dataset,
        edit=lambda v:v['dataset'].update(supersedes_version_id=old['id']))
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    root='/api/runs/result-'+original['job_id'][4:]
    snapshot=api.get(root+'/review',headers=headers(session)).json()['snapshot']
    preview=api.get(root+'/review-corrections',params={'replacement_version_id':new['id']},headers=headers(session))
    assert preview.status_code==200,preview.text
    delta=preview.json()['comparison'];target=snapshot['targets'][0]
    value=dict(schema_version=1,snapshot_id=snapshot['snapshot_id'],target_id=target['id'],target_sha256=target['scope_sha256'],
        replacement=delta['replacement'],change_sha256=delta['change_sha256'],reviewer_label='Fictional analyst',reason='Replace the supplied sales observation using an accounting correction request.')
    assert api.post(root+'/review-corrections',json=value,headers=headers(session,'fresh-close-correction-link')).status_code==201
    assert close_state.inspect(session.inputs,entity['id'])==basis
    # Only the existing accounting job path may commit the exact-cent change.
    corrected=submit(session,new)
    with worker(session) as store:assert run_one(store)==(True,False)
    with close_state.open_state(close_state.state_path(session.inputs,entity['id'])) as state:
        assert state.get_run('close-june')['bundle']['bound_tree']['actual_cents']==6500
        assert state.get_run('close-june-corrected')['bundle']['bound_tree']['actual_cents']==7500
    path='/api/runs/result-'+corrected['job_id'][4:]+'/review-corrections'
    assert len(api.get(path,headers=headers(session)).json()['incoming'])==1
