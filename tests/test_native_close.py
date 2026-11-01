"""Real saved close outputs, exact bridge bindings and truthful display scopes."""
import copy
import hashlib
from decimal import Decimal
import pytest

from test_native_reports import legacy, native, case, metric, chart, hashes, client
from keystone.workspace.report_views.projection import build_view
from keystone.workspace.report_views.series import prepare_series
from keystone.workspace.report_views.validation import validate_view
from keystone.workspace.report_views.values import canonical, digest
from scripts.prepare_close_report_qa import close_cases, prepare


def table(view, ident): return next(t for t in view['tables'] if t['id']==ident)
def cell(row, column): return next(c for c in row['cells'] if c['column_id']==column)


@pytest.fixture(scope='module')
def closes(tmp_path_factory): return close_cases(tmp_path_factory.mktemp('saved-closes'))


def render(native, source, version='1.1.0'):
    _, _, _, run, artifacts=case(native,'close')
    run=run.model_copy(update={'source_run_id':source['run_id'],'entity':source['request']['entity'],
        'native_view':run.native_view.model_copy(update={'adapter_version':version})})
    primary=artifacts[0].model_copy(update={'sha256':hashlib.sha256(canonical(source)).hexdigest()})
    series=prepare_series(run,source,primary)
    secondary=artifacts[1].model_copy(update={'sha256':hashlib.sha256(canonical(series)).hexdigest()})
    view=build_view(run,source,series,[primary,secondary])
    validate_view(view,run,source,series,[primary,secondary])
    return view,series,run,[primary,secondary]


def test_default_close_reconciles_and_cost_amount_is_distinct_from_profit_effect(native):
    view, *_=case(native,'close')
    assert [Decimal(metric(view,i)['value']) for i in ['close-budget-cents','close-actual-cents','close-total-variance-cents']]==[60,65,5]
    points=chart(view,'close-bridge')['series'][0]['points']
    assert [(p['start'],p['end']) for p in points]==[('0','60'),('60','70'),('70','65'),('0','65')]
    assert metric(view,'account-2-total-variance-cents')['value']=='5'
    assert metric(view,'account-2-profit-impact')['value']=='-5'
    assert metric(view,'forecast-projected-landing-cents')['value']=='780'
    assert metric(view,'forecast-band-0')['value'] is None
    assert metric(view,'forecast-prob-hit-target')['value'] is None
    assert view['summary']['template_id']=='close-summary-v1'
    assert view['state']['financial_approval'] is False


@pytest.mark.parametrize('name',['close-loss','close-zero','close-cost','close-held','close-uncertainty','close-yearend','close-many','close-corrected'])
def test_real_offline_close_cases_preserve_saved_results(native,closes,name):
    source=closes[name];before=copy.deepcopy(source)
    view,*_=render(native,source)
    assert source==before
    assert Decimal(metric(view,'close-actual-cents')['value'])*100==source['report']['full_hierarchy']['actual_cents']
    assert view['identity']['period_end']==source['request']['close_period']
    assert view['state']['financial_approval'] is False


def test_standalone_cost_bridge_increase_is_adverse(native,closes):
    view,*_=render(native,closes['close-cost'])
    step=chart(view,'close-bridge')['series'][0]['points'][1]
    assert (step['y'],step['start'],step['end'],step['assessment'])==('5','40','45','adverse')


def test_held_forecast_has_no_available_published_values(native,closes):
    view,*_=render(native,closes['close-held'])
    assert all(m['value'] is None and m['availability']=='withheld' for m in view['metrics'] if m['id'].startswith('forecast-') or m['id'].startswith('account-forecast-'))
    assert 'Withheld' in str(table(view,'forecast-basis'))


def test_point_only_never_promotes_raw_interval_or_probability(native,closes):
    source=copy.deepcopy(closes['close-original'])
    rf=source['report']['reforecasts']['profit'];rf.update(band_cents=[1,999999],prob_hit_target=.7)
    with pytest.raises(ValueError):render(native,source)


def test_populated_interval_and_probability_keep_their_saved_model_basis(native,closes):
    source=closes['close-uncertainty'];view,*_=render(native,source)
    rf=source['report']['reforecasts']['profit']
    assert rf['publication_status']=='model_estimate'
    assert metric(view,'forecast-band-0')['availability']=='available'
    assert Decimal(metric(view,'forecast-band-0')['value'])*100==rf['band_cents'][0]
    assert metric(view,'forecast-prob-hit-target')['visibility']=='diagnostic'


def test_closed_year_is_realised_target_outcome_not_forward_probability(native,closes):
    view,*_=render(native,closes['close-yearend'])
    assert 'no remaining horizon' in metric(view,'forecast-prob-hit-target')['label']
    assert metric(view,'forecast-prob-hit-target')['value']=='1.0'
    assert metric(view,'forecast-band-0')['value']==metric(view,'forecast-band-1')['value']


def test_correction_keeps_original_delta_effective_versions_and_dated_history_distinct(native,closes):
    original,*_=render(native,closes['close-original'])
    corrected,*_=render(native,closes['close-corrected'])
    assert metric(original,'forecast-projected-landing-cents')['value']=='780'
    assert metric(corrected,'forecast-projected-landing-cents')['value']=='800'
    assert metric(corrected,'close-actual-cents')['value']=='65'  # Correction was to January, not June.
    assert len(table(corrected,'submitted-actuals')['rows'])==1
    assert len(table(corrected,'effective-actuals')['rows'])==12
    assert cell(next(r for r in table(corrected,'close-basis')['rows'] if r['id']=='supersedes'),'value')['text']=='qa-original'
    assert chart(original,'close-variance-history')['series'][0]['points'][0]['y']=='5'
    assert chart(corrected,'close-variance-history')['series'][0]['points'][0]['y']=='15'


def test_many_accounts_are_complete_and_not_hidden_by_exception_selection(native,closes):
    view,*_=render(native,closes['close-many'])
    assert len(table(view,'accounts')['rows'])==33
    assert len(chart(view,'close-bridge')['series'][0]['points'])==34
    assert len(table(view,'budget-panel')['rows'])==384
    assert len(view['metrics'])<=500


@pytest.mark.parametrize('damage',['source-panel','source-version','reported-total','original-delta'])
def test_operator_refuses_contradictory_financial_evidence(native,closes,damage):
    source=copy.deepcopy(closes['close-original'])
    if damage=='source-panel':source['sources']['budget'][0]['amount_cents']+=1
    if damage=='source-version':source['lineage']['budget']['version']='wrong-version'
    if damage=='reported-total':source['report']['full_hierarchy']['actual_cents']+=1
    if damage=='original-delta':source['request']['actuals']['rows'][0]['amount_cents']+=1;source['request_digest']=digest(source['request'])
    with pytest.raises(ValueError):render(native,source)


@pytest.mark.parametrize('damage',['value','start','end','assessment'])
def test_changed_retained_bridge_is_refused_even_with_new_hash_and_matching_view(native,closes,damage):
    source=closes['close-original'];view,series,run,artifacts=render(native,source)
    series['derivations']['bridge']['data'][1][damage]='adverse' if damage=='assessment' else '999'
    artifacts[1]=artifacts[1].model_copy(update={'sha256':hashlib.sha256(canonical(series)).hexdigest()})
    view=build_view(run,source,series,artifacts)
    with pytest.raises(ValueError):validate_view(view,run,source,series,artifacts)


def test_old_close_recipe_is_unchanged_and_readable(native,closes):
    view,*_=render(native,closes['close-original'],'1.0.0')
    assert view['summary']['template_id']=='saved-summary-v1'
    assert not any(t['id']=='close-basis' for t in view['tables'])


def test_qa_prepare_preserves_sources_refuses_overwrite_and_all_workflows_read(native,tmp_path,monkeypatch):
    before=hashes(native);dest=tmp_path/'close-qa';receipt=prepare(native,dest)
    assert hashes(native)==before and receipt['production_release_approved'] is False
    api=client(dest)
    import agent4.close,agent4.report
    def forbidden(*a,**k):raise AssertionError('Reading reran an engine')
    monkeypatch.setattr(agent4.close,'execute_close',forbidden)
    monkeypatch.setattr(agent4.report,'validate_bundle',forbidden)
    runs=api.get('/api/runs').json()['runs'];assert len(runs)==14
    for run in runs:assert api.get('/api/runs/'+run['id']+'/report-view').status_code==200
    with pytest.raises(FileExistsError):prepare(native,dest)
    with pytest.raises(ValueError):prepare(native,native/'forbidden-child')
    assert hashes(native)==before
