"""Batch 1 regressions: independent finance examples and provider boundary tests.

All provider tests use public-API-shaped doubles; no network or API keys.
"""
import json
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from agent.state import RunState
from tools import data
from tools.analytical import run_dcf, compute_ratios, compute_derived, peer_outlier_check, _two_stage_ev
from tests.conftest import make_state

FIN = {"revenue": 1000, "net_income": 150, "operating_income": 200, "ebit": 1000,
       "depreciation_amortization": 200, "capex": 100, "tax_provision": 250,
       "pretax_income": 1000, "change_in_working_capital": 0,
       "total_debt": 300, "cash_and_equivalents": 100}
PRICES = {"shares_outstanding": 10, "current_price": 500, "market_cap": 5000}


def state(fin=None, prices=None):
    return make_state("TST", {**FIN, **(fin or {})}, {**PRICES, **(prices or {})})


def provider(monkeypatch, **overrides):
    date = pd.Timestamp("2025-12-31")
    obj = SimpleNamespace(
        financials=pd.DataFrame({date: {"Total Revenue": 1000, "EBIT": 1000,
            "Operating Income": 200, "Net Income": 150, "Tax Provision": 250,
            "Pretax Income": 1000, "Reconciled Depreciation": 80}}),
        cashflow=pd.DataFrame({date: {"Depreciation And Amortization": 200,
            "Capital Expenditure": -100, "Change In Working Capital": -100,
            "Operating Cash Flow": 700}}),
        balance_sheet=pd.DataFrame({date: {"Total Debt": 300, "Cash And Cash Equivalents": 100}}),
        info={"financialCurrency": "EUR", "currency": "EUR", "regularMarketTime": 1750000000},
        fast_info={"last_price": 500, "market_cap": 5000, "shares": 10},
        analyst_price_targets={}, revenue_estimate=pd.DataFrame(), earnings_estimate=pd.DataFrame())
    for k, v in overrides.items():
        setattr(obj, k, v)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda ticker: obj))
    return obj


@pytest.mark.parametrize("key", ["discount_rate", "terminal_growth", "high_growth", "tax_rate"])
@pytest.mark.parametrize("bad", [float('nan'), float('inf'), float('-inf'), True, "0.1"])
def test_invalid_dcf_parameters_refused(key, bad):
    assert "error" in run_dcf({"ticker": "TST", key: bad}, state())


@pytest.mark.parametrize("key", ["ebit", "capex", "depreciation_amortization", "total_debt", "cash_and_equivalents"])
def test_nonfinite_financials_refused(key):
    assert "error" in run_dcf({"ticker": "TST"}, state({key: float('nan')}))


@pytest.mark.parametrize("key", ["shares_outstanding", "current_price", "market_cap"])
@pytest.mark.parametrize("bad", [-1, 0, float('nan'), float('inf')])
def test_invalid_market_inputs_refused(key, bad):
    assert "error" in run_dcf({"ticker": "TST"}, state(prices={key: bad}))


def test_boolean_horizon_refused():
    assert "error" in run_dcf({"ticker": "TST", "horizon_years": True}, state())


@pytest.mark.parametrize("weights", [{"bear": .2}, {"bear": -.1, "base": .6, "bull": .5},
    {"bear": .3, "base": .5, "bull": .3}, {"bear": float('nan'), "base": .5, "bull": .5}])
def test_invalid_weights_refused(weights):
    assert "error" in run_dcf({"ticker": "TST", "weights": weights}, state())


def test_dcf_independent_two_year_benchmark():
    # Year 1: 100*1.10/1.10 = 100. Year 2:112.2/1.21.
    # Terminal:112.2*1.02/(.10-.02)/1.21. Total = 1375 exactly.
    ev, _ = _two_stage_ev(100, .10, .02, .10, 2)
    assert ev == pytest.approx(1375)


def test_one_year_horizon_respects_initial_growth():
    # 100*1.20/1.10 + (120*1.02/.08)/1.10 = 1500
    assert _two_stage_ev(100, .20, .02, .10, 1)[0] == pytest.approx(1500)
    r = run_dcf({"ticker": "TST", "horizon_years": 1}, state())
    assert r["enterprise_value"]["bear"] < r["enterprise_value"]["bull"]


def test_zero_equity_is_zero_not_missing():
    # FCFF850, one year at 10%, discount10%, terminal0 -> EV9350.
    s = state({"total_debt": 9350, "cash_and_equivalents": 0})
    r = run_dcf({"ticker": "TST", "horizon_years": 1, "high_growth": .10,
                 "discount_rate": .10, "terminal_growth": 0}, s)
    assert r["value_per_share"]["base"] == 0


def test_negative_equity_is_distress_not_negative_share_target():
    r = run_dcf({"ticker": "TST"}, state({"total_debt": 1e9}))
    assert r["equity_value"]["base"] < 0
    assert r["applicability"] == "distressed_equity"
    assert r["value_per_share"]["base"] is None
    assert r["implied_upside"] is None


def test_assumptions_are_explicit_and_tax_not_clamped():
    r = run_dcf({"ticker": "TST"}, state({"tax_provision": 600}))
    assert r["assumptions"]["fcff_inputs"]["tax_rate"] == .6
    r = run_dcf({"ticker": "TST"}, state({"pretax_income": -1000, "change_in_working_capital": None}))
    assert len(r["warnings"]) == 2
    assert r["assumptions"]["fcff_inputs"]["tax_rate"] == .25


def test_currency_and_units_required_not_guessed():
    for patch in ({"currency": None}, {"monetary_unit": "millions"}):
        assert "error" in run_dcf({"ticker": "TST"}, state(patch))
    assert "error" in run_dcf({"ticker": "TST"}, state(prices={"currency": "USD"}))
    assert "error" in compute_ratios({"ticker": "TST"}, state(prices={"currency": "GBp"}))


def test_share_basis_mismatch_refused():
    assert "error" in run_dcf({"ticker": "TST"}, state(prices={"shares_outstanding": 100}))


def test_explicit_statement_date_mismatch_refused():
    assert "error" in run_dcf({"ticker": "TST"}, state({"statement_periods": {"cash_flow": "2024-12-31"}}))


def test_ebit_consistent_and_large_loss_margin_retained():
    r = compute_ratios({"ticker": "TST"}, state({"net_income": -1500}))
    assert r["ratios"]["ev_ebit"] == 5.2  # EV5200 / EBIT1000, not operating income200
    assert r["ratios"]["net_margin"] == -1.5


def test_yoy_refuses_stub_period():
    r = compute_ratios({"ticker": "TST"}, state({"revenue_prior": 800, "prior_period": "2025-06-30"}))
    assert r["ratios"]["revenue_growth_yoy"] is None


def test_provider_zero_preserved_and_nan_alias_skipped(monkeypatch):
    obj = provider(monkeypatch)
    date = obj.financials.columns[0]
    obj.financials.loc['EBIT', date] = 0
    obj.cashflow.loc['Depreciation And Amortization', date] = 0
    f = data._financials_yfinance('TST')['financials']
    assert f['ebit'] == 0 and f['depreciation_amortization'] == 0
    obj.financials.loc['EBIT', date] = float('nan')
    f = data._financials_yfinance('TST')['financials']
    assert f['ebit'] == 200


def test_provider_never_substitutes_other_statement_periods(monkeypatch):
    obj = provider(monkeypatch)
    obj.cashflow.columns = [pd.Timestamp('2024-12-31')]
    obj.balance_sheet.columns = [pd.Timestamp('2023-12-31')]
    result = data._financials_yfinance('TST')
    f = result['financials']
    assert f['capex'] is None and f['total_debt'] is None
    assert f['statement_periods']['cash_flow'] is None
    assert len(result['warnings']) == 2
    s = RunState(ticker='TST'); s.results['get_financials'] = result
    assert 'error' in run_dcf({'ticker':'TST'}, s)


@pytest.mark.parametrize('raw,expected', [(-100,750), (100,950)])
def test_provider_wc_absorption_and_release_end_to_end(monkeypatch, raw, expected):
    obj = provider(monkeypatch)
    obj.cashflow.loc['Change In Working Capital', obj.cashflow.columns[0]] = raw
    result = data._financials_yfinance('TST')
    s = RunState(ticker='TST'); s.results['get_financials'] = result
    s.results['get_prices'] = data._prices_yfinance('TST')
    r = run_dcf({'ticker':'TST'}, s)
    assert r['assumptions']['fcf_base'] == expected
    assert result['normalization']['working_capital']['raw'] == raw
    assert result['financials']['free_cash_flow'] == 600
    json.dumps(r, allow_nan=False)


def test_apple_2025_provider_cashflow_sign_evidence(monkeypatch):
    # Yahoo AAPL annual CF retrieved 2026-09-25, USD millions. These signed
    # adjustments reconcile to OCF; subtracting the -25000 row does not.
    operating_adjustments = -6682 - 347 + 1400 - 9197 + 902 - 11076
    assert 112010 + 11698 + 12863 - 89 + operating_adjustments == 111482
    obj = provider(monkeypatch)
    obj.cashflow = pd.DataFrame({pd.Timestamp('2025-12-31'):{
        'Change In Working Capital': operating_adjustments,
        'Operating Cash Flow':111482, 'Capital Expenditure':-12715,
        'Depreciation And Amortization':11698}})
    f = data._financials_yfinance('TST')['financials']
    assert f['change_in_working_capital'] == 25000
    assert f['capex'] == 12715 and f['free_cash_flow'] == 98767


@pytest.mark.parametrize('targets', [{'current':500}, {'numberOfAnalysts':0}, {'mean':float('nan')}, {}])
def test_empty_or_current_only_consensus_is_unavailable(monkeypatch, targets):
    provider(monkeypatch, analyst_price_targets=targets)
    assert data._consensus_yfinance('TST')['available'] is False


def test_consensus_filters_zero_coverage_and_keeps_real_estimates(monkeypatch):
    provider(monkeypatch, revenue_estimate=pd.DataFrame({'avg':[100,120], 'numberOfAnalysts':[0,5]},index=['0y','+1y']))
    r = data._consensus_yfinance('TST')
    assert r['available'] and r['consensus']['revenue_estimate_avg'] == {'+1y':120}
    assert r['coverage']['revenue_estimate_avg']['+1y'] == 5
    assert r['as_of'] is None and r['retrieved_at'] is not None


def test_trend_no_year_overwrite_and_no_stub_comparison(monkeypatch):
    df = pd.DataFrame({pd.Timestamp('2025-12-31'):{'Total Revenue':2000},
                       pd.Timestamp('2025-06-30'):{'Total Revenue':1000},
                       pd.Timestamp('2024-12-31'):{'Total Revenue':1000}})
    provider(monkeypatch, financials=df)
    r = data._trend_yfinance('TST')
    assert r['revenue_by_year']['2025'] == 2000
    assert r['revenue_cagr'] == 1
    assert r['excluded_periods'][0]['period'] == '2025-06-30'


@pytest.mark.parametrize('rev', [{}, {'2025':100}, {'2024':-100,'2025':100}, {'2024':float('nan'),'2025':100}, {'2023':100,'2025':120}])
def test_insufficient_history_not_available(rev):
    r = data._summarise_trend('TST', 'test', rev, {})
    assert r['available'] is False and r['revenue_cagr'] is None
    json.dumps(r,allow_nan=False)


def test_flat_peers_report_indeterminate_and_large_deviation(monkeypatch):
    monkeypatch.setattr(data,'get_financials',lambda inp: make_state(inp['ticker'],FIN).results['get_financials'])
    monkeypatch.setattr(data,'get_prices',lambda inp: {'ticker':inp['ticker'], 'currency':'EUR', 'monetary_unit':'base', 'market_cap':3000})
    r = peer_outlier_check({'ticker':'TST','peers':['A','B','C','D','E']},state({'net_income':50}))
    assert r['target_pe'] == 100 and r['peer_median'] == 20
    assert r['is_outlier'] is None and r['deviation_from_median'] == 4
    assert r['comparison_status'] == 'insufficient_dispersion'


def test_peer_failure_is_explained_and_other_peers_still_used(monkeypatch):
    def fetch(inp):
        if inp['ticker'] == 'BAD':
            raise RuntimeError('test outage')
        return make_state(inp['ticker'], FIN).results['get_financials']
    monkeypatch.setattr(data,'get_financials',fetch)
    monkeypatch.setattr(data,'get_prices',lambda inp: {'ticker':inp['ticker'], 'currency':'EUR', 'monetary_unit':'base', 'market_cap':3000})
    r = peer_outlier_check({'ticker':'TST','peers':['A','B','BAD']},state())
    assert r['n_peers'] == 2 and 'provider failure' in r['excluded_peers']['BAD']
    assert r['peer_evidence']['A']['period'] == '2025-12-31'


def test_growth_comparison_uses_percentage_points():
    s = state()
    s.results['get_consensus'] = {'ticker':'TST','available':True,'consensus':{'revenue_estimate_avg':{'0y':100,'+1y':120}}}
    s.results['get_historical_trend'] = {'ticker':'TST','revenue_cagr':.10}
    r = compute_derived({'ticker':'TST'},s)['metrics']['growth_vs_history']
    assert r['percentage_points'] == 10 and 'as_pct' not in r


def test_oldest_empty_provider_column_does_not_discard_valid_history():
    r = data._summarise_trend('TST','test',{'2021':None,'2022':100,'2023':110,'2024':121,'2025':133.1},{})
    assert r['available'] and r['revenue_cagr'] == .1
    assert r['cagr_years'] == ['2022','2023','2024','2025']


def test_financial_overflow_never_published_as_infinity():
    r = compute_ratios({'ticker':'TST'},state({'net_income':1e-310}))
    assert 'error' in r
    json.dumps(r, allow_nan=False)
    r = run_dcf({'ticker':'TST','high_growth':1e308},state())
    assert 'error' in r
    json.dumps(r, allow_nan=False)


def test_missing_statement_contract_refused():
    assert 'error' in run_dcf({'ticker':'TST'},state({'statement_periods':None}))


def test_zero_target_coverage_and_past_only_estimates_are_unavailable(monkeypatch):
    provider(monkeypatch,analyst_price_targets={'mean':500,'numberOfAnalysts':0},
             revenue_estimate=pd.DataFrame({'avg':[100]},index=['-1y']))
    assert data._consensus_yfinance('TST')['available'] is False


def test_weighted_value_uses_unrounded_scenarios():
    r=run_dcf({'ticker':'TST','horizon_years':1,'discount_rate':.1,'terminal_growth':0,
               'high_growth':.1,'weights':{'bear':.1,'base':.2,'bull':.7}},state())
    # EV: 9010 / 9350 / 9690; debt300-cash100 => equity8810/9150/9490.
    assert r['scenario_weighted_per_share'] == 935.4
    assert r['implied_upside'] == .8708


@pytest.mark.parametrize('patch',[{'capex':-100},{'capex_convention':None},{'working_capital_convention':'cash_flow_contribution'}])
def test_unnormalized_cashflow_conventions_refused(patch):
    assert 'error' in run_dcf({'ticker':'TST'},state(patch))


def test_invalid_peer_is_excluded_without_poisoning_other_evidence(monkeypatch):
    def fetch(inp):
        return make_state(inp['ticker'],{**FIN,'net_income':float('nan') if inp['ticker']=='BAD' else 150}).results['get_financials']
    monkeypatch.setattr(data,'get_financials',fetch)
    monkeypatch.setattr(data,'get_prices',lambda inp: {'ticker':inp['ticker'],'currency':'EUR','monetary_unit':'base','market_cap':3000})
    r=peer_outlier_check({'ticker':'TST','peers':['A','B','BAD']},state())
    assert r['n_peers']==2 and 'net_income' in r['excluded_peers']['BAD']
    json.dumps(r,allow_nan=False)
