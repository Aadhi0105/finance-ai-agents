"""Financial correctness regressions, using independent oracles and failure boundaries."""
from copy import deepcopy
from datetime import date, timedelta
import json
import math
import random
import statistics

import numpy as np
import pytest
from scipy import stats

from tools.significance import one_sample_t, t_critical, mean_ci
from tools.event_study import run_event_study, _car_for_event
from agent3.track_a_live import assemble_peer_events, _event_record, home_index, load_live_event_set
from agent3.study_plan import validate_plan
from agent3.scenario import scenario_from_event_study
from agent3.validation import assess


REVIEW = {'reviewed_by':'test reviewer', 'reviewed_at':'2026-09-29T12:00:00Z',
          'rationale':'Synthetic evidence for controlled tests only', 'source_url':'https://example.org/issuer'}


def event(i=0, car=.02):
    rng=random.Random(40+i)
    market=[rng.gauss(0,.01) for _ in range(250)]
    stock=[.001+1.3*m for m in market]
    anchor=date(2015,1,1)+timedelta(days=10*i)
    return {'release_timestamp':str(anchor)+'T08:00:00+00:00', 'exchange_timezone':'UTC', 'session':'before_open',
            'ticker':f'TEST{i}', 'issuer_id':f'issuer-{i}', 'event_date':str(anchor),
            'anchor_date':str(anchor),'est_stock':stock,'est_market':market,
            'evt_stock':[.001+car/3]*3,'evt_market':[0.0]*3,
            'est_dates':[str(anchor-timedelta(days=400-j)) for j in range(250)],
            'window_dates':[str(anchor+timedelta(days=j)) for j in (-1,0,1)],
            'date_status':'reviewed','benchmark_status':'reviewed','design_status':'reviewed',
            'review_evidence':{k:dict(REVIEW) for k in ['date','benchmark','design']}}


def eligible_study():
    events=[event(i, .04+i*.004) for i in range(10)]
    controls=[event(i+20, -.01 if i%2 else .01) for i in range(10)]
    return run_event_study(events, 'earnings', controls)


def series():
    ds=[]; d=date(2023,1,2); rng=random.Random(88); s=m=100.; stock=[]; market=[]
    while len(ds)<1000:
        if d.weekday()<5:
            ds.append(d); m*=1+rng.gauss(.0002,.008); s*=1+rng.gauss(.0004,.01)
            stock.append((d,s)); market.append((d,m))
        d+=timedelta(days=1)
    return stock,market


def company():
    return {'issuer_id':'ASML','benchmark':'^AEX','timezone':'Europe/Amsterdam',
            'stock_return_basis':'price_return','benchmark_return_basis':'price_return',
            'benchmark_review':dict(REVIEW),
            'reviewed_events':[{**REVIEW,'release_timestamp':'2026-07-15T07:00:00+02:00','session':'before_open'}]}


def plan():
    return {'schema_version':1,'event_class':'earnings','companies':{'ASML.AS':company()},
            'comparability_review':dict(REVIEW),'sampling_review':dict(REVIEW),'hypotheses':['earnings']}


@pytest.mark.parametrize('dof',[1,7,11,13,16,21,31,100])
def test_exact_cutoff_and_decision_agree_with_scipy(dof):
    n=dof+1; z=np.arange(n,dtype=float);z=(z-z.mean())/z.std(ddof=1)
    for t in [1.96,2.0, float(stats.t.ppf(.975,dof))*.999, float(stats.t.ppf(.975,dof))*1.001]:
        vals=(z+t/math.sqrt(n)).tolist(); r=one_sample_t(vals); oracle=stats.ttest_1samp(vals,0)
        assert r['p_value']==pytest.approx(oracle.pvalue)
        assert r['significant']==bool(oracle.pvalue < .05)
    assert t_critical(dof)==pytest.approx(stats.t.ppf(.975,dof))


def test_confidence_level_is_honored_and_invalid_settings_rejected():
    vals=[.01,.03,-.02,.07]
    for level in ['90','95','99']:
        oracle=stats.ttest_1samp(vals,0).confidence_interval(float(level)/100)
        assert mean_ci(vals,level)['ci']==pytest.approx([oracle.low,oracle.high])
    for value in [True,0,-1,1.5]:
        with pytest.raises(ValueError):t_critical(value)
    for level in [True,'nan',0,100]:
        with pytest.raises(ValueError):mean_ci(vals,level)


def test_market_model_matches_independent_lstsq():
    e=event();e['est_stock']=[x+.001*math.sin(i) for i,x in enumerate(e['est_stock'])]
    alpha,beta=np.linalg.lstsq(np.column_stack([np.ones(250),e['est_market']]),e['est_stock'],rcond=None)[0]
    expected=np.array(e['evt_stock'])-alpha-beta*np.array(e['evt_market'])
    r=_car_for_event(e)
    assert r['alpha']==pytest.approx(alpha,abs=1e-14)
    assert r['beta']==pytest.approx(beta,abs=1e-14)
    assert r['car']==pytest.approx(expected.sum(),abs=1e-14)


@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),'0.01',-1.,-1.1])
def test_invalid_nested_returns_are_accounted_and_block_inference(bad):
    e=event();e['evt_stock'][0]=bad
    r=run_event_study([e,event(1)])
    assert r['n_events']==1 and r['rejected_events'][0]['index']==0
    assert r['caar_significant'] is None
    json.dumps(r,allow_nan=False)


@pytest.mark.parametrize('field,value',[('evt_stock',[]),('est_market',[0.]*250),('ticker',None),('event_date','yesterday')])
def test_missing_windows_rank_and_identity(field,value):
    e=event();e[field]=value
    r=run_event_study([e]);assert r['n_events']==0 and r['rejected_events']


def test_duplicate_and_overlap_do_not_add_observations():
    e=event();dup=deepcopy(e);overlap=deepcopy(e)
    overlap['anchor_date']=overlap['event_date']='2015-01-02'
    overlap['window_dates']=['2015-01-01','2015-01-02','2015-01-03']
    r=run_event_study([e,dup,overlap]*10)
    assert r['n_events']==1 and len(r['rejected_events'])==29
    assert r['p_value'] is None


def test_repeated_issuer_and_shared_dates_withhold_inference_and_bootstrap():
    events=[event(i) for i in range(10)]
    for e in events:e['issuer_id']='same-firm'
    r=run_event_study(events)
    assert r['n_issuers']==1 and 'repeated_issuer_dependence' in r['inference_reasons']
    assert r['caar_significant'] is None
    s=scenario_from_event_study(r,n_boot=200)
    assert s['verdict']=='UNDETERMINED' and s['distribution']['mean_ci95'] is None
    assert s['bootstrap']['replicates']==0
    events=[event(i) for i in range(10)]
    for e in events:e['window_dates']=events[0]['window_dates'];e['anchor_date']=events[0]['anchor_date']
    r=run_event_study(events)
    assert 'overlapping_cross_issuer_windows' in r['inference_reasons']


def test_available_inference_requires_evidence_and_has_valid_control():
    r=eligible_study()
    assert r['inference_status']=='available' and r['caar_significant'] is True
    assert r['placebo']['inference_status']=='available' and r['placebo']['caar_significant'] is False
    assert r['p_value']==pytest.approx(stats.ttest_1samp([e['car'] for e in r['per_event']],0).pvalue)
    events=[event(i) for i in range(10)]
    for e in events:e.pop('review_evidence')
    assert 'missing_review_evidence' in run_event_study(events)['inference_reasons']


def test_family_adjustment_and_fail_closed_gate():
    r=eligible_study()
    g=assess(r,contributing_peers=10,study_plan={'hypotheses':['earnings','other']},comparability_status='human_reviewed')
    assert g['verdict']=='PASS' and g['adjusted_p_value']==pytest.approx(r['p_value']*2)
    assert assess(r)['verdict']=='HOLD_FOR_REVIEW'
    assert assess({})['verdict']=='HOLD_FOR_REVIEW'
    for p in [None,{'caar_significant':None}]:
        altered={**r,'placebo':p}
        assert assess(altered,study_plan={'hypotheses':['earnings']},comparability_status='human_reviewed')['verdict']=='HOLD_FOR_REVIEW'


@pytest.mark.parametrize('nboot',[0,-1,True,1.5,100001])
def test_invalid_bootstrap_configuration_never_emits_nan(nboot):
    s=scenario_from_event_study(eligible_study(),n_boot=nboot)
    assert s['verdict']=='REFUSED' and s['distribution'] is None
    json.dumps(s,allow_nan=False)


def test_timezone_conversion_retains_provider_evidence_and_requires_review():
    raw={'release_timestamp':'2026-01-27T19:00:00-05:00','session':'unknown'}
    rec=_event_record(raw,'Europe/Amsterdam')
    assert str(rec['release_date'])=='2026-01-28'
    assert rec['provider_timestamp']==raw['release_timestamp']
    stock,market=series()
    ev,_,_=assemble_peer_events('ASML.AS',stock,market,[raw])
    assert ev[0]['event_date']=='2026-01-28' and ev[0]['date_status']=='unverified'
    assert ev[0]['anchor_date']=='2026-01-28'


def test_issuer_review_overrides_provider_date_without_fixed_offset(monkeypatch):
    from agent3 import track_a_live as live
    stock,market=series()
    monkeypatch.setattr(live,'_fetch_prices',lambda tk,**kw: market if tk.startswith('^') else stock)
    # A reviewed issuer list replaces provider event selection, not a guessed +1 offset.
    monkeypatch.setattr(live,'_fetch_earnings_dates',lambda tk:pytest.fail('should use the reviewed issuer record'))
    r=load_live_event_set('asml.as',[],'earnings',study_plan=plan())
    e=r['events'][0]
    assert e['anchor_date']=='2026-07-15' and e['window_dates']==['2026-07-14','2026-07-15','2026-07-16']
    assert e['review_evidence']['date']['source_url']==REVIEW['source_url']
    assert e['date_status']=='reviewed'


@pytest.mark.parametrize('session,expected',[('before_open','2026-07-17'),('during_session','2026-07-17'),('after_close','2026-07-20')])
def test_release_session_controls_trading_anchor(session,expected):
    stock,market=series()
    e={**REVIEW,'release_timestamp':'2026-07-17T17:00:00+02:00','session':session,'date_status':'reviewed'}
    events,_,_=assemble_peer_events('ASML.AS',stock,market,[e])
    assert events[0]['anchor_date']==expected
    assert len(events[0]['est_stock'])==250 and len(events[0]['evt_stock'])==3
    dates=[d for d,_ in stock];i=dates.index(date.fromisoformat(expected))
    assert events[0]['est_dates'][0]==str(dates[i-280])
    assert events[0]['est_dates'][-1]==str(dates[i-31])


def test_same_anchor_is_rejected_and_gaps_disclosed():
    stock,market=series(); days=[date(2026,7,18),date(2026,7,19)]
    ev,_,rep=assemble_peer_events('ASML.AS',stock,market,days)
    assert len(ev)==1 and len(rep['rejected_events'])==1
    market=[row for row in market if row[0]!=date(2026,7,16)]
    ev,_,_=assemble_peer_events('ASML.AS',stock,market,[date(2026,7,20)])
    assert ev[0]['quality_flags']==['calendar_gap_or_missing_bar']


def test_bad_prices_and_unknown_benchmarks_are_not_silently_used():
    stock,market=series()
    with pytest.raises(ValueError):assemble_peer_events('ASML.AS',stock+stock[-1:],market,[date(2026,1,28)])
    stock[300]=(stock[300][0],0)
    with pytest.raises(ValueError):assemble_peer_events('ASML.AS',stock,market,[date(2026,1,28)])
    assert home_index('asml.as')=='^AEX'
    with pytest.raises(ValueError):home_index('UNKNOWN.XYZ')


def test_plan_must_cover_exact_universe_and_compatible_return_basis():
    p=plan();assert validate_plan(p,['ASML.AS'],'earnings')==p
    for mutate in [lambda p:p['companies']['ASML.AS'].update(benchmark_return_basis='total_return'),
                   lambda p:p.update(hypotheses=['other']),
                   lambda p:p['companies']['ASML.AS']['reviewed_events'][0].pop('source_url')]:
        p=plan();mutate(p)
        with pytest.raises((ValueError,KeyError)):validate_plan(p,['ASML.AS'],'earnings')
    with pytest.raises(ValueError):validate_plan(plan(),['ASML.AS','ASM.AS'],'earnings')


def test_invalid_source_and_peer_types_are_not_demo_fallbacks():
    from agent3.track_a import load_event_set
    from agent3.peers import _pin
    with pytest.raises(ValueError):load_event_set('semicap_earnings',source='yfinanc')
    with pytest.raises(ValueError):_pin('ASML.AS',{'peers':'ABC'},'model')


def test_actual_mcp_matches_local_and_rejects_boolean_returns():
    from mcp_server.client import run_event_study as remote
    events=[event(i,.02+i*.001) for i in range(10)]
    assert remote(events,'earnings')==run_event_study(events,'earnings')
    e=event();e['evt_stock'][0]=True
    local=run_event_study([e],'earnings'); actual=remote([e],'earnings')
    assert actual==local and actual['rejected_events'] and actual['caar_significant'] is None


def test_unknown_inference_survives_storage(tmp_path):
    from agent3.catalyst_state import CatalystStore
    store=CatalystStore(str(tmp_path/'state.duckdb'))
    try:
        store.record_outcome('unknown',{'event_type':'earnings','caar_significant':None},{'verdict':'HOLD_FOR_REVIEW'})
        assert store.outcomes_for('earnings')[0]['significant'] is None
    finally:store.close()


def test_correlated_panel_simulations_cannot_manufacture_an_independent_p_value():
    for seed in range(12):
        rng=random.Random(seed)
        observations=[]
        for firm in range(3):
            shared=rng.gauss(.01,.05)
            for quarter in range(8):
                e=event(firm*8+quarter,shared+rng.gauss(0,.001));e['issuer_id']=f'firm-{firm}'
                observations.append(e)
        result=run_event_study(observations)
        assert result['caar_significant'] is None and result['p_value'] is None
        scenario=scenario_from_event_study(result,n_boot=200)
        assert scenario['distribution']['mean_ci95'] is None


def test_local_mcp_parity_for_eligible_control_and_degenerate_data():
    from mcp_server.client import run_event_study as remote
    data=[event(i,.02+i*.001) for i in range(10)]
    control=[event(i+30,-.01 if i%2 else .01) for i in range(10)]
    assert remote(data,'earnings',control)==run_event_study(data,'earnings',control)
    degenerate=[event(i,0) for i in range(10)]
    # Exact identical zero returns after constant-alpha fit.
    for e in degenerate:e['est_stock']=[0.]*250;e['evt_stock']=[0.]*3
    result=run_event_study(degenerate)
    assert result['caar_significant'] is None
    assert 'degenerate_zero_dispersion' in result['inference_reasons']


def test_malformed_event_metadata_is_json_safe_and_unknown_placebo_is_not_clean():
    e=event();e['other_metadata']=float('nan')
    result=run_event_study([e],placebo_events='invalid')
    assert result['rejected_events'] and result['placebo']['rejected_events']
    assert result['placebo']['caar_significant'] is None
    assert 'UNAVAILABLE' in result['placebo']['interpretation']
    json.dumps(result,allow_nan=False)


def test_assembly_contains_failure_for_one_peer(monkeypatch):
    import agent3.track_a_live as live
    stock,market=series()
    def prices(tk,**kw):
        if tk=='BAD':return stock+stock[-1:]
        return market if tk.startswith('^') else stock
    monkeypatch.setattr(live,'_fetch_prices',prices)
    monkeypatch.setattr(live,'_fetch_earnings_dates',lambda tk:[date(2026,1,28),date(2025,10,15),date(2025,7,16),date(2025,4,16),date(2025,1,29)])
    result=load_live_event_set('ASML.AS',['BAD'],'earnings')
    assert result['target_contributed'] and result['contributing_peers']==['ASML.AS']
    assert result['excluded_peers']==['BAD']
    assert result['per_peer_report'][1]['error'].startswith('ValueError')


def test_cli_and_renderers_cannot_publish_a_held_forward_distribution(monkeypatch,capsys,tmp_path):
    from agent3.orchestrator import analyze_event_type,render_brief,render_scan
    from agent3 import run_live
    from agent3.catalyst_state import CatalystStore
    result=analyze_event_type('semicap_earnings')
    # Simulate an older saved shape with a CALIBRATED scenario under a held gate.
    result['scenario'].update(verdict='CALIBRATED',publication_state='HELD_FOR_REVIEW',distribution={'p25':999})
    monkeypatch.setattr(run_live,'analyze_event_type',lambda *a,**k:result)
    monkeypatch.setattr(run_live,'CatalystStore',lambda:CatalystStore(str(tmp_path/'db.duckdb')))
    assert run_live.main(['ASML.AS','earnings','--peers','ASM.AS'])==3
    output=capsys.readouterr().out+render_brief(result)+render_scan([result])
    assert 'CALIBRATED' not in output and '999' not in output
    assert 'HELD_FOR_REVIEW' in output


def test_orchestrator_can_publish_eligible_history_and_hold_adjusted_failure(monkeypatch):
    import agent3.orchestrator as orchestrator
    controls=[event(i+20,-.01 if i%2 else .01) for i in range(10)]
    family={'hypotheses':['earnings','other']}
    def assembled(events):
        return {'events':events,'placebo_events':controls,'contributing_peers':[e['ticker'] for e in events],
                'study_plan':family,'comparability_status':'human_reviewed'}
    good=assembled([event(i,.04+i*.004) for i in range(10)])
    monkeypatch.setattr(orchestrator,'load_event_set',lambda *a,**kw:good)
    r=orchestrator.analyze_event_type('earnings')
    assert r['gate']['verdict']=='PASS' and r['scenario']['verdict']=='HISTORICAL'
    assert r['scenario']['distribution']['mean_ci95'] is not None
    assert 'Historical quantiles:' in orchestrator.render_brief(r)
    centered=np.arange(10,dtype=float);centered=(centered-centered.mean())/centered.std(ddof=1)
    cars=.01*(centered+2.4/math.sqrt(10))
    weaker=assembled([event(i,float(c)) for i,c in enumerate(cars)])
    monkeypatch.setattr(orchestrator,'load_event_set',lambda *a,**kw:weaker)
    r=orchestrator.analyze_event_type('earnings')
    assert r['study']['caar_significant'] is True
    assert r['gate']['adjusted_p_value']>.05
    assert r['scenario']['publication_state']=='HELD_FOR_REVIEW'
    assert 'Historical quantiles:' not in orchestrator.render_brief(r)


def test_incomplete_provenance_cannot_self_certify_inference():
    for field,value in [('review_evidence',{'date':{**REVIEW,'source_url':123}}),('release_timestamp',None),('session','unknown')]:
        data=[event(i,.02+i*.003) for i in range(10)]
        for e in data:e[field]=value
        r=run_event_study(data)
        assert r['inference_status']=='unavailable' and r['caar_significant'] is None
        json.dumps(r,allow_nan=False)


def test_control_reusing_actual_event_cannot_pass():
    events=[event(i,.02+i*.003) for i in range(10)]
    r=run_event_study(events,'earnings',deepcopy(events))
    assert r['placebo']['inference_status']=='unavailable'
    assert 'control_overlaps_real_event' in r['placebo']['inference_reasons']


def test_listing_aliases_cannot_create_additional_issuers():
    e=event();duplicate=deepcopy(e)
    duplicate.update(ticker='OTHER',issuer_id=e['issuer_id'].upper()+' ')
    r=run_event_study([e,duplicate])
    assert r['n_events']==1 and r['rejected_events']
