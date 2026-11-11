"""Review scope binds evidence and decisions without promoting financial claims."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog, RunV2, RunV3
from keystone.workspace.report_views.values import digest
from keystone.workspace.review.contracts import Decision, ReviewError, Snapshot, reduce_decisions
from keystone.workspace.review.projection import project_review
from test_native_reports import hashes, legacy, native
from test_workspace_onboarding import session, headers, ORIGIN

ROOT = Path(__file__).resolve().parents[1]
CASES = ['research-snapshot', 'research-legacy', 'monitoring-snapshot', 'monitoring-legacy',
         'event-snapshot', 'event-legacy', 'news-snapshot', 'news-legacy', 'close-snapshot',
         'close-legacy', 'private-local-research', 'private-local-monitoring',
         'private-local-events', 'private-local-news', 'private-fresh-close']


def example(name='private-local-research'):
    data = json.loads((ROOT / 'web/tests/fixtures' / (name + '.json')).read_text())
    raw = deepcopy(data['run'])
    for artifact in raw['artifacts']:
        artifact.pop('url', None)
    run = (RunV3 if 'input_origin' in raw else RunV2).model_validate(raw)
    return project_review(SimpleNamespace(workspace_id='workspace-fictional-review'), run, data['report'])


def decision(snapshot, target=None, disposition='acknowledged', sequence=1):
    target = target or next(t for t in snapshot['targets'] if t['availability'] == 'available')
    return dict(schema_version=1, kind='keystone.review-decision', id='decision-' + uuid.uuid4().hex,
                sequence=sequence, snapshot_id=snapshot['snapshot_id'], target_id=target['id'],
                target_sha256=target['scope_sha256'], disposition=disposition,
                reviewer_label='Fictional analyst', identity_assurance='local_operator_unverified',
                reason='Inspected the retained source; financial limitations remain.',
                recorded_at='2026-11-11T12:00:00Z', financial_approval=False)


@pytest.mark.parametrize('name', CASES)
def test_all_supported_report_families_have_separate_source_bound_review(name):
    result = example(name)
    captured=json.loads((ROOT/'web/tests/fixtures/review-snapshots.json').read_text())
    assert result==captured[name]
    snapshot = Snapshot.model_validate(result['snapshot'])
    assert snapshot.financial_approval is False
    assert snapshot.authenticated_reviewer is False and snapshot.decisions_enabled is False
    assert result['progress']['analyst_review'] == 'not_started'
    assert result['progress']['financial_approval'] is False
    assert {t.kind for t in snapshot.targets} == {
        'source_inputs', 'financial_mappings', 'calculation_assumptions', 'report_section', 'review_issue'}
    for model, file, value in [(Snapshot, 'snapshot.schema.json', result['snapshot']),
                               (Decision, 'decision.schema.json', decision(result['snapshot']))]:
        schema = json.loads((ROOT / 'keystone/workspace/review' / file).read_text())
        assert schema == model.model_json_schema()
        Draft202012Validator(schema).validate(value)


def test_review_completion_cannot_release_evidence_holds_or_grant_approval():
    snapshot = example()['snapshot']
    events = [decision(snapshot, target=t, sequence=i+1) for i, t in enumerate(
        t for t in snapshot['targets'] if t['availability'] == 'available')]
    before = deepcopy(snapshot)
    result = reduce_decisions(snapshot, events)
    assert result['analyst_review'] == 'reviewed_with_limitations'
    assert result['financial_approval'] is False
    assert result['evidence_gate'] == snapshot['evidence_gate'] == 'held_for_review'
    assert snapshot == before
    assert reduce_decisions(snapshot, events[:1])['analyst_review'] == 'in_review'
    changes = decision(snapshot, disposition='changes_requested', sequence=len(events)+1)
    assert reduce_decisions(snapshot, events+[changes])['analyst_review'] == 'changes_requested'
    reopen = decision(snapshot, disposition='reopened', sequence=len(events)+2)
    progress = reduce_decisions(snapshot, events+[changes, reopen])
    assert progress['analyst_review'] == 'in_review' and progress['targets'][reopen['target_id']] == 'pending'


@pytest.mark.parametrize('field,value', [
    ('snapshot_id', 'review-'+'0'*64), ('target_id', 'missing-target'),
    ('target_sha256', '0'*64), ('sequence', 2), ('sequence', True),
    ('financial_approval', True), ('financial_approval', 0), ('schema_version', True),
    ('identity_assurance', 'authenticated'),
    ('disposition', 'approved'), ('reason', '  '), ('reviewer_label', '\t'),
    ('recorded_at', '2026-11-11T12:00:00'), ('extra_approval', True),
])
def test_invalid_or_stale_decisions_never_become_effective(field, value):
    snapshot = example()['snapshot']
    event = decision(snapshot); event[field] = value
    with pytest.raises(ReviewError):
        reduce_decisions(snapshot, [event])


def test_duplicate_event_and_out_of_order_history_are_refused():
    snapshot = example()['snapshot']; first = decision(snapshot)
    repeated = dict(first, sequence=2)
    with pytest.raises(ReviewError): reduce_decisions(snapshot, [first, repeated])
    second = decision(snapshot, sequence=2)
    with pytest.raises(ReviewError): reduce_decisions(snapshot, [second, first])
    with pytest.raises(ReviewError): reduce_decisions(snapshot, [first]*2001)


def test_new_input_request_presentation_or_workspace_requires_new_scope():
    data = json.loads((ROOT/'web/tests/fixtures/private-local-research.json').read_text())
    raw = deepcopy(data['run'])
    for artifact in raw['artifacts']: artifact.pop('url', None)
    run = RunV3.model_validate(raw)
    manifest = SimpleNamespace(workspace_id='workspace-fictional-review')
    snapshot = project_review(manifest, run, data['report'])['snapshot']
    first = decision(snapshot)
    variants = []
    for field, value in [('version_id', 'version-'+'a'*32), ('request_sha256', '1'*64),
                         ('contract_sha256', '2'*64)]:
        other = deepcopy(raw); other['input_origin'][field] = value
        variants.append(project_review(manifest, RunV3.model_validate(other), data['report'])['snapshot'])
    other = deepcopy(raw); other['native_view']['adapter_version'] = '1.0.1'
    variants.append(project_review(manifest, RunV3.model_validate(other), data['report'])['snapshot'])
    other = deepcopy(raw); other['artifacts'][0]['sha256'] = '3'*64
    variants.append(project_review(manifest, RunV3.model_validate(other), data['report'])['snapshot'])
    variants.append(project_review(SimpleNamespace(workspace_id='workspace-other'), run, data['report'])['snapshot'])
    for changed in variants:
        assert changed['snapshot_id'] != snapshot['snapshot_id']
        with pytest.raises(ReviewError): reduce_decisions(changed, [first])
    # A newer report does not invalidate the historical review of its own input.
    assert reduce_decisions(snapshot, [first])['analyst_review'] == 'in_review'


def test_unrecorded_subjects_cannot_be_acknowledged():
    snapshot = example('news-legacy')['snapshot']
    missing = next((t for t in snapshot['targets'] if t['availability']=='not_recorded'), None)
    if missing is None:
        # A source with no retained assumptions/method section is explicit.
        data = json.loads((ROOT/'web/tests/fixtures/news-legacy.json').read_text())
        data['report']['sections'] = []
        raw = deepcopy(data['run'])
        for a in raw['artifacts']: a.pop('url',None)
        snapshot = project_review(SimpleNamespace(workspace_id='workspace-test'), RunV2.model_validate(raw),data['report'])['snapshot']
        missing = next(t for t in snapshot['targets'] if t['availability']=='not_recorded')
    with pytest.raises(ReviewError): reduce_decisions(snapshot,[decision(snapshot,target=missing)])


def test_snapshot_and_subject_hashes_are_checked_before_reducing():
    snapshot = example()['snapshot']
    for mutate in (lambda s:s['targets'][0].update(title='Changed scope'),
                   lambda s:s['binding'].update(version_id='version-changed'),
                   lambda s:s.update(financial_approval=True)):
        altered=deepcopy(snapshot);mutate(altered)
        with pytest.raises(ReviewError):reduce_decisions(altered)


def test_input_acceptance_needs_a_complete_version_and_request_binding():
    for field in ('dataset_id','version_id','contract_sha256','request_sha256'):
        snapshot=example()['snapshot'];snapshot['binding'][field]=None
        snapshot['snapshot_id']='review-'+digest({k:v for k,v in snapshot.items() if k!='snapshot_id'})
        with pytest.raises(ReviewError):reduce_decisions(snapshot)


@pytest.mark.parametrize('field,value',[('schema_version',True),('financial_approval',0),
                                     ('authenticated_reviewer',0),('decisions_enabled',0)])
def test_wire_literal_types_match_the_json_schema(field,value):
    snapshot=example()['snapshot'];snapshot[field]=value
    with pytest.raises(ValueError):Snapshot.model_validate(snapshot)


def test_review_refuses_changed_source_bytes_after_a_successful_read(native,tmp_path):
    import shutil
    root=tmp_path/'changed';shutil.copytree(native,root)
    client=TestClient(create_app(root),base_url='http://127.0.0.1')
    url='/api/runs/research-example/review';assert client.get(url).status_code==200
    run=Catalog(root).load().runs[0]
    artifact=next(a for a in run.artifacts if a.id==run.native_view.source_artifact_ids[0])
    path=root/'runs'/run.id/artifact.name;path.write_bytes(path.read_bytes()+b' ')
    response=client.get(url)
    assert response.status_code==503 and 'snapshot' not in response.json()


def test_review_get_and_head_are_read_only_and_do_not_reexecute(native,monkeypatch):
    import socket
    from keystone.workspace.report_views import delivery
    monkeypatch.setattr(socket.socket,'connect',lambda *_a,**_k:pytest.fail('Review attempted acquisition'))
    delivery._VALIDATED.clear()
    before=hashes(native)
    client=TestClient(create_app(native),base_url='http://127.0.0.1')
    for run in Catalog(native).load().runs:
        url=f'/api/runs/{run.id}/review'
        response=client.get(url);assert response.status_code==200,response.text
        assert Snapshot.model_validate(response.json()['snapshot']).binding.run_id==run.id
        head=client.head(url)
        assert head.status_code==200 and not head.content
        assert head.headers['content-length']==str(len(response.content))
        assert response.headers['cache-control']=='no-store'
        assert client.post(url,json={'disposition':'approved'}).status_code==405
    assert hashes(native)==before
    assert client.get('/api/runs/missing/review').status_code==404
    assert client.get('/api/runs/research-example/review?approve=true').status_code==422
    assert client.get('/api/runs/research-example/review',headers={'Origin':'https://example.com'}).status_code==403


def test_legacy_without_native_view_has_no_invented_review_scope(legacy):
    client=TestClient(create_app(legacy),base_url='http://127.0.0.1')
    response=client.get('/api/runs/research-example/review')
    assert response.status_code==409 and response.json()['error']['code']=='native_view_unavailable'


def test_private_review_rechecks_token_source_version_and_permissions(session):
    from test_workspace_local_research import ingest,request
    from test_workspace_fresh_close import worker
    from keystone.workspace.worker import run_one
    _,_,permission,version=ingest(session)
    job,_=session.submit(request(version),'review-foundation-private')
    with worker(session) as store:run_one(store)
    run_id='result-'+job['job_id'][4:];url=f'/api/runs/{run_id}/review'
    client=TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN)
    assert client.get(url).status_code==403
    response=client.get(url,headers=headers(session));assert response.status_code==200,response.text
    snapshot=response.json()['snapshot']
    assert snapshot['binding']['version_id']==version['id']
    assert snapshot['binding']['request_sha256']==job['request_sha256']
    assert snapshot['input_acceptance']=='accepted_for_processing'
    session.inputs.revoke_permission(permission['id'],'Fictional review test')
    refused=client.get(url,headers=headers(session))
    assert refused.status_code==403 and refused.json()['error']['code']=='input_policy_refused'
