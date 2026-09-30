"""Batch 2 integration at real adapter, process, publication and recovery boundaries."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from agent3 import execution, orchestrator, peers, run_live
from agent3.execution import Attempt, read_record
from agent3.track_a import load_event_set


def proposal():
    return {'sector': 'equipment', 'peers': ['asm.as', 'BESI.AS'],
            'rationale': 'Equipment peers with distinct product exposure',
            'assessments': [{'ticker': t, 'rationale': 'Related equipment; product mix differs',
                             'source_urls': ['https://example.org/issuer']} for t in ['ASM.AS', 'BESI.AS']]}


def sdk(monkeypatch, text, stop='end_turn', block_type='text'):
    """Mock HTTP only: exercise AnthropicModel.respond and SDK response conversion."""
    import anthropic
    from anthropic import _base_client
    # Use the transport package selected by the installed SDK (httpx or httpx2).
    httpx = getattr(_base_client, 'httpx2', None) or _base_client.httpx
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'id': 'msg_test', 'type': 'message', 'role': 'assistant',
                              'model': 'test-model', 'stop_reason': stop, 'stop_sequence': None,
                              'content': [{'type': block_type, 'text': text}],
                              'usage': {'input_tokens': 20, 'output_tokens': 40}})
    client = anthropic.Anthropic(api_key='test-key', http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(peers.AnthropicModel, '_lazy_client', lambda self: client)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    return requests


def request(tmp_path):
    return {'ticker': 'ASML.AS', 'event_type': 'earnings', 'peers': ['ASM.AS'],
            'live_propose': False, 'study_plan': None, 'db': str(tmp_path / 'state.duckdb'), 'transport': '0'}


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    import dotenv
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *a, **k: None)
    monkeypatch.delenv('AGENT3_LIVE_PROPOSE', raising=False)
    monkeypatch.delenv('AGENT_STATS_VIA_MCP', raising=False)


def test_real_shared_adapter_and_audited_unverified_decision(monkeypatch):
    requests = sdk(monkeypatch, json.dumps(proposal()))
    checkpoints = []
    result = peers.propose_peers('asml.as', live=True,
                                 checkpoint=lambda s, d: checkpoints.append(deepcopy(d)))
    assert len(requests) == 1 and requests[0]['tools'] == []
    assert result['peers'] == ['ASM.AS', 'BESI.AS']
    assert result['comparability_status'] == 'unverified'
    assert result['assessments'][0]['evidence_status'] == 'unverified_model_claim'
    audit = result['proposal_audit']
    assert audit['status'] == 'accepted_unverified' and audit['request_id'] == 'msg_test'
    assert audit['model'] and audit['system'] and audit['messages'] and audit['response'] and audit['usage']
    assert checkpoints[-1]['pinned_peer_set']['peers'] == result['peers']


@pytest.mark.parametrize('raw,stop', [
    ('I cannot help. {"peers": ["ASM.AS"]}', 'end_turn'),
    (json.dumps(proposal()), 'max_tokens'),
    (json.dumps(proposal()), 'refusal'),
    ('{"peers":"ABC"}', 'end_turn'),
    ('[]', 'end_turn'),
    ('{"sector":"x","rationale":"x","peers":[]}', 'end_turn'),
    ('{"peers": [NaN]}', 'end_turn'),
    ('Refused. ```json\n' + json.dumps(proposal()) + '\n```', 'end_turn'),
    ('{"peers":[],"peers":["ASM.AS"]}', 'end_turn'),
])
def test_model_refusals_and_invalid_shapes_cannot_be_accepted(monkeypatch, raw, stop):
    requests = sdk(monkeypatch, raw, stop)
    with pytest.raises(peers.PeerProposalError) as caught:
        peers.propose_peers('ASML.AS', live=True)
    assert caught.value.audit['status'] == 'refused'
    assert len(requests) == 1


@pytest.mark.parametrize('mutation', [
    lambda p: p.update(assessments=[]),
    lambda p: p['assessments'][0].update(ticker='OTHER'),
    lambda p: p['assessments'][0].update(source_urls=['file:///etc/passwd']),
    lambda p: p['assessments'][0].update(source_urls=['https://user:pass@example.org']),
    lambda p: p['assessments'][0].update(rationale=''),
    lambda p: p.update(peers=[True]),
    lambda p: p.update(peers=['X'] * 21),
])
def test_peer_assessment_schema(monkeypatch, mutation):
    p = proposal(); mutation(p)
    sdk(monkeypatch, json.dumps(p))
    with pytest.raises(peers.PeerProposalError):
        peers.propose_peers('ASML.AS', live=True)


def test_live_missing_credentials_never_falls_back_to_stub(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', '  ')
    with pytest.raises(peers.PeerProposalError, match='missing_credentials'):
        peers.propose_peers('ASML.AS', live=True)
    assert load_event_set('earnings', source='yfinance', ticker='ASML.AS')['verdict'] == 'REFUSED'
    # Explicit empty list is target-only and bypasses the model, not a missing override.
    assert peers.propose_peers('ASML.AS', override=[], live=True)['proposed_by'] == 'override'


def test_model_error_redacts_exception_and_has_no_retry(monkeypatch, tmp_path):
    calls = []
    def fail(self):
        calls.append(1)
        raise RuntimeError('secret-key-example credential')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'secret-key-example')
    monkeypatch.setattr(peers.AnthropicModel, '_lazy_client', fail)
    req = request(tmp_path); req.update(peers=None, live_propose=True)
    attempt = Attempt.create(tmp_path / 'runs', req)
    assert execution.execute(attempt) == 4
    saved = read_record(attempt.path)
    assert saved['stage'] == 'peer_selection' and saved['reason'] == 'model_unavailable'
    assert 'secret-key-example' not in attempt.path.read_text() and len(calls) == 1
    assert saved['peer_proposal_audit']['error_type'] == 'RuntimeError'


def test_mcp_error_is_unavailable_and_not_a_pass(monkeypatch):
    monkeypatch.setattr(orchestrator, '_event_study_fn', lambda: lambda *a: {'error': 'MCP rejected'})
    result = orchestrator.analyze_event_type('semicap_earnings')
    assert result['status'] == 'unavailable'
    assert 'UNAVAILABLE' in orchestrator.render_brief(result)
    assert 'UNAVAILABLE' in orchestrator.render_scan([result])
    assert 'scenario' not in result


def test_attempt_database_failure_retains_result_as_held(monkeypatch, tmp_path):
    import agent3.catalyst_state as state
    result = orchestrator.analyze_event_type('semicap_earnings')
    monkeypatch.setattr(execution, 'analyze_event_type', lambda *a, **k: deepcopy(result))
    monkeypatch.setattr(state, 'CatalystStore', lambda *a: (_ for _ in ()).throw(OSError('private password')))
    attempt = Attempt.create(tmp_path / 'runs', request(tmp_path))
    assert execution.execute(attempt) == 5
    saved = read_record(attempt.path)
    assert saved['stage'] == 'persistence' and saved['result']['status'] == 'failed'
    assert saved['result']['scenario']['distribution'] is None
    assert 'private password' not in attempt.path.read_text()


@pytest.mark.parametrize('change', [
    lambda r: r['scenario'].update(publication_state='CALIBRATED', verdict='CALIBRATED'),
    lambda r: r['gate'].update(verdict='UNKNOWN'),
    lambda r: r['gate'].update(checks=[]),
    lambda r: r['study'].update(caar_significant=None),
    lambda r: r['study'].update(caar=True),
    lambda r: r['scenario'].update(distribution={'p25': float('nan')}),
    lambda r: r.update(status='failed'),
])
def test_output_modes_fail_closed_for_stale_or_unknown_states(change):
    result = {'event_type': 'earnings', 'status': 'completed',
              'study': {'caar': .02, 'p_value': .001, 'inference_status': 'available', 'caar_significant': True},
              'gate': {'verdict': 'PASS', 'checks': [{'status': 'pass'}]},
              'scenario': {'verdict': 'HISTORICAL', 'publication_state': 'HISTORICAL',
                           'distribution': {'p25': .01, 'median_car': .02, 'p75': .03}}}
    change(result)
    assert not orchestrator.publication_allowed(result)
    text = orchestrator.render_brief(result) + orchestrator.render_scan([result])
    assert 'CALIBRATED' not in text and 'Historical quantiles:' not in text


def test_retry_pins_peers_and_review_request_without_mutating_original(monkeypatch, tmp_path, capsys):
    req = request(tmp_path); req.update(peers=None, live_propose=True)
    original = Attempt.create(tmp_path / 'runs', req)
    pinned = peers._pin('ASML.AS', proposal(), 'model')
    original.checkpoint('assembly', {'pinned_peer_set': pinned})
    original.finish('unavailable', 'run_deadline_exceeded')
    before = original.path.read_bytes()
    captured = []
    def run(attempt, timeout):
        captured.append(deepcopy(attempt.record))
        attempt.finish('refused', 'test_stop_before_network')
        return 2
    monkeypatch.setattr(run_live, 'run_bounded', run)
    assert run_live.main(['--retry-from', str(original.path), '--output-dir', str(tmp_path / 'runs')]) == 2
    retried = captured[0]
    assert retried['request']['peers'] == ['ASM.AS', 'BESI.AS']
    assert retried['request']['live_propose'] is False
    assert retried['request']['study_plan'] == original.record['request']['study_plan']
    assert retried['retry_peer_set'] == pinned
    assert retried['run_id'] != original.record['run_id'] and original.path.read_bytes() == before
    assert run_live.main(['--retry-from', str(original.path), '--peers', 'OTHER']) == 2
    assert len(captured) == 1


@pytest.mark.parametrize('args', [[], ['ASML.AS', 'e', '--timeout', '0'],
                                 ['ASML.AS', 'e', '--study-plan', '/does/not/exist'],
                                 ['ASML.AS', 'e', '--peers', 'bad/ticker'],
                                 ['ASML.AS', 'e', '--peers', '--live-propose']])
def test_cli_configuration_fails_without_network_or_traceback(monkeypatch, tmp_path, capsys, args):
    monkeypatch.setattr(run_live, 'run_bounded', lambda *a: pytest.fail('must not launch'))
    assert run_live.main(args + ['--output-dir', str(tmp_path)]) == 2
    assert 'Traceback' not in capsys.readouterr().err


def test_bounded_worker_deadline_kills_process_and_retains_checkpoint(monkeypatch, tmp_path):
    attempt = Attempt.create(tmp_path / 'runs', request(tmp_path))
    attempt.checkpoint('assembly', {'per_peer_report': [{'ticker': 'ASM.AS', 'assembled': 1}]})
    real_popen = subprocess.Popen
    processes = []
    def spawn(*args, **kwargs):
        p = real_popen([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
        processes.append(p)
        return p
    monkeypatch.setattr(execution.subprocess, 'Popen', spawn)
    start = time.monotonic()
    assert execution.run_bounded(attempt, .1) == 4
    assert time.monotonic() - start < 5 and processes[0].poll() is not None
    saved = read_record(attempt.path)
    assert saved['reason'] == 'run_deadline_exceeded'
    assert saved['stage'] == 'assembly' and saved['per_peer_report']


def test_real_worker_missing_credentials_from_foreign_cwd(monkeypatch, tmp_path):
    monkeypatch.setenv('ANTHROPIC_API_KEY', '')
    req = request(tmp_path); req.update(peers=None, live_propose=True)
    attempt = Attempt.create(tmp_path / 'runs', req)
    monkeypatch.chdir(tmp_path)
    assert execution.run_bounded(attempt, 30) == 4
    saved = read_record(attempt.path)
    assert saved['reason'] == 'missing_credentials'
    assert saved['peer_proposal_audit']['status'] == 'refused'


def test_store_accepts_bare_filename_and_default_is_anchored(monkeypatch, tmp_path):
    from agent3.catalyst_state import CatalystStore, _DEFAULT_DB
    assert Path(_DEFAULT_DB).is_absolute()
    monkeypatch.chdir(tmp_path)
    store = CatalystStore('bare.duckdb')
    store.close()
    assert (tmp_path / 'bare.duckdb').exists()


def test_cli_dotenv_uses_repo_path_without_overriding_shell(monkeypatch, tmp_path):
    import dotenv
    calls = []
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(run_live, 'run_bounded', lambda a, t: (a.finish('unavailable', 'test'), 4)[1])
    assert run_live.main(['ASML.AS', 'earnings', '--output-dir', str(tmp_path)]) == 4
    assert calls == [((execution.ROOT / '.env',), {'override': False})]


def test_exact_json_fence_is_accepted_with_original_response_retained(monkeypatch):
    raw = '```json\n' + json.dumps(proposal()) + '\n```'
    sdk(monkeypatch, raw)
    pinned = peers.propose_peers('ASML.AS', live=True)
    assert pinned['peers'] == ['ASM.AS', 'BESI.AS']
    assert pinned['proposal_audit']['response'][0]['text'] == raw


def test_eligible_history_renders_and_inconsistent_saved_pass_is_held():
    from test_agent3_batch1 import eligible_study
    from agent3.scenario import scenario_from_event_study
    from agent3.validation import assess
    study = eligible_study()
    plan = {'hypotheses': ['earnings']}
    scenario = scenario_from_event_study(study)
    scenario['publication_state'] = scenario['verdict']
    result = {'event_type': 'earnings', 'status': 'completed', 'study': study,
              'study_plan': plan, 'comparability_status': 'human_reviewed',
              'contributing_peers': [e['ticker'] for e in study['per_event']],
              'scenario': scenario, 'gate': assess(study, study_plan=plan, comparability_status='human_reviewed')}
    assert orchestrator.publication_allowed(result)
    assert 'Historical quantiles:' in orchestrator.render_brief(result)
    result['study']['n_events'] = 999
    assert not orchestrator.publication_allowed(result)
    assert 'Historical quantiles:' not in orchestrator.render_brief(result)


def test_all_provider_failures_are_unavailable_and_accounted(monkeypatch):
    import agent3.track_a_live as live
    monkeypatch.setattr(live, '_fetch_prices', lambda *a, **kw: (_ for _ in ()).throw(ConnectionError('credential-url')))
    result = orchestrator.analyze_event_type('earnings', source='yfinance', ticker='ASML.AS', peers=['ASM.AS'])
    assert result['status'] == 'unavailable'
    assert result['excluded_peers'] == ['ASML.AS', 'ASM.AS']
    assert all('ConnectionError' in r['error'] for r in result['per_peer_report'])
    assert 'credential-url' not in json.dumps(result)


@pytest.mark.parametrize('website,expected', [('https://www.tel.com', 'provider_consistent'),
                                            ('https://www.te.com', 'unresolved_identity'),
                                            (None, 'unresolved_identity')])
def test_model_listing_domain_consistency(monkeypatch, website, expected):
    import agent3.track_a_live as live
    monkeypatch.setattr(live, '_fetch_identity', lambda tk: {'symbol': tk, 'quoteType': 'EQUITY', 'website': website})
    result = live._identity_check('TEL', {'source_urls': ['https://www.tel.com/ir']})
    assert result['status'] == expected


def test_model_identity_mismatch_is_excluded_before_prices(monkeypatch):
    import agent3.track_a_live as live
    monkeypatch.setattr(live, '_fetch_identity', lambda tk: {'symbol': tk, 'quoteType': 'EQUITY', 'website': 'https://www.te.com'})
    calls = []
    def prices(tk, **kw):
        calls.append(tk)
        return []
    monkeypatch.setattr(live, '_fetch_prices', prices)
    monkeypatch.setattr(live, '_fetch_earnings_dates', lambda *a: [])
    result = live.load_live_event_set('ASML.AS', ['TEL'], 'earnings',
                                      peer_assessments={'TEL': {'source_urls': ['https://www.tel.com']}})
    assert 'TEL' not in calls
    report = result['per_peer_report'][1]
    assert report['excluded'] and report['identity_check']['status'] == 'unresolved_identity'


def test_retry_preserves_model_identity_checks_and_skips_proposal(monkeypatch):
    import agent3.track_a_live as live
    pinned = peers._validate_model(proposal(), 'ASML.AS')
    monkeypatch.setattr(peers, 'propose_peers', lambda *a, **k: pytest.fail('must reuse saved proposal'))
    captured = []
    def assemble(*args, **kwargs):
        captured.append(kwargs)
        return {'verdict': 'REFUSED', 'events': []}
    monkeypatch.setattr(live, 'load_live_event_set', assemble)
    result = load_event_set('earnings', source='yfinance', ticker='ASML.AS', peers=pinned['peers'], peer_decision=pinned)
    assert set(captured[0]['peer_assessments']) == {'ASM.AS', 'BESI.AS'}
    assert result['pinned_peer_set'] == pinned


def test_provider_error_records_failure_operation_without_raw_message(monkeypatch):
    import agent3.track_a_live as live
    monkeypatch.setattr(live, '_fetch_prices', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('secret-url')))
    result = live.load_live_event_set('ASML.AS', [], 'earnings')
    assert result['per_peer_report'][0]['failure_stage'] == 'stock_prices'
    assert 'secret-url' not in json.dumps(result)


@pytest.mark.parametrize('field,value', [('study', []), ('scenario', 'bad'), ('gate', []),
                                         ('per_peer_report', [False])])
def test_malformed_saved_sections_render_as_held(field, value):
    result = {'event_type': 'e', field: value}
    assert not orchestrator.publication_allowed(result)
    text = orchestrator.render_brief(result) + orchestrator.render_scan([result])
    assert 'HELD_FOR_REVIEW' in text and 'Historical quantiles:' not in text


def test_guarded_mcp_transport_produces_normal_study():
    code = """
from mcp_server.client import run_event_study
from agent3.track_a import load_event_set
es=load_event_set('semicap_earnings', source='fixture')
r=run_event_study(es['events'], 'semicap_earnings', es['placebo_events'])
assert r['n_events'] == 8 and r['inference_status'] != 'available'
"""
    env = dict(os.environ, AGENT_MCP_PARENT_GUARD='1')
    result = subprocess.run([sys.executable, '-c', code], cwd=execution.ROOT,
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_parent_watchdog_stops_detached_server_when_worker_dies(tmp_path):
    # The heartbeat proves the detached process stopped executing after parent loss.
    heartbeat = tmp_path / 'heartbeat'
    server = """
from mcp_server.parent_guard import start_parent_watchdog
import os, time
from pathlib import Path
start_parent_watchdog(os.getppid())
p=Path(%r)
while True:
    p.write_text(str(time.monotonic()))
    time.sleep(.02)
""" % str(heartbeat)
    parent_code = """
import subprocess, sys, time
subprocess.Popen([sys.executable, '-c', %r], start_new_session=True)
time.sleep(30)
""" % server
    parent = subprocess.Popen([sys.executable, '-c', parent_code], cwd=execution.ROOT)
    try:
        deadline = time.monotonic() + 5
        while not heartbeat.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert heartbeat.exists()
        parent.kill(); parent.wait()
        time.sleep(.3)
        last = heartbeat.read_text()
        time.sleep(.3)
        assert heartbeat.read_text() == last
    finally:
        if parent.poll() is None:
            parent.kill(); parent.wait()
