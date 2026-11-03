"""Private ingestion, source pins, real offline worker and protected delivery."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import uuid
import time

from fastapi.testclient import TestClient
import pytest

from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog,read_json
from keystone.workspace.job_store import JobStore
from keystone.workspace.worker import run_one,recover_delivery
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.onboarding.service import PrivateAdmission
from keystone.workspace.onboarding.store import InputStore,create_workspace
from test_native_reports import legacy,native,hashes

ORIGIN='http://127.0.0.1:8765'


def test_package_schema_matches_documentation_and_example_is_structurally_valid():
    root=Path(__file__).resolve().parents[1]/'docs/webapp/data-onboarding'
    assert json.loads((root/'input-package.schema.json').read_text())==c.SCHEMA
    value=json.loads((root/'examples/synthetic-close-request.json').read_text())
    c.ENVELOPE.validate(value)
    assert value['payload']==json.loads((root.parents[2]/'fixtures/agent4/close-june.json').read_text())


@pytest.fixture
def session(tmp_path):
    root=create_workspace(tmp_path/'private','Private fictional test workspace')
    service=PrivateAdmission(root,ORIGIN,enable_imports=True,enable_jobs=True)
    yield service
    service.close()


def headers(session,key=None):
    h={'Authorization':'Bearer '+session.token,'Origin':ORIGIN,'Content-Type':'application/json'}
    if key:h['Idempotency-Key']=key
    return h


def prepare(session,native,workflow,category='synthetic',policy_changes=None,edit=None,api=None):
    catalog=Catalog(native)
    run=next(r for r in catalog.load().runs if r.workflow==workflow)
    primary=next(a for a in run.artifacts if a.id==run.native_view.source_artifact_ids[0])
    payload=read_json(catalog.read(run.id,primary))
    if edit:edit(payload)
    members=[];ticker=None
    if workflow=='monitoring':members=sorted({r['entity'] for r in payload['current']})
    elif workflow=='events':members=sorted({e['ticker'] for e in payload['inputs']['assembled_inputs']['events']})
    elif workflow=='research':ticker=payload['meta']['ticker']
    elif workflow=='news':ticker=payload['inputs']['request']['ticker']
    name=payload['request']['entity'] if workflow=='close' else run.entity
    entity_request=dict(name=name,kind='group' if members else 'company',ticker=ticker,members=members)
    entity=(api.post('/api/entities',json=entity_request,headers=headers(session)).json() if api else session.inputs.create_entity(entity_request))
    dataset_request=dict(entity_id=entity['id'],title='Fictional '+workflow,workflow=workflow,payload_format=c.FORMATS[workflow])
    dataset=(api.post('/api/datasets',json=dataset_request,headers=headers(session)).json() if api else session.inputs.create_dataset(dataset_request))
    id_='permission-'+uuid.uuid4().hex
    evidence=b'Fictional test-only scope; no actual provider or company permission claimed.'
    policy=dict(schema_version=1,id=id_,workspace_id=session.inputs.descriptor['id'],entity_id=entity['id'],
        payload_sha256=c.fingerprint(payload),category=category,provider_or_owner='Fictional test author',
        intended_use='private_personal_evaluation',evidence_sha256=c.sha(evidence),reviewed_by='Synthetic test operator',
        reviewed_at='2026-01-01T00:00:00Z',expires_at=None,
        rights=dict(local_retention='allowed',local_processing='allowed',local_backup='allowed',model_transfer='denied',sharing='denied'))
    if policy_changes:policy.update(deepcopy(policy_changes))
    session.inputs.install_permission(policy,evidence)
    listing=None if ticker is None else dict(ticker=ticker,exchange=None,quote_currency=None,share_class=None)
    value=dict(schema_version=1,kind='keystone.input-package',workflow=workflow,payload_format=c.FORMATS[workflow],
        dataset=dict(title=dataset['title'],entity_id=entity['id'],listing=listing,upstream_id=run.source_run_id,supersedes_version_id=None),
        sources=[dict(source_id='source',role='retained_source',category=category,provider_or_owner=policy['provider_or_owner'],reference=None,
            period_start=None,period_end=None,published_at=None,retrieved_at=None,currency=None,units=None,permission_record_id=id_)],payload=payload)
    data=c.canonical(value)
    descriptor=dict(schema_version=1,dataset_id=dataset['id'],package_bytes=len(data),package_sha256=c.sha(data),
        payload_sha256=c.fingerprint(payload),metadata={k:v for k,v in value.items() if k!='payload'})
    return value,data,descriptor,policy


def ingest(session,native,workflow,key=None,category='synthetic',**options):
    value,data,descriptor,policy=prepare(session,native,workflow,category,**options)
    key=key or 'import-'+uuid.uuid4().hex
    api=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    try:
        reserved=api.post('/api/imports',json=descriptor,headers=headers(session,key))
        assert reserved.status_code==201,reserved.text
        attempt=reserved.json()['import_attempt']['id']
        result=api.put('/api/imports/'+attempt+'/package',content=data,headers=headers(session,key))
        assert result.status_code==200,result.text
        assert result.json()['state']=='accepted',result.text
        version=session.inputs.version(result.json()['version_id'])
    finally:api.close()
    return version,value,data,descriptor,policy,attempt,key


def submit(session,version,key=None):
    request=dict(schema_version=2,workflow=version['contract']['metadata']['workflow'],timeout_seconds=60,
        source=dict(kind='dataset_version',dataset_id=version['dataset_id'],version_id=version['id'],contract_sha256=version['contract_sha256']))
    return session.submit(request,key or 'job-'+uuid.uuid4().hex)[0]


@pytest.mark.parametrize('workflow',['research','monitoring','events','news','close'])
def test_import_version_to_supervised_native_result_without_bootstrap_report(session,native,workflow,tmp_path):
    before=hashes(native)
    version,*_=ingest(session,native,workflow)
    assert Catalog(session.catalog.root).load().runs==[]
    job=submit(session,version)
    store=JobStore(session.store.root,session.catalog.root,worker=True)
    try:
        assert run_one(store)==(True,False)
        result=session.get(job['job_id'])['job']
        assert result['status']=='review_required',result
        assert result['execution']['attempt']==1 and result['financial_approval'] is False
        assert run_one(store)==(False,False)
    finally:store.close()
    # Python CI does not build web/dist; the static-shell boundary has its own
    # fixture, while the separate frontend job verifies the actual production build.
    frontend=tmp_path/'frontend';frontend.mkdir()
    (frontend/'index.html').write_text('<html><title>Keystone</title><div id="root"></div></html>')
    with TestClient(create_app(session.catalog.root,frontend=frontend,admission=session,private=session),base_url=ORIGIN) as api:
        assert api.get('/').status_code==200
        assert api.get('/').headers['content-type'].startswith('text/html')
        runid='result-'+job['job_id'][4:]
        assert api.get('/api/runs/'+runid+'/report-view').status_code==403
        response=api.get('/api/runs/'+runid+'/report-view',headers=headers(session))
        assert response.status_code==200,response.text
        view=response.json()
        assert view['state']['data_classification']=='synthetic'
        assert view['state']['financial_approval'] is False
        run=api.get('/api/runs/'+runid,headers=headers(session)).json()
        assert run['input_origin']['version_id']==version['id'] and run['input_origin']['contract_sha256']==version['contract_sha256']
        for artifact in run['artifacts']:
            file=api.get(artifact['url'],headers=headers(session))
            assert file.status_code==200 and c.sha(file.content)==artifact['sha256']
            assert file.headers['content-disposition'].startswith('attachment;')
    assert hashes(native)==before
    assert session.inputs.version(version['id'])==version


def test_private_reads_and_mutations_require_access_and_explicit_opt_in(session):
    old_headers=headers(session)
    with TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN) as api:
        for path in ('/api/workspace','/api/runs','/api/entities','/api/datasets','/api/imports','/api/jobs'):
            assert api.get(path).status_code==403
            assert api.head(path).status_code==403
            assert api.get(path,headers={**headers(session),'Origin':'http://elsewhere.invalid'}).status_code==403
        assert api.get('/api/execution').status_code==200
        assert session.inputs.descriptor['name'] not in api.get('/api/execution').text
        assert api.post('/api/entities',json={'name':'Unapproved'},headers={'Authorization':'Bearer '+session.token}).status_code==403
    session.close()
    readonly=PrivateAdmission(session.inputs.root,ORIGIN)
    try:
        with TestClient(create_app(readonly.catalog.root,admission=readonly,private=readonly),base_url=ORIGIN) as api:
            assert api.get('/api/workspace',headers=headers(readonly)).status_code==200
            assert api.post('/api/entities',json={'name':'Not enabled'},headers=headers(readonly)).status_code==405
            assert api.post('/api/jobs',json={},headers=headers(readonly,'disabled-test')).status_code==405
            assert api.get('/api/workspace',headers=old_headers).status_code==403
    finally:readonly.close()
    with pytest.raises(ValueError):create_app(session.catalog.root)


def test_missing_permission_is_refused_before_payload_or_attempt_is_retained(session,native):
    value,data,descriptor,policy=prepare(session,native,'close')
    descriptor['metadata']['sources'][0]['permission_record_id']='nonexistent'
    before=hashes(session.inputs.root/'staging')
    with pytest.raises(c.InputError,match='input_policy_refused'):session.inputs.reserve(descriptor,'unknown-policy')
    assert session.inputs.attempts()['items']==[] and hashes(session.inputs.root/'staging')==before


def client(session):
    return TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)


def test_lost_ack_and_same_content_have_stable_attempt_and_version_identities(session,native):
    version,value,data,descriptor,policy,attempt,key=ingest(session,native,'close')
    api=client(session)
    replay=api.post('/api/imports',json=descriptor,headers=headers(session,key))
    assert replay.status_code==200 and replay.json()['replayed']
    assert replay.json()['import_attempt']['id']==attempt
    assert api.put('/api/imports/'+attempt+'/package',content=data,headers=headers(session,key)).json()['version_id']==version['id']
    changed={**descriptor,'package_sha256':'f'*64}
    assert api.post('/api/imports',json=changed,headers=headers(session,key)).status_code==409
    key2='second-identity'
    duplicate=api.post('/api/imports',json=descriptor,headers=headers(session,key2)).json()['import_attempt']['id']
    receipt=api.put('/api/imports/'+duplicate+'/package',content=data,headers=headers(session,key2))
    assert receipt.status_code==200 and receipt.json()['version_id']==version['id']
    assert receipt.json()['reason']=='duplicate_version'
    assert len(session.inputs.versions(version['dataset_id'])['items'])==1
    assert len(session.inputs.attempts()['items'])==2


@pytest.mark.parametrize('category',['public_provider','issuer','confidential'])
def test_declared_real_categories_require_policy_and_propagate_without_synthetic_relabelling(session,native,category):
    version,*_=ingest(session,native,'close',category=category)
    job=submit(session,version);store=JobStore(session.store.root,session.catalog.root,worker=True)
    try:run_one(store)
    finally:store.close()
    response=client(session).get('/api/runs/result-'+job['job_id'][4:]+'/report-view',headers=headers(session))
    assert response.status_code==200,response.text
    view=response.json()
    assert view['state']['data_classification']==c.CLASSIFICATIONS[category]
    assert view['sources'][0]['source_type']==c.CLASSIFICATIONS[category]
    assert view['state']['financial_approval'] is False


def test_revoked_policy_blocks_admission_claim_delivery_and_input_reads(session,native):
    version,value,data,descriptor,policy,attempt,key=ingest(session,native,'close')
    job=submit(session,version)
    session.inputs.revoke_permission(policy['id'],'Synthetic revocation boundary test')
    with pytest.raises(c.InputError,match='input_policy_refused'):session.inputs.version(version['id'])
    with pytest.raises(Exception):submit(session,version)
    store=JobStore(session.store.root,session.catalog.root,worker=True)
    try:
        run_one(store)
        assert session.get(job['job_id'])['job']['status']=='source_changed'
        assert not (store.root/'operations'/job['operation_id']).exists()
    finally:store.close()
    response=client(session).get('/api/datasets/'+version['dataset_id']+'/versions/'+version['id'],headers=headers(session))
    assert response.status_code==403


def test_changed_accepted_input_cannot_be_executed_or_downloaded(session,native):
    version,*_=ingest(session,native,'monitoring');job=submit(session,version)
    target=session.inputs.root/'inputs'/version['id']/'payload.json';target.write_bytes(target.read_bytes()+b'\n')
    api=client(session)
    path='/api/datasets/'+version['dataset_id']+'/versions/'+version['id']+'/files/payload.json'
    assert api.get(path,headers=headers(session)).status_code==503
    store=JobStore(session.store.root,session.catalog.root,worker=True)
    try:
        run_one(store);assert session.get(job['job_id'])['job']['status']=='source_changed'
        assert not (store.root/'operations'/job['operation_id']).exists()
    finally:store.close()


@pytest.mark.parametrize('after',[False,True])
def test_prepared_import_recovers_once_without_running_validator_or_job(session,native,monkeypatch,after):
    value,data,descriptor,policy=prepare(session,native,'close');key='recovery-input'
    api=client(session)
    attempt=api.post('/api/imports',json=descriptor,headers=headers(session,key)).json()['import_attempt']['id']
    promote=session.inputs._promote
    def fail(source,target):
        if after:promote(source,target)
        raise OSError('PRIVATE-disk-path-not-for-client')
    with monkeypatch.context() as patch:
        patch.setattr(session.inputs,'_promote',fail)
        response=api.put('/api/imports/'+attempt+'/package',content=data,headers=headers(session,key))
    assert response.status_code==503 and 'PRIVATE' not in response.text
    assert session.inputs.attempt(attempt)[1]['state']=='delivery_failed'
    assert session.inputs.versions(descriptor['dataset_id'])['items']==[]
    session.close()
    import keystone.workspace.onboarding.service as module
    with monkeypatch.context() as patch:
        patch.setattr(module.subprocess,'run',lambda *a,**k:pytest.fail('Recovery repeated validation'))
        from keystone.maintenance import control_write_gate
        with control_write_gate():
            receipt=session.inputs.recover(attempt);again=session.inputs.recover(attempt)
    assert receipt==again and receipt['state']=='accepted'
    assert len(session.inputs.versions(descriptor['dataset_id'])['items'])==1
    assert Catalog(session.catalog.root).load().runs==[]


def test_damaged_prepared_input_is_refused_without_overwriting_original(session,native,monkeypatch):
    value,data,descriptor,policy=prepare(session,native,'close');api=client(session);key='damaged-input'
    attempt=api.post('/api/imports',json=descriptor,headers=headers(session,key)).json()['import_attempt']['id']
    with monkeypatch.context() as patch:
        patch.setattr(session.inputs,'_promote',lambda *a:(_ for _ in ()).throw(OSError('disk')))
        assert api.put('/api/imports/'+attempt+'/package',content=data,headers=headers(session,key)).status_code==503
    journal=read_json((session.inputs.root/'staging'/attempt/'prepared.json').read_bytes())
    target=session.inputs.root/'staging'/attempt/journal['prepared']['transfer_id']/'payload.json'
    target.write_bytes(target.read_bytes()+b'\n');preserved=target.read_bytes()
    with pytest.raises(c.InputError):session.inputs.recover(attempt)
    assert target.read_bytes()==preserved and session.inputs.attempt(attempt)[1]['state']=='delivery_failed'


def test_invalid_or_unpermitted_bytes_are_not_persisted(session,native):
    value,data,descriptor,policy=prepare(session,native,'close')
    # A token holder cannot persist different content by claiming an approved payload hash.
    value['payload']['PRIVATE_UNAPPROVED']='do not retain this value'
    changed=c.canonical(value)
    descriptor.update(package_bytes=len(changed),package_sha256=c.sha(changed))
    api=client(session);key='mismatched-content'
    attempt=api.post('/api/imports',json=descriptor,headers=headers(session,key)).json()['import_attempt']['id']
    response=api.put('/api/imports/'+attempt+'/package',content=changed,headers=headers(session,key))
    assert response.status_code==422 and 'UNAPPROVED' not in response.text
    assert session.inputs.attempt(attempt)[1]['state']=='rejected'
    assert not list((session.inputs.root/'staging').rglob('package.json'))
    assert not session.inputs.versions(descriptor['dataset_id'])['items']


@pytest.mark.parametrize('raw',[
    b'{"duplicate":1,"duplicate":2}',b'{"v":NaN}',b'{"v":1e9999}',
    ('['*65+'0'+']'*65).encode(),'{"v":1}'.encode('utf-16'),b'{broken',
])
def test_bounded_json_refuses_ambiguous_or_unsafe_inputs(raw):
    with pytest.raises(c.InputError):c.bounded_json(raw)


def test_raw_close_request_and_client_approval_cannot_enter_saved_profiles(session):
    metadata=json.loads((Path(__file__).resolve().parents[1]/'docs/webapp/data-onboarding/examples/synthetic-close-request.json').read_text())
    assert c.envelope(metadata)['payload_format']==c.FRESH_CLOSE
    # A raw request is a distinct format, never a saved-close source.
    assert metadata['payload_format']!=c.FORMATS['close']
    metadata['payload_format']='agent4.close/1';metadata['financial_approval']=True
    with pytest.raises(c.InputError):c.envelope(metadata)


def test_input_capacity_and_unresolved_limit_preserve_existing_attempts(session,native,monkeypatch):
    value,data,descriptor,policy=prepare(session,native,'close')
    monkeypatch.setattr(c,'MAX_PENDING',1)
    first,_=session.inputs.reserve(descriptor,'one-reservation')
    with pytest.raises(c.InputError,match='input_capacity'):session.inputs.reserve(descriptor,'another-reservation')
    assert session.inputs.attempt(first['id'])[1]['state']=='reserved'
    monkeypatch.setattr(c,'MAX_PENDING',5);monkeypatch.setattr(c,'MAX_INPUT_BYTES',1)
    with pytest.raises(c.InputError,match='input_capacity'):session.inputs.reserve(descriptor,'capacity-reservation')


def test_research_listing_mismatch_is_rejected_after_authorised_transfer(session,native):
    value,data,descriptor,policy=prepare(session,native,'research')
    descriptor['metadata']['dataset']['listing']['ticker']='OTHER'
    with pytest.raises(c.InputError):session.inputs.reserve(descriptor,'wrong-listing')


def test_server_restart_holds_inflight_import_and_rotates_access(session,native):
    value,data,descriptor,policy=prepare(session,native,'close')
    receipt,_=session.inputs.reserve(descriptor,'interrupted-transfer')
    session.inputs.transition(receipt['id'],'receiving',transfer_id='transfer-example')
    old=session.token;session.close()
    replacement=PrivateAdmission(session.inputs.root,ORIGIN,enable_imports=True)
    try:
        assert replacement.token!=old
        assert replacement.inputs.attempt(receipt['id'])[1]['state']=='interrupted'
        assert Catalog(replacement.catalog.root).load().runs==[]
        assert not list((replacement.inputs.root/'inputs').iterdir())
    finally:replacement.close()


def test_expired_policy_is_rechecked_before_claim(session,native,monkeypatch):
    expiry=datetime.now(timezone.utc)+timedelta(hours=1)
    version,*_=ingest(session,native,'close',policy_changes={'expires_at':expiry.isoformat()})
    job=submit(session,version)
    import keystone.workspace.onboarding.store as module
    class Future(datetime):
        @classmethod
        def now(cls,tz=None):return expiry+timedelta(seconds=1)
    monkeypatch.setattr(module,'datetime',Future)
    store=JobStore(session.store.root,session.catalog.root,worker=True)
    try:
        run_one(store)
        assert session.get(job['job_id'])['job']['status']=='source_changed'
        assert not (store.root/'operations'/job['operation_id']).exists()
    finally:store.close()


def test_new_version_never_rewrites_prior_bytes_or_changes_existing_job_source(session,native):
    first,value,data,descriptor,policy,_,_=ingest(session,native,'close')
    original=hashes(session.inputs.root/'inputs'/first['id'])
    job=submit(session,first)
    value['dataset']['title']='A separate declared version label'
    value['dataset']['supersedes_version_id']=first['id']
    data2=c.canonical(value)
    descriptor2={**descriptor,'package_bytes':len(data2),'package_sha256':c.sha(data2),'metadata':{k:v for k,v in value.items() if k!='payload'}}
    api=client(session);key='new-version-contract'
    attempt=api.post('/api/imports',json=descriptor2,headers=headers(session,key)).json()['import_attempt']['id']
    result=api.put('/api/imports/'+attempt+'/package',content=data2,headers=headers(session,key))
    assert result.status_code==200 and result.json()['version_id']!=first['id']
    assert hashes(session.inputs.root/'inputs'/first['id'])==original
    assert session.store.immutable(job['job_id']).source.version_id==first['id']
    assert len(session.inputs.versions(first['dataset_id'])['items'])==2


def test_input_download_rehashes_final_bytes_after_version_check(session,native,monkeypatch):
    version,*_=ingest(session,native,'close')
    read=session.inputs.read;calls=0
    def changed(relative,*args):
        nonlocal calls
        data=read(relative,*args)
        if relative.endswith('/payload.json'):
            calls+=1
            if calls==2:return data+b'\n'
        return data
    monkeypatch.setattr(session.inputs,'read',changed)
    path='/api/datasets/'+version['dataset_id']+'/versions/'+version['id']+'/files/payload.json'
    assert client(session).get(path,headers=headers(session)).status_code==503


def test_registered_metadata_must_match_the_job_delivery_fingerprint(session,native):
    version,*_=ingest(session,native,'close');job=submit(session,version)
    store=JobStore(session.store.root,session.catalog.root,worker=True)
    try:run_one(store)
    finally:store.close()
    path=session.catalog.root/'catalog.json';raw=read_json(path.read_bytes())
    raw['runs'][0]['summary']='Changed but structurally valid overview.'
    path.write_bytes(c.canonical(raw));Catalog(session.catalog.root).load()
    response=client(session).get('/api/runs/result-'+job['job_id'][4:],headers=headers(session))
    assert response.status_code==503


def test_supervised_validation_timeout_can_only_retry_the_explicit_import_identity(session,native,monkeypatch):
    value,data,descriptor,policy=prepare(session,native,'close');api=client(session);key='validation-time-limit'
    attempt=api.post('/api/imports',json=descriptor,headers=headers(session,key)).json()['import_attempt']['id']
    with monkeypatch.context() as patch:
        patch.setattr(c,'VALIDATION_SECONDS',.001)
        response=api.put('/api/imports/'+attempt+'/package',content=data,headers=headers(session,key))
    assert response.status_code==409 and session.inputs.attempt(attempt)[1]['state']=='interrupted'
    assert not session.inputs.versions(descriptor['dataset_id'])['items']
    retry=api.put('/api/imports/'+attempt+'/package',content=data,headers=headers(session,key))
    assert retry.status_code==200 and retry.json()['id']==attempt
    assert len(session.inputs.versions(descriptor['dataset_id'])['items'])==1
    assert Catalog(session.catalog.root).load().runs==[]


@pytest.mark.parametrize('workflow,edit',[
    ('research',lambda p:p['analysis'].update(unsupported_financial_tool={})),
    ('monitoring',lambda p:p['run'].update(cycle='9')),
    ('close',lambda p:p.update(schema_version=True)),
])
def test_authorised_content_still_needs_a_valid_financial_family(session,native,workflow,edit):
    value,data,descriptor,policy=prepare(session,native,workflow,edit=edit);api=client(session);key='invalid-family-input'
    attempt=api.post('/api/imports',json=descriptor,headers=headers(session,key)).json()['import_attempt']['id']
    response=api.put('/api/imports/'+attempt+'/package',content=data,headers=headers(session,key))
    assert response.status_code==422 and session.inputs.attempt(attempt)[1]['state']=='rejected'
    assert not session.inputs.versions(descriptor['dataset_id'])['items']
    assert Catalog(session.catalog.root).load().runs==[]


def test_currency_declaration_cannot_silently_relabel_eur_close(session,native):
    value,data,descriptor,policy=prepare(session,native,'close')
    value['sources'][0]['currency']='USD';data=c.canonical(value)
    descriptor.update(package_bytes=len(data),package_sha256=c.sha(data),metadata={k:v for k,v in value.items() if k!='payload'})
    api=client(session);key='currency-mismatch'
    attempt=api.post('/api/imports',json=descriptor,headers=headers(session,key)).json()['import_attempt']['id']
    assert api.put('/api/imports/'+attempt+'/package',content=data,headers=headers(session,key)).status_code==422


def test_private_api_creation_and_owned_background_worker(session,native):
    root=session.inputs.root;session.close()
    owned=PrivateAdmission(root,ORIGIN,enable_imports=True,enable_jobs=True,enable_worker=True)
    with TestClient(create_app(owned.catalog.root,admission=owned,private=owned),base_url=ORIGIN) as api:
        value,data,descriptor,policy=prepare(owned,native,'close',api=api)
        key='owned-import-pipeline'
        attempt=api.post('/api/imports',json=descriptor,headers=headers(owned,key)).json()['import_attempt']['id']
        accepted=api.put('/api/imports/'+attempt+'/package',content=data,headers=headers(owned,key))
        assert accepted.status_code==200,accepted.text
        version=owned.inputs.version(accepted.json()['version_id'])
        request=dict(schema_version=2,workflow='close',timeout_seconds=60,source=dict(kind='dataset_version',
            dataset_id=version['dataset_id'],version_id=version['id'],contract_sha256=version['contract_sha256']))
        response=api.post('/api/jobs',json=request,headers=headers(owned,'owned-job-pipeline'))
        assert response.status_code==202 and response.json()['job']['worker_enabled']
        job=response.json()['job'];deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            saved=api.get('/api/jobs/'+job['job_id'],headers=headers(owned)).json()['job']
            if saved['status'] in {'completed','review_required','failed','source_changed','outcome_unknown','delivery_failed'}:break
            time.sleep(.05)
        assert saved['status']=='review_required',saved
        assert api.get('/api/runs/result-'+job['job_id'][4:]+'/report-view',headers=headers(owned)).status_code==200


def test_source_permissions_and_recovery_have_no_browser_write_route(session,native,capsys):
    value,data,descriptor,policy=prepare(session,native,'close');api=client(session)
    assert api.post('/api/permissions',json=policy,headers=headers(session)).status_code==405
    receipt,_=session.inputs.reserve(descriptor,'operator-only-recovery')
    from keystone.workspace.__main__ import main
    assert main(['recover-import','--workspace',str(session.inputs.root),'--import-id',receipt['id']])==2
    assert session.inputs.attempt(receipt['id'])[1]['state']=='reserved'
    assert session.token not in capsys.readouterr().err


def test_backup_holds_are_not_silently_excluded(session,native):
    value,data,descriptor,policy=prepare(session,native,'close')
    held=deepcopy(policy);held['id']='permission-'+uuid.uuid4().hex;held['rights']['local_backup']='pending'
    session.inputs.install_permission(held,b'Fictional test-only scope; no actual provider or company permission claimed.')
    with pytest.raises(c.InputError,match='input_policy_refused'):session.inputs.backup_plan()


def test_quiesced_local_snapshot_covers_private_inputs_and_excludes_access_token(session,native,tmp_path,capsys):
    version,*_=ingest(session,native,'close');job=submit(session,version)
    worker=JobStore(session.store.root,session.catalog.root,worker=True)
    try:run_one(worker)
    finally:worker.close()
    token=session.token;session.close()
    from keystone.workspace.__main__ import main
    from keystone.storage import verify,restore
    target=tmp_path/'local-snapshots'
    assert main(['snapshot-private','--workspace',str(session.inputs.root),'--destination',str(target)]) is None
    result=json.loads(capsys.readouterr().out);manifest=verify(Path(result['snapshot']))
    assert result['protection']=='local_snapshot_only'
    files=set(manifest['files'])
    assert {'workspace.json','inputs.sqlite3','reports/catalog.json','control/jobs.sqlite3'}<=files
    assert 'inputs/'+version['id']+'/payload.json' in files
    assert not any(name.endswith('.key') or name.endswith('.env') for name in files)
    assert token not in json.dumps(manifest)
    restored=restore(Path(result['snapshot']),tmp_path/'restored')
    assert InputStore(restored).version(version['id'])==version
    # Portable control rebinding is a separate 3D acceptance requirement. An old
    # absolute workspace binding must fail closed, never create a fresh queue.
    with pytest.raises(Exception):PrivateAdmission(restored,ORIGIN,enable_jobs=True,enable_worker=True)


@pytest.mark.parametrize('workflow',['monitoring','news'])
def test_incomplete_evidence_is_retained_with_a_hold_and_cannot_start_a_job(session,native,workflow):
    def edit(payload):
        if workflow=='monitoring':
            payload.update(run=None,current=[],reviews=[],decisions=[],cycles=[],attempts=[],unreadable_audits=0)
        else:
            from agent3.bundles import retained_inputs,digest
            payload['record'].pop('result',None)
            payload['record']['status']='failed'
            payload['inputs']=retained_inputs(payload['record'])
            payload['content_fingerprint']=digest(payload['inputs'])
            payload['bundle_sha256']=digest({k:v for k,v in payload.items() if k!='bundle_sha256'})
    value,data,descriptor,policy=prepare(session,native,workflow,edit=edit)
    value['dataset']['upstream_id']=None
    data=c.canonical(value)
    descriptor.update(package_bytes=len(data),package_sha256=c.sha(data),metadata={k:v for k,v in value.items() if k!='payload'})
    api=client(session);key='held-evidence-input'
    attempt=api.post('/api/imports',json=descriptor,headers=headers(session,key)).json()['import_attempt']['id']
    result=api.put('/api/imports/'+attempt+'/package',content=data,headers=headers(session,key))
    assert result.status_code==200,result.text
    version=session.inputs.version(result.json()['version_id'])
    assert not version['contract']['validation']['eligible'] and version['contract']['validation']['reasons']
    with pytest.raises(Exception):submit(session,version)
    assert Catalog(session.catalog.root).load().runs==[]
