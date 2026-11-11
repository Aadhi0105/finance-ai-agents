"""Launcher safety checks: real file/lease boundaries, controlled build/process I/O."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from scripts import open_keystone as launcher


@pytest.fixture
def configured(tmp_path, monkeypatch):
    root = tmp_path / 'repository with spaces'
    state = root / 'state/launcher'
    workspace = root / 'output/existing workspace'
    for path in (root / '.venv/bin', workspace / 'reports', workspace / 'control', state):
        path.mkdir(parents=True, exist_ok=True)
    (root / '.venv/bin/python').write_text('fixture executable')
    (workspace / 'workspace.json').write_text(json.dumps(dict(kind='keystone.private-workspace', id='workspace-example')))
    (workspace / 'reports/catalog.json').write_text('{}')
    (workspace / 'control/access-token.key').write_text('fictional-token')
    node = root / 'tools/node'; node.parent.mkdir(); node.write_text('fixture node')
    manager = node.parent / 'pnpm.mjs'; manager.write_text('fixture manager')
    (root / 'web').mkdir()
    (root / 'web/package.json').write_text(json.dumps({'packageManager':'pnpm@11.25.0'}))
    settings = state / 'settings.json'
    value = dict(schema_version=1, workspace=str(workspace), port=8765, node=str(node), pnpm_js=str(manager))
    settings.write_text(json.dumps(value))
    monkeypatch.setattr(launcher, 'ROOT', root)
    monkeypatch.setattr(launcher, 'STATE', state)
    return launcher.load_settings(settings), settings


@pytest.mark.parametrize('value', [True, 80, 65536, '8765'])
def test_invalid_port_never_starts_or_opens(configured, value):
    _, settings = configured
    config = json.loads(settings.read_text()); config['port'] = value
    settings.write_text(json.dumps(config))
    with pytest.raises(launcher.LaunchError, match='settings.json'):
        launcher.load_settings(settings)


def test_missing_workspace_is_not_created(configured):
    config, settings = configured
    missing = config['workspace'].parent / 'missing'
    with pytest.raises(launcher.LaunchError): launcher.load_settings(settings, workspace=missing)
    assert not missing.exists()


@pytest.mark.parametrize('target', ['settings', 'descriptor'])
def test_nonobject_configuration_has_a_clear_error(configured, target):
    config, settings = configured
    path = settings if target == 'settings' else config['workspace'] / 'workspace.json'
    path.write_text('[]')
    with pytest.raises(launcher.LaunchError, match='settings.json'): launcher.load_settings(settings)


def test_browser_failure_leaves_a_manual_address(configured, monkeypatch, capsys):
    config, _ = configured
    def failed(_): raise launcher.webbrowser.Error('No browser installed')
    monkeypatch.setattr(launcher.webbrowser, 'open', failed)
    launcher.announce(config, True)
    assert 'http://127.0.0.1:8765/' in capsys.readouterr().out


def test_failed_build_preserves_existing_website(configured, monkeypatch):
    config, _ = configured
    previous = launcher.ROOT / 'web/dist'; previous.mkdir()
    (previous / 'index.html').write_text('existing website')
    calls = []
    def run(command, **options):
        calls.append(command)
        if command[-1] == '--version': return SimpleNamespace(stdout='v24.22.1' if len(command)==2 else '11.25.0')
        partial = Path(command[command.index('--outDir')+1]); partial.mkdir()
        (partial / 'index.html').write_text('incomplete new website')
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(launcher.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError): launcher.build_website(config)
    assert (previous / 'index.html').read_text() == 'existing website'
    assert not list(launcher.STATE.glob('web-build-*'))
    assert all('install' not in command for command in calls)


def test_successful_build_uses_explicit_tools_and_keeps_old_assets(configured, monkeypatch):
    config, _ = configured
    previous = launcher.ROOT / 'web/dist'; (previous / 'assets').mkdir(parents=True)
    (previous / 'assets/old.js').write_text('old tab asset')
    (previous / 'index.html').write_text('old index')
    monkeypatch.setenv('PATH', '/usr/bin:/bin')
    def run(command, **options):
        assert command[0] == str(config['node'])
        if command[-1] == '--version': return SimpleNamespace(stdout='v24.22.1' if len(command)==2 else '11.25.0')
        assert options['env']['PATH'].startswith(str(config['node'].parent))
        assert command[:4] == [str(config['node']),str(config['pnpm_js']),'run','build']
        output = Path(command[command.index('--outDir')+1]); (output / 'assets').mkdir(parents=True)
        (output / 'assets/new.js').write_text('new tab asset')
        (output / 'index.html').write_text('new index')
    monkeypatch.setattr(launcher.subprocess, 'run', run)
    launcher.build_website(config)
    assert (previous / 'index.html').read_text() == 'new index'
    assert (previous / 'assets/new.js').read_text() == 'new tab asset'
    assert (previous / 'assets/old.js').read_text() == 'old tab asset'


def test_busy_unmanaged_port_preserves_server_and_skips_build(configured, monkeypatch):
    config, _ = configured
    monkeypatch.setattr(launcher, 'port_busy', lambda _: True)
    monkeypatch.setattr(launcher, 'build_website', lambda _: pytest.fail('Built against an unknown server'))
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **k: pytest.fail('Started a duplicate server'))
    monkeypatch.setattr(launcher.webbrowser, 'open', lambda _: pytest.fail('Opened an unverified server'))
    with pytest.raises(launcher.LaunchError, match='original terminal'): launcher.open_workspace(config)
    assert (config['workspace'] / 'control/access-token.key').read_text() == 'fictional-token'
    assert list(launcher.STATE.glob('*.lock'))  # Locks are retained, not deleted.


@contextmanager
def running_launcher(config, code='current'):
    key = hashlib.sha256((str(config['workspace'])+':'+str(config['port'])).encode()).hexdigest()[:24]
    (launcher.STATE / (key+'.json')).write_text(json.dumps(dict(workspace_id=config['workspace_id'], revision=code)))
    with launcher.lease(launcher.STATE / (key+'.lock')): yield


def test_reopen_changed_backend_requires_restart(configured, monkeypatch):
    config, _ = configured
    monkeypatch.setattr(launcher, 'revision', lambda: 'changed')
    monkeypatch.setattr(launcher, 'build_website', lambda _: pytest.fail('Built before restart'))
    with running_launcher(config):
        with pytest.raises(launcher.LaunchError, match='Local code has changed'): launcher.open_workspace(config)


def test_reopen_matching_backend_builds_then_verifies_then_opens_without_child(configured, monkeypatch):
    config, _ = configured; events = []
    monkeypatch.setattr(launcher, 'revision', lambda: 'current')
    monkeypatch.setattr(launcher, 'build_website', lambda _: events.append('build'))
    monkeypatch.setattr(launcher, 'wait_ready', lambda _: events.append('verified'))
    monkeypatch.setattr(launcher.webbrowser, 'open', lambda _: events.append('browser') or True)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **k: pytest.fail('Started a duplicate server'))
    with running_launcher(config): assert launcher.open_workspace(config) == 0
    assert events == ['build','verified','browser']


def test_source_change_during_build_prevents_server_start(configured, monkeypatch):
    config, _ = configured
    versions = iter(['before','after'])
    monkeypatch.setattr(launcher, 'revision', lambda: next(versions))
    monkeypatch.setattr(launcher, 'port_busy', lambda _: False)
    monkeypatch.setattr(launcher, 'build_website', lambda _: None)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **k: pytest.fail('Started changed code'))
    with pytest.raises(launcher.LaunchError, match='changed during the build'): launcher.open_workspace(config)


def test_failed_readiness_closes_only_owned_child_and_never_opens_browser(configured, monkeypatch):
    config, _ = configured; events=[]
    class Child:
        stopped=False
        def poll(self): return 0 if self.stopped else None
        def terminate(self): events.append('terminate-owned'); self.stopped=True
        def wait(self): events.append('wait-owned'); return 0
    child=Child()
    monkeypatch.setattr(launcher, 'revision', lambda: 'current')
    monkeypatch.setattr(launcher, 'port_busy', lambda _: False)
    monkeypatch.setattr(launcher, 'build_website', lambda _: events.append('build'))
    def spawn(command, **options):
        assert command[0] == str(launcher.ROOT / '.venv/bin/python')
        assert '--enable-worker' in command and '--enable-imports' in command and '--enable-review-notes' in command
        assert str(config['workspace']) in command
        events.append('spawn'); return child
    def not_ready(*_): raise launcher.LaunchError('Not ready')
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    monkeypatch.setattr(launcher, 'wait_ready', not_ready)
    monkeypatch.setattr(launcher.webbrowser, 'open', lambda _: pytest.fail('Opened before readiness'))
    with pytest.raises(launcher.LaunchError, match='Not ready'): launcher.open_workspace(config)
    assert events == ['build','spawn','terminate-owned','wait-owned']
    assert list(launcher.STATE.glob('*.lock'))
    assert sorted(p.name for p in launcher.STATE.glob('*.json')) == ['settings.json']


@pytest.mark.parametrize('mutation', ['wrong_workspace','paid','no_worker','no_notes','redirect'])
def test_readiness_refuses_wrong_workspace_or_execution_boundary(configured, monkeypatch, mutation):
    config, _ = configured
    class Response:
        headers={'Cache-Control':'no-store'}
        def __init__(self, value): self.value=value
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return json.dumps(self.value).encode()
    class Opener:
        def open(self, request, **_):
            if mutation=='redirect': raise launcher.HTTPError(request.full_url,302,'Redirect',{},None)
            if request.full_url.endswith('/api/execution'):
                assert request.get_header('Authorization') is None
                return Response(dict(classification='private',local_token_required=True))
            assert request.get_header('Authorization') == 'Bearer fictional-token'
            value=dict(workspace_id=config['workspace_id'],kind='keystone.private-workspace-reports',
                       input_admission_enabled=True,job_admission_enabled=True,job_worker_enabled=True,review_notes_enabled=True,
                       live_data_enabled=False,paid_models_enabled=False)
            if mutation=='wrong_workspace': value['workspace_id']='other-workspace'
            if mutation=='paid': value['paid_models_enabled']=True
            if mutation=='no_worker': value['job_worker_enabled']=False
            if mutation=='no_notes': value['review_notes_enabled']=False
            return Response(value)
    def opener(*handlers):
        assert any(isinstance(h, launcher.NoRedirect) for h in handlers)
        return Opener()
    monkeypatch.setattr(launcher, 'build_opener', opener)
    assert launcher.probe(config) is False


def test_exited_child_never_reaches_browser_readiness(configured, monkeypatch):
    config, _ = configured
    monkeypatch.setattr(launcher,'probe',lambda _:pytest.fail('Readiness checked after process exit'))
    with pytest.raises(launcher.LaunchError,match='stopped before'):
        launcher.wait_ready(config,SimpleNamespace(poll=lambda:2))
