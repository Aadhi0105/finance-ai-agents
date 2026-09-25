"""Publication is fail-closed; evidence survives optional presentation failures."""
import json
from pathlib import Path
import pytest
import composer
import run
from agent.state import RunState
from filelock import FileLock, Timeout


def sidecar(tmp_path):
    state = RunState('T'); state.finish('completed','Qualitative note.','end_turn')
    return Path(run._snapshot('T','offline',state.outcome.text,state,str(tmp_path)))


def fake_charts(monkeypatch, fail=None):
    for name in ['price_vs_index','price_ma','vol_drawdown','peer_scatter','dcf_footballfield']:
        def render(*args, name=name):
            if name == fail:
                raise RuntimeError('SECRET')
            return b'png'
        monkeypatch.setattr(composer, 'render_' + name + '_png', render)
    monkeypatch.setattr(composer, '_valid_history', lambda x: x)


def test_atomic_failure_keeps_prior_checkpoint(tmp_path, monkeypatch):
    path = tmp_path/'model.json'; path.write_text('prior')
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(composer.os,'replace',fail)
    with pytest.raises(OSError):
        composer.atomic_write(path, 'new')
    assert path.read_text() == 'prior'
    assert list(tmp_path.iterdir()) == [path]


def test_chart_failure_preserves_analysis_and_other_charts(tmp_path, monkeypatch):
    path = sidecar(tmp_path); before = json.loads(path.read_text())
    fake_charts(monkeypatch, 'price_ma')
    report = composer.build_report(str(path))
    record = json.loads(path.read_text())
    assert record['analysis'] == before['analysis']
    assert record['execution'] == before['execution']
    assert record['artifacts']['status'] == 'degraded'
    assert len(record['artifacts']['charts']) == 4
    assert report.endswith('report_REVIEW.html')
    assert 'Chart unavailable' in Path(report).read_text()
    assert 'SECRET' not in path.read_text()


def test_corrupt_record_removes_stale_approved_report(tmp_path):
    path = tmp_path/'model.json'; path.write_text('{broken')
    approved = tmp_path/'report.html'; approved.write_text('old approval')
    with pytest.raises(ValueError):
        composer.build_report(str(path))
    assert not approved.exists()


def test_stored_approval_cannot_override_missing_completion(tmp_path, monkeypatch):
    path = sidecar(tmp_path); record = json.loads(path.read_text())
    record.pop('execution'); record['validation'] = {'verdict':'pass'}
    composer.save_record(path,record); fake_charts(monkeypatch)
    (tmp_path/'report.html').write_text('old')
    report = composer.build_report(str(path))
    assert report.endswith('report_REVIEW.html')
    assert not (tmp_path/'report.html').exists()
    checks = json.loads(path.read_text())['validation']['checks']
    assert any(c['check']=='execution_status' and c['status']=='fail' for c in checks)


def test_lock_prevents_concurrent_rebuild_without_removing_report(tmp_path):
    path = sidecar(tmp_path); approved = tmp_path/'report.html'; approved.write_text('old')
    with FileLock(str(tmp_path/'.report.lock')):
        with pytest.raises(Timeout):
            composer.build_report(str(path))
    assert approved.exists()


def test_report_write_failure_leaves_failed_sidecar_and_no_report(tmp_path, monkeypatch):
    path = sidecar(tmp_path); fake_charts(monkeypatch)
    original = composer.atomic_write
    def write(path, content):
        if str(path).endswith('.html'):
            raise OSError('full')
        return original(path,content)
    monkeypatch.setattr(composer,'atomic_write',write)
    with pytest.raises(OSError):
        composer.build_report(str(path))
    assert json.loads(path.read_text())['artifacts']['status'] == 'failed'
    assert not list(tmp_path.glob('*.html'))


def test_fetch_failure_still_saves_analysis_and_builds_review(tmp_path, monkeypatch):
    from tools import data
    state = RunState('T'); state.finish('completed','Qualitative note.','end_turn')
    fake_charts(monkeypatch)
    def fetch(*args):
        assert (tmp_path/'model.json').exists()  # persisted before external work
        raise RuntimeError('SECRET')
    monkeypatch.setattr(data,'get_price_history',fetch)
    code = run._emit_artifacts('T','offline',state.outcome.text,state,str(tmp_path))
    record = json.loads((tmp_path/'model.json').read_text())
    assert code == 1
    assert record['execution']['status'] == 'completed'
    assert record['artifacts']['status'] == 'degraded'
    assert (tmp_path/'report_REVIEW.html').exists()


@pytest.mark.parametrize('status,artifact,verdict,reason,expected', [
    ('completed','complete','pass','end_turn',0),
    ('completed','complete','flag_for_review','end_turn',3),
    ('incomplete','complete','pass','max_tokens',4),
    ('failed','complete','pass','model_error',1),
    ('completed','degraded','pass','end_turn',1),
    ('incomplete','pending','pass','interrupted',130)])
def test_exit_codes(status, artifact, verdict, reason, expected):
    assert run._exit_code({'execution':{'status':status,'outcome':{'reason':reason}},
        'artifacts':{'status':artifact},'validation':{'verdict':verdict}}) == expected


@pytest.mark.parametrize('args',[['--offline','../bad'],['--live','T','--offline','T'],
                                 ['--peers','T'],['--unknown']])
def test_invalid_cli_usage_has_no_execution(args):
    with pytest.raises(SystemExit) as exc:
        run.main(args)
    assert exc.value.code == 2


def test_unique_output_directories(tmp_path):
    first, _ = run._new_output('T',tmp_path)
    second, _ = run._new_output('T',tmp_path)
    assert first != second


def test_invalid_library_ticker_preserves_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENT_DATA_SOURCE','original')
    with pytest.raises(ValueError):
        run.run_offline('../bad',output_root=tmp_path)
    assert run.os.environ['AGENT_DATA_SOURCE'] == 'original'


@pytest.mark.parametrize('history',[[],[{'date':'2026-01-01','close':float('nan')}],
    [{'date':'2026-01-01','close':1},{'date':'2026-01-01','close':2}]])
def test_invalid_history_is_not_rendered(history):
    with pytest.raises(ValueError):
        composer._valid_history(history)


def test_rebuild_retries_chart_errors_but_retains_fetch_errors(tmp_path, monkeypatch):
    path = sidecar(tmp_path); record = json.loads(path.read_text())
    record['artifacts']['errors'] = [{'stage':'fetch_index_history','error_type':'TimeoutError'},
                                    {'stage':'chart_price_ma','error_type':'RuntimeError'}]
    composer.save_record(path,record); fake_charts(monkeypatch)
    composer.build_report(str(path))
    record = json.loads(path.read_text())
    assert record['artifacts']['errors'] == [{'stage':'fetch_index_history','error_type':'TimeoutError'}]
    assert record['artifacts']['status'] == 'degraded'


def test_offline_command_forces_fixture_and_rebuild_needs_no_provider(tmp_path, monkeypatch):
    from tools import data
    monkeypatch.setenv('AGENT_DATA_SOURCE','yfinance')
    monkeypatch.setenv('ANTHROPIC_API_KEY','unused-test-value')
    fake_charts(monkeypatch)
    code = run.run_offline(output_root=tmp_path)
    assert code == 3  # illustrative fixture evidence requires review
    assert run.os.environ['AGENT_DATA_SOURCE'] == 'yfinance'
    path = next(tmp_path.glob('*/model.json'))
    record = json.loads(path.read_text())
    assert record['execution']['status'] == 'completed'
    assert record['meta']['data_source'] == 'fixture'
    assert len(record['call_history']) >= 7
    assert 'unused-test-value' not in path.read_text()
    monkeypatch.setattr(data,'get_price_history',lambda *args: pytest.fail('rebuild fetched data'))
    assert run.rebuild(str(path)) == 3


def test_matplotlib_unavailable_preserves_text_report(tmp_path, monkeypatch):
    import builtins
    path = sidecar(tmp_path)
    original = builtins.__import__
    def import_without_matplotlib(name, *args, **kwargs):
        if name == 'matplotlib' or name.startswith('matplotlib.'):
            raise ImportError('not installed')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',import_without_matplotlib)
    report = composer.build_report(str(path))
    record = json.loads(path.read_text())
    assert record['artifacts']['status'] == 'degraded'
    assert record['artifacts']['charts'] == []
    assert 'Qualitative note.' in Path(report).read_text()
    assert record['execution']['status'] == 'completed'
