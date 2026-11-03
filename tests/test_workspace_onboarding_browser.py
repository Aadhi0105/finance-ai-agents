"""3C static shell and read-only protected package inspection."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from keystone.workspace.api import create_app
from keystone.workspace.onboarding import contracts as c
from test_workspace_onboarding import session,headers,ORIGIN
from test_workspace_fresh_close import package,request
from test_native_reports import hashes


def api_for(session,**kwargs):
    return TestClient(create_app(session.catalog.root,admission=session,private=session,**kwargs),base_url=ORIGIN)


def test_private_shell_is_static_while_all_private_records_remain_protected(session,tmp_path):
    frontend=tmp_path/'web';frontend.mkdir();(frontend/'index.html').write_text('<html><title>Keystone</title><div id="root"></div></html>')
    api=api_for(session,frontend=frontend)
    try:
        response=api.get('/')
        assert response.status_code==200 and response.headers['content-type'].startswith('text/html')
        assert session.inputs.descriptor['name'] not in response.text
        assert session.inputs.descriptor['id'] not in response.text
        assert session.token not in response.text
        assert response.headers['cache-control']=='no-store'
        for route in ['/api/workspace','/api/entities','/api/datasets','/api/imports','/api/jobs','/api/runs']:
            assert api.get(route).status_code==403
    finally:api.close()


@pytest.mark.parametrize('float_and_unicode',[False,True])
def test_inspection_uses_authoritative_hashes_without_retention_or_execution(session,float_and_unicode):
    source=request()
    if float_and_unicode:
        source['budget']['source']='Fictional budget · EUR €'
        source['actuals']['rows'][0]['amount_cents']=11000.0
    entity,dataset,_,raw,expected=package(session,source)
    before=hashes(session.inputs.root)
    api=api_for(session)
    try:
        result=api.post('/api/datasets/'+dataset['id']+'/inspect',content=raw,headers=headers(session))
        assert result.status_code==200,result.text
        value=result.json()
        assert value['descriptor']==expected
        assert value['policy']['classification']=='synthetic'
        assert value['financial_approval'] is False
        assert value['validation']=='pending_import' and value['processing']=='not_started'
        assert hashes(session.inputs.root)==before
        assert not (session.inputs.root/'accounting').exists()
        # Regression for the reservation path shared with read-only inspection.
        receipt,replayed=session.inputs.reserve(value['descriptor'],'browser-inspection-import')
        assert receipt['state']=='reserved' and receipt['dataset_id']==dataset['id'] and not replayed
        assert session.inputs.attempt(receipt['id'])[0]==expected
    finally:api.close()


@pytest.mark.parametrize('change',[
    lambda h:h.pop('Authorization'),
    lambda h:h.update(Authorization='Bearer wrong'),
    lambda h:h.update(Origin='https://untrusted.example'),
    lambda h:h.update({'Sec-Fetch-Site':'cross-site'}),
])
def test_package_inspection_requires_current_access_and_exact_origin(session,change):
    _,dataset,_,raw,_=package(session)
    before=hashes(session.inputs.root);h=headers(session);change(h)
    api=api_for(session)
    try:
        assert api.post('/api/datasets/'+dataset['id']+'/inspect',content=raw,headers=h).status_code==403
        assert hashes(session.inputs.root)==before
    finally:api.close()


def test_source_revocation_between_inspection_and_reservation_holds_input(session):
    _,dataset,policy,raw,_=package(session)
    api=api_for(session)
    try:
        inspected=api.post('/api/datasets/'+dataset['id']+'/inspect',content=raw,headers=headers(session))
        assert inspected.status_code==200
        session.inputs.revoke_permission(policy['id'],'Fictional operator withdrawal')
        response=api.post('/api/imports',json=inspected.json()['descriptor'],headers=headers(session,'withdrawn-browser-import'))
        assert response.status_code==403 and response.json()['error']['code']=='input_policy_refused'
        assert session.inputs.attempts()['items']==[]
    finally:api.close()


@pytest.mark.parametrize('body',[b'{"a":1,"a":2}',b'{"a":NaN}',b'[]',b'not-json'])
def test_inspection_refuses_ambiguous_json_without_saving_bytes(session,body):
    _,dataset,_,_,_=package(session);before=hashes(session.inputs.root)
    api=api_for(session)
    try:
        result=api.post('/api/datasets/'+dataset['id']+'/inspect',content=body,headers=headers(session))
        assert result.status_code==422
        assert hashes(session.inputs.root)==before
    finally:api.close()


def test_inspection_respects_disabled_imports_media_size_and_dataset_identity(session):
    _,dataset,_,raw,_=package(session);api=api_for(session)
    try:
        response=api.post('/api/datasets/'+dataset['id']+'/inspect',content=raw,headers={**headers(session),'Content-Encoding':'gzip'})
        assert response.status_code==415
        response=api.post('/api/datasets/'+dataset['id']+'/inspect',content=raw,headers={**headers(session),'Content-Length':'20000001'})
        assert response.status_code==413
        other=session.inputs.create_dataset(dict(entity_id=dataset['entity_id'],title='Other evidence',workflow='close',payload_format='agent4.close/1'))
        assert api.post('/api/datasets/'+other['id']+'/inspect',content=raw,headers=headers(session)).status_code==422
        session.imports_enabled=False
        assert api.post('/api/datasets/'+dataset['id']+'/inspect',content=raw,headers=headers(session)).status_code==405
        assert session.inputs.attempts()['items']==[]
    finally:api.close()
