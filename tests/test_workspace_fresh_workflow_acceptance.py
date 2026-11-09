"""4D cross-workflow volume, storage-fault and recovery acceptance.

Real supervised children cover the full happy/delivery paths. In-process renderer
faults isolate the actual write boundaries; they do not simulate OS power loss.
"""
from copy import deepcopy
from contextlib import contextmanager
from datetime import date, timedelta
import errno
import importlib
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid

from fastapi.testclient import TestClient
import pytest

from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog
from keystone.workspace.job_contract import JobError
from keystone.workspace.job_files import prepare_inputs
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.worker import run_one, recover_delivery
from keystone.maintenance import gate
from scripts.fresh_workflow_acceptance_cases import WORKFLOWS, package, entity
from test_workspace_onboarding import session, headers, ORIGIN
from test_workspace_fresh_close import worker
from test_workspace_local_research import request as research_request
from test_workspace_local_workflows import request as workflow_request
from test_native_reports import hashes


@contextmanager
def api_client(*args, **kwargs):
    # The fixture owns the service lifespan. Closing a request client must not
    # shut down its private admission store between phases of the same trial.
    api = TestClient(*args, **kwargs)
    try: yield api
    finally: api.close()


def prepare(session, w, *, maximum=False, edit=None):
    value = package(w)
    if not maximum:
        if w == 'research': value['payload']['periods'] = value['payload']['periods'][-3:]
        elif w == 'monitoring': value['payload']['items'] = value['payload']['items'][:2]
        elif w == 'events':
            value['payload']['events'] = value['payload']['events'][:1]
            value['payload']['controls'] = []
        else: value['payload']['articles'] = value['payload']['articles'][:2]
    e = session.inputs.create_entity(entity(w))
    d = session.inputs.create_dataset(dict(entity_id=e['id'], title='Fictional 4D '+w,
                                           workflow=w, payload_format=value['payload_format']))
    value['dataset']['entity_id'] = value['payload']['entity_id'] = e['id']
    if edit: edit(value)
    evidence = b'4D fictional engineering scope only; no real source rights claimed.'
    policy = dict(schema_version=1, id='permission-'+uuid.uuid4().hex,
                  workspace_id=session.inputs.descriptor['id'], entity_id=e['id'],
                  payload_sha256=c.fingerprint(value['payload']), category='synthetic',
                  provider_or_owner=value['sources'][0]['provider_or_owner'],
                  intended_use='private_personal_evaluation', evidence_sha256=c.sha(evidence),
                  reviewed_by='Fictional 4D operator', reviewed_at='2026-01-01T00:00:00Z', expires_at=None,
                  rights=dict(local_retention='allowed', local_processing='allowed', local_backup='allowed',
                              model_transfer='denied', sharing='denied'))
    session.inputs.install_permission(policy, evidence)
    for source in value['sources']: source['permission_record_id'] = policy['id']
    return value, d, policy


def intake(session, w, **options):
    value, d, policy = prepare(session, w, **options)
    raw = c.canonical(value)
    with api_client(create_app(session.catalog.root, admission=session, private=session), base_url=ORIGIN) as api:
        result = api.post('/api/datasets/'+d['id']+'/inspect', content=raw, headers=headers(session))
        assert result.status_code == 200, result.text
        descriptor = result.json()['descriptor']; key = '4d-import-'+uuid.uuid4().hex
        result = api.post('/api/imports', json=descriptor, headers=headers(session, key))
        assert result.status_code == 201, result.text
        attempt = result.json()['import_attempt']['id']
        result = api.put('/api/imports/'+attempt+'/package', content=raw, headers=headers(session, key))
        assert result.status_code == 200, result.text
    return session.inputs.version(result.json()['version_id']), policy


def request(version):
    return research_request(version) if version['contract']['metadata']['workflow'] == 'research' else workflow_request(version)


def delivery(w):
    return importlib.import_module('keystone.workspace.onboarding.'+
                                   ('research' if w == 'research' else 'local_workflows')+'.delivery')


def assert_originals(session, before):
    assert hashes(session.inputs.root/'inputs') == before[0]
    assert hashes(session.catalog.root) == before[1]


@pytest.mark.parametrize('w', WORKFLOWS)
def test_maximum_volume_survives_supervised_native_delivery(session, w, record_property):
    version, _ = intake(session, w, maximum=True)
    assert version['contract']['validation']['analytical_execution'] == 'not_started'
    assert not session.catalog.load().runs
    job, _ = session.submit(request(version), '4d-maximum-volume')
    started = time.monotonic()
    with worker(session) as store:
        assert run_one(store) == (True, False)
        saved = store.get(job['job_id'])['job']
        assert saved['status'] == 'review_required', saved
        assert saved['execution']['attempt'] == 1
        assert run_one(store) == (False, False)
    elapsed = time.monotonic() - started
    catalog = Catalog(session.catalog.root); run = catalog.load().runs[0]
    result = json.loads(catalog.read(run.id, next(a for a in run.artifacts if a.id == 'local-result')))
    m = {m['id']:m['value'] for m in result['metrics']}
    if w == 'research':
        assert m['revenue-2025'] == '1000000000'
        assert float(m['operating-margin']) == .12 and float(m['base-fcff']) == 80_000_000
        assert len(next(s for s in result['series'] if s['id'] == 'revenue-history')['points']) == 10
    elif w == 'monitoring':
        assert (m['assessed'], m['breaches'], m['missing']) == ('10', '10', '10')
        assert len(result['charts']) == 20
        assert sum(len(ch['points']) for ch in result['charts']) == 2000
        assert sum(ch['points'][-1]['value'] is None for ch in result['charts']) == 10
    elif w == 'events':
        assert m['events'] == m['issuers'] == '20'
        assert float(m['mean-car']) == pytest.approx(.06)
        assert m['p-value'] is None and result['details']['scenario']['distribution'] is None
    else:
        assert (m['articles'], m['clusters'], m['scored']) == ('100', '100', '100')
        assert len(result['rows']) == 100
        for story in result['details']['scored_items']:
            score = story['score_evidence']
            assert score['positive_count'] == 1 and score['negative_count'] == 0
            assert story['sentiment'] == pytest.approx(1/len(re.findall(r'[a-z]+', (story['headline']+' '+story['body']).lower())))
    with api_client(create_app(session.catalog.root, admission=session, private=session), base_url=ORIGIN) as api:
        response = api.get('/api/runs/'+run.id+'/report-view', headers=headers(session))
        assert response.status_code == 200, response.text
        view = response.json(); assert view['state']['financial_approval'] is False
        for artifact in run.artifacts:
            assert c.sha(catalog.read(run.id, artifact)) == artifact.sha256
    record_property('workflow', w); record_property('elapsed_seconds', round(elapsed, 3))
    record_property('artifact_bytes', sum(a.bytes for a in run.artifacts))
    record_property('input_bytes', (session.inputs.root/'inputs'/version['id']/'package.json').stat().st_size)


def test_compact_monitoring_diagnostics_preserve_all_shared_engine_values(monkeypatch):
    import scheduler.cycle
    from test_workspace_local_workflows import pure
    original = scheduler.cycle.calculate_observation
    observed = []
    def capture(*args, **kwargs):
        row = original(*args, **kwargs)
        observed.append(deepcopy(row))
        return row
    monkeypatch.setattr(scheduler.cycle, 'calculate_observation', capture)
    result = pure('monitoring')
    details = result['details']
    assert details['diagnostic_encoding'] == 'interned-method-metadata/1'
    saved = [row for item in details['items'] for row in item['rows']]
    assert len(saved) == len(observed)
    for row, shared in zip(saved, observed):
        for key in ('_anomaly_detail','_drift_detail','_breach_detail'):
            diagnostic = dict(row[key]); metadata = details['diagnostic_methods'][diagnostic.pop('method_ref')]
            assert {**diagnostic, **metadata} == shared[key]
        assert row['cycle'] == shared['cycle'] and row['value'] == shared['value']
        assert row['data_ts'] == shared['data_ts'].isoformat()


@pytest.mark.parametrize('w,which', [('research','periods'), ('monitoring','items'),
    ('monitoring','observations'), ('events','events'), ('events','controls'),
    ('news','articles'), ('news','positive'), ('news','negative')])
def test_one_over_structural_limit_refused_before_acceptance(session, w, which):
    def edit(value):
        p = value['payload']
        # The extra record is otherwise valid: a duplicate identity/date must
        # not accidentally hide a missing structural count guard in this test.
        if which == 'periods':
            extra = deepcopy(p['periods'][0]); extra.update(period_start='2015-01-01',period_end='2015-12-31')
            p['periods'].insert(0,extra); value['sources'][0]['period_start'] = '2015-01-01'
        elif which == 'items':
            extra = deepcopy(p['items'][-1]); extra['id'] = 'policy-over-limit'; p['items'].append(extra)
        elif which == 'observations':
            observations = p['items'][0]['observations']; extra = deepcopy(observations[-1])
            extra['date'] = (date.fromisoformat(extra['date'])+timedelta(days=1)).isoformat()
            observations.append(extra); p['as_of'] = value['sources'][0]['period_end'] = extra['date']
        elif which in {'events','controls'}:
            extra = deepcopy(p[which][0]); offset = timedelta(days=28)
            for key in ('event_date','anchor_date'): extra[key] = (date.fromisoformat(extra[key])+offset).isoformat()
            for key in ('est_dates','window_dates'):
                extra[key] = [(date.fromisoformat(day)+offset).isoformat() for day in extra[key]]
            p[which].append(extra); value['sources'][0]['period_end'] = max(value['sources'][0]['period_end'],extra['window_dates'][-1])
        elif which == 'articles':
            extra = deepcopy(p['articles'][-1]); extra.update(id='article-over-limit',url='https://example.invalid/news/extra')
            p['articles'].append(extra)
        else: p['word_list'][which].append('additional'+which+'word')
    value, dataset, _ = prepare(session, w, maximum=True, edit=edit)
    before = hashes(session.inputs.root/'inputs')
    with api_client(create_app(session.catalog.root, admission=session, private=session), base_url=ORIGIN) as api:
        response = api.post('/api/datasets/'+dataset['id']+'/inspect', content=c.canonical(value), headers=headers(session))
        # Inspection checks transfer identity/rights, not financial semantics.
        assert response.status_code == 200 and response.json()['validation'] == 'pending_import'
        key = '4d-one-over-limit'
        reserved = api.post('/api/imports',json=response.json()['descriptor'],headers=headers(session,key))
        assert reserved.status_code == 201, reserved.text
        attempt = reserved.json()['import_attempt']['id']
        response = api.put('/api/imports/'+attempt+'/package',content=c.canonical(value),headers=headers(session,key))
        assert response.status_code == 422, response.text
        assert session.inputs.attempt(attempt)[1]['state'] == 'rejected'
    assert hashes(session.inputs.root/'inputs') == before
    assert session.inputs.versions(dataset['id'])['items'] == []
    assert not session.catalog.load().runs


@pytest.mark.parametrize('w', WORKFLOWS)
@pytest.mark.parametrize('fault', ['write','fsync','rename','commit'])
def test_new_input_storage_fault_preserves_previous_version(session, monkeypatch, w, fault):
    old, _ = intake(session, w)
    before = (hashes(session.inputs.root/'inputs'), hashes(session.catalog.root))
    value, dataset, _ = prepare(session, w)
    raw = c.canonical(value); key = '4d-storage-fault'
    from keystone.workspace.onboarding import service, store as inputs
    original_write = service.write_new; original_sync = inputs.sync_directory; original_connect = sqlite3.connect
    triggered = []
    class FailCommit(sqlite3.Connection):
        def commit(self):
            if not triggered and self.execute("SELECT count(*) FROM objects WHERE kind='version'").fetchone()[0] > 1:
                triggered.append(True); raise OSError(errno.ENOSPC, 'private commit fault')
            return super().commit()
    def connect(*args, **kw):
        if str(args[0]).endswith('inputs.sqlite3?mode=rw'): kw['factory'] = FailCommit
        return original_connect(*args, **kw)
    def write(path, data):
        if Path(path).name == 'package.json':
            triggered.append(True); raise OSError(errno.ENOSPC, 'private write fault')
        return original_write(path, data)
    def sync(path):
        if Path(path) == session.inputs.root/'inputs':
            triggered.append(True); raise OSError(errno.EIO, 'private flush fault')
        return original_sync(path)
    def rename(*_):
        triggered.append(True); raise OSError(errno.ENOSPC, 'private rename fault')
    with api_client(create_app(session.catalog.root, admission=session, private=session), base_url=ORIGIN) as api:
        inspection = api.post('/api/datasets/'+dataset['id']+'/inspect', content=raw, headers=headers(session))
        assert inspection.status_code == 200, inspection.text
        reserved = api.post('/api/imports', json=inspection.json()['descriptor'], headers=headers(session,key))
        assert reserved.status_code == 201, reserved.text
        attempt = reserved.json()['import_attempt']['id']
        with monkeypatch.context() as patch:
            if fault == 'write': patch.setattr(service, 'write_new', write)
            elif fault == 'fsync': patch.setattr(inputs, 'sync_directory', sync)
            elif fault == 'rename': patch.setattr(session.inputs, '_promote', rename)
            else: patch.setattr(inputs.sqlite3, 'connect', connect)
            response = api.put('/api/imports/'+attempt+'/package', content=raw, headers=headers(session,key))
        assert triggered and response.status_code in {409,503}, response.text
        assert 'private ' not in response.text
    assert hashes(session.inputs.root/'inputs'/old['id']) == {
        path.removeprefix(old['id']+'/'): digest for path,digest in before[0].items()}
    assert hashes(session.catalog.root) == before[1]
    assert session.inputs.version(old['id']) == old
    assert session.inputs.versions(dataset['id'])['items'] == []
    if fault != 'write':
        recovered = session.inputs.recover(attempt)
        assert recovered['state'] == 'accepted'
        assert session.inputs.recover(attempt) == recovered
    assert not session.catalog.load().runs


@pytest.mark.parametrize('w', WORKFLOWS)
@pytest.mark.parametrize('fault', ['result_write','native_view','proof_write','stage_flush','promote'])
def test_renderer_storage_fault_has_no_partial_delivery_or_second_attempt(session, monkeypatch, w, fault):
    version, _ = intake(session, w); job, _ = session.submit(request(version), '4d-render-fault')
    before = (hashes(session.inputs.root/'inputs'), hashes(session.catalog.root))
    module = delivery(w); original_write = module.write_new; original_flush = module.flush_tree; original_rename = module.os.rename
    triggered = []
    def fail():
        triggered.append(True); raise OSError(errno.ENOSPC, 'fictional storage boundary fault')
    def write(path, data):
        if Path(path).name == ('payload.json' if fault == 'result_write' else 'analysis-commit.json'): fail()
        return original_write(path, data)
    def flush(path):
        if Path(path).name.startswith(('.research-', '.local-workflows-')): fail()
        return original_flush(path)
    def rename(source, target, *args, **kw):
        if Path(target).name == 'result': fail()
        return original_rename(source, target, *args, **kw)
    with worker(session) as store:
        record = store.claim_next(); folder = prepare_inputs(store, record)
        with monkeypatch.context() as patch:
            if fault in {'result_write','proof_write'}: patch.setattr(module, 'write_new', write)
            elif fault == 'native_view': patch.setattr(module, 'register_views', lambda *_: fail())
            elif fault == 'stage_flush': patch.setattr(module, 'flush_tree', flush)
            else: patch.setattr(module.os, 'rename', rename)
            with gate():
                with pytest.raises(OSError): module.render(folder, record)
        assert triggered and not (folder/'result').exists()
        with pytest.raises(Exception): recover_delivery(store, job['job_id'])
        assert store.get(job['job_id'])['job']['execution']['attempt'] == 1
        assert run_one(store) == (False, False)
    assert_originals(session, before)


@pytest.mark.parametrize('w', WORKFLOWS)
@pytest.mark.parametrize('fault', ['write','flush','rename','inventory'])
def test_delivery_disk_fault_recovers_exact_saved_proof_once(session, monkeypatch, w, fault):
    from keystone.workspace import job_delivery as public
    from keystone.workspace import worker as runtime
    version, _ = intake(session, w)
    prior, _ = session.submit(request(version), '4d-prior-result')
    with worker(session) as store: assert run_one(store) == (True, False)
    catalog = Catalog(session.catalog.root); old = catalog.load().runs[0]
    old_hashes = hashes(catalog.root/'runs'/old.id)
    job, _ = session.submit(request(version), '4d-delivery-fault')
    original_write = public.write_new; original_flush = public.flush_tree; original_rename = public.os.rename
    triggered = []
    def fail(*_):
        triggered.append(True); raise OSError(errno.ENOSPC, 'private delivery fault')
    def write(path, data):
        if Path(path).parent.name.startswith('.pending-'): fail()
        return original_write(path, data)
    def flush(path):
        if Path(path).name.startswith('.pending-'): fail()
        return original_flush(path)
    def rename(source, target, *args, **kw):
        if Path(source).name.startswith('.pending-'): fail()
        return original_rename(source, target, *args, **kw)
    with worker(session) as store:
        with monkeypatch.context() as patch:
            if fault == 'write': patch.setattr(public, 'write_new', write)
            elif fault == 'flush': patch.setattr(public, 'flush_tree', flush)
            elif fault == 'rename': patch.setattr(public.os, 'rename', rename)
            else: patch.setattr(public, '_replace_inventory', fail)
            assert run_one(store) == (True, False)
        saved = store.get(job['job_id'])['job']
        assert triggered and saved['status'] == 'delivery_failed', saved
        assert [r.id for r in catalog.load().runs] == [old.id]
        proof = hashes(store.root/'jobs'/job['job_id']/'result')
        with monkeypatch.context() as patch:
            patch.setattr(runtime.operation, 'execute', lambda *_a, **_k: pytest.fail('Recovery executed again'))
            patch.setattr(delivery(w), 'render', lambda *_a, **_k: pytest.fail('Recovery rendered again'))
            if fault == 'inventory':
                path = store.root/'jobs'/job['job_id']/'result/runs'/('result-'+job['job_id'][4:])/'analysis-commit.json'
                original = path.read_bytes(); path.write_bytes(original+b' ')
                with pytest.raises(Exception): recover_delivery(store,job['job_id'])
                assert len(catalog.load().runs) == 1
                path.write_bytes(original)
            for _ in range(2):
                recovered = recover_delivery(store, job['job_id'])['job']
                assert recovered['status'] == 'review_required'
                assert recovered['execution']['attempt'] == 1
            assert run_one(store) == (False, False)
        assert hashes(store.root/'jobs'/job['job_id']/'result') == proof
    assert len(catalog.load().runs) == 2
    assert hashes(catalog.root/'runs'/old.id) == old_hashes


def test_mixed_workflow_reservations_include_all_pending_profiles(session):
    versions = {w:intake(session,w)[0] for w in WORKFLOWS}
    jobs = []
    for i in range(6):
        w = WORKFLOWS[i % 4]; body = request(versions[w]); key = f'4d-mixed-reservation-{i}'
        jobs.append((session.submit(body,key)[0], body, key))
    before = (hashes(session.inputs.root/'inputs'), hashes(session.catalog.root))
    with pytest.raises(JobError, match='job_capacity_reached'):
        session.submit(request(versions['news']), '4d-mixed-over-capacity')
    for job, body, key in jobs:
        original, replay = session.submit(body,key)
        assert replay and original['job_id'] == job['job_id']
        assert original['execution']['attempt'] == 0
    assert_originals(session,before)


@pytest.mark.parametrize('w', WORKFLOWS)
def test_supervisor_timeout_keeps_one_attempt_and_never_publishes(session,monkeypatch,w):
    from keystone import operation
    version, _ = intake(session,w)
    body = request(version); body['timeout_seconds'] = 1
    job, _ = session.submit(body,'4d-timeout')
    # A controlled sleeping child tests the real supervisor deadline without
    # relying on host load or changing any production request/runner options.
    monkeypatch.setitem(operation.ENTRYPOINTS,'workspace-saved',['-c','import time; time.sleep(30)'])
    with worker(session) as store:
        assert run_one(store) == (True,False)
        saved = store.get(job['job_id'])['job']
        assert saved['status'] == 'outcome_unknown'
        assert saved['execution']['attempt'] == 1
        assert run_one(store) == (False,False)
        with pytest.raises(Exception): recover_delivery(store,job['job_id'])
    assert session.submit(body,'4d-timeout')[0]['job_id'] == job['job_id']
    assert not session.catalog.load().runs


@pytest.mark.parametrize('bad', [1, True, '1e3', '1,000', 'NaN', 'Infinity', '-0', '-0.0',
                                '01', '.5', '1.0000001', '1000000000000000'])
def test_research_decimal_contract_refuses_coercion_and_ambiguous_values(bad):
    from test_workspace_local_research import example
    from keystone.workspace.onboarding.research.contracts import semantic
    value = example()
    value['payload']['periods'][-1]['observations']['revenue']['value'] = bad
    with pytest.raises(ValueError):
        semantic(value,dict(id='entity-northstar',kind='company',ticker='NSTAR'))


@pytest.mark.parametrize('case', ['missing_revenue','missing_profit','missing_source','missing_reason',
    'unused_source','duplicate_source','wrong_currency','wrong_quote_basis','wrong_unit','adr',
    'bank','quarter','overlap','duplicate_year','unsorted','future_period','unknown_thesis','unknown_broker'])
def test_research_contract_refuses_unsupported_or_contradictory_basis(case):
    from test_workspace_local_research import example,set_obs
    from keystone.workspace.onboarding.research.contracts import semantic
    value = example(); p = value['payload']; current = p['periods'][-1]
    if case == 'missing_revenue': set_obs(value,'revenue',None)
    elif case == 'missing_profit':
        set_obs(value,'operating_income',None); set_obs(value,'net_income',None)
    elif case == 'missing_source': current['observations']['revenue']['source_id'] = None
    elif case == 'missing_reason':
        set_obs(value,'revenue',None); current['observations']['revenue']['missing_reason'] = None
    elif case == 'unused_source':
        extra = deepcopy(value['sources'][0]); extra['source_id'] = 'unused'; value['sources'].append(extra)
    elif case == 'duplicate_source': value['sources'].append(deepcopy(value['sources'][0]))
    elif case == 'wrong_currency': p['currency'] = 'USD'
    elif case == 'wrong_quote_basis': p['quote']['listing']['share_class'] = 'preferred'
    elif case == 'wrong_unit': current['monetary_unit'] = 'millions'
    elif case == 'adr': p['instrument_type'] = 'adr'
    elif case == 'bank': p['company_type'] = 'financial_services'
    elif case == 'quarter': current['period_start'] = '2025-10-01'
    elif case == 'overlap': current['period_start'] = '2024-12-31'
    elif case == 'duplicate_year': p['periods'].append(deepcopy(current))
    elif case == 'unsorted': p['periods'].reverse()
    elif case == 'future_period': current['period_end'] = '2999-12-31'
    elif case == 'unknown_thesis': p['thesis'] = '<script>run()</script>'
    else: p['broker_reports'] = []
    with pytest.raises(ValueError):
        semantic(value,dict(id='entity-northstar',kind='company',ticker='NSTAR'))


@pytest.mark.parametrize('w', WORKFLOWS)
def test_permission_revoked_after_calculation_blocks_private_delivery(session,w):
    version, policy = intake(session,w); job, _ = session.submit(request(version),'4d-revoke-completed')
    with worker(session) as store: assert run_one(store) == (True,False)
    run = session.catalog.load().runs[0]
    before = (hashes(session.inputs.root/'inputs'), hashes(session.catalog.root))
    session.inputs.revoke_permission(policy['id'],'Fictional 4D post-completion revocation')
    with api_client(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN) as api:
        response = api.get('/api/runs/'+run.id+'/report-view',headers=headers(session))
        assert response.status_code in {403,409},response.text
    assert_originals(session,before)
    assert session.get(job['job_id'])['job']['execution']['attempt'] == 1


def test_mixed_completed_and_queued_restore_preserves_proofs_and_holds_all_queues(session,tmp_path):
    from test_workspace_private_recovery import capture
    from keystone.workspace.onboarding.recovery import restore_private,release_restored_job
    from keystone.workspace.onboarding.service import PrivateAdmission
    jobs = []; queued = []
    for w in WORKFLOWS:
        version, _ = intake(session,w)
        jobs.append(session.submit(request(version),'4d-complete-'+w)[0])
        with worker(session) as store: assert run_one(store) == (True,False)
    for w,job in zip(WORKFLOWS,jobs):
        body = session.store.immutable(job['job_id']).request.model_dump()
        queued.append(session.submit(body,'4d-queued-'+w)[0])
    original_token = session.token
    before = (hashes(session.inputs.root/'inputs'),hashes(session.catalog.root))
    target = restore_private(capture(session,tmp_path), tmp_path/'mixed-restored')
    replacement = PrivateAdmission(target,ORIGIN,enable_imports=True,enable_jobs=True)
    try:
        assert replacement.token != original_token
        assert_originals(replacement,before)
        with worker(replacement) as store:
            assert run_one(store) == (False,False)
            for job in jobs:
                assert recover_delivery(store,job['job_id'])['job']['status'] == 'review_required'
            for job in queued:
                saved = store.get(job['job_id'])['job']
                assert saved['restoration_hold'] is True and saved['execution']['attempt'] == 0
                release_restored_job(store,job['job_id'],'Rechecked fictional 4D source, permissions and current code')
                assert run_one(store) == (True,False)
                assert store.get(job['job_id'])['job']['execution']['attempt'] == 1
        assert len(replacement.catalog.load().runs) == 8
    finally: replacement.close()
    assert_originals(session,before)
