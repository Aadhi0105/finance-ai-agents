"""Batch 4 acceptance tests: public CLI, independent values and real boundaries."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest
from agent.state import RunState
from tools.registry import ToolRegistry
from tests.conftest import make_state

ROOT = Path(__file__).resolve().parents[1]


def test_full_dcf_against_hand_calculated_benchmark():
    from tools.analytical import run_dcf
    # FCFF=2000*.75+400-200-200=1500. Two-year terminal growth 2%,
    # discount10%, first-year growth6/10/14%. EV=19875/20625/21375.
    # Net debt400, 20 shares; weighted20/50/30 gives 1015 per share.
    state = make_state('T', {'ebit':2000,'depreciation_amortization':400,'capex':200,
        'tax_provision':500,'pretax_income':2000,'change_in_working_capital':200,
        'total_debt':600,'cash_and_equivalents':200},
        {'current_price':500,'shares_outstanding':20,'market_cap':10000})
    result = run_dcf({'ticker':'T','horizon_years':2,'high_growth':.10,
        'terminal_growth':.02,'discount_rate':.10,'tax_rate':.25,
        'weights':{'bear':.2,'base':.5,'bull':.3}}, state)
    assert result['enterprise_value'] == pytest.approx({'bear':19875,'base':20625,'bull':21375})
    assert result['equity_value'] == pytest.approx({'bear':19475,'base':20225,'bull':20975})
    assert result['value_per_share'] == {'bear':973.75,'base':1011.25,'bull':1048.75}
    assert result['scenario_weighted_per_share'] == 1015
    assert result['implied_upside'] == 1.03
    assert result['terminal_value_concentration']['base'] == .8598


@pytest.mark.parametrize('peers,allowed', [(['A','B'],True),(['b','a'],True),
    (['A'],False),(['A','C'],False),(['A','A','B'],False)])
def test_requested_peers_enforced_before_fetch(peers, allowed):
    state = RunState('T'); state.configuration['peers']=['A','B']
    registry = ToolRegistry(state)
    schema, _ = registry._reg['peer_outlier_check']
    calls = []
    registry._reg['peer_outlier_check']=(schema,lambda args,state: calls.append(args) or {'ok':True})
    result = registry.dispatch('peer_outlier_check',{'ticker':'T','peers':peers})
    assert bool(calls) is allowed
    if not allowed:
        assert result['error_type']=='peer_set_mismatch'


@pytest.fixture
def cli_environment(tmp_path):
    # Guard imports in the CHILD interpreter: a leaked live source fails, even
    # if machine credentials/network are available. No renderer or finance mocks.
    guard = tmp_path/'guard'; guard.mkdir()
    (guard/'sitecustomize.py').write_text('''import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in ('yfinance', 'anthropic'):
        raise RuntimeError('live dependency forbidden in offline acceptance test')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
''')
    return {**os.environ,'AGENT_DATA_SOURCE':'yfinance','PYTHONPATH':str(guard),
            'MPLCONFIGDIR':str(tmp_path/'mpl'), 'ANTHROPIC_API_KEY':'unused-test-key'}


def invoke(args, cwd, env):
    return subprocess.run([sys.executable,str(ROOT/'run.py'),*args],cwd=cwd,env=env,
                          capture_output=True,text=True,timeout=60)


def test_cli_run_rebuild_and_reproducible_financial_evidence(tmp_path, cli_environment):
    records=[]
    for seed in ['17','93']:
        result=invoke(['--offline','ASML.AS','--output',str(tmp_path/seed)],tmp_path,
                      {**cli_environment,'PYTHONHASHSEED':seed})
        assert result.returncode==3, result.stderr
        path, = (tmp_path/seed).glob('*/model.json')
        record=json.loads(path.read_text())
        assert record['execution']['status']=='completed'
        assert record['validation']['note_grounding']['passed']
        assert record['validation']['verdict']=='flag_for_review'
        assert record['artifacts']['status']=='complete'
        html=(path.parent/'report_REVIEW.html').read_text()
        images=re.findall(r'data:image/png;base64,([^"\s]+)',html)
        assert len(images)==5
        for encoded in images:
            png=base64.b64decode(encoded)
            assert png.startswith(b'\x89PNG\r\n\x1a\n') and len(png)>1000
        assert 'unused-test-key' not in path.read_text()
        rebuilt=invoke(['--rebuild',str(path)],tmp_path,cli_environment)
        assert rebuilt.returncode==3,rebuilt.stderr
        after=json.loads(path.read_text())
        assert after['execution']==record['execution']
        assert after['call_history']==record['call_history']
        records.append(after)
    for key in ['analysis','chart_data','note']:
        assert records[0][key]==records[1][key]


def test_cli_missing_fixture_is_reviewable_failure(tmp_path, cli_environment):
    result=invoke(['--offline','MISSING','--output',str(tmp_path/'runs')],tmp_path,cli_environment)
    assert result.returncode==3  # model completed; failed financial evidence requires review
    path,=(tmp_path/'runs').glob('*/model.json')
    record=json.loads(path.read_text())
    assert record['validation']['n_fail']>0
    assert any(c['status']=='error' for c in record['call_history'])
    assert not (path.parent/'report.html').exists()


def test_cli_help_has_no_run_side_effects(tmp_path, cli_environment):
    result=invoke(['--help'],tmp_path,cli_environment)
    assert result.returncode==0 and 'usage:' in result.stdout
    assert not list(tmp_path.glob('**/model.json'))


def test_nonfinite_history_does_not_destroy_saved_analysis(tmp_path, monkeypatch):
    import run
    from tools import data
    state=RunState('T');state.finish('completed','Qualitative note.','end_turn')
    monkeypatch.setattr(data,'get_price_history',lambda *args: {'history':[
        {'date':'2026-01-01','close':float('nan')}]})
    assert run._emit_artifacts('T','offline',state.outcome.text,state,str(tmp_path))==1
    record=json.loads((tmp_path/'model.json').read_text())
    assert record['execution']['status']=='completed'
    assert record['artifacts']['status']=='degraded'
    assert any(e['stage']=='fetch_price_history' for e in record['artifacts']['errors'])


def test_unknown_record_version_requires_review():
    from validation.publication import assess_record
    record={'schema_version':999,'analysis':{},'note':'Qualitative note.',
            'execution':{'status':'completed','outcome':{'status':'completed'}}}
    validation,_=assess_record(record)
    assert any(c['check']=='record_schema' and c['status']=='fail' for c in validation['checks'])


@pytest.mark.parametrize('result,status',[('invalid','unavailable'),
    ('{"status":"observed","evidence":{}}','observed')])
def test_provider_probe_checks_worker_output(monkeypatch,result,status):
    from scripts import check_agent1_live as probe
    monkeypatch.setattr(probe.subprocess,'run',lambda *a,**kw: SimpleNamespace(returncode=0,stdout=result))
    assert probe.probe('T','get_prices',1)['status']==status


def test_provider_probe_timeout_is_explicit(monkeypatch):
    from scripts import check_agent1_live as probe
    def timeout(*args,**kwargs):
        raise subprocess.TimeoutExpired('provider',1)
    monkeypatch.setattr(probe.subprocess,'run',timeout)
    assert probe.probe('T','get_prices',1)=={'status':'unavailable','error_type':'timeout'}


def test_real_report_approval_is_revoked_after_evidence_damage(tmp_path, monkeypatch):
    import composer
    from tools import data
    from validation import gate
    from tests.test_gate import _clean, NOW
    analysis=_clean()  # synthetic, explicitly dated provider-shaped evidence
    state=RunState('T')
    for name,result in analysis.items():
        state.record_tool(name,{'ticker':'T'},result)
    state.finish('completed','[[claim:dcf_value]]','end_turn')
    original=gate.assess
    monkeypatch.setattr(gate,'assess',lambda a,**kw: original(a,now=NOW,**kw))
    path=composer.write_sidecar(ticker='T',mode='test',note=state.outcome.text,
        analysis=state.results,calls=state.calls,execution=state.execution_record(),
        price_history=data._history_synthetic('T'),index_history=data._history_synthetic('^GSPC'),
        out_dir=str(tmp_path))
    assert composer.build_report(path).endswith('/report.html')
    record=json.loads(Path(path).read_text())
    assert record['validation']['verdict']=='pass'
    record['analysis']['compute_ratios']['ratios']['net_margin']=999
    composer.save_record(path,record)
    assert composer.build_report(path).endswith('/report_REVIEW.html')
    assert not (tmp_path/'report.html').exists()
    assert json.loads(Path(path).read_text())['validation']['n_fail']>0
