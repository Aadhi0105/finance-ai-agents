"""Local possession controls, private observations and identifier-free exports."""
from copy import deepcopy
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from keystone.workspace.api import create_app
from keystone.workspace import privacy
from keystone.workspace.onboarding.service import PrivateAdmission
from keystone.workspace.onboarding import contracts as c
from test_workspace_onboarding import session,headers,ORIGIN,ingest,prepare
from test_native_reports import hashes,native,legacy


def api(session):return TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)


def test_private_observation_and_export_are_protected_readonly_and_do_not_expose_identifiers(session):
    before=hashes(session.inputs.root)
    with api(session) as client:
        for path in ('/api/privacy','/api/privacy/diagnostic'):
            assert client.get(path).status_code==403
            assert client.get(path,headers={**headers(session),'Origin':'https://foreign.example'}).status_code==403
            response=client.get(path,headers=headers(session));assert response.status_code==200,response.text
            assert response.headers['cache-control']=='no-store'
            assert response.headers['referrer-policy']=='no-referrer'
            assert 'camera=()' in response.headers['permissions-policy']
            assert client.head(path,headers=headers(session)).content==b''
            assert client.get(path+'?key=fictional-secret',headers=headers(session)).status_code==422
            for method in ('POST','PUT','PATCH','DELETE'):assert client.request(method,path,headers=headers(session)).status_code==405
            assert session.token not in response.text and str(session.inputs.root) not in response.text
        view=client.get('/api/privacy',headers=headers(session)).json();privacy.Privacy.model_validate(view)
        assert view['state']=='checked' and view['sources']['records']==0
        export=client.get('/api/privacy/diagnostic',headers=headers(session));privacy.Diagnostic.model_validate(export.json())
        assert export.headers['content-disposition']=='attachment; filename="keystone-access-check.json"'
        assert not any(s in export.text for s in (session.inputs.descriptor['id'],session.inputs.descriptor['name'],'records','workspace_id','permission-'))
        assert all(export.json()['controls'][k] is False for k in ('automatic_session_expiry','external_sharing_enabled','live_data_enabled','paid_models_enabled','financial_approval','production_release_approved'))
        assert hashes(session.inputs.root)==before


@pytest.mark.parametrize('change',['mode','contents','replaced','missing','link','hardlink','directory','fifo','control_link'])
def test_key_compromise_holds_protected_reads_without_following_or_rewriting_files(session,tmp_path,change):
    client=api(session);h=headers(session);key=session.token_file;original=key.read_bytes()
    if change=='mode':key.chmod(0o644)
    elif change=='contents':key.write_bytes(b'x'*44)
    elif change=='replaced':
        new=key.with_name('new.key');new.write_bytes(original);new.chmod(0o600);os.replace(new,key)
    elif change=='missing':key.unlink()
    elif change=='link':
        outside=tmp_path/'outside';outside.write_bytes(original);key.unlink();key.symlink_to(outside)
    elif change=='hardlink':os.link(key,tmp_path/'linked')
    elif change=='directory':key.unlink();key.mkdir(mode=0o700)
    elif change=='fifo':key.unlink();os.mkfifo(key,0o600)
    else:
        control=session.store.root;control.rename(tmp_path/'retained-control');control.symlink_to(tmp_path/'retained-control',target_is_directory=True)
    response=client.get('/api/privacy',headers=h)
    assert response.status_code==403 and response.json()['error']['code']=='job_access_required'
    assert original.decode().strip() not in response.text and str(key) not in response.text
    assert session.token is None
    # A compromised session stays held even if the same inode's mode/content is repaired.
    if change=='mode':key.chmod(0o600)
    if change=='contents':key.write_bytes(original)
    assert client.get('/api/workspace',headers=h).status_code==403
    client.close()


def test_restart_rotates_key_and_preserves_saved_evidence(session):
    root=session.inputs.root;old=headers(session);before=hashes(root);session.close()
    restarted=PrivateAdmission(root,ORIGIN)
    try:
        with api(restarted) as client:
            assert client.get('/api/workspace',headers=old).status_code==403
            assert client.get('/api/privacy',headers=headers(restarted)).status_code==200
            after=hashes(root)
            assert {k:v for k,v in before.items() if k!='control/access-token.key'}=={k:v for k,v in after.items() if k!='control/access-token.key'}
    finally:restarted.close()


@pytest.mark.parametrize('failure',['none','revoked','expired','backup_pending','evidence_changed','permission_hash','budget'])
def test_source_use_counts_preserve_holds_without_reading_financial_prose(session,native,monkeypatch,failure):
    version,*rest=ingest(session,native,'research');policy=rest[3]
    if failure in {'expired','backup_pending'}:
        policy=deepcopy(policy)
        if failure=='expired':policy['expires_at']='2026-02-01T00:00:00Z'
        else:policy['rights']['local_backup']='pending'
        data=c.canonical(policy)
        with session.inputs.write() as con:con.execute('UPDATE objects SET value=?,sha256=? WHERE id=?',(data.decode(),c.sha(data),policy['id']))
        (session.inputs.root/'permissions'/policy['id']/'record.json').write_bytes(data)
    elif failure=='revoked':session.inputs.revoke_permission(policy['id'],'Fictional test revocation')
    elif failure=='evidence_changed':(session.inputs.root/'permissions'/policy['id']/'evidence').write_bytes(b'changed fictional evidence')
    elif failure=='permission_hash':
        with session.inputs.write() as con:con.execute('UPDATE objects SET sha256=? WHERE id=?',('0'*64,policy['id']))
    elif failure=='budget':monkeypatch.setattr(privacy,'MAX_SOURCE_BYTES',100)
    before=hashes(session.inputs.root);real=session.inputs.read
    def guarded(name,*args,**kw):
        if name.startswith('inputs/') and not name.endswith('/contract.json'):pytest.fail('Privacy read financial payload/prose')
        return real(name,*args,**kw)
    monkeypatch.setattr(session.inputs,'read',guarded)
    result=privacy.source_summary(session.inputs)
    if failure in {'evidence_changed','permission_hash','budget'}:
        assert result.state=='unavailable' and result.records is None and result.rights is None
    else:
        assert result.records==1 and result.versions==1
        assert result.state==('checked' if failure=='none' else 'attention')
        assert result.held_records==(1 if failure in {'revoked','expired'} else 0)
        # A changed record invalidates the pinned version even for backup-only changes.
        assert result.held_versions==(0 if failure=='none' else 1)
    assert hashes(session.inputs.root)==before


@pytest.mark.parametrize('member',['unknown','unsafe','linked','bound'])
def test_file_observation_never_repairs_or_follows_unsafe_members(session,tmp_path,member):
    root=session.inputs.root
    if member=='unknown':p=root/'unexpected';p.write_bytes(b'fictional private');p.chmod(0o600)
    elif member=='unsafe':p=root/'unexpected';p.write_bytes(b'fictional exposed');p.chmod(0o644)
    elif member=='linked':
        outside=tmp_path/'outside';outside.write_bytes(b'no read');(root/'outside-link').symlink_to(outside)
    else:root.chmod(0o755)
    before=hashes(root) if member!='linked' else None
    value=privacy.observe(session)
    assert value['controls']['workspace_files']==('unavailable' if member=='bound' else 'attention')
    if before is not None:assert hashes(root)==before


def test_unexpected_private_failure_uses_safe_body_and_headers(session,monkeypatch,caplog):
    secret='fictional-secret /Users/private/provider-key'
    monkeypatch.setattr(privacy,'observe',lambda *_:(_ for _ in ()).throw(RuntimeError(secret)))
    with api(session) as client:
        for method in ('GET','HEAD'):
            response=client.request(method,'/api/privacy',headers=headers(session))
            assert response.status_code==503
            assert response.headers['cache-control']=='no-store' and 'Content-Security-Policy' in response.headers
            assert secret not in response.text and secret not in caplog.text


@pytest.mark.parametrize('header',[{'Host':'remote.example'},{'Sec-Fetch-Site':'cross-site'},{'Origin':'null'}])
def test_foreign_access_to_private_download_is_refused(session,header):
    client=api(session)
    response=client.get('/api/privacy/diagnostic',headers={**headers(session),**header})
    assert response.status_code==403 and 'source_use' not in response.text


def test_closed_schemas_are_checked_in_and_reject_private_extra_fields(session):
    root=Path(__file__).parents[1]
    for name,model in [('privacy',privacy.Privacy),('privacy-diagnostic',privacy.Diagnostic)]:
        assert json.loads((root/'keystone/workspace'/f'{name}.schema.json').read_text())==model.model_json_schema()
    value=privacy.diagnostic(session)
    for name in ('workspace_id','token','log','path','source_text'):
        with pytest.raises(ValueError):privacy.Diagnostic.model_validate({**value,name:'private'})
