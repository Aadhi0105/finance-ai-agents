"""Real subprocess admission/cancellation and mocked paid-call boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from keystone import operation, budget
from keystone.maintenance import gate, inherited_fds
from agent.models import AnthropicModel


def test_concurrent_legacy_cli_refused(tmp_path):
    with gate():
        result = subprocess.run([sys.executable, 'run.py', '--offline', 'ASML.AS', '--output', str(tmp_path/'out')], capture_output=True)
    assert result.returncode != 0
    assert not (tmp_path/'out').exists()


def test_inherited_lease_and_cleanup(tmp_path):
    with gate():
        code = 'from keystone.maintenance import gate\nwith gate(): print("admitted")'
        p = subprocess.run([sys.executable, '-c', code], pass_fds=inherited_fds(), capture_output=True, text=True)
        assert p.returncode == 0 and 'admitted' in p.stdout
    with gate(exclusive=True):
        pass


def test_supervised_agent1_duplicate_and_permissions(tmp_path):
    args = ['--offline', 'ASML.AS', '--output', str(tmp_path/'research')]
    code, path, record = operation.execute('agent1', args, 'research-one', directory=tmp_path/'ops')
    assert code == 3 and record['status'] == 'review_required'
    assert not path.stat().st_mode & 0o077
    assert not next((tmp_path/'research').glob('*/model.json')).stat().st_mode & 0o077
    assert json.loads((path.parent/'usage.json').read_text())['requests_reserved'] == 0
    for changed in (args, ['--offline', 'OTHER']):
        with pytest.raises(FileExistsError):
            operation.execute('agent1', changed, 'research-one', directory=tmp_path/'ops')
    assert len(list((tmp_path/'research').iterdir())) == 1


def test_supervised_agent3_nested_worker(tmp_path):
    args = ['ASML.AS', '--alias', 'ASML', '--scorer', 'stub', '--demo', '--fixture', 'fixtures/news.json',
            '--as-of', '2026-01-28T23:59:00Z', '--db', str(tmp_path/'catalyst.duckdb'), '--output-dir', str(tmp_path/'news')]
    code, path, record = operation.execute('agent3-news', args, 'news-one', directory=tmp_path/'ops')
    assert code == 3 and record['status'] == 'review_required'
    saved = json.loads(next((tmp_path/'news').glob('*/run.json')).read_text())
    assert saved['status'] == 'held'


@pytest.mark.parametrize('agent,args', [('agent1',['--live','ASML.AS']),('agent3-events',[]),('agent3-news',['ASML.AS']),('agent2',['--data-source=yfinance'])])
def test_live_data_requires_opt_in(tmp_path, agent, args):
    with pytest.raises(ValueError, match='Live data'):
        operation.execute(agent,args,'live',directory=tmp_path/'ops')
    assert not (tmp_path/'ops').exists()


@pytest.mark.parametrize('args', [['--reset'],['--loop'],['--cron']])
def test_unsupported_operations(tmp_path,args):
    with pytest.raises(ValueError):operation.execute('agent2',args,'bad',directory=tmp_path/'ops')


def test_timeout_retains_possible_commit_and_kills_descendant(tmp_path,monkeypatch):
    marker = tmp_path/'committed'; late = tmp_path/'late'
    child = f'import time; from pathlib import Path; time.sleep(3); Path({str(late)!r}).write_text("bad")'
    script = tmp_path/'stall.py'
    script.write_text(f'import subprocess,sys,time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text("saved")\nsubprocess.Popen([sys.executable,"-c",{child!r}])\ntime.sleep(60)\n')
    monkeypatch.setitem(operation.ENTRYPOINTS,'agent1',[str(script)])
    code,path,record = operation.execute('agent1',[],'timeout',directory=tmp_path/'ops',timeout=1)
    assert code == 124 and record['status']=='outcome_unknown'
    assert marker.read_text()=='saved'
    time.sleep(3)
    assert not late.exists()
    with gate(): pass
    with pytest.raises(FileExistsError):operation.execute('agent1',[],'timeout',directory=tmp_path/'ops')


def make_budget(tmp_path,monkeypatch,**overrides):
    p=tmp_path/'usage.json'
    data=dict(schema_version=1,enabled=True,max_requests=12,max_output_tokens=48000,
              requests_reserved=0,output_tokens_reserved=0,input_bytes_limit=100000,
              deadline_epoch=time.time()+60,calls=[])
    data.update(overrides);operation.write_record(p,data)
    monkeypatch.setenv('KEYSTONE_SUPERVISED','1');monkeypatch.setenv('KEYSTONE_USAGE_PATH',str(p))
    return p


@pytest.mark.parametrize('overrides',[dict(enabled=False),dict(max_requests=0),dict(max_output_tokens=1),dict(deadline_epoch=0),dict(input_bytes_limit=1)])
def test_budget_refuses_before_client(tmp_path,monkeypatch,overrides):
    make_budget(tmp_path,monkeypatch,**overrides)
    model=AnthropicModel();monkeypatch.setattr(model,'_lazy_client',lambda:pytest.fail('network admitted'))
    with pytest.raises(budget.BudgetRefused):model.respond('system',[],[])


def test_unknown_usage_stops_next_call(tmp_path,monkeypatch):
    p=make_budget(tmp_path,monkeypatch)
    model=AnthropicModel()
    def fail(**kw):raise RuntimeError('SENSITIVE-provider-error')
    model._client=SimpleNamespace(messages=SimpleNamespace(create=fail))
    with pytest.raises(RuntimeError):model.respond('SECRET-PROMPT',[],[])
    with pytest.raises(budget.BudgetRefused):model.respond('other',[],[])
    data=json.loads(p.read_text());assert data['requests_reserved']==1
    assert data['calls'][0]['status']=='usage_unknown'
    assert 'SENSITIVE' not in p.read_text() and 'SECRET-PROMPT' not in p.read_text()


def test_known_usage_and_output_reservation_ceiling(tmp_path,monkeypatch):
    p=make_budget(tmp_path,monkeypatch,max_output_tokens=8000)
    model=AnthropicModel()
    response=SimpleNamespace(content=[],stop_reason='end_turn',usage=SimpleNamespace(model_dump=lambda:dict(input_tokens=20,output_tokens=5)))
    model._client=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw:response))
    for _ in range(2):model.respond('s',[],[])
    with pytest.raises(budget.BudgetRefused):model.respond('s',[],[])
    data=json.loads(p.read_text())
    assert data['output_tokens_reserved']==8000 and len(data['calls'])==2
    assert all(c['usage']['input_tokens']==20 and c['cost_status']=='unpriced' for c in data['calls'])


def test_process_failure_logs_no_raw_output(tmp_path,monkeypatch):
    monkeypatch.setitem(operation.ENTRYPOINTS,'agent1',['-c','import sys; print("SECRET-TEXT"); sys.exit(1)'])
    code,path,record=operation.execute('agent1',[],'failed',directory=tmp_path/'ops')
    assert code==1 and record['status']=='failed_inspect_state'
    assert 'SECRET-TEXT' not in path.read_text()


def test_committed_delivery_status():
    assert operation.outcome('agent4-close',3)[0]=='committed_delivery_failed'
    assert operation.outcome('agent2',3)[0]=='review_required'


def test_interrupted_database_transaction_preserves_committed_state(tmp_path,monkeypatch):
    import duckdb
    db=tmp_path/'state.duckdb'
    script=tmp_path/'transaction.py'
    script.write_text(f'import duckdb,time\nc=duckdb.connect({str(db)!r})\nc.execute("CREATE TABLE ledger (id INTEGER)")\nc.execute("INSERT INTO ledger VALUES (1)")\nc.execute("BEGIN")\nc.execute("INSERT INTO ledger VALUES (2)")\ntime.sleep(60)\n')
    monkeypatch.setitem(operation.ENTRYPOINTS,'agent1',[str(script)])
    code,_,record=operation.execute('agent1',[],'transaction',directory=tmp_path/'ops',timeout=2)
    assert code==124 and record['status']=='outcome_unknown'
    con=duckdb.connect(str(db))
    try:assert con.execute('SELECT * FROM ledger').fetchall()==[(1,)]
    finally:con.close()


def test_sigterm_supervisor_records_cancellation(tmp_path):
    import signal
    ready=tmp_path/'ready'
    script=tmp_path/'worker.py'
    script.write_text(f'from pathlib import Path\nimport time\nPath({str(ready)!r}).touch()\ntime.sleep(60)\n')
    command=('from keystone.operation import execute,ENTRYPOINTS\n'
             f'ENTRYPOINTS["agent1"]=[{str(script)!r}]\n'
             f'code,_,_=execute("agent1",[],"cancel",directory={str(tmp_path/"ops")!r})\n'
             'raise SystemExit(code)')
    p=subprocess.Popen([sys.executable,'-c',command],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        until=time.monotonic()+10
        while not ready.exists() and p.poll() is None and time.monotonic()<until:time.sleep(.05)
        assert ready.exists()
        p.send_signal(signal.SIGTERM)
        assert p.wait(timeout=10)==130
    finally:
        if p.poll() is None:p.kill();p.wait()
    record=json.loads((tmp_path/'ops/cancel/operation.json').read_text())
    assert record['status']=='outcome_unknown' and record['termination']=='cancelled'
    with gate():pass


def test_empty_fixture_does_not_bypass_live_admission(tmp_path):
    with pytest.raises(ValueError,match='Live data'):
        operation.execute('agent3-news',['ASML.AS','--fixture='],'empty',directory=tmp_path/'ops')


def test_abbreviated_live_option_cannot_start_provider(tmp_path):
    code,_,_=operation.execute('agent1',['--liv=ASML.AS'],'abbreviated',directory=tmp_path/'ops')
    assert code==2


def test_control_record_failure_never_launches_worker(tmp_path,monkeypatch):
    def fail(*_):raise OSError('disk unavailable')
    monkeypatch.setattr(operation,'sync_directory',fail)
    monkeypatch.setattr(operation.subprocess,'Popen',lambda *a,**k:pytest.fail('worker launched without durable identity'))
    with pytest.raises(OSError):operation.execute('agent1',[],'disk-failure',directory=tmp_path/'ops')
    assert (tmp_path/'ops/disk-failure').is_dir()
    with gate():pass
