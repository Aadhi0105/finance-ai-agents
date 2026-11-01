"""Source-bound monitoring scopes, real offline correction flows and compatibility."""
import copy
from datetime import date
import hashlib
import json

import pytest

from test_native_reports import legacy, native, case, metric, chart
from keystone.workspace.report_views.projection import build_view
from keystone.workspace.report_views.series import prepare_series
from keystone.workspace.report_views.validation import validate_view
from keystone.workspace.report_views.values import canonical
from monitoring.reporting import load_snapshot
from monitoring.recovery import decide
from scheduler import cycle
from state.store import StateStore
from state.store import _json_date


def table(view, ident):
    return next(t for t in view['tables'] if t['id'] == ident)


def cell(row, name):
    return next(c for c in row['cells'] if c['column_id'] == name)


def render(native, source, version='1.1.0'):
    source = json.loads(json.dumps(source, default=_json_date))
    _, _, _, run, artifacts = case(native, 'monitoring')
    run = run.model_copy(update={'source_run_id': str(source['run']['cycle']),
        'native_view': run.native_view.model_copy(update={'adapter_version': version})})
    primary = artifacts[0].model_copy(update={'sha256': hashlib.sha256(canonical(source)).hexdigest()})
    series = prepare_series(run, source, primary)
    secondary = artifacts[1].model_copy(update={'sha256': hashlib.sha256(canonical(series)).hexdigest()})
    view = build_view(run, source, series, [primary, secondary])
    validate_view(view, run, source, series, [primary, secondary])
    return view


def test_real_saved_selected_cycle_and_export_have_different_breach_scopes(native):
    view, source, *_ = case(native, 'monitoring')
    assert metric(view, 'cycle-items')['value'] == '4'
    assert metric(view, 'cycle-breaches')['value'] == '1'
    assert metric(view, 'surfaced-items')['value'] == '2'
    assert metric(view, 'effective-items')['value'] == '5'
    assert metric(view, 'effective-breaches')['value'] == '2'
    original = table(view, 'cycle-observations')['rows']
    assert cell(original[0], 'breach')['text'] == 'No recorded breach'
    assert cell(original[0], 'attention')['text'] == 'Surfaced for attention'
    effective = table(view, 'effective-observations')['rows']
    delta = next(r for r in effective if cell(r, 'item')['text'] == 'delta_leverage')
    assert cell(delta, 'observed')['text'] == '2026-01-07'
    assert 'not verified contractual' in view['summary']['text']
    assert view['state']['financial_approval'] is False
    assert metric(view, 'effective-items')['period_label'].startswith('Snapshot export: ')
    assert 'Snapshot export:' in next(f for f in view['findings'] if f['id']=='finding-effective-items')['content']['text']


@pytest.mark.parametrize('status', ['NEW_BREACH', 'WIDENING', 'IMPROVING', 'KNOWN_STABLE'])
def test_breach_counts_use_boolean_not_classification_name(native, status):
    def edit(s): s['run']['rows'][1]['status'] = status
    view, *_ = case(native, 'monitoring', edit)
    assert metric(view, 'cycle-breaches')['value'] == '1'


def test_quiet_cycle_does_not_clear_ongoing_breaches(native):
    def edit(s): s['run']['surfaced'] = []
    view, *_ = case(native, 'monitoring', edit)
    assert metric(view, 'surfaced-items')['value'] == '0'
    assert metric(view, 'effective-breaches')['value'] == '2'


def test_no_new_observations_explicitly_does_not_reassess_compliance(native):
    def edit(s): s['run'].update(rows=[], surfaced=[], triage_history={})
    view, *_ = case(native, 'monitoring', edit)
    assert metric(view, 'cycle-items')['value'] == '0'
    assert 'Compliance was not reassessed' in view['summary']['text']
    assert metric(view, 'effective-breaches')['value'] == '2'
    assert not view['charts'][0]['series']


def test_baseline_suppression_is_explicit_and_does_not_erase_flags(native):
    def edit(s): s['run'].update(baseline=True, surfaced=[])
    view, *_ = case(native, 'monitoring', edit)
    assert 'alerting was suppressed' in view['summary']['text']
    assert metric(view, 'cycle-breaches')['value'] == '1'


@pytest.mark.parametrize('flag', [None, 'false', 0])
def test_incomplete_or_nonboolean_flags_withhold_count_instead_of_zero(native, flag):
    def edit(s): s['run']['rows'][0]['breached'] = flag
    view, *_ = case(native, 'monitoring', edit)
    assert metric(view, 'cycle-breaches')['value'] is None
    assert metric(view, 'cycle-breaches')['availability'] == 'withheld'


def test_unknown_units_never_become_available_values_or_history(native):
    def edit(s): s['run']['rows'][0]['metric'] = 'unregistered_metric'
    view, *_ = case(native, 'monitoring', edit)
    assert metric(view, 'cycle-value-0')['value'] is None
    assert chart(view, 'history-0')['series'] == []


@pytest.mark.parametrize('kind', ['missing', 'bad-date', 'duplicate-date'])
def test_history_requires_actual_valid_dated_source_rows(native, kind):
    def edit(s):
        h = s['run']['triage_history']
        if kind == 'missing': h.clear()
        elif kind == 'bad-date': next(iter(h.values()))[0]['data_ts'] = 'not-a-date'
        else: next(iter(h.values()))[1]['data_ts'] = next(iter(h.values()))[0]['data_ts']
    view, *_ = case(native, 'monitoring', edit)
    assert view['charts'][0]['availability'] != 'available'
    assert not view['charts'][0]['series']


def test_zero_history_point_is_retained_as_zero(native):
    def edit(s): next(iter(s['run']['triage_history'].values()))[0]['value'] = 0
    view, *_ = case(native, 'monitoring', edit)
    assert chart(view, 'history-0')['series'][0]['points'][0]['y'] == '0'


@pytest.fixture
def correction(tmp_path, monkeypatch):
    cov = dict(item_id='x', entity='Synthetic X', metric='current_ratio', covenant_type='test', threshold=3,
        direction='below', cycle_values={'1':1, '2':4, '3':5, '4':2, '5':2}, data_ts_by_cycle={'4':'2026-01-02'})
    monkeypatch.setattr(cycle, '_load_watchlist', lambda: ([cov], date(2026,1,1)))
    db = str(tmp_path / 'controlled.db')
    runs = [cycle.run_cycle(db_path=db) for _ in range(4)]
    store = StateStore(db)
    try: review = store.reviews()[0]['review_id']
    finally: store.close()
    return db, cov, runs, review, tmp_path


def test_real_held_correction_is_unapplied_and_original_history_is_not_restated(native, correction):
    db, _, runs, _, root = correction
    source = load_snapshot(db, cycle=3, audit_dir=root)
    before = copy.deepcopy(source)
    view = render(native, source)
    assert source == before and source['run'] == runs[2]
    assert metric(view, 'effective-value-0')['value'] == '5.0'
    assert metric(view, 'pending-value-0')['value'] == '2'
    assert metric(view, 'pending-previous-0')['value'] == '4.0'
    assert 'correction review pending' in cell(table(view, 'effective-observations')['rows'][0], 'state')['text']
    assert table(view, 'correction-decisions')['rows'] == []


@pytest.mark.parametrize('action', ['approve', 'reject'])
def test_real_decision_preserves_original_cycle_and_exposes_separate_decision_history(native, correction, action):
    db, _, runs, token, root = correction
    decide(db, token, action, 'Local analyst', 'Controlled source review')
    source = load_snapshot(db, cycle=3, audit_dir=root)
    view = render(native, source)
    assert source['run'] == runs[2]
    assert metric(view, 'reviews-count')['value'] == '0'
    assert metric(view, 'decisions-count')['value'] == '1'
    assert cell(table(view, 'correction-decisions')['rows'][0], 'action')['text'] == action
    rows = table(view, 'decision-observations')['rows']
    if action == 'approve':
        assert len(rows) == 6
        assert metric(view, 'decision-0-before-value-1')['value'] == '4'
        assert metric(view, 'decision-0-after-value-1')['value'] == '2'
    else:
        assert rows == []  # Rejection does not manufacture a restated history.


def test_definition_decision_keeps_replacement_series_distinct(native, correction):
    db, cov, _, token, root = correction
    decide(db, token, 'reject', 'Local analyst', 'Withdraw correction')
    cov['threshold'] = 7
    cycle.run_cycle(db_path=db)
    store = StateStore(db)
    try: token = store.reviews()[0]['review_id']
    finally: store.close()
    decide(db, token, 'approve', 'Local analyst', 'New definition', replacement_id='x-v2')
    source = load_snapshot(db, cycle=3, audit_dir=root)
    view = render(native, source)
    assert any('retired series; replacement item: x-v2' in cell(r, 'state')['text'] for r in table(view, 'effective-observations')['rows'])
    assert any(cell(r, 'item')['text'] == 'x-v2' and cell(r, 'side')['text'] == 'after' for r in table(view, 'decision-observations')['rows'])
    assert metric(view, 'effective-breaches')['value'] == '0'  # Retired breached row remains evidence, not an active item.


def test_unreadable_audits_keep_empty_attempts_from_becoming_success(native):
    def edit(s): s.update(unreadable_audits=1)
    view, *_ = case(native, 'monitoring', edit)
    assert any(r['title'] == 'Triage audit coverage is incomplete' for r in view['review_items'])


def test_registered_10_recipe_remains_available_without_11_context(native):
    _, source, *_ = case(native, 'monitoring')
    view = render(native, source, '1.0.0')
    assert view['summary']['template_id'] == 'saved-summary-v1'
    assert not any(t['id'] == 'monitor-basis' for t in view['tables'])
    assert not any(m['id'] == 'cycle-breaches' for m in view['metrics'])


def test_changed_summary_count_is_refused_even_when_still_schema_valid(native):
    view, source, series, run, artifacts = case(native, 'monitoring')
    metric(view, 'cycle-breaches')['value'] = '0'
    with pytest.raises(ValueError):
        validate_view(view, run, source, series, artifacts)


def test_attempt_metadata_does_not_publish_raw_model_commentary_or_local_paths(native):
    def edit(s):
        s['attempts'] = [dict(execution=dict(status='failed',run_id='synthetic-attempt'),
            model_mode='offline_stub',publication='withheld',commentary='UNVERIFIED ACTION',artifact='/private/qa/audit.json')]
    view, *_ = case(native, 'monitoring', edit)
    row = table(view, 'triage-attempts')['rows'][0]
    assert cell(row, 'status')['text'] == 'failed'
    assert cell(row, 'attempt')['text'] == 'synthetic-attempt'
    assert 'UNVERIFIED ACTION' not in str(view) and '/private/qa' not in str(view)


def test_qa_workspace_preserves_sources_refuses_overwrite_and_serves_every_family(native, tmp_path):
    from scripts.prepare_monitoring_report_qa import prepare
    from test_native_reports import client, hashes
    before = hashes(native)
    destination = tmp_path / 'qa-workspace'
    receipt = prepare(native, destination)
    assert hashes(native) == before
    assert receipt['production_release_approved'] is False
    api = client(destination)
    runs = api.get('/api/runs').json()['runs']
    assert len(runs) == 13
    for run in runs:
        assert api.get('/api/runs/' + run['id'] + '/report-view').status_code == 200
    held = api.get('/api/runs/monitor-pending/report-view').json()
    assert metric(held, 'reviews-count')['value'] == '1'
    with pytest.raises(FileExistsError): prepare(native, destination)
    assert hashes(native) == before
    with pytest.raises(ValueError): prepare(native, native / 'forbidden-child')
    assert not (native / 'forbidden-child').exists()
