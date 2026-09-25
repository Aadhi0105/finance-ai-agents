"""Evidence gate regressions: completeness, reconciliation and review policy."""
from copy import deepcopy
from datetime import date
import pytest
from tools import data
from tools.analytical import compute_ratios, run_dcf
from tests.conftest import make_state
from validation import gate

NOW = date(2026, 3, 1)


def _clean():
    f = {"revenue":1000,"net_income":150,"operating_income":200,"ebit":200,
         "depreciation_amortization":40,"capex":20,"tax_provision":50,"pretax_income":200,
         "change_in_working_capital":0,"total_debt":100,"cash_and_equivalents":50}
    s = make_state('T',f,{'market_cap':2000,'shares_outstanding':10,'current_price':200})
    for v in s.results.values():
        v.update(source='yfinance',retrieved_at='2026-03-01T00:00:00Z',as_of='2026-03-01')
    s.results['compute_ratios'] = compute_ratios({'ticker':'T'},s)
    s.results['run_dcf'] = run_dcf({'ticker':'T','horizon_years':10,'discount_rate':.09,'terminal_growth':.025,'high_growth':.12,'weights':{'bear':.25,'base':.5,'bull':.25}},s)
    s.results['get_consensus']={'ticker':'T','source':'yfinance','retrieved_at':'2026-03-01',
        'as_of':'2026-03-01','available':True,'monetary_unit':'base','reporting_currency':'EUR',
        'coverage':{'revenue_estimate_avg':{'0y':5,'+1y':5}},'consensus':{'revenue_estimate_avg':{'0y':1000,'+1y':1200}}}
    peer_values={'A':10,'B':12,'C':14,'D':16,'E':18}
    evidence={}
    for symbol, pe in peer_values.items():
        ps=make_state(symbol, f, {'market_cap':pe*150})
        for snapshot in ps.results.values():
            snapshot.update(source='yfinance',retrieved_at='2026-03-01',as_of='2026-03-01')
        evidence[symbol]={'pe':pe, 'financials':ps.results['get_financials'],'prices':ps.results['get_prices']}
    s.results['peer_outlier_check']={'ticker':'T','peer_pes':peer_values,'peer_evidence':evidence,
        'n_peers':5,'is_outlier':False,'comparison_status':'screening_only','target_pe':13.33,
        'peer_median':14.,'peer_mad':2.,'peer_mean':14.,'peer_stdev':2.83,
        'modified_z':-.22,'z_score':-.24}
    return s.results


def test_clean_run_passes_high_confidence():
    v=gate.assess(_clean(),now=NOW)
    assert v['verdict']=='pass', v['checks']
    assert v['confidence']=='high'


@pytest.mark.parametrize('tool',gate._REQUIRED)
def test_required_tools_cannot_be_omitted(tool):
    a=_clean();del a[tool]
    assert gate.assess(a,now=NOW)['verdict']=='flag_for_review'


@pytest.mark.parametrize('tool',gate._REQUIRED)
def test_required_error_results_cannot_pass(tool):
    a=_clean();a[tool]={'ticker':'T','error':'failed'}
    assert gate.assess(a,now=NOW)['n_fail']>0


def test_nonfinite_result_rejected():
    a=_clean();a['run_dcf']['implied_upside']=float('nan')
    assert gate.assess(a,now=NOW)['n_fail']>0


def test_recomputed_large_negative_margin_is_valid():
    a=_clean();a['get_financials']['financials']['net_income']=-1500
    s=make_state('T',extra=a);a['compute_ratios']=compute_ratios({'ticker':'T'},s)
    assert not any(c['check']=='reconcile_compute_ratios' and c['status']=='fail' for c in gate.assess(a,now=NOW)['checks'])


def test_wrong_margin_value_rejected_even_when_another_metric_matches():
    a=_clean();a['compute_ratios']['ratios']['operating_margin']=a['run_dcf']['implied_upside']
    assert gate.assess(a,now=NOW)['n_fail']>0


def test_missing_net_income_fails():
    a=_clean();a['get_financials']['financials']['net_income']=None
    assert gate.assess(a,now=NOW)['n_fail']>0


def test_valuation_gap_is_finding_not_fault():
    a=_clean()
    checks=[{'check':'valuation_gap','status':'info_finding','detail':'large gap'}]
    assert gate.aggregate_checks(checks)['verdict']=='pass'
    assert gate.aggregate_checks(checks)['score']==1


def test_incomplete_bridge_blocks_equity_publication():
    a=_clean();a['get_financials']['financials']['total_debt']=None
    a['run_dcf']=run_dcf({'ticker':'T'},make_state('T',extra=a))
    assert any(c['check']=='net_debt_bridge' and c['status']=='fail' for c in gate.assess(a,now=NOW)['checks'])


def test_single_warning_cannot_pass_high_confidence():
    r=gate.aggregate_checks([{'check':'assumption','status':'quality_warn','detail':'default tax'}])
    assert r['score']==.85 and r['verdict']=='flag_for_review' and r['confidence']=='medium'


def test_aggregate_checks_consistent_after_added_fail():
    r=gate.aggregate_checks([{'check':'note','status':'fail','detail':'unbound claim'}])
    assert r['score']==0 and r['confidence']=='low' and r['n_fail']==1


@pytest.mark.parametrize('period',['2027-12-31',None,'not-a-date'])
def test_unknown_or_future_statement_date_fails(period):
    a=_clean();a['get_financials']['financials']['period']=period
    assert gate.assess(a,now=NOW)['n_fail']>0


def test_old_financials_warn():
    a=_clean();a['get_financials']['financials']['period']='2020-12-31'
    assert any(c['check']=='filing_recency' and c['status']=='quality_warn' for c in gate.assess(a,now=NOW)['checks'])


def test_unknown_observation_date_requires_review():
    a=_clean();a['get_prices']['as_of']=None
    assert gate.assess(a,now=NOW)['verdict']=='flag_for_review'


def test_default_tax_and_working_capital_are_surfaced():
    a=_clean();a['get_financials']['financials'].update(tax_provision=None,change_in_working_capital=None)
    a['run_dcf']=run_dcf({'ticker':'T'},make_state('T',extra=a))
    checks=gate.assess(a,now=NOW)['checks']
    assert sum(c['check']=='dcf_assumption' for c in checks)==2


def test_empty_history_does_not_pass_by_presence():
    a=_clean();a['get_consensus']['available']=False
    a['get_historical_trend']={'ticker':'T','source':'yfinance','available':True,'revenue_by_year':{}}
    assert any(c['check']=='comparison_basis' and c['status']=='fail' for c in gate.assess(a,now=NOW)['checks'])


def test_current_price_is_not_consensus():
    a=_clean();a['get_consensus']['consensus']={'price_target':{'current':200}}
    assert any(c['check']=='comparison_basis' and c['status']=='fail' for c in gate.assess(a,now=NOW)['checks'])


def test_refreshed_input_requires_recalculation_even_if_numbers_unchanged():
    a=_clean(); calls=[{'tool':k,'status':'success','output':deepcopy(v)} for k,v in a.items()]
    calls.append({'tool':'get_prices','status':'success','output':deepcopy(a['get_prices'])})
    r=gate.assess(a,now=NOW,calls=calls)
    assert any(c['check']=='stale_run_dcf' and c['status']=='fail' for c in r['checks'])


def test_changed_price_caught_without_call_log():
    a=_clean();a['get_prices'].update(current_price=250,market_cap=2500)
    assert any(c['check']=='reconcile_run_dcf' and c['status']=='fail' for c in gate.assess(a,now=NOW)['checks'])


def test_empty_gate_cannot_pass():
    assert gate.aggregate_checks([])['verdict']=='flag_for_review'
    assert gate.assess({},now=NOW)['n_fail']>0


@pytest.mark.parametrize('value',[None,[],42,{'ratios':None}])
def test_malformed_outputs_fail_without_crashing(value):
    a=_clean();a['compute_ratios']=value
    assert gate.assess(a,now=NOW)['n_fail']>0
