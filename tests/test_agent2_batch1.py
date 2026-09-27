"""Independent boundary, timing and alert regressions for Agent 2 batch 1."""
import json
import math
from datetime import date
import pytest
from tools.covenant_checks import threshold_check
from tools.statistical_checks import anomaly_significance_check, drift_check, breach_probability, _first_passage_prob
from scheduler import cycle
from state.store import StateStore
from monitoring.triage import recheck_flag


@pytest.mark.parametrize('bad', [None, True, '3', float('nan'), float('inf'), -float('inf')])
def test_invalid_observation_never_looks_safe(bad):
    assert threshold_check(bad, 3, 'below')['breached'] is None
    for result in (anomaly_significance_check([1]*6+[bad]),
                   drift_check(list(range(7)), [1]*6+[bad]),
                   breach_probability([1]*6+[bad], 3, 'below')):
        assert 'error' in result
        json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('arguments', [dict(min_obs=True),dict(min_obs=1),dict(horizon=0),dict(horizon=True),dict(horizon=-1),dict(tail_at=0),dict(tail_at=1.1),dict(tail_at=float('nan'))])
def test_invalid_probability_parameters(arguments):
    assert 'error' in breach_probability([1]*7, 3, 'below', **arguments)


@pytest.mark.parametrize('times', [[0]*6, [0,1,2], [0,1,2,4,3,5], [0,1,2,3,4,float('nan')]])
def test_invalid_time_axis(times):
    assert 'error' in drift_check(times,[1]*6)


def test_threshold_preserves_sub_display_precision():
    result = threshold_check(3+1e-8,3,'below')
    assert result['breached'] and result['margin'] > 0


def test_strict_deterministic_crossing():
    assert not threshold_check(3,3,'below')['breached']
    assert breach_probability([3]*6,3,'below')['breach_probability'] == 0
    assert _first_passage_prob(0,-1,0,6) == 0
    assert _first_passage_prob(0,1,0,6) == 1
    assert _first_passage_prob(6,1,0,6) == 0
    assert _first_passage_prob(5,1,0,6) == 1
    assert _first_passage_prob(-1,-1,0,6) == 1


def test_brownian_zero_drift_reflection_identity_and_stable_tail():
    assert _first_passage_prob(1,0,1,1) == pytest.approx(math.erfc(1/math.sqrt(2)))
    # Independent direct erfc expression in a range where its factors are representable.
    a,m,s,t = 1,1,.1,.5
    scale=s*math.sqrt(t)
    expected=.5*math.erfc((a-m*t)/scale/math.sqrt(2))+math.exp(2*m*a/s**2)*.5*math.erfc((a+m*t)/scale/math.sqrt(2))
    assert _first_passage_prob(a,m,s,t) == pytest.approx(expected,rel=1e-12,abs=0)
    assert math.isfinite(_first_passage_prob(1,1,1e-8,1))


def test_perfect_trend_is_explicit_and_json_safe():
    r=drift_check([0,2,4,6,8,10],[0,1,2,3,4,5],threshold=6,direction='below')
    assert r['drifting'] and r['slope']==.5 and r['toward_breach']
    assert r['slope_tstat'] is None and r['inference_status']=='zero_residual_trend'
    assert r['cycles_to_breach_at_current_drift']==2
    json.dumps(r,allow_nan=False)


def test_away_drift_does_not_hide_high_crossing_risk():
    b=breach_probability([2,0,2,0,2,1],1.1,'below')
    assert b['tail_flag'] and not b['toward_breach']
    row={'status':'OK','breach_tail':True,'breach_prob':b['breach_probability'],'_breach_detail':b}
    assert cycle._surfaces(row)
    assert any('BREACH_PROB' in t for t in cycle._stat_tags(row))


def test_threshold_breach_alone_requires_escalation():
    class Store:
        def get_history_series(self,item):return []
    result=recheck_flag(Store(),{'x':{'entity':'X','breached':True}},'x')
    assert result['verdict']=='breach' and 'escalate' in result['recommendation']


def covenant(values, dates=None):
    return {'item_id':'x','entity':'X','metric':'m','covenant_type':'test','threshold':10,'direction':'below',
            'cycle_values':{str(k):v for k,v in values.items()},'data_ts_by_cycle':dates or {}}


@pytest.mark.parametrize('patch', [{'threshold':float('nan')},{'direction':'wrong'},{'cycle_values':{'1':True}}, {'data_ts_by_cycle':{'1':'2026-02-01'}}])
def test_bad_watchlist_cannot_write_state(tmp_path,monkeypatch,patch):
    cov={**covenant({1:1}),**patch}
    monkeypatch.setattr(cycle,'_load_watchlist',lambda:([cov],date(2026,1,1)))
    db=str(tmp_path/'t.duckdb')
    with pytest.raises(ValueError):cycle.run_cycle(db_path=db)
    store=StateStore(db)
    try:assert store.full_state()==[] and store.next_cycle()==1
    finally:store.close()


def test_duplicate_watchlist_rejected(tmp_path,monkeypatch):
    cov=covenant({1:1})
    monkeypatch.setattr(cycle,'_load_watchlist',lambda:([cov,cov],date(2026,1,1)))
    with pytest.raises(ValueError):cycle.run_cycle(db_path=str(tmp_path/'t.duckdb'))


def test_irregular_spacing_keeps_dated_drift_but_refuses_probability(tmp_path,monkeypatch):
    cov=covenant({1:1,2:2,4:4,5:5,7:7,8:8})
    monkeypatch.setattr(cycle,'_load_watchlist',lambda:([cov],date(2026,1,1)))
    db=str(tmp_path/'t.duckdb')
    for n in [1,2,4,5,7,8]:r=cycle.run_cycle(db_path=db,asof_cycle=n)
    row=r['rows'][0]
    assert row['drift_slope']==1  # per actual elapsed day, not per observation
    assert row['_drift_detail']['time_unit']=='days'
    assert row['breach_prob'] is None
    assert 'irregular' in row['_breach_detail']['reason']


def test_fixed_interval_probability_declares_calendar_horizon(tmp_path,monkeypatch):
    cov=covenant({n:float(n) for n in [1,3,5,7,9,11]})
    monkeypatch.setattr(cycle,'_load_watchlist',lambda:([cov],date(2026,1,1)))
    db=str(tmp_path/'t.duckdb')
    for n in [1,3,5,7,9,11]:r=cycle.run_cycle(db_path=db,asof_cycle=n)
    assert r['rows'][0]['_breach_detail']['horizon_days']==12


def test_mcp_probability_and_zero_residual_are_json_safe():
    from mcp_server.client import breach_probability as remote_breach, drift_check as remote_drift
    assert remote_breach([3]*6,3,'below')==breach_probability([3]*6,3,'below')
    args=([0,1,2,3,4,5],[0,1,2,3,4,5])
    result=remote_drift(*args)
    assert result==drift_check(*args)
    json.dumps(result,allow_nan=False)


def test_mcp_does_not_coerce_boolean_observations():
    from mcp_server.client import breach_probability as remote
    assert 'error' in remote([True]*6,3,'below')


def test_cycle_rejects_entire_batch_before_writing_valid_rows(tmp_path,monkeypatch):
    good=covenant({1:1});bad={**covenant({1:float('nan')}),'item_id':'bad'}
    monkeypatch.setattr(cycle,'_load_watchlist',lambda:([good,bad],date(2026,1,1)))
    db=str(tmp_path/'t.duckdb')
    with pytest.raises(ValueError):cycle.run_cycle(db_path=db)
    store=StateStore(db)
    try:assert store.full_state()==[]
    finally:store.close()
