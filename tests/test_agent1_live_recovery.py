"""Bounded narrative repair and transparent incomplete chart windows."""
import json
import pytest
from agent.models import ModelResponse, TextBlock, ToolUseBlock
from tests.test_agent1_execution import execute
from tools.price_history import prepare_history


def answer(text):
    return ModelResponse('end_turn',[TextBlock(text)])


def test_single_revision_retains_original_and_feedback():
    outcome,state=execute([answer('bad 123'),answer('corrected')],
        final_feedback=lambda text,results: 'Remove numbers' if '123' in text else None)
    assert outcome.status=='completed' and outcome.text=='corrected'
    assert len(state.model_turns)==2
    assert state.conversation[1]['content'][0]['text']=='bad 123'
    assert state.conversation[2]['content']=='Remove numbers'


def test_repeated_bad_revision_never_starts_third_call():
    outcome,state=execute([answer('bad'),answer('still bad'),answer('unused')],
                          final_feedback=lambda *args:'fix')
    assert len(state.model_turns)==2 and outcome.text=='still bad'


def test_good_draft_needs_no_extra_call():
    _,state=execute([answer('good')],final_feedback=lambda *args:None)
    assert len(state.model_turns)==1


def test_revision_cannot_refresh_financial_evidence():
    outcome,state=execute([answer('bad'),ModelResponse('tool_use',[
        ToolUseBlock('a','sample',{'count':1})])],final_feedback=lambda *args:'fix')
    assert outcome.reason=='narrative_revision_requested_tools'
    assert not state.calls


def test_revision_truncation_is_incomplete():
    outcome,_=execute([answer('bad'),ModelResponse('max_tokens',[TextBlock('partial')])],
                      final_feedback=lambda *args:'fix')
    assert outcome.status=='incomplete'


def test_revision_respects_total_iteration_budget():
    outcome,state=execute([answer('bad')],max_iters=1,final_feedback=lambda *args:'fix')
    assert len(state.model_turns)==1 and outcome.text=='bad'


def history(closes):
    return {'ticker':'T','source':'yfinance','history':[
        {'date':f'2026-09-{i+1:02d}','close':v,'volume':10} for i,v in enumerate(closes)]}


def test_trailing_missing_close_is_audited_without_invented_prices():
    original=history([100,101,float('nan')])
    result=prepare_history(original)
    assert [r['close'] for r in result['history']]==[100,101]
    assert result['raw_history'][-1]['close'] is None
    assert result['excluded_observations'][0]['date']=='2026-09-03'
    assert result['effective_end_date']=='2026-09-02'
    assert '2026-09-03' in result['warnings'][0]
    json.dumps(result,allow_nan=False)


@pytest.mark.parametrize('closes',[[100,None,101],[None,100,101],[None,None],[100,None]])
def test_no_bridging_gaps_or_insufficient_window(closes):
    result=prepare_history(history(closes))
    assert result['error'] and not result['history']
    assert len(result['raw_history'])==len(closes)


def test_history_warning_survives_rebuild_and_keeps_review(tmp_path, monkeypatch):
    import composer
    from run import _emit_artifacts
    from agent.state import RunState
    from tools import data
    state=RunState('T');state.finish('completed','Qualitative note.','end_turn')
    monkeypatch.setattr(data,'get_price_history',lambda *args:history([100,101,None]))
    assert _emit_artifacts('T','live',state.outcome.text,state,str(tmp_path))==3
    path=tmp_path/'model.json'
    before=json.loads(path.read_text())
    assert before['artifacts']['status']=='complete'
    assert len(before['artifacts']['charts'])==5
    composer.build_report(str(path))
    after=json.loads(path.read_text())
    assert after['chart_data']==before['chart_data']
    assert any(c['check']=='history_price_history' and c['status']=='quality_warn'
               for c in after['validation']['checks'])
    assert '2026-09-03' in (tmp_path/'report_REVIEW.html').read_text()


def test_failed_repair_still_fails_publication():
    from validation.publication import assess_record
    result,_=assess_record({'schema_version':2,'analysis':{},'note':'unsupported 123',
        'execution':{'status':'completed','outcome':{'status':'completed'}}})
    assert not result['note_grounding']['passed']


def test_provider_missing_close_and_volume_are_json_safe(monkeypatch):
    import pandas as pd
    import sys
    from types import SimpleNamespace
    from tools.data import _history_yfinance
    frame=pd.DataFrame({'Close':[101,float('nan')],'Volume':[None,float('inf')]},
                       index=pd.to_datetime(['2026-09-24','2026-09-25']))
    monkeypatch.setitem(sys.modules,'yfinance',SimpleNamespace(
        Ticker=lambda ticker:SimpleNamespace(history=lambda **kw:frame)))
    result=_history_yfinance('T','1mo')
    assert result['history'][-1]['close'] is None
    assert all(row['volume'] is None for row in result['history'])
    json.dumps(result,allow_nan=False)


def test_rejected_revision_falls_back_to_evidence_and_requires_review():
    from run import _finalize_narrative
    from agent.state import RunState
    from validation.publication import assess_record
    state=RunState('T')
    state.results={'get_financials':{'ticker':'T','financials':{'currency':'EUR'}},
                   'get_prices':{'ticker':'T','currency':'EUR','current_price':100}}
    state.conversation=[{'role':'assistant','content':'Unsupported 123'}]
    state.finish('completed','Unsupported 123','end_turn',2)
    note=_finalize_narrative(state)
    assert '123' not in note and 'Interpretive prose is withheld' in note
    assert state.conversation[0]['content']=='Unsupported 123'
    result,_=assess_record({'schema_version':2,'analysis':state.results,'note':note,
                           'execution':state.execution_record()})
    assert result['note_grounding']['passed']
    assert any(c['check']=='narrative_fallback' and c['status']=='quality_warn' for c in result['checks'])


def test_fallback_does_not_invent_evidence_or_complete_interrupted_run():
    from run import _finalize_narrative
    from agent.state import RunState
    state=RunState('T');state.finish('completed','Unsupported 123')
    assert _finalize_narrative(state)=='Unsupported 123'
    state.finish('incomplete','Partial 123','max_tokens')
    assert _finalize_narrative(state)=='Partial 123'
    assert state.outcome.status=='incomplete'
