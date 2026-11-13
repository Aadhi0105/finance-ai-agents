"""Identity checks never install, migrate, execute queued work or reveal paths."""
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from keystone import installation as install
from keystone.workspace.api import create_app
from keystone.workspace.installation_contract import Installation
from test_workspace_onboarding import session,headers,ORIGIN
from test_native_reports import hashes

ROOT=Path(__file__).parents[1]

@pytest.fixture
def ready_api(session,monkeypatch):
    real=install.runtime()
    real.update(platform='Darwin',architecture='arm64',python='3.11.9',supported=True,dependency_mismatches=[])
    monkeypatch.setattr(install,'runtime',lambda:real)
    monkeypatch.setattr(install,'frontend_identity',lambda *_:dict(state='matched',source_sha256='1'*64,built_at='2026-11-13T00:00:00+00:00'))
    return TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)


def test_protected_installation_observation_is_readonly_redacted_and_scoped(session,ready_api):
    before=hashes(session.inputs.root)
    assert ready_api.get('/api/installation').status_code==403
    assert ready_api.get('/api/installation',headers={**headers(session),'Origin':'https://foreign.example'}).status_code==403
    response=ready_api.get('/api/installation',headers=headers(session));assert response.status_code==200,response.text
    value=response.json();Installation.model_validate(value)
    assert value['state']=='checked' and not value['restart_required']
    assert value['workspace_id']==session.inputs.descriptor['id']
    assert value['compatibility']['versions']==dict(inputs=1,jobs=2,catalog=3)
    assert all(value[k] is False for k in ('automatic_update','automatic_migration','financial_approval','production_release_approved'))
    assert str(ROOT) not in response.text and session.token not in response.text
    assert 'no-store' in response.headers['cache-control']
    assert ready_api.head('/api/installation',headers=headers(session)).status_code==200
    assert ready_api.get('/api/installation?path=/private',headers=headers(session)).status_code==422
    for method in ('POST','PUT','PATCH','DELETE'):assert ready_api.request(method,'/api/installation',headers=headers(session)).status_code==405
    assert hashes(session.inputs.root)==before


def test_contract_matches_checked_in_schema(session,ready_api):
    schema=json.loads((ROOT/'keystone/workspace/installation.schema.json').read_text())
    assert schema==Installation.model_json_schema()
    Draft202012Validator(schema).validate(ready_api.get('/api/installation',headers=headers(session)).json())


def test_running_identity_does_not_follow_changed_source(session,ready_api,monkeypatch):
    old=ready_api.get('/api/installation',headers=headers(session)).json()
    changed={**old['current_source'],'sha256':'2'*64}
    monkeypatch.setattr(install,'source_identity',lambda:changed)
    before=hashes(session.inputs.root)
    value=ready_api.get('/api/installation',headers=headers(session)).json()
    assert value['restart_required'] and value['state']=='attention'
    assert value['running_source']==old['running_source'] and value['current_source']==changed
    assert hashes(session.inputs.root)==before


@pytest.mark.parametrize('kind',['legacy','future','input_future','catalog_future','broken','link'])
def test_workspace_format_refusal_never_migrates_or_repairs(session,tmp_path,kind):
    root=session.inputs.root
    if kind in {'legacy','future','input_future'}:
        path=session.inputs.path if kind=='input_future' else session.store.path
        with sqlite3.connect(path) as con:con.execute('PRAGMA user_version='+str(1 if kind=='legacy' else 99))
    elif kind=='catalog_future':
        path=root/'reports/catalog.json';value=json.loads(path.read_text());value['schema_version']=99;path.write_bytes(install.canonical(value))
    elif kind=='broken':session.store.path.write_bytes(b'fictional corrupt ledger')
    else:
        original=root/'control';original.rename(tmp_path/'elsewhere');original.symlink_to(tmp_path/'elsewhere',target_is_directory=True)
    before=hashes(root) if kind!='link' else None
    value=install.compatibility(root)
    assert value['state']==('migration_required' if kind=='legacy' else 'unsupported' if kind in {'future','input_future','catalog_future'} else 'unavailable')
    assert not value['automatic_migration']
    if before is not None:assert hashes(root)==before


def test_new_never_opened_workspace_has_known_initial_format(tmp_path):
    from keystone.workspace.onboarding.store import create_workspace
    root=create_workspace(tmp_path/'fresh','Fictional installation')
    before=hashes(root);value=install.compatibility(root)
    assert value['state']=='compatible' and value['versions']['jobs'] is None
    assert hashes(root)==before and not (root/'control').exists()


@pytest.fixture
def website(tmp_path):
    root=tmp_path/'source'
    for name in ('package.json','pnpm-lock.yaml','tsconfig.json','vite.config.ts','index.html','scripts/build.mjs','src/main.tsx'):
        p=root/'web'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('controlled source '+name)
    site=root/'web/dist';(site/'assets').mkdir(parents=True)
    (site/'index.html').write_text('<script src="/assets/app.js"></script>');(site/'assets/app.js').write_text('controlled built app')
    stamp=dict(schema_version=1,kind='keystone.frontend-build',source_sha256=install.frontend_source(root),built_at='2026-11-13T00:00:00Z',
        files={name:install.sha((site/name).read_bytes()) for name in ('index.html','assets/app.js')})
    (site/'build.json').write_text(json.dumps(stamp));return root,site


@pytest.mark.parametrize('change',['none','source','asset','index','stamp','oversized_stamp','path','link','hardlink'])
def test_build_binding_checks_sources_assets_and_paths_without_trusting_stamp_alone(website,tmp_path,change):
    root,site=website
    if change=='source':(root/'web/src/main.tsx').write_text('new source')
    elif change in {'asset','index'}:(site/('assets/app.js' if change=='asset' else 'index.html')).write_text('changed output')
    elif change=='stamp':(site/'build.json').write_text('broken stamp')
    elif change=='oversized_stamp':(site/'build.json').write_bytes(b'x'*256001)
    elif change=='path':
        stamp=json.loads((site/'build.json').read_text());stamp['files']['../../secret']='0'*64;(site/'build.json').write_text(json.dumps(stamp))
    elif change=='link':
        p=site/'assets/app.js';data=p.read_bytes();p.unlink();outside=tmp_path/'outside';outside.write_bytes(data);p.symlink_to(outside)
    elif change=='hardlink':
        p=site/'assets/app.js';data=p.read_bytes();p.unlink();outside=tmp_path/'outside';outside.write_bytes(data);p.hardlink_to(outside)
    value=install.frontend_identity(site,root)
    assert value['state']==('matched' if change=='none' else 'stale' if change=='source' else 'unavailable')


def test_runtime_lock_includes_web_dependencies_and_keeps_original_lock_unchanged():
    rows=install.requirements();assert {'fastapi','annotated-doc','starlette','uvicorn'}<=rows.keys()
    assert rows['fastapi'][0]=='0.162.0' and len(rows['fastapi'][1])==64
    assert install.sha((ROOT/'requirements-macos-arm64-py311.lock').read_bytes())=='a29f15bc4bf65d773fc01d847b1ed7942bcbb2fda502239cc9e2337fbb3c9349'


def test_identity_rejects_linked_or_secret_source_members(tmp_path):
    (tmp_path/'.env').write_text('fixture secret')
    with pytest.raises(ValueError):install.file_proofs(tmp_path,['.env'])
    with pytest.raises(ValueError):install.file_proofs(tmp_path,['../foreign.py'])
    outside=tmp_path/'outside.py';outside.write_text('source');(tmp_path/'link.py').symlink_to(outside)
    with pytest.raises(ValueError):install.file_proofs(tmp_path,['link.py'])


@pytest.mark.parametrize('status',['prepared','preparing','failed_preserved'])
def test_staged_identity_requires_completed_preparation_and_declared_source(tmp_path,status):
    root=tmp_path/'installation/app';root.mkdir(parents=True);(root/'main.py').write_text('controlled code')
    receipt=dict(schema_version=1,kind='keystone.local-installation',status=status,source_commit='a'*40,development=False,source_files=install.file_proofs(root,['main.py']))
    (root.parent/'installation.json').write_text(json.dumps(receipt))
    assert install.source_identity(root)['mode']==('staged' if status=='prepared' else 'unavailable')
    if status=='preparing':assert install.source_identity(root,allow_preparing=True)['mode']=='staged'
    if status=='prepared':
        (root/'state').mkdir();(root/'state/.keystone-maintenance.lock').touch()
        assert install.source_identity(root)['mode']=='staged'
        (root/'extra.py').write_text('unregistered executable code')
        assert install.source_identity(root)['mode']=='unavailable'


def test_replaced_workspace_root_is_not_reported_as_compatible(session,ready_api,monkeypatch):
    before=hashes(session.inputs.root)
    monkeypatch.setattr(session.inputs,'_root_identity',(-1,-1))
    value=ready_api.get('/api/installation',headers=headers(session)).json()
    assert value['state']=='attention' and value['compatibility']['state']=='unavailable'
    assert hashes(session.inputs.root)==before


@pytest.mark.parametrize('bad',['pkg==file:///private --hash=sha256:'+'0'*64,'-r ../../outside','pkg==1 --index-url https://foreign.invalid'])
def test_bootstrap_lock_parser_refuses_path_versions_and_arbitrary_includes(tmp_path,bad):
    (tmp_path/'requirements-macos-arm64-py311.lock').write_text('good==1 --hash=sha256:'+'0'*64+'\n')
    (tmp_path/install.LOCK).write_text(bad+'\n')
    with pytest.raises(ValueError):install.requirements(tmp_path)


def test_staged_identity_and_launcher_revision_do_not_need_git(tmp_path,monkeypatch):
    from scripts import open_keystone as launcher
    root=tmp_path/'standalone/app';root.mkdir(parents=True);(root/'main.py').write_text('controlled source')
    record=dict(schema_version=1,kind='keystone.local-installation',status='prepared',source_commit='a'*40,development=False,source_files=install.file_proofs(root,['main.py']))
    (root.parent/'installation.json').write_text(json.dumps(record))
    monkeypatch.setattr(install.subprocess,'run',lambda *a,**k:pytest.fail('Staged identity attempted Git discovery'))
    monkeypatch.setattr(launcher,'ROOT',root)
    identity=install.source_identity(root)
    assert identity['mode']=='staged' and launcher.revision()==identity['sha256']


def test_snapshot_provenance_uses_the_staged_release_identity(tmp_path,monkeypatch):
    from keystone import storage
    from test_production_storage import plan_for,entry
    root=tmp_path/'standalone/app';root.mkdir(parents=True)
    names=['main.py','run.py','monitor.py','composer.py','requirements.txt']
    for name in names:(root/name).write_text('controlled source')
    record=dict(schema_version=1,kind='keystone.local-installation',status='prepared',source_commit='b'*40,development=False,source_files=install.file_proofs(root,names))
    (root.parent/'installation.json').write_text(json.dumps(record))
    evidence=tmp_path/'evidence';evidence.mkdir();(evidence/'data.json').write_text('{"synthetic":true}')
    monkeypatch.setattr(storage,'ROOT',root)
    monkeypatch.setattr(storage.platform,'platform',lambda:'controlled test platform')
    monkeypatch.setattr(install.subprocess,'run',lambda *a,**k:pytest.fail('Snapshot attempted parent Git discovery'))
    saved=storage.snapshot(plan_for([entry(evidence)]),tmp_path/'snapshots',quiescent=True)
    manifest=storage.verify(saved)
    assert manifest['code_commit']=='b'*40 and manifest['code_source']['mode']=='staged' and manifest['worktree_dirty'] is False
