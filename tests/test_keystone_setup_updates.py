"""New-destination setup and snapshot-copy recovery preserve the previous install."""
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from scripts import setup_keystone as setup
from scripts import check_workspace_update as update
from scripts import open_keystone as launcher
from test_open_keystone import configured
from test_workspace_onboarding import session
from test_workspace_private_recovery import capture
from test_native_reports import hashes

REAL_INSTALL_CHECK=launcher.check_installation


@pytest.fixture
def staging(tmp_path,monkeypatch):
    root=tmp_path/'reviewed-source';(root/'web').mkdir(parents=True)
    (root/'web/package.json').write_text('{"packageManager":"pnpm@11.25.0"}')
    (root/'main.py').write_text('reviewed source')
    wheels=tmp_path/'wheels';wheels.mkdir()
    node=tmp_path/'node';node.write_text('trusted test node')
    manager=tmp_path/'pnpm.mjs';manager.write_text('trusted test manager')
    previous=tmp_path/'previous';previous.mkdir();(previous/'keep').write_bytes(b'previous install')
    monkeypatch.setattr(setup.sys,'version_info',(3,11,9))
    import platform
    monkeypatch.setattr(platform,'system',lambda:'Darwin');monkeypatch.setattr(platform,'machine',lambda:'arm64')
    monkeypatch.setattr(setup,'source_files',lambda _:['main.py','web/package.json'])
    monkeypatch.setattr(setup,'source_identity',lambda _:dict(mode='checkout',commit='a'*40,dirty=False,sha256='1'*64))
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(returncode=0,stdout='v24.22.1\n' if args==[str(node),'--version'] else '11.25.0\n')
    def stage(destination,**kwargs):return setup.stage(destination,wheels,node,manager,source=root,run=kwargs.pop('run',run),**kwargs)
    return root,previous,calls,stage


def test_offline_stage_uses_new_source_runtime_and_site_without_selecting_workspace(staging,tmp_path,monkeypatch):
    root,previous,calls,stage=staging;before=hashes(previous)
    monkeypatch.setenv('ANTHROPIC_API_KEY','fictional-not-forwarded')
    monkeypatch.setenv('PIP_INDEX_URL','https://private-registry.invalid/secret')
    destination=tmp_path/'new';value=stage(destination)
    assert value['status']=='prepared' and value['workspace_selected'] is False
    assert hashes(previous)==before and (destination/'app/main.py').read_bytes()==(root/'main.py').read_bytes()
    record=json.loads((destination/'installation.json').read_text());assert record['status']=='prepared'
    install=next((a,k) for a,k in calls if 'install' in a and 'pip' in a)
    assert '--no-index' in install[0] and '--require-hashes' in install[0] and '--only-binary=:all:' in install[0]
    frontend=next(a for a,_ in calls if 'install' in a and '--offline' in a)
    assert '--frozen-lockfile' in frontend and '--ignore-scripts' in frontend
    for _,kwargs in calls:
        if 'env' in kwargs:assert 'ANTHROPIC_API_KEY' not in kwargs['env'] and 'PIP_INDEX_URL' not in kwargs['env']
    assert not (root/'.venv').exists()


@pytest.mark.parametrize('failure',['venv','pip','frontend','build','doctor'])
def test_failed_stage_preserves_previous_and_partial_candidate_for_inspection(staging,tmp_path,failure):
    _,previous,calls,stage=staging;before=hashes(previous)
    def failing(args,**kw):
        if args[-1]=='--version':return SimpleNamespace(stdout='v24.22.1' if len(args)==2 else '11.25.0')
        triggered=(failure=='venv' and 'venv' in args or failure=='pip' and 'pip' in args or failure=='frontend' and '--offline' in args
                   or failure=='build' and 'build' in args or failure=='doctor' and 'doctor' in args)
        if triggered:raise subprocess.CalledProcessError(2,args)
        return SimpleNamespace(returncode=0)
    target=tmp_path/'failed'
    with pytest.raises(subprocess.CalledProcessError):stage(target,run=failing)
    assert json.loads((target/'installation.json').read_text())['status']=='failed_preserved'
    assert (target/'app/main.py').exists() and hashes(previous)==before
    with pytest.raises(ValueError):stage(target)


def test_dirty_source_requires_explicit_development_stage(staging,tmp_path,monkeypatch):
    *_,stage=staging
    monkeypatch.setattr(setup,'source_identity',lambda _:dict(commit='a'*40,dirty=True,sha256='1'*64))
    target=tmp_path/'development'
    with pytest.raises(ValueError):stage(target)
    assert not target.exists()
    assert stage(target,development=True)['development'] is True


@pytest.mark.parametrize('mode',['unsupported','migration_required','unavailable'])
def test_managed_launcher_refuses_format_before_build_or_start(configured,monkeypatch,mode):
    import keystone.installation
    config,_=configured
    monkeypatch.setattr(keystone.installation,'compatibility',lambda _:dict(state=mode))
    monkeypatch.setattr(launcher,'build_website',lambda _:pytest.fail('Built despite format refusal'))
    with pytest.raises(launcher.LaunchError,match='format needs review'):launcher.open_workspace(config)


def test_receipt_write_failure_keeps_previous_receipt_bytes(tmp_path,monkeypatch):
    path=tmp_path/'installation.json';setup.save(path,dict(status='preparing'));before=path.read_bytes()
    monkeypatch.setattr(setup.os,'replace',lambda *_:(_ for _ in ()).throw(OSError('fictional storage full')))
    with pytest.raises(OSError):setup.save(path,dict(status='prepared'))
    assert path.read_bytes()==before and not list(tmp_path.glob('.installation-*'))


@pytest.mark.parametrize('candidate_ok',[True,False])
def test_update_checks_previous_on_fresh_recovery_copy_even_when_candidate_fails(session,tmp_path,monkeypatch,candidate_ok):
    snapshot=capture(session,tmp_path/'snapshot');before=hashes(snapshot)
    candidate=tmp_path/'candidate';previous=tmp_path/'previous';candidate.mkdir();previous.mkdir()
    python=tmp_path/'python';python.write_text('trusted fixture runtime')
    identity=dict(mode='checkout',commit='a'*40,dirty=False,sha256='1'*64)
    monkeypatch.setattr(update,'source_identity',lambda _:identity)
    called=[]
    def check(py,root,args,log):
        called.append((root,args))
        if root==candidate and not candidate_ok:raise ValueError('fictional rejected candidate')
    monkeypatch.setattr(update,'run_check',check)
    monkeypatch.setattr(update,'initialise',lambda py,root,workspace,log:called.append((root,['initialise',str(workspace)])))
    monkeypatch.setattr(update,'check_web',lambda *args:dict(status='checked'))
    value=update.rehearse(snapshot,candidate,python,previous,python,tmp_path/'trial')
    assert value['candidate']==('checked' if candidate_ok else 'failed_preserved')
    assert value['rollback']=='checked' and value['status']==('passed' if candidate_ok else 'failed_preserved')
    assert any(root==previous and 'audit-private' in args for root,args in called)
    assert (tmp_path/'trial/candidate-workspace').is_dir() and (tmp_path/'trial/rollback-workspace').is_dir()
    assert not value['active_installation_changed'] and not value['authoritative_workspace_selected']
    assert hashes(snapshot)==before


def test_rehearsal_refuses_snapshot_overlap_before_any_write(session,tmp_path,monkeypatch):
    snapshot=capture(session,tmp_path/'snapshots');before=hashes(snapshot)
    candidate=tmp_path/'candidate';previous=tmp_path/'previous';candidate.mkdir();previous.mkdir()
    python=tmp_path/'python';python.write_text('runtime')
    monkeypatch.setattr(update,'source_identity',lambda _:dict(sha256='1'*64,commit='a'*40,dirty=False))
    with pytest.raises(ValueError,match='overlaps'):update.rehearse(snapshot,candidate,python,previous,python,snapshot/'trial')
    assert hashes(snapshot)==before


@pytest.mark.parametrize('marker',['workspace.json','inputs.sqlite3','installation.json','pyvenv.cfg'])
def test_new_destinations_cannot_nest_inside_retained_state(tmp_path,marker):
    protected=tmp_path/'protected';protected.mkdir();(protected/marker).write_text('retained')
    before=hashes(protected)
    with pytest.raises(ValueError):setup.new_destination(protected/'new-install')
    assert hashes(protected)==before


@pytest.mark.parametrize('problem',['source','runtime','platform','website'])
def test_installation_gate_runs_before_worker_start(configured,monkeypatch,problem):
    import keystone.installation as install
    config,_=configured
    monkeypatch.setattr(launcher,'check_installation',REAL_INSTALL_CHECK)
    monkeypatch.setattr(install,'source_identity',lambda _:dict(sha256=None if problem=='source' else '1'*64))
    monkeypatch.setattr(install,'runtime',lambda _:dict(supported=problem!='platform',dependency_mismatches=[{}] if problem=='runtime' else []))
    monkeypatch.setattr(install,'frontend_identity',lambda *_:dict(state='unavailable' if problem=='website' else 'matched'))
    monkeypatch.setattr(launcher,'port_busy',lambda _:False);monkeypatch.setattr(launcher,'revision',lambda:'unchanged')
    monkeypatch.setattr(launcher,'build_website',lambda _:None)
    monkeypatch.setattr(launcher.subprocess,'Popen',lambda *a,**k:pytest.fail('Worker was started before installation gate passed'))
    with pytest.raises(launcher.LaunchError):launcher.open_workspace(config)


@pytest.mark.parametrize('bad',['none','workspace','source','kind','worker_flags','format','schema'])
def test_candidate_readiness_must_match_the_exact_workspace_and_source(bad):
    identity=dict(mode='staged',commit='a'*40,dirty=False,sha256='1'*64)
    value=dict(schema_version=1,kind='keystone.installation',workspace_id='workspace-'+'a'*32,state='checked',restart_required=False,
        running_source=identity,current_source=identity,frontend=dict(state='matched'),compatibility=dict(state='compatible'),
        automatic_update=False,automatic_migration=False,financial_approval=False,production_release_approved=False)
    if bad=='workspace':value['workspace_id']='workspace-'+'b'*32
    elif bad=='source':value['current_source']={**identity,'sha256':'2'*64}
    elif bad=='kind':value['kind']='other'
    elif bad=='worker_flags':value['automatic_update']=True
    elif bad=='format':value['compatibility']['state']='unsupported'
    elif bad=='schema':value['schema_version']=True
    assert update.readiness_matches(value,'workspace-'+'a'*32,identity) is (bad=='none')
