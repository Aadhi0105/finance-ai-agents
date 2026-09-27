"""Issuer arithmetic and publication boundaries use independently reviewed data."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pandas as pd
import pytest
from tools import data
from tools.issuer_reconciliation import apply_reviewed_profile, REFERENCE_DIR
from validation.qualitative_claims import control_note
from validation.publication import assess_record


def reference():
    return json.loads((REFERENCE_DIR/'ASML.AS-2025-12-31.json').read_text())


def snapshot():
    return json.loads((REFERENCE_DIR/'ASML.AS-provider-2026-09-26.json').read_text())


def normalized():
    # Adapter's new operating-income selection, starting from retained old inputs.
    result=snapshot()['financials']
    f=result['financials'];f['provider_ebit']=f['ebit'];f['ebit']=f['operating_income']
    return result


def test_issuer_statement_identities():
    r=reference();f=r['expected_provider_fields']
    wc=sum(r['cash_flow_components'].values())
    assert wc==1026500000
    assert wc-r['cash_flow_components']['current_tax_assets_and_liabilities']==692400000
    assert f['net_income']+sum(r['noncash_adjustments'].values())+wc==r['operating_cash_flow']
    assert r['pp_and_e_purchases']+r['intangible_purchases']==f['capex']
    assert r['operating_cash_flow']-f['capex']==f['free_cash_flow']
    assert r['current_borrowings']+r['noncurrent_debt']==f['total_debt']
    assert f['pretax_income']+r['interest_expense']==r['provider_ebit']
    assert f['operating_income']+r['interest_income']==r['provider_ebit']
    assert f['cash_and_equivalents']-f['total_debt']==8525100000


def test_saved_provider_snapshot_reconciles_with_explicit_corrections():
    result=apply_reviewed_profile(normalized())
    assert result['issuer_reconciliation']['status']=='matched'
    assert all(c['matched'] for c in result['issuer_reconciliation']['checks'])
    assert result['financials']['ebit']==11301400000
    assert result['financials']['provider_ebit']==11524400000
    assert result['financials']['change_in_working_capital']==-692400000
    assert result['normalization']['working_capital']['raw']==1026500000
    assert result['normalization']['working_capital']['current_tax_cash_contribution']==334100000
    # Current shares are deliberately not certified by annual reconciliation.
    assert 'shares' not in [c['field'] for c in result['issuer_reconciliation']['checks']]
    assert snapshot()['prices']['shares_outstanding'] != reference()['issuer_year_end_shares']


@pytest.mark.parametrize('field',list(reference()['expected_provider_fields']))
def test_material_mismatch_prevents_adjustment(field):
    result=normalized();original=result['financials']['change_in_working_capital']
    result['financials'][field]+=200000
    result=apply_reviewed_profile(result)
    assert result['issuer_reconciliation']['status']=='mismatch' and result['error']
    assert result['financials']['change_in_working_capital']==original


@pytest.mark.parametrize('patch',[{'period':'2026-12-31'},{'currency':'USD'}])
def test_profile_never_generalizes_to_other_period_or_currency(patch):
    result=normalized();result['financials'].update(patch)
    assert 'issuer_reconciliation' not in apply_reviewed_profile(result)


def test_actual_adapter_prefers_operating_income_and_preserves_provider_ebit(monkeypatch):
    from tests.test_agent1_financial_correctness import provider
    obj=provider(monkeypatch)
    result=data._financials_yfinance('TST')
    assert result['financials']['ebit']==200
    assert result['financials']['provider_ebit']==1000
    obj.financials.loc['Operating Income',obj.financials.columns[0]]=0
    assert data._financials_yfinance('TST')['financials']['ebit']==0
    obj.financials.loc['Operating Income',obj.financials.columns[0]]=float('nan')
    result=data._financials_yfinance('TST')
    assert result['financials']['ebit']==1000 and result['warnings']


def test_live_fetch_entry_applies_profile(monkeypatch):
    monkeypatch.setenv('AGENT_DATA_SOURCE','yfinance')
    monkeypatch.setattr(data,'_financials_yfinance',lambda ticker: normalized())
    assert data.get_financials({'ticker':'ASML.AS'})['financials']['change_in_working_capital']==-692400000


def evidence():
    return {'get_financials':{'ticker':'T','financials':{'currency':'EUR','period':'2025-12-31','revenue':100}}}


@pytest.mark.parametrize('prose',[
    'The company has a monopoly and a strong backlog.',
    'BUY: this stock is guaranteed to outperform.',
    'In my opinion management is excellent.',
    'Verified claim: demand is booming [issuer](https://www.asml.com).',
    '<script>alert("trusted")</script>',
    'Revenue is collapsing despite the reported figure.',
    '[[claim:revenue]] proves the stock is a buy.',
])
def test_all_unsourced_prose_withheld_including_fake_citations(prose):
    note=prose+'\n[[claim:revenue]]'
    result=control_note(note,evidence())
    assert prose not in result['published_note']
    assert result['withheld_lines']==[prose]
    assert 'EUR 100.00' in result['published_note']


def test_publication_cannot_approve_unsourced_qualitative_claims():
    note='The company is a monopoly.\n[[claim:revenue]]'
    result,published=assess_record({'schema_version':2,'analysis':evidence(),'note':note,
        'execution':{'status':'completed','outcome':{'status':'completed'}}})
    assert result['note_grounding']['passed']
    assert result['qualitative_controls']['withheld_lines']==['The company is a monopoly.']
    assert 'monopoly' not in published
    assert result['verdict']=='flag_for_review'
    assert any(c['check']=='qualitative_claims' for c in result['checks'])


def test_marker_only_note_has_no_withheld_prose():
    result=control_note('[[claim:revenue]]',evidence())
    assert result['withheld_count']==0


def test_reconciled_fcff_benchmark_from_issuer_lines():
    from agent.state import RunState
    from tools.analytical import run_dcf
    s=RunState('ASML.AS')
    s.results={'get_financials':apply_reviewed_profile(normalized()),'get_prices':snapshot()['prices']}
    result=run_dcf({'ticker':'ASML.AS'},s)
    # 11,301.4*(1-2,013.4/11,406.1)+1,025.9-1,631.2+692.4, EUR millions.
    assert result['assumptions']['fcf_base']==pytest.approx(9393581600.196386)
    assert result['scenario_weighted_per_share']==594.97


def test_selected_valuation_ebit_must_match_reviewed_operating_basis():
    value=normalized();value['financials']['ebit']=11524400000
    assert apply_reviewed_profile(value)['error']


def test_rebuild_withholds_old_prose_and_preserves_original_audit(tmp_path):
    import composer
    from tools.data import _history_synthetic
    note='The company has a monopoly. BUY now.\n[[claim:revenue]]'
    path=composer.write_sidecar(ticker='T',mode='test',note=note,analysis=evidence(),
        execution={'status':'completed','outcome':{'status':'completed'}},
        price_history=_history_synthetic('T'),index_history=_history_synthetic('^GSPC'),
        out_dir=str(tmp_path))
    report=composer.build_report(path)
    content=Path(report).read_text()
    record=json.loads(Path(path).read_text())
    assert 'monopoly' not in content and 'BUY now' not in content
    assert 'EUR 100.00' in content
    assert record['note_template']==note
    assert 'monopoly' in record['validation']['qualitative_controls']['withheld_lines'][0]
