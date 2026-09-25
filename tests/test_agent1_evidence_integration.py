"""Runtime publication checks with real calculations and sidecar persistence."""
import json
from datetime import date
import pytest
from agent.state import RunState
from tools import data
from tools.analytical import compute_ratios, run_dcf, peer_outlier_check
from validation import gate
from tests.test_gate import _clean, NOW


def test_fully_recorded_run_can_pass():
    a=_clean()
    # Explicit log order, including upstream data before each calculation.
    calls=[{'tool':k,'status':'success','output':v} for k,v in a.items()]
    assert gate.assess(a,now=NOW,calls=calls)['verdict']=='pass'


@pytest.mark.parametrize('patch',[
 {'n_peers':9}, {'peer_median':999}, {'is_outlier':True}, {'peer_evidence':{}},
 {'peer_pes':[]}, {'peer_pes':{'A':float('nan'),'B':12}},
])
def test_peer_evidence_cannot_be_fabricated_or_incomplete(patch):
    a=_clean();a['peer_outlier_check'].update(patch)
    assert gate.assess(a,now=NOW)['verdict']=='flag_for_review'


def test_zero_coverage_consensus_cannot_pass():
    a=_clean();a['get_consensus']['coverage']={'revenue_estimate_avg':{'0y':0,'+1y':0}}
    assert gate.assess(a,now=NOW)['n_fail']>0


def test_default_forecast_parameters_require_review():
    a=_clean()
    from types import SimpleNamespace
    a['run_dcf']=run_dcf({'ticker':'T'},SimpleNamespace(ticker='T',results=a))
    r=gate.assess(a,now=NOW)
    assert any(c['check']=='model_defaults' and c['status']=='quality_warn' for c in r['checks'])
    assert not any(c['check']=='reconcile_run_dcf' and c['status']=='fail' for c in r['checks'])


def test_full_precision_tax_override_reconciles():
    a=_clean()
    from types import SimpleNamespace
    a['run_dcf']=run_dcf({'ticker':'T','tax_rate':.123456789},SimpleNamespace(ticker='T',results=a))
    assert not any(c['check']=='reconcile_run_dcf' and c['status']=='fail' for c in gate.assess(a,now=NOW)['checks'])


@pytest.mark.parametrize('note,grounded',[
 ('[[claim:operating_margin]]\n[[claim:dcf_value]]',True),
 ('Operating margin EUR999999.\n[[claim:dcf_value]]',False),
])
def test_emission_persists_grounding_and_requires_review(tmp_path,monkeypatch,note,grounded):
    import run, composer
    a=_clean();s=RunState(ticker='T')
    for name,result in a.items():
        s.record_tool(name,{'ticker':'T'},result)
    # Unknown quote observation time is a real quality limitation, despite
    # otherwise supported claims. Verify the publication filename and sidecar.
    s.results['get_prices']['as_of']=None
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(data,'get_price_history',lambda *args: {'history':[],'source':'fixture-synthetic'})
    run._emit_artifacts('T','offline',note,s)
    sidecars=list(tmp_path.glob('output/*/model.json'))
    assert len(sidecars)==1
    record=json.loads(sidecars[0].read_text())
    validation=record['validation']
    assert validation['verdict']=='flag_for_review'
    assert validation['note_grounding']['passed'] is grounded
    assert validation['note_grounding']['original_note']==note
    assert validation['note_grounding']['evidence'][0]['ticker']=='T'
    assert 'source:' in record['note']
    assert (sidecars[0].parent/'report_REVIEW.html').exists()
    assert not (sidecars[0].parent/'report.html').exists()


def test_real_fixture_chain_has_no_reconciliation_failures(monkeypatch):
    monkeypatch.setenv('AGENT_DATA_SOURCE','fixture')
    s=RunState(ticker='ASML.AS')
    for name,fn,inp in [
      ('get_financials',data.get_financials,{}), ('get_prices',data.get_prices,{}),
      ('compute_ratios',compute_ratios,{}),('run_dcf',run_dcf,{}),
      ('peer_outlier_check',peer_outlier_check,{'peers':['ASM.AS','BESI.AS','LRCX']}),
      ('get_consensus',data.get_consensus,{}),('get_historical_trend',data.get_historical_trend,{})]:
        inp={'ticker':s.ticker,**inp};s.record_tool(name,inp,fn(inp,s))
    r=gate.assess(s.results,now=NOW,calls=s.calls)
    assert r['n_fail']==0,r['checks']
    assert r['verdict']=='flag_for_review'  # fixtures, defaults and small peer set


@pytest.mark.parametrize('tool,value',[
 ('get_financials',{'ticker':'T','financials':{'statement_periods':[]}}),
 ('run_dcf',{'ticker':'T','assumptions':[]}),
 ('get_historical_trend',{'ticker':'T','revenue_by_year':42}),
])
def test_malformed_nested_data_is_failed_gate(tool,value):
    a=_clean();a[tool]=value
    assert gate.assess(a,now=NOW)['n_fail']>0


@pytest.mark.parametrize('change',[{'reporting_currency':'USD'},{'monetary_unit':None},{'coverage':{}}])
def test_consensus_currency_units_and_coverage_require_evidence(change):
    a=_clean();a['get_consensus'].update(change)
    assert gate.assess(a,now=NOW)['verdict']=='flag_for_review'


def test_historical_period_labels_must_match_the_calculation():
    a=_clean();a['get_consensus']['available']=False
    a['get_historical_trend']={'ticker':'T','source':'yfinance','retrieved_at':'2026-03-01',
        'available':True,'revenue_by_year':{'2024':100,'2025':110},'revenue_cagr':.1,
        'cagr_years':['2020','2021']}
    assert gate.assess(a,now=NOW)['n_fail']>0
