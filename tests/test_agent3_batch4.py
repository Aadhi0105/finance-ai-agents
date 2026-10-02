"""Durability, offline replay, fail-closed exports and state recovery regressions."""
from copy import deepcopy
from datetime import date
import json
import socket
import subprocess
import sys

import duckdb
import pytest

from agent3 import bundles, execution, orchestrator
from agent3.catalyst_state import CatalystStore
from agent3.track_a import load_event_set
from agent3.news_funnel import run_funnel

ASOF = '2026-10-02T12:00:00+00:00'


def track_a(tmp_path, *, terminal=None, refused=False):
    attempt = execution.Attempt.create(tmp_path, {'event_type': 'semicap_earnings', 'source': 'fixture'})
    es = load_event_set('semicap_earnings', source='fixture')
    if refused:
        es.update(verdict='REFUSED', reason='insufficient history')
    result = orchestrator.analyze_assembled('semicap_earnings', es)
    attempt.checkpoint('assembled', {'assembled_inputs': es, 'n_event_types_tested': 1})
    attempt.checkpoint('result', {'result': result})
    attempt.finish(terminal or result['status'])
    return attempt


def article(**kw):
    return {'id': 'a', 'headline': 'ASML reports growth', 'body': 'Strong profit growth.',
            'published_at': '2026-10-02T09:00:00Z', 'retrieved_at': ASOF,
            'entities': ['ASML.AS'], 'source': 'Example', 'url': 'https://example.org/a',
            'language': 'en', **kw}


class Score:
    name = 'controlled'
    def score(self, item):
        return {'score': .3, 'confidence': None, 'scorer': self.name,
                'flag_review': False, 'review_reasons': []}


def track_b(tmp_path, *, items=None, scorer=None, terminal=None, mode='live'):
    request = {'ticker': 'ASML.AS', 'aliases': ['ASML'], 'max_age_days': 7,
               'data_mode': mode, 'scorer': 'controlled', 'as_of': ASOF}
    attempt = execution.Attempt.create(tmp_path, request)
    items = [article()] if items is None else items
    result = run_funnel(items, {'ASML.AS'}, scorer or Score(), aliases={'ASML.AS': ['ASML']},
                        as_of=ASOF, max_age_days=7, data_mode=mode)
    attempt.checkpoint('news_scoring', {'input_items': items, 'as_of': ASOF})
    attempt.checkpoint('news_result', {'result': result})
    attempt.finish(terminal or result['status'])
    return attempt


def sealed(attempt):
    return bundles.read_bundle(bundles.seal(attempt))


def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('offline replay attempted external I/O')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(orchestrator, 'load_event_set', forbidden)
    import agent3.sentiment as sentiment
    monkeypatch.setattr(sentiment, 'get_scorer', forbidden)
    monkeypatch.setenv('AGENT_STATS_VIA_MCP', '1')
    monkeypatch.setattr(orchestrator, '_event_study_fn', forbidden)


@pytest.mark.parametrize('terminal', [None, 'failed', 'unavailable'])
def test_track_a_exact_offline_rebuild_preserves_holds(tmp_path, monkeypatch, terminal):
    attempt = track_a(tmp_path, terminal=terminal)
    b = sealed(attempt)
    offline(monkeypatch)
    replay = bundles.replay(b)
    assert replay['verification'] == 'matched'
    assert replay['result'] == attempt.record['result']
    assert replay['result']['scenario']['distribution'] is None
    assert bundles.replay(b) == replay
    assert 'Historical quantiles:' not in bundles.export_html(b, replay)


def test_assembly_refusal_can_be_replayed(tmp_path, monkeypatch):
    b = sealed(track_a(tmp_path, refused=True))
    offline(monkeypatch)
    r = bundles.replay(b)
    assert r['verification'] == 'matched' and r['result']['status'] == 'refused'


@pytest.mark.parametrize('terminal', [None, 'failed', 'unavailable'])
@pytest.mark.parametrize('mode', ['fixture', 'live'])
def test_track_b_exact_replay_without_scoring(tmp_path, monkeypatch, terminal, mode):
    attempt = track_b(tmp_path, terminal=terminal, mode=mode)
    b = sealed(attempt)
    offline(monkeypatch)
    r = bundles.replay(b)
    assert r['verification'] == 'matched'
    assert r['result'] == attempt.record['result']
    if terminal or mode == 'fixture':
        assert r['result']['signals'][0]['level'] is None
        assert 'document tone=HELD' in bundles.export_html(b, r)


@pytest.mark.parametrize('items', [[], [article(published_at='2099-01-01T00:00:00Z')],
                                    [article(), article(id='b', headline='asml reports growth!')],
                                    [article(), article(body='Profit declines.')]])
def test_news_empty_excluded_duplicate_and_changed_stories_replay(tmp_path, items):
    assert bundles.replay(sealed(track_b(tmp_path, items=items)))['verification'] == 'matched'


def test_saved_scorer_failure_replayed_without_model(tmp_path, monkeypatch):
    class Broken:
        name = 'finbert'
        def score(self, item):
            raise RuntimeError('private SDK text')
    b = sealed(track_b(tmp_path, scorer=Broken(), terminal='unavailable'))
    offline(monkeypatch)
    r = bundles.replay(b)
    assert r['verification'] == 'matched'
    assert r['result']['scored_items'][0]['score_evidence']['error_type'] == 'RuntimeError'
    assert 'private SDK text' not in json.dumps(b)


def test_partial_failure_is_retained_but_not_fabricated_as_rebuild(tmp_path):
    a = execution.Attempt.create(tmp_path, {'ticker': 'ASML.AS'})
    a.finish('unavailable', 'provider_unavailable')
    b = sealed(a)
    r = bundles.replay(b)
    assert r['verification'] == 'not_rebuildable' and 'result' not in r
    assert 'No analytical output is verified' in bundles.export_html(b, r)


def test_write_once_and_attempt_identity_vs_content(tmp_path):
    a = track_a(tmp_path)
    b = track_a(tmp_path)
    ba, bb = sealed(a), sealed(b)
    assert ba['attempt_id'] != bb['attempt_id']
    assert ba['content_fingerprint'] == bb['content_fingerprint']
    assert ba['bundle_sha256'] != bb['bundle_sha256']
    assert bundles.seal(a).exists()
    a.record['reason'] = 'conflicting mutation'
    with pytest.raises(ValueError, match='conflict'):
        bundles.seal(a)


def test_input_fingerprint_changes_on_window_change(tmp_path):
    a = track_a(tmp_path)
    before = deepcopy(bundles.retained_inputs(a.record))
    a.record['assembled_inputs']['events'][0]['evt_stock'][0] += .01
    assert bundles.digest(before) != bundles.digest(bundles.retained_inputs(a.record))
    b = track_a(tmp_path)
    assert sealed(a)['content_fingerprint'] != sealed(b)['content_fingerprint']
    assert bundles.replay(sealed(a))['verification'] == 'mismatch'


@pytest.mark.parametrize('field', ['inputs', 'record', 'provenance', 'bundle_sha256'])
def test_tampered_bundle_rejected(tmp_path, field):
    a = track_a(tmp_path)
    b = sealed(a)
    b[field] = 'tampered'
    path = tmp_path/'tampered.json'
    path.write_text(json.dumps(b))
    with pytest.raises(ValueError):
        bundles.read_bundle(path)


def test_rehashed_output_still_must_reproduce(tmp_path):
    a = track_b(tmp_path)
    a.record['result']['signals'][0]['level'] = .99
    b = sealed(a)
    r = bundles.replay(b)
    assert r['verification'] == 'mismatch' and 'result' not in r
    with pytest.raises(ValueError):
        bundles.export_html(b, r)


def test_changed_saved_article_cannot_reuse_unbound_score(tmp_path):
    a = track_b(tmp_path)
    a.record['input_items'][0]['body'] = 'New content'
    assert bundles.replay(sealed(a))['verification'] == 'mismatch'


def test_legacy_and_running_records_cannot_claim_bundle_replay(tmp_path):
    a = execution.Attempt.create(tmp_path, {})
    with pytest.raises(ValueError):
        bundles.seal(a)
    with pytest.raises(ValueError, match='legacy'):
        bundles.read_bundle(a.path)


def test_export_escapes_untrusted_text_and_refuses_overwrite(tmp_path):
    a = track_a(tmp_path, refused=True)
    a.record['assembled_inputs']['reason'] = '<script>alert(1)</script>'
    a.record['result']['reason'] = '<script>alert(1)</script>'
    b = sealed(a)
    html = bundles.export_html(b, bundles.replay(b))
    assert '<script>' not in html and '&lt;script&gt;' in html
    path = tmp_path/'report.html'
    bundles.write_text_once(path, html)
    bundles.write_text_once(path, html)
    with pytest.raises(ValueError):
        bundles.write_text_once(path, 'overwrite')
    assert path.read_text() == html


def test_outcome_idempotency_conflict_and_tristate(tmp_path):
    store = CatalystStore(tmp_path/'state.db')
    try:
        for i, sig in enumerate([None, False, True]):
            study = {'event_type': 'e', 'caar_significant': sig, 'inference_status': 'unavailable' if sig is None else 'available'}
            store.record_outcome(str(i), study, {'verdict': 'HOLD_FOR_REVIEW'}, ['ASML.AS'])
            store.record_outcome(str(i), deepcopy(study), {'verdict': 'HOLD_FOR_REVIEW'}, ['ASML.AS'])
            with pytest.raises(ValueError, match='conflicting'):
                store.record_outcome(str(i), {**study, 'caar': .1}, {'verdict': 'HOLD_FOR_REVIEW'}, ['ASML.AS'])
        rows = store.outcomes_for('e')
        assert len(rows) == 3 and [r['significant'] for r in rows] == [True, False, None]
        assert all(r['pinned_peers'] == ['ASML.AS'] for r in rows)
        assert rows[-1]['inference_status'] == 'unavailable'
    finally:
        store.close()


def test_legacy_database_migration_does_not_invent_missing_evidence(tmp_path):
    path = str(tmp_path/'legacy.db')
    con = duckdb.connect(path)
    con.execute('CREATE TABLE event_outcomes(run_id VARCHAR PRIMARY KEY,event_type VARCHAR,run_ts TIMESTAMP,n_events INTEGER,caar DOUBLE,t_stat DOUBLE,significant BOOLEAN,verdict VARCHAR,confidence DOUBLE,pinned_peers VARCHAR)')
    con.execute("INSERT INTO event_outcomes VALUES ('old','e',CURRENT_TIMESTAMP,8,.01,NULL,NULL,'HOLD_FOR_REVIEW',NULL,'ASML.AS')")
    con.close()
    store = CatalystStore(path)
    try:
        row = store.outcomes_for('e')[0]
        assert row['significant'] is None and row['evidence_status'] == 'legacy_summary_only'
        assert row['inference_status'] == 'unknown'
        with pytest.raises(ValueError, match='legacy'):
            store.record_outcome('old', {'event_type': 'e'}, {})
    finally:
        store.close()


def test_calendar_transitions_corrections_and_missing_ids(tmp_path):
    store = CatalystStore(tmp_path/'calendar.db')
    try:
        args = ('release', 'ASML.AS', 'earnings', '2026-10-10')
        store.upsert_catalyst(*args)
        store.upsert_catalyst(*args)
        assert len(store.calendar_history('release')) == 1
        with pytest.raises(ValueError):
            store.upsert_catalyst(*args[:3], '2026-10-11')
        assert len(store.calendar_history('release')) == 1
        store.upsert_catalyst(*args[:3], '2026-10-11', reason='issuer corrected schedule')
        store.mark_status('release', 'occurred')
        with pytest.raises(ValueError):
            store.mark_status('release', 'upcoming')
        store.mark_status('release', 'upcoming', reason='occurrence entered in error')
        history = store.calendar_history('release')
        assert len(history) == 4 and history[1]['before']['scheduled_date'] == '2026-10-10'
        assert history[1]['after']['scheduled_date'] == '2026-10-11'
        assert len(store.upcoming(date(2026, 10, 1))) == 1
        with pytest.raises(KeyError):
            store.mark_status('missing', 'occurred')
        with pytest.raises(ValueError):
            store.mark_status('release', 'anything')
    finally:
        store.close()


def test_index_recovery_preserves_failed_terminal_state(tmp_path):
    a = track_a(tmp_path, terminal='failed')
    path = bundles.seal(a)
    store = CatalystStore(tmp_path/'index.db')
    try:
        r = a.record['result']
        store.record_outcome(a.record['run_id'], r['study'], r['gate'], r['pinned_peers'])
        store.index_bundle(path)
        store.index_bundle(path)
        rows = store.bundles()
        assert len(rows) == 1 and rows[0]['status'] == 'failed'
        assert rows[0]['reconciliation'] == 'summary_conflict_or_terminal_failure'
        assert store.outcomes_for('semicap_earnings')[0]['bundle_status'] == 'failed'
        b = bundles.read_bundle(path)
        b['record']['reason'] = 'new content, same attempt'
        b['bundle_sha256'] = bundles.digest({k: v for k, v in b.items() if k != 'bundle_sha256'})
        new = tmp_path/'conflict.json'
        new.write_text(json.dumps(b))
        with pytest.raises(ValueError, match='conflicting bundle'):
            store.index_bundle(new)
    finally:
        store.close()


def test_parent_timeout_seals_and_indexes(tmp_path, monkeypatch):
    a = execution.Attempt.create(tmp_path, {'db': str(tmp_path/'index.db')})
    class Worker:
        pid = 123
        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired('worker', timeout)
    monkeypatch.setattr(execution.subprocess, 'Popen', lambda *a, **k: Worker())
    monkeypatch.setattr(execution.os, 'killpg', lambda *a: None)
    assert execution.run_bounded(a, 1) == 4
    b = bundles.read_bundle(a.path.with_name('bundle.json'))
    assert b['record']['reason'] == 'run_deadline_exceeded'
    assert execution.read_record(a.path.with_name('index-receipt.json'))['indexed']


def test_bundle_survives_index_failure(tmp_path, monkeypatch, capsys):
    a = track_a(tmp_path)
    a.record['request']['db'] = str(tmp_path/'index.db')
    a.save()
    class Worker:
        returncode = 3
        def wait(self, timeout=None): pass
    monkeypatch.setattr(execution.subprocess, 'Popen', lambda *a, **k: Worker())
    monkeypatch.setattr(CatalystStore, 'index_bundle', lambda *a: (_ for _ in ()).throw(OSError('private path')))
    assert execution.run_bounded(a, 1) == 3
    assert bundles.read_bundle(a.path.with_name('bundle.json'))['record']['status'] == 'held'
    assert not execution.read_record(a.path.with_name('index-receipt.json'))['indexed']
    assert 'database index pending' in capsys.readouterr().out


def test_actual_news_worker_bundle_replay_export_and_index(tmp_path):
    fixture = tmp_path/'fixture.json'
    fixture.write_text(json.dumps({'items': [article()]}))
    output = tmp_path/'runs'
    command = [sys.executable, '-m', 'agent3.run_news', 'ASML.AS', '--alias', 'ASML',
               '--scorer', 'lm', '--fixture', str(fixture), '--as-of', ASOF.replace('+00:00', 'Z'),
               '--output-dir', str(output), '--db', str(tmp_path/'state.db')]
    run = subprocess.run(command, cwd=execution.ROOT, capture_output=True, text=True, timeout=30)
    assert run.returncode == 3, run.stdout + run.stderr
    path = next(output.glob('*/bundle.json'))
    replay = subprocess.run([sys.executable, '-m', 'agent3.bundles', str(path), '--output',
                             str(tmp_path/'replay.json'), '--html', str(tmp_path/'report.html'),
                             '--index-db', str(tmp_path/'recovered.db')],
                            cwd=execution.ROOT, capture_output=True, text=True, timeout=30)
    assert replay.returncode == 0, replay.stdout + replay.stderr
    assert execution.read_record(tmp_path/'replay.json')['verification'] == 'matched'
    assert 'HELD_FOR_REVIEW' in (tmp_path/'report.html').read_text()


def test_provider_partial_inputs_retained_before_later_failure(monkeypatch):
    import agent3.track_a_live as live
    def prices(tk, **kw):
        if tk.startswith('^'):
            raise RuntimeError('private provider data')
        return [(date(2026, 1, 1), 50.)]
    monkeypatch.setattr(live, '_fetch_prices', prices)
    retained = {}
    live.load_live_event_set('ASML.AS', [], 'earnings', checkpoint=lambda stage, data: retained.update(deepcopy(data)))
    snapshot = retained['provider_snapshots']['ASML.AS']
    assert snapshot['stock_prices'] == [['2026-01-01', 50.]]
    assert snapshot['stock_prices_retrieved_at']
    assert 'benchmark_prices' not in snapshot
    assert 'private provider data' not in json.dumps(retained)


@pytest.mark.parametrize('significant', [False, True])
def test_eligible_historical_and_null_replay_without_losing_tristate(tmp_path, monkeypatch, significant):
    from test_agent3_batch1 import event
    events = [event(i, .04 + .004*i if significant else (-.01 if i % 2 else .01)) for i in range(10)]
    controls = [event(i+20, -.01 if i % 2 else .01) for i in range(10)]
    peers = [e['ticker'] for e in events]
    es = {'verdict': 'OK', 'events': events, 'placebo_events': controls,
          'study_plan': {'hypotheses': ['earnings']}, 'comparability_status': 'human_reviewed',
          'contributing_peers': peers, 'pinned_peers': peers}
    a = execution.Attempt.create(tmp_path, {'event_type': 'earnings'})
    result = orchestrator.analyze_assembled('earnings', es)
    assert result['status'] == 'completed' and result['study']['caar_significant'] is significant
    a.checkpoint('assembled', {'assembled_inputs': es, 'n_event_types_tested': 1})
    a.checkpoint('result', {'result': result})
    a.finish('completed')
    b = sealed(a)
    offline(monkeypatch)
    replay = bundles.replay(b)
    assert replay['verification'] == 'matched'
    html = bundles.export_html(b, replay)
    assert ('Publication: HISTORICAL' if significant else 'Publication: NULL') in html
    assert 'Historical quantiles:' in html
    assert 'No forward predictive calibration is claimed' in html


def test_multiple_testing_setting_is_retained_and_rechecked(tmp_path):
    from test_agent3_batch1 import eligible_study
    study = eligible_study()
    result = {'status': 'completed', 'study': study,
              'gate': {'verdict': 'PASS', 'checks': [{'status': 'pass'}]},
              'scenario': {'verdict': 'HISTORICAL', 'publication_state': 'HISTORICAL',
                           'distribution': {'p25': .01, 'median_car': .02, 'p75': .03}},
              'comparability_status': 'human_reviewed', 'study_plan': {'hypotheses': ['earnings']},
              'contributing_peers': [str(i) for i in range(10)], 'n_event_types_tested': 2}
    assert not orchestrator.publication_allowed(result)


def test_source_version_change_is_disclosed_without_claiming_original_runtime(tmp_path, monkeypatch):
    b = sealed(track_a(tmp_path))
    monkeypatch.setattr(bundles, 'provenance', lambda: {})
    replay = bundles.replay(b)
    assert replay['verification'] == 'matched' and not replay['same_source_and_runtime']


def test_bundle_redacts_configured_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('PRIVATE_API_TOKEN', 'sensitive-placeholder-value')
    a = track_a(tmp_path)
    a.record['request']['note'] = 'sensitive-placeholder-value'
    path = bundles.seal(a)
    assert 'sensitive-placeholder-value' not in path.read_text()
    assert '[REDACTED]' in path.read_text()


def test_index_receipt_failure_cannot_rewrite_sealed_attempt(tmp_path, monkeypatch, capsys):
    a = track_a(tmp_path)
    a.record['request']['db'] = str(tmp_path/'index.db')
    a.save()
    original = bundles.write_once
    def fail_receipt(path, value):
        if path.name == 'index-receipt.json':
            raise OSError('disk error')
        return original(path, value)
    class Worker:
        returncode = 3
        def wait(self, timeout=None): pass
    monkeypatch.setattr(execution.subprocess, 'Popen', lambda *a, **k: Worker())
    monkeypatch.setattr(bundles, 'write_once', fail_receipt)
    assert execution.run_bounded(a, 1) == 3
    assert bundles.read_bundle(a.path.with_name('bundle.json'))['record']['status'] == 'held'
    assert a.record['status'] == 'held'
    assert 'receipt could not be written' in capsys.readouterr().out
