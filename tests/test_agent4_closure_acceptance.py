"""The controlled financial-year acceptance stays part of regression coverage."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from scripts.check_agent4_closure import FIXTURE, run_acceptance, verify_answer_key
from agent4.state import VarianceStore


def test_controlled_financial_year_and_recovery(tmp_path):
    result=run_acceptance(tmp_path/'acceptance')
    assert result['status']=='passed'
    assert result['committed_closes']==14
    assert result['auxiliary_history_gap']=='passed'
    assert result['state_counts']=={'budget':2,'actuals':13,'reforecast':14,'runs':14}
    assert result['results'][-1]['profit_landing_cents']==595000
    with VarianceStore(result['database']) as store:
        assert [r['status'] for r in store.attempt_history('close-04')]==['started','failed','started','committed','started','replayed']
        original=store.get_run('close-02')['bundle']
        revised=store.get_run('july-restated')['bundle']
        assert original['report']['full_hierarchy']['actual_cents']==40000
        feb=[r for r in revised['sources']['effective_actuals'] if r['period']=='2026-02-28']
        assert {r['line']:r['source_version'] for r in feb}=={'sales':'restatement-feb','cost':'actual-02'}
    html=Path(result['html_path']).read_text()
    assert '€5,950.00' in html and '€5,550.00' in html
    assert 'deterministic closed-year outcome' in html


@pytest.mark.parametrize('field',['monthly_profit_original','july_profit_landing','year_end_profit'])
def test_independent_oracle_rejects_wrong_expected_answers(field):
    case=deepcopy(json.loads(FIXTURE.read_text()))
    if isinstance(case['answer_key'][field],list):case['answer_key'][field][0]+=1
    else:case['answer_key'][field]+=1
    with pytest.raises(AssertionError):verify_answer_key(case)
