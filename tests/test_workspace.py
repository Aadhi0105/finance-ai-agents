"""Read-only web boundary and real offline evidence integration."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import socket
from urllib.parse import urljoin, urlsplit

from fastapi.testclient import TestClient
import pytest

from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog
from keystone.workspace.prepare import prepare_workspace


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    destination = tmp_path_factory.mktemp('workspace') / 'saved'
    # The preparer must stay offline even with live defaults in the environment.
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('AGENT_DATA_SOURCE', 'yfinance')
        patch.setenv('AGENT_STATS_VIA_MCP', '1')
        patch.setenv('LM_DICTIONARY_CSV', '/not-an-approved-dictionary.csv')
        def forbidden(*args, **kwargs):
            raise AssertionError('Workspace preparation attempted network access')
        patch.setattr(socket.socket, 'connect', forbidden)
        prepare_workspace(destination)
        import os
        assert os.environ['AGENT_DATA_SOURCE'] == 'yfinance'
        assert os.environ['AGENT_STATS_VIA_MCP'] == '1'
        assert os.environ['LM_DICTIONARY_CSV'] == '/not-an-approved-dictionary.csv'
    return destination


@pytest.fixture
def client(prepared):
    return TestClient(create_app(prepared), base_url='http://127.0.0.1')


def test_real_saved_results_cover_all_four_agents_and_preserve_holds(client, prepared):
    response = client.get('/api/workspace')
    assert response.status_code == 200
    workspace = response.json()
    assert workspace['production_release_approved'] is False
    assert workspace['read_only'] and not workspace['live_data_enabled'] and not workspace['paid_models_enabled']
    runs = workspace['runs']
    assert {r['agent'] for r in runs} == {'agent1', 'agent2', 'agent3', 'agent4'}
    assert {r['workflow'] for r in runs} == {'research', 'monitoring', 'events', 'news', 'close'}
    assert all(r['review_status'] == 'review_required' for r in runs)
    research = next(r for r in runs if r['agent'] == 'agent1')
    assert research['execution_status'] == 'completed'
    assert len([a for a in research['artifacts'] if a['kind'] == 'chart']) == 5
    assert client.get('/api/runs?agent=agent3').json()['runs'] == [r for r in runs if r['agent'] == 'agent3']
    assert client.get('/api/runs?agent=unknown').status_code == 422
    close = next(r for r in runs if r['agent'] == 'agent4')
    evidence = next(a for a in close['artifacts'] if a['kind'] == 'evidence')
    saved = client.get(evidence['url']).json()
    tree = saved['report']['full_hierarchy']
    assert (tree['budget_cents'], tree['actual_cents']) == (6000, 6500)
    assert close['metrics'][2]['value'] == 'EUR +5.00'
    for run in runs:
        assert client.get('/api/runs/' + run['id']).json() == run
    assert str(prepared) not in response.text


def test_all_gets_and_heads_leave_every_saved_file_unchanged(client, prepared):
    before = hashes(prepared)
    for run in client.get('/api/runs').json()['runs']:
        for artifact in run['artifacts']:
            response = client.get(artifact['url'])
            assert response.status_code == 200
            assert hashlib.sha256(response.content).hexdigest() == artifact['sha256']
            head = client.head(artifact['url'])
            assert head.status_code == 200 and not head.content
    assert hashes(prepared) == before


def test_original_report_links_resolve_to_registered_artifacts(client):
    class References(HTMLParser):
        def __init__(self):
            super().__init__()
            self.references = []

        def handle_starttag(self, tag, attrs):
            for name, value in attrs:
                if name in {'href', 'src'} and value:
                    self.references.append(value)

    for run in client.get('/api/runs').json()['runs']:
        report = next(a for a in run['artifacts'] if a['id'] == run['report_id'])
        registered = {a['url'] for a in run['artifacts']}
        parser = References()
        parser.feed(client.get(report['url']).text)
        local_paths = set()
        for reference in parser.references:
            parsed = urlsplit(reference)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            path = urlsplit(urljoin(report['url'], reference)).path
            assert path in registered, (run['id'], reference)
            assert client.get(path).status_code == 200
            local_paths.add(path)
        if run['agent'] == 'agent4':
            base = f"/api/runs/{run['id']}/files/{run['source_run_id']}"
            assert {base + '.html', base + '.json'} <= local_paths
            expected = f'attachment; filename="{run["source_run_id"]}.json"'
            assert client.get(base + '.json').headers['content-disposition'] == expected


@pytest.mark.parametrize('method', ['post', 'put', 'patch', 'delete', 'options'])
def test_no_browser_mutations(client, prepared, method):
    before = hashes(prepared)
    assert getattr(client, method)('/api/runs').status_code == 405
    assert hashes(prepared) == before


@pytest.mark.parametrize('headers', [
    {'host': 'attacker.example'}, {'host': 'localhost.attacker.example'},
    {'origin': 'https://attacker.example'}, {'origin': 'null'},
    {'sec-fetch-site': 'cross-site'},
])
def test_cross_origin_and_rebinding_requests_refused(client, headers):
    assert client.get('/api/workspace', headers=headers).status_code == 403
    assert client.get('/api/workspace', headers={'origin': 'http://127.0.0.1'}).status_code == 200


def test_reports_are_sandboxed_and_json_is_downloadable(client):
    for run in client.get('/api/runs').json()['runs']:
        for artifact in run['artifacts']:
            response = client.get(artifact['url'])
            assert response.headers['cache-control'] == 'no-store'
            assert response.headers['x-content-type-options'] == 'nosniff'
            if artifact['kind'] == 'report':
                csp = response.headers['content-security-policy']
                assert "default-src 'none'" in csp and 'sandbox allow-same-origin' in csp
                sandbox = csp.split('sandbox ', 1)[1].split(';', 1)[0].split()
                assert set(sandbox) == {'allow-same-origin', 'allow-downloads'}
                assert "form-action 'none'" in csp
            if artifact['name'].endswith('.json'):
                assert response.headers['content-disposition'].startswith('attachment;')


@pytest.mark.parametrize('path', [
    '/.env', '/catalog.json', '/_private/monitor.duckdb', '/api/runs/missing',
    '/api/runs/research-example/files/.env',
    '/api/runs/research-example/files/%2e%2e/%2e%2e/.env',
    '/api/runs/research-example/files/%252e%252e%252f.env',
    '/api/runs/research-example/files/other.json', '/assets/../../.env',
])
def test_unregistered_paths_and_files_are_not_served(client, path):
    assert client.get(path).status_code == 404


def test_changed_evidence_fails_closed_without_paths_or_contents(prepared, tmp_path):
    root = tmp_path / 'changed'
    shutil.copytree(prepared, root)
    target = root / 'runs/research-example/model.json'
    target.write_text('PRIVATE_CHANGED_CONTENT')
    client = TestClient(create_app(root), base_url='http://127.0.0.1')
    for url in ['/api/workspace', '/api/runs', '/api/runs/research-example/files/model.json']:
        response = client.get(url)
        assert response.status_code == 503
        assert str(root) not in response.text and 'PRIVATE_CHANGED_CONTENT' not in response.text


@pytest.mark.parametrize('target', ['catalog.json', 'runs/research-example/model.json', 'runs/research-example'])
def test_symlinks_cannot_expose_other_files(prepared, tmp_path, target):
    root = tmp_path / 'linked'
    shutil.copytree(prepared, root)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.json').write_text('OUTSIDE_SECRET')
    path = root / target
    if path.is_dir():
        shutil.rmtree(path)
        path.symlink_to(outside, target_is_directory=True)
    else:
        path.unlink()
        path.symlink_to(outside / 'secret.json')
    client = TestClient(create_app(root), base_url='http://127.0.0.1')
    response = client.get('/api/workspace')
    assert response.status_code == 503 and 'OUTSIDE_SECRET' not in response.text


@pytest.mark.parametrize('damage', ['issuer', 'approved', 'duplicate', 'path', 'missing-report', 'unknown-field'])
def test_inventory_cannot_silently_expand_its_scope(prepared, tmp_path, damage):
    root = tmp_path / 'bad-inventory'
    shutil.copytree(prepared, root)
    value = json.loads((root / 'catalog.json').read_text())
    if damage == 'issuer': value['classification'] = 'issuer'
    if damage == 'approved': value['production_release_approved'] = True
    if damage == 'duplicate': value['runs'].append(value['runs'][0])
    if damage == 'path': value['runs'][0]['artifacts'][0]['name'] = '../private.html'
    if damage == 'missing-report': value['runs'][0]['report_id'] = 'missing'
    if damage == 'unknown-field': value['runs'][0]['command'] = 'run arbitrary command'
    (root / 'catalog.json').write_text(json.dumps(value))
    client = TestClient(create_app(root), base_url='http://127.0.0.1')
    assert client.get('/api/workspace').status_code == 503


def test_empty_workspace_is_valid_and_existing_preparation_is_preserved(prepared, tmp_path):
    before = hashes(prepared)
    with pytest.raises(FileExistsError):
        prepare_workspace(prepared)
    assert hashes(prepared) == before
    root = tmp_path / 'empty'
    root.mkdir()
    value = json.loads((prepared / 'catalog.json').read_text())
    value['runs'] = []
    (root / 'catalog.json').write_text(json.dumps(value))
    client = TestClient(create_app(root), base_url='http://127.0.0.1')
    assert client.get('/api/runs').json() == {'runs': []}
    assert Catalog(root).load().classification == 'synthetic'


def test_catalog_rejects_duplicate_json_fields(prepared, tmp_path):
    (tmp_path / 'catalog.json').write_text('{"runs": [], "runs": []}')
    client = TestClient(create_app(tmp_path), base_url='http://127.0.0.1')
    assert client.get('/api/workspace').status_code == 503
