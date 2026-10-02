"""Issuer-date acceptance and non-human validation plan safeguards."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from agent3.study_plan import validate_plan
from agent3.validation import assess
from agent3.track_a_live import assemble_peer_events, load_live_event_set
from test_agent3_batch1 import eligible_study, plan, series

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('bad', ['true', 1, None, [], {}])
def test_validation_only_requires_boolean(bad):
    p = plan(); p['validation_only'] = bad
    with pytest.raises(ValueError, match='validation_only'):
        validate_plan(p, ['ASML.AS'], 'earnings')


def test_validation_only_cannot_promote_otherwise_eligible_study():
    study = eligible_study()
    p = {'hypotheses': ['earnings']}
    assert assess(study, study_plan=p, comparability_status='human_reviewed')['verdict'] == 'PASS'
    for flag in [True, 'true', None, 1]:
        gate = assess(study, study_plan={**p, 'validation_only': flag}, comparability_status='human_reviewed')
        assert gate['verdict'] == 'HOLD_FOR_REVIEW'
        assert any(c['check'] == 'validation_only' and c['status'] == 'fail' for c in gate['checks'])


@pytest.mark.parametrize('filename,tk', [('asml-as-source-plan.json','ASML.AS'), ('nvda-source-plan.json','NVDA')])
def test_issuer_source_plans_anchor_to_correct_session(filename, tk):
    p = json.loads((ROOT/'fixtures/agent3_closure'/filename).read_text())
    validate_plan(p, [tk], 'issuer_date_validation')
    c = p['companies'][tk]
    stock, market = series()
    events, _, report = assemble_peer_events(tk, stock, market,
        [{**e, 'date_status': 'reviewed'} for e in c['reviewed_events']],
        exchange_timezone=c['timezone'], benchmark=c['benchmark'], company=c, plan=p)
    assert report['assembled'] == 5
    by_timestamp = {e['release_timestamp']:e for e in c['reviewed_events']}
    for event in events:
        assert event['anchor_date'] == by_timestamp[event['release_timestamp']]['expected_anchor_date']
        assert event['date_status'] == event['benchmark_status'] == 'source_checked'
        assert event['design_status'] == 'unverified'
        assert len(event['est_dates']) == 250 and len(event['window_dates']) == 3


def test_failure_location_retained_without_exception_secrets(monkeypatch):
    def unavailable(*args, **kwargs):
        raise ValueError('secret-provider-token')
    monkeypatch.setattr('agent3.track_a_live._fetch_prices', unavailable)
    result = load_live_event_set('ASML.AS', [], 'earnings')
    report = result['per_peer_report'][0]
    assert report['failure_stage'] == 'stock_prices'
    assert report['failure_location']['function'] == 'unavailable'
    assert isinstance(report['failure_location']['line'], int)
    assert 'secret-provider-token' not in json.dumps(result)


def test_raw_price_oracle_detects_tampered_windows_and_dates(tmp_path, monkeypatch):
    from agent3 import bundles, execution, orchestrator
    from scripts.check_agent3_closure import verify
    stock, market = series()
    monkeypatch.setattr('agent3.track_a_live._fetch_prices', lambda ticker, **kwargs: market if ticker == '^AEX' else stock)
    p = json.loads((ROOT/'fixtures/agent3_closure/asml-as-source-plan.json').read_text())
    attempt = execution.Attempt.create(tmp_path, {'event_type': 'issuer_date_validation', 'source': 'live'})
    es = load_live_event_set('ASML.AS', [], 'issuer_date_validation', study_plan=p, checkpoint=attempt.checkpoint)
    result = orchestrator.analyze_assembled('issuer_date_validation', es)
    attempt.checkpoint('assembled', {'assembled_inputs': es, 'n_event_types_tested': 1})
    attempt.checkpoint('result', {'result': result})
    attempt.finish(result['status'])
    bundle = bundles.read_bundle(bundles.seal(attempt))
    assert verify(bundle)['status'] == 'passed'
    missing = deepcopy(bundle)
    missing['record']['assembled_inputs']['events'].pop()
    with pytest.raises(ValueError, match='missing or unexpected issuer events'):
        verify(missing)
    for field, value, error in [('anchor_date','2026-01-29','date mismatch'),
                                ('evt_stock',[.9,.9,.9], 'evt_stock mismatch'),
                                ('date_status','reviewed','mislabeled')]:
        changed = deepcopy(bundle)
        changed['record']['assembled_inputs']['events'][0][field] = value
        with pytest.raises(ValueError, match=error):
            verify(changed)
