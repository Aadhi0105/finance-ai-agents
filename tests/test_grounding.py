"""Numbers require named, current metric evidence; pooled matching is forbidden."""
from copy import deepcopy
import pytest
from validation.note_grounding import ground_note, build_evidence_catalog

_RESULTS={
 'get_financials':{'ticker':'T','financials':{'currency':'EUR','period':'2025-12-31'}},
 'compute_ratios':{'ticker':'T','period':'2025-12-31','ratios':{'operating_margin':.3462,'pe':13.33}},
 'run_dcf':{'ticker':'T','period':'2025-12-31','scenario_weighted_per_share':214.21,'implied_upside':-.184},
 'get_prices':{'ticker':'T','currency':'EUR','as_of':'2026-03-01','current_price':180},
}


def test_claims_render_metric_company_period_unit_and_source():
    r=ground_note('Profitability supports the view.\n[[claim:operating_margin]]\n[[claim:dcf_value]]',_RESULTS)
    assert r['passed'] and r['claims_checked']==2
    assert 'operating margin: +34.62%' in r['rendered_note']
    assert 'EUR 214.21 per share' in r['rendered_note']
    assert '2025-12-31' in r['rendered_note']
    assert r['evidence'][0]['path']=='ratios.operating_margin'
    assert r['evidence'][0]['ticker']=='T'


@pytest.mark.parametrize('text',[
 'Operating margin 18.4%.', 'Upside +18.4%.', 'Net debt €-100.',
 'Fair value EUR999999.', 'Fair value 999999.', 'Fair value $214.21.',
 'Operating margin 34.62%.', 'Trades at 13.33x.', 'Growth ten percent.',
 'Loss (18.4%).', 'Value 2e3.', 'Growth .184.', 'Revenue doubled to 200.',
 'Operating margin [[claim:dcf_gap]]', '[[claim:unknown]]',
])
def test_raw_numbers_wrong_metrics_and_unknown_claims_fail(text):
    r=ground_note(text+'\n[[claim:pe]]',_RESULTS)
    assert not r['passed']
    assert r['unmatched']


def test_sign_is_supplied_by_source_not_model():
    r=ground_note('[[claim:dcf_gap]]',_RESULTS)
    assert r['passed'] and '-18.40%' in r['rendered_note']


def test_wrong_company_cannot_supply_metric():
    a=deepcopy(_RESULTS);a['run_dcf']['ticker']='OTHER'
    assert not ground_note('[[claim:dcf_value]]',a)['passed']


def test_failed_and_nonfinite_tools_cannot_supply_metric():
    a=deepcopy(_RESULTS);a['run_dcf']['error']='failed'
    assert not ground_note('[[claim:dcf_value]]',a)['passed']
    a=deepcopy(_RESULTS);a['run_dcf']['scenario_weighted_per_share']=float('nan')
    assert not ground_note('[[claim:dcf_value]]',a)['passed']


def test_earlier_calls_are_not_an_unattributed_number_pool():
    assert not ground_note('EUR205 then EUR220',{'call_0':{'scenario_weighted_per_share':205},'call_1':{'scenario_weighted_per_share':220}})['passed']


def test_no_claims_is_not_vacuous_pass():
    assert not ground_note('Looks reasonable.',_RESULTS)['passed']
    assert not ground_note('',_RESULTS)['passed']


def test_percentage_point_unit_not_percent():
    a=deepcopy(_RESULTS);a['compute_derived']={'ticker':'T','metrics':{'growth_vs_history':{'percentage_points':10}}}
    r=ground_note('[[claim:growth_vs_history]]',a)
    assert r['passed'] and '+10.00 percentage points' in r['rendered_note']


def test_zero_currency_keeps_zero_and_currency_identity():
    a=deepcopy(_RESULTS);a['run_dcf'].update(currency='USD',scenario_weighted_per_share=0)
    assert 'USD 0.00' in ground_note('[[claim:dcf_value]]',a)['rendered_note']


def test_catalog_never_includes_unrelated_nested_numbers():
    a=deepcopy(_RESULTS);a['debug']={'duration_ms':999999,'other_company':{'margin':.777}}
    assert not any(i['value'] in (999999,.777) for i in build_evidence_catalog(a).values())
