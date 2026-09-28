"""Persistent cycle/recovery contracts, using disposable databases only."""
from datetime import date
from pathlib import Path
import json
import os
import subprocess
import sys
import pytest
from scheduler import cycle
from state.store import StateStore
from tests.test_agent2_batch1 import covenant
from tests.test_agent2_state import _row

ROOT=Path(__file__).resolve().parents[1]


def setup(monkeypatch, covs):
    monkeypatch.setattr(cycle, '_load_watchlist', lambda: (covs,date(2026,1,1)))


def test_stale_and_missing_cycles_advance_to_next_observation(tmp_path,monkeypatch):
    setup(monkeypatch,[covenant({1:1,2:1,4:4},{'2':'2026-01-01'})])
    db=str(tmp_path/'t.db')
    results=[cycle.run_cycle(db_path=db) for _ in range(4)]
    assert [r['cycle'] for r in results]==[1,2,3,4]
    assert results[1]['status']==results[2]['status']=='no_new_observations'
    assert 'compliance was not reassessed' in results[2]['report']
    store=StateStore(db)
    try:
        assert len(store.get_history_series('x'))==2
        assert store.get_run(3)==results[2]
    finally:store.close()


def test_empty_watchlist_progress(tmp_path,monkeypatch):
    setup(monkeypatch,[])
    db=str(tmp_path/'t.db')
    assert cycle.run_cycle(db_path=db)['cycle']==1
    assert cycle.run_cycle(db_path=db)['cycle']==2


def test_explicit_replay_is_identical_and_does_not_call_provider(tmp_path,monkeypatch):
    db=str(tmp_path/'t.db');first=cycle.run_cycle(db_path=db)
    monkeypatch.setattr(cycle,'_load_watchlist',lambda:pytest.fail('replay fetched new data'))
    replay=cycle.run_cycle(db_path=db,asof_cycle=1)
    assert replay=={**first,'replayed':True}
    store=StateStore(db)
    try:assert store.next_cycle()==2
    finally:store.close()


def test_catchup_gap_and_unavailable_replay(tmp_path):
    db=str(tmp_path/'t.db');cycle.run_cycle(db_path=db)
    result=cycle.run_cycle(db_path=db,asof_cycle=5)
    assert result['gap']==3
    with pytest.raises(ValueError,match='skipped'):cycle.run_cycle(db_path=db,asof_cycle=3)
    assert cycle.run_cycle(db_path=db)['cycle']==6


@pytest.mark.parametrize('older',[False,True])
def test_corrections_quarantined_without_overwriting(tmp_path,monkeypatch,older):
    cov=covenant({1:1,2:2,3:9},{'3':'2026-01-01' if older else '2026-01-02'})
    setup(monkeypatch,[cov]);db=str(tmp_path/'t.db')
    cycle.run_cycle(db_path=db);cycle.run_cycle(db_path=db)
    r=cycle.run_cycle(db_path=db)
    assert r['status']=='review_required'
    assert r['skipped'][0]['reason']=='correction_requires_review'
    assert r['skipped'][0]['candidate']['value']==9
    store=StateStore(db)
    try:
        assert store.get_current('x')['value']==2
        assert [x['value'] for x in store.get_history_series('x')]==[1,2]
        assert store.get_run(3)['skipped']==r['skipped']
    finally:store.close()


def test_definition_change_requires_review(tmp_path,monkeypatch):
    cov=covenant({1:1,2:2});setup(monkeypatch,[cov]);db=str(tmp_path/'t.db')
    cycle.run_cycle(db_path=db);cov['threshold']=100
    r=cycle.run_cycle(db_path=db)
    assert r['skipped'][0]['reason']=='definition_change_requires_review'


@pytest.mark.parametrize('method',['write_history','upsert_current','write_run'])
@pytest.mark.parametrize('exception',[RuntimeError,KeyboardInterrupt])
def test_failure_rolls_back_ledger_history_and_details(tmp_path,monkeypatch,method,exception):
    db=str(tmp_path/'t.db');cycle.run_cycle(db_path=db)
    original=getattr(StateStore,method)
    def fail(self,*args):
        original(self,*args)
        raise exception('injected after write')
    with monkeypatch.context() as m:
        m.setattr(StateStore,method,fail)
        with pytest.raises(exception):cycle.run_cycle(db_path=db)
    store=StateStore(db)
    try:
        assert store.next_cycle()==2 and store.get_run(2) is None
        assert all(r['cycle']==1 for r in store.full_state())
        assert store.con.execute('SELECT count(*) FROM observation_details WHERE data_ts > ?', ['2026-01-01']).fetchone()[0]==0
    finally:store.close()
    assert cycle.run_cycle(db_path=db)['cycle']==2


def test_render_failure_cannot_advance_state(tmp_path,monkeypatch):
    db=str(tmp_path/'t.db')
    monkeypatch.setattr(cycle,'_build_report',lambda *a: (_ for _ in ()).throw(RuntimeError('render')))
    with pytest.raises(RuntimeError):cycle.run_cycle(db_path=db)
    store=StateStore(db)
    try:assert store.next_cycle()==1 and store.full_state()==[]
    finally:store.close()


def test_complete_diagnostics_saved_and_detached(tmp_path):
    db=str(tmp_path/'t.db');r=cycle.run_cycle(db_path=db);row=r['rows'][0]
    store=StateStore(db)
    try:
        saved=store.get_observation_evidence(row['item_id'],row['data_ts'])
        assert saved==row and '_anomaly_detail' in saved
        saved['_anomaly_detail'].clear()
        assert store.get_observation_evidence(row['item_id'],row['data_ts'])==row
    finally:store.close()


def test_legacy_history_advances_without_inventing_ledger(tmp_path):
    db=str(tmp_path/'legacy.db');s=StateStore(db)
    s.write_history(_row(cycle=4));s.upsert_current(_row(cycle=4))
    s.con.execute('DROP TABLE cycle_runs');s.con.execute('DROP TABLE observation_details');s.close()
    s=StateStore(db)
    try:
        assert s.next_cycle()==5 and s.get_run(4) is None
        assert s.get_observation_evidence('acme','2026-01-01') is None
    finally:s.close()
    assert cycle.run_cycle(db_path=db)['cycle']==5


def test_bare_database_filename_and_conflicting_duplicate(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);s=StateStore('simple.db')
    try:
        s.write_history(_row());s.write_history(_row())
        with pytest.raises(ValueError):s.write_history(_row(value=9))
        assert len(s.get_history_series('acme'))==1
    finally:s.close()


def test_overlapping_processes_same_cycle_replay(tmp_path):
    db=str(tmp_path/'overlap.db')
    code='from scheduler.cycle import run_cycle; import sys; r=run_cycle(db_path=sys.argv[1],asof_cycle=1); print(r["replayed"])'
    env={**os.environ,'PYTHONPATH':str(ROOT)}
    children=[subprocess.Popen([sys.executable,'-c',code,db],cwd=tmp_path,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    outputs=[]
    for child in children:
        out,err=child.communicate(timeout=30);assert child.returncode==0,err;outputs.append(out.strip())
    assert sorted(outputs)==['False','True']
    s=StateStore(db)
    try:assert s.next_cycle()==2
    finally:s.close()


def test_cli_other_directory_and_quoted_cron(tmp_path):
    db=tmp_path/'folder with spaces'/'monitor.db'
    r=subprocess.run([sys.executable,str(ROOT/'monitor.py'),'--once','--db',str(db)],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stderr
    assert 'BASELINE' in r.stdout and db.exists()
    from scheduler.trigger import cron_line
    import shlex
    assert shlex.quote(str(ROOT)) in cron_line()


def test_review_hold_persists_across_later_fresh_data(tmp_path,monkeypatch):
    cov=covenant({1:1,2:9,3:3},{'2':'2026-01-01'})
    setup(monkeypatch,[cov]);db=str(tmp_path/'t.db')
    cycle.run_cycle(db_path=db);cycle.run_cycle(db_path=db)
    r=cycle.run_cycle(db_path=db)
    assert r['status']=='review_required' and r['skipped'][0]['reason']=='pending_review'
    store=StateStore(db)
    try:
        assert store.get_current('x')['value']==1
        assert store.pending_review('x')['candidate']['value']==9
    finally:store.close()


def test_review_queue_rolls_back_with_failed_ledger(tmp_path,monkeypatch):
    cov=covenant({1:1,2:9},{'2':'2026-01-01'});setup(monkeypatch,[cov]);db=str(tmp_path/'t.db')
    cycle.run_cycle(db_path=db)
    with monkeypatch.context() as m:
        m.setattr(StateStore,'write_run',lambda *a: (_ for _ in ()).throw(RuntimeError('ledger')))
        with pytest.raises(RuntimeError):cycle.run_cycle(db_path=db)
    s=StateStore(db)
    try:assert s.pending_review('x') is None and s.next_cycle()==2
    finally:s.close()


def test_hard_process_termination_releases_lock_and_rolls_back(tmp_path):
    import time
    db=str(tmp_path/'crash.db');marker=tmp_path/'ready'
    code='''from state.store import StateStore
from tests.test_agent2_state import _row
from pathlib import Path
import sys,time
s=StateStore(sys.argv[1])
with s.transaction():
 s.write_history(_row())
 s.upsert_current(_row())
 s.write_run({'cycle':1})
 Path(sys.argv[2]).touch()
 time.sleep(60)
'''
    child=subprocess.Popen([sys.executable,'-c',code,db,str(marker)],cwd=ROOT,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+10
        while not marker.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.02)
        assert marker.exists()
        child.kill();child.communicate(timeout=10)
        s=StateStore(db)
        try:assert s.full_state()==[] and s.next_cycle()==1 and s.get_run(1) is None
        finally:s.close()
        assert cycle.run_cycle(db_path=db)['cycle']==1
    finally:
        if child.poll() is None:child.kill();child.communicate(timeout=10)


def test_replay_does_not_run_model_triage(monkeypatch):
    import monitor
    monkeypatch.setattr(monitor,'run_triage',lambda *a,**k:pytest.fail('replayed triage'))
    monitor._triage_if_needed({'replayed':True,'surfaced':[{'item_id':'x'}]},live=True)


def test_automatic_overlapping_runs_allocate_distinct_cycles(tmp_path):
    db=str(tmp_path/'automatic.db')
    code='from scheduler.cycle import run_cycle; import sys; print(run_cycle(db_path=sys.argv[1])["cycle"])'
    env={**os.environ,'PYTHONPATH':str(ROOT)}
    children=[subprocess.Popen([sys.executable,'-c',code,db],cwd=tmp_path,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    outputs=[]
    for child in children:
        out,err=child.communicate(timeout=30);assert child.returncode==0,err;outputs.append(out.strip())
    assert sorted(outputs)==['1','2']
    s=StateStore(db)
    try:
        assert s.next_cycle()==3 and s.get_run(1) and s.get_run(2)
        assert len(s.get_history_series('acme_leverage'))==2
    finally:s.close()


def test_cron_preserves_custom_database_path(tmp_path):
    from scheduler.trigger import cron_line
    import shlex
    path=tmp_path/'custom db.duckdb'
    assert '--db '+shlex.quote(str(path)) in cron_line(db_path=str(path))
