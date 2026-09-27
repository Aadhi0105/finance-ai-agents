"""Closure acceptance: supported scope and unavailable comparison evidence."""
import pytest
from tools.analytical import run_dcf, compute_ratios
from tools import data
from tests.test_agent1_financial_correctness import state, provider


@pytest.mark.parametrize('sector', ['Financial Services', 'Financials', 'Real Estate'])
def test_sector_specific_business_refuses_generic_dcf(sector):
    result = run_dcf({'ticker': 'TST'}, state({'sector': sector}))
    assert 'outside supported scope' in result['error']
    assert 'value_per_share' not in result


@pytest.mark.parametrize('instrument', ['ETF', 'MUTUALFUND', 'INDEX'])
def test_non_equity_instrument_refuses_dcf(instrument):
    assert 'outside supported scope' in run_dcf({'ticker':'TST'}, state({'instrument_type':instrument}))['error']


def test_negative_earnings_and_fcff_do_not_become_positive_valuation():
    s = state({'net_income':-150, 'ebit':-1000})
    assert compute_ratios({'ticker':'TST'}, s)['ratios']['pe'] is None
    assert 'error' in run_dcf({'ticker':'TST'}, s)


def test_actual_provider_missing_consensus_remains_unavailable(monkeypatch):
    provider(monkeypatch)
    monkeypatch.setenv('AGENT_DATA_SOURCE', 'yfinance')
    result = data.get_consensus({'ticker':'TST'})
    assert result['available'] is False


def test_live_adapter_retains_scope_classification(monkeypatch):
    provider(monkeypatch, info={'financialCurrency':'EUR', 'sector':'Financial Services', 'quoteType':'EQUITY'})
    result = data._financials_yfinance('TST')
    assert result['financials']['sector'] == 'Financial Services'
    assert result['financials']['instrument_type'] == 'EQUITY'
    assert any('ordinary-share basis' in w for w in result['warnings'])


def test_rejected_peer_request_preserves_subject_evidence_and_audit():
    from copy import deepcopy
    s = state()
    s.results['compute_ratios'] = compute_ratios({'ticker':'TST'}, s)
    before = deepcopy(s.results)
    s.record_tool('get_financials', {'ticker':'OTHER'},
                  {'error':'ticker differs from run subject', 'error_type':'ticker_mismatch'})
    assert s.results == before
    assert s.calls[-1]['status'] == 'error'
    assert s.calls[-1]['input']['ticker'] == 'OTHER'
    # A failed refresh for the actual subject still invalidates stale calculations.
    s.record_tool('get_financials', {'ticker':'TST'}, {'error':'provider unavailable'})
    assert 'compute_ratios' not in s.results
