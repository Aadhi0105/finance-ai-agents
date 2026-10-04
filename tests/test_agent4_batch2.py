"""History/current alignment and adversarial publication-boundary regressions."""
from copy import deepcopy
import json
import pytest
from agent4.hierarchy import rollup
from agent4.commentary import build_registry, compose, reconcile
from agent4.output import board_pack, exception_view
from agent4.persistence import classify_persistence
from agent4.materiality import classify_variance
from agent4.reforecast import reforecast


def fixture():
    with open('fixtures/pnl.json') as stream:
        return rollup(json.load(stream))


def nodes(tree):
    yield tree
    for c in tree.get('children',[]):yield from nodes(c)


def test_current_variance_used_once_and_stale_persistence_refused():
    tree=fixture();premium=next(n for n in nodes(tree) if n['name']=='Product Premium')
    h=premium['history_snapshot']
    assert h['current_cents']==4080000 and h['prior_cents'][-1]==195000
    assert premium['persistence']['persistence']=='ONE_OFF'
    stale=classify_persistence(h['prior_cents'], name=premium['name'])
    assert stale['persistence']=='STRUCTURAL'
    with pytest.raises(ValueError,match='current node history'):
        board_pack(tree,persistence_by_line={premium['name']:stale})


@pytest.mark.parametrize('values',[[1,-1,1,-1,1,-1,float('nan')],[True]*7,None,[1.2]*7])
def test_invalid_persistence_cannot_be_one_off(values):
    r=classify_persistence(values)
    assert r['persistence']=='UNKNOWN' and r['confidence'] is None


def test_deterministic_break_metadata_retained():
    r=classify_variance({'name':'X','total_variance_cents':500},10000,100000,[0]*6)
    assert r['significance']['inference_status']=='zero_dispersion_break'
    assert 'not a stochastic' in r['reason']
    p=classify_persistence([0]*6+[500])
    assert p['diagnostic']['inference_status']=='zero_dispersion_break'
    assert p['provisional'] and 'not a calibrated' in p['confidence_kind']


def test_dated_gap_holds_analysis():
    t={'name':'Profit','context':{'close_date':'2026-09-30'},'children':[
        {'name':'Sales','sign':'add','leaf':{'name':'Sales','type':'revenue','budget':{'amount':100},'actual':{'amount':200}},
         'history_frequency':'monthly','observation_history':[
             {'period':f'2026-{m:02}-28','variance_cents':100} for m in [1,2,3,4,5,7]]}]}
    row=rollup(t)['children'][0]
    assert row['history_snapshot']['gaps']
    assert row['persistence']['persistence']=='UNKNOWN'
    assert row['significance']['significant'] is None
    assert row['significance']['inference_status']=='held_history_gap'


@pytest.mark.parametrize('text,refs,tier',[
    ('Sales were €999,999.00.',{'actual':99999900},'computed_fact'),
    ('P(hit target) 99%.',{},'observation'),
    ('Classified TOP_PRIORITY with confidence 0.99.',{'quadrant':'TOP_PRIORITY','confidence':.99},'observation'),
    ('The new supplier caused the loss.',{},'hypothesis'),
    ('Actual USD 999999; 99 employees; margin 800 bps.',{},'computed_fact'),
    ('Definitely verified by the issuer.',{},'fabricated')])
def test_audit_forgery_cases_rejected(text,refs,tier):
    registry=build_registry(fixture())
    assert not reconcile([{'tier':tier,'text':text,'refs':refs}],registry)['passed']


@pytest.mark.parametrize('mutation',['text','refs','tier','node','registry','omission','duplicate'])
def test_tampered_canonical_claims_rejected(mutation):
    tree=fixture();registry=build_registry(tree);claims=compose(tree)
    assert reconcile(claims,registry)['passed']
    if mutation=='text':claims[0]['text']+=' USD 999999 from a new supplier.'
    elif mutation=='refs':claims[0]['refs'][0]['field']='forged_actual'
    elif mutation=='tier':claims[0]['tier']='hypothesis'
    elif mutation=='node':claims[0]['node_id']='Other'
    elif mutation=='registry':claims[0]['registry_id']='older_close'
    elif mutation=='omission':claims.pop()
    else:claims.append(deepcopy(claims[0]))
    assert not reconcile(claims,registry)['passed']


def test_mutated_registry_and_classification_fail():
    tree=fixture();registry=build_registry(tree);claims=compose(tree)
    registry['snapshot']['tree']['actual_cents']+=1
    assert not reconcile(claims,registry)['passed']
    tree['quadrant']='TOP_PRIORITY'
    with pytest.raises(ValueError,match='classification changed'):board_pack(tree)


def test_root_forecast_publishes_band_target_horizon_assumptions():
    tree=fixture();rf=reforecast(60000,120000,2,4,variance_history_cents=[-10000,10000]*4,name=tree['name'])
    pack=board_pack(tree,reforecast_by_line={tree['node_id']:rf})
    claim=next(c for c in pack['commentary'] if c['kind']=='forecast' and c['node_id']==tree['node_id'])
    assert '80% range' in claim['text'] and 'Target €1,200.00' in claim['text']
    assert 'remaining periods 2' in claim['text'] and 'uncalibrated model estimate' in claim['text']
    assert 'not inferred from single-close actuals' in claim['text']
    assert pack['reforecasts'][tree['node_id']]['band_cents']==rf['band_cents']
    assert 'registry' in pack and 'full_hierarchy' in pack
    json.dumps(pack,allow_nan=False)


def test_forecast_mutation_wrong_line_and_wrong_close_refused():
    tree=fixture();rf=reforecast(600,1200,2,4,name=tree['name'])
    rf['projected_landing_cents']+=1
    with pytest.raises(ValueError):board_pack(tree,reforecast_by_line={tree['name']:rf})
    rf=reforecast(600,1200,2,4,name='Materials')
    with pytest.raises(ValueError):board_pack(tree,reforecast_by_line={tree['name']:rf})
    raw={'name':'Profit','context':{'close_date':'2026-09-30'},'children':[{'name':'Sales','sign':'add','leaf':{'name':'Sales','type':'revenue','budget':{'amount':1},'actual':{'amount':2}}}]}
    with pytest.raises(ValueError):board_pack(rollup(raw),reforecast_by_line={'Profit':reforecast(100,1200,1,12,name='Profit',close_period='2026-08-31')})


def test_held_and_unavailable_forecasts_are_visible():
    tree=fixture()
    for rf in [reforecast(100,1200,1,4,name=tree['name']),reforecast(100,1200,1,4,budget_phasing_cents=[1],name=tree['name'])]:
        pack=board_pack(tree,reforecast_by_line={tree['name']:rf})
        text=next(c['text'] for c in pack['commentary'] if c['kind']=='forecast')
        assert 'unavailable' in text or 'held for review' in text


def test_unaligned_trend_rejected_and_aligned_trend_point_only():
    assert 'error' in reforecast(100,1200,1,12,actual_history_cents=[10000]*8)
    history=[100]*8;dates=[f'2026-{m:02}-28' for m in range(1,9)]
    r=reforecast(800,1200,8,12,actual_history_cents=history,actual_periods=dates,
                 frequency='monthly',close_period=dates[-1],variance_history_cents=[-10,10]*4)
    assert r['method'].startswith('time-series') and r['projected_landing_cents']==1200
    assert r['band_cents'] is None and r['prob_hit_target'] is None
    assert 'parameter uncertainty' in r['reason']


def test_unknown_persistence_does_not_publish_probability():
    r=reforecast(100,1200,1,4,persistence='UNKNOWN',variance_history_cents=[-10,10]*4)
    assert r['prob_hit_target'] is None and r['publication_status']=='point_only'


def test_exception_claim_set_and_closed_year_probability():
    tree=fixture();rf=reforecast(100,1200,4,4,name=tree['name'])
    pack=exception_view(tree,reforecast_by_line={tree['name']:rf})
    assert pack['reconciliation']['passed']
    claim=next(c for c in pack['commentary'] if c['kind']=='forecast')
    assert '0%' in claim['text'] and 'deterministic closed-year' in claim['text']
