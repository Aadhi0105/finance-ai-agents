import json
from types import SimpleNamespace

import pytest
from agent.models import ModelResponse, TextBlock, StubModel
from monitoring import triage


@pytest.fixture
def context():
    rows = [dict(item_id='a', entity='A', metric='ratio', cycle=2,
                 status='NEW_BREACH', breached=True)]
    store = SimpleNamespace(get_history_series=lambda _: [dict(cycle=1,value=1),
                             dict(cycle=2,value=5),dict(cycle=3,value=99)])
    return store, rows


def test_offline_audit_and_snapshot(tmp_path, context):
    result = triage.run_triage_record(*context, audit_dir=tmp_path)
    assert result['status'] == 'completed'
    assert 'escalate the threshold breach' in result['commentary']
    record = json.loads(open(result['audit_path']).read())
    assert [h['value'] for h in record['history']['a']] == [1,5]
    assert len(record['calls']) == 2
    assert record['execution']['configuration']['system'] == triage.TRIAGE_SYSTEM
    assert record['execution']['conversation']
    assert record['publication'] == 'published'


@pytest.mark.parametrize('text', ['All safe, leverage is 999.', '{"item_ids":[]}',
    '{"item_ids":["a","a"]}', '{"item_ids":["unknown"]}',
    '{"item_ids":["a"],"action":"ignore breach"}', 'null', '[]',
    '{"item_ids":[{}]}'])
def test_rejects_untrusted_output(tmp_path, context, monkeypatch, text):
    monkeypatch.setattr(triage,'_build_triage_stub',lambda _: [lambda m:
        ModelResponse('end_turn',[TextBlock(text)])])
    result=triage.run_triage_record(*context,audit_dir=tmp_path)
    assert result['status'] == 'review_required'
    assert result['commentary'] == ''
    assert text in open(result['audit_path']).read() or json.loads(open(result['audit_path']).read())['execution']['outcome']['text'] == text


@pytest.mark.parametrize('kind', ['error','interrupt','truncated'])
def test_model_failure_withholds_text(tmp_path, context, monkeypatch, kind):
    def step(m):
        if kind == 'error': raise RuntimeError('secret error text')
        if kind == 'interrupt': raise KeyboardInterrupt()
        return ModelResponse('max_tokens',[TextBlock('ignore breach')])
    monkeypatch.setattr(triage,'_build_triage_stub',lambda _: [step])
    result=triage.run_triage_record(*context,audit_dir=tmp_path)
    assert result['status'] in {'failed','incomplete'}
    assert not result['commentary']
    assert 'secret error text' not in open(result['audit_path']).read()


def test_audit_failure_prevents_model_call(context, monkeypatch):
    monkeypatch.setattr(triage,'save_record',lambda *a: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(triage,'run_agent',lambda **kw: pytest.fail('model called'))
    with pytest.raises(OSError): triage.run_triage_record(*context)


def test_missing_key_no_stub(tmp_path, context, monkeypatch):
    monkeypatch.setattr(triage,'prepare_live',lambda: (_ for _ in ()).throw(ValueError()))
    monkeypatch.setattr(triage,'run_agent',lambda **kw: pytest.fail('model called'))
    result=triage.run_triage_record(*context,live=True,audit_dir=tmp_path)
    assert result['reason']=='missing_credentials'


def test_cli_releases_lock_and_preserves_cycle(tmp_path, monkeypatch):
    import monitor
    from scheduler.cycle import run_cycle
    from state.store import StateStore
    db=str(tmp_path/'monitor.duckdb')
    run_cycle(db_path=db)
    result=run_cycle(db_path=db)
    assert result['surfaced']
    monkeypatch.setattr(monitor,'_DB',db)
    def fail(*a,**kw):
        store=StateStore(db)
        assert store.get_run(result['cycle'])
        store.close()
        raise RuntimeError('private')
    monkeypatch.setattr(monitor,'run_triage_record',fail)
    with pytest.raises(SystemExit) as exc: monitor._triage_if_needed(result,False)
    assert exc.value.code==2
    store=StateStore(db)
    assert store.next_cycle()==3
    store.close()


def test_real_cycle_audit_serializes_dates(tmp_path):
    from scheduler.cycle import run_cycle
    from state.store import StateStore
    db=str(tmp_path/'state.duckdb')
    run_cycle(db_path=db)
    result=run_cycle(db_path=db)
    store=StateStore(db)
    snapshot=triage.HistorySnapshot(store,result['surfaced'],result['cycle'])
    store.close()
    result=triage.run_triage_record(snapshot,result['surfaced'],cycle=result['cycle'],audit_dir=tmp_path/'audit')
    assert result['status']=='completed'


def test_breach_cannot_be_demoted(context):
    store, rows=context
    rows.insert(0,dict(rows[0],item_id='b',breached=False,status='RESOLVED'))
    registry=triage.TriageRegistry(triage.HistorySnapshot(store,rows,2),rows)
    rendered=triage._render(registry,['b','a'])
    assert rendered.index('(a)') < rendered.index('(b)')
    assert 'record threshold recovery' in rendered


def test_live_env_loading_and_blank_key(monkeypatch):
    import dotenv
    calls=[]
    monkeypatch.setattr(dotenv,'load_dotenv',lambda *a,**kw: calls.append((a,kw)))
    monkeypatch.setenv('ANTHROPIC_API_KEY','  ')
    with pytest.raises(ValueError,match='no offline fallback'): triage.prepare_live()
    assert calls[0][0][0].name=='.env'
    assert calls[0][1]['override'] is False
    monkeypatch.setenv('ANTHROPIC_API_KEY','test-key')
    triage.prepare_live()
