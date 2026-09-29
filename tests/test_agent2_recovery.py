"""Decision integrity, recalculation, recovery and original-evidence retry tests."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import subprocess
import sys

import pytest
from monitoring.recovery import decide, retry_triage
from scheduler import cycle
from state.store import StateStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def held(tmp_path, monkeypatch):
    cov={'item_id':'x','entity':'X','metric':'ratio','covenant_type':'test','threshold':3,
         'direction':'below','cycle_values':{'1':1,'2':4,'3':5,'4':2,'5':2,'6':2},
         'data_ts_by_cycle':{'4':'2026-01-02'}}
    monkeypatch.setattr(cycle,'_load_watchlist',lambda:([cov],date(2026,1,1)))
    db=str(tmp_path/'monitor.db')
    runs=[cycle.run_cycle(db_path=db) for _ in range(4)]
    store=StateStore(db)
    try: token=store.reviews()[0]['review_id']
    finally: store.close()
    return db,cov,runs,token


def inspect(db):
    store=StateStore(db)
    try:
        return dict(history=store.get_history_series('x'), current=store.get_current('x'),
                    reviews=store.reviews(), decisions=store.decisions(), next=store.next_cycle(),
                    runs=[store.get_run(i) for i in range(1,store.next_cycle())])
    finally:store.close()


def test_approve_recalculates_suffix_preserves_originals_and_resumes(held):
    db,cov,runs,token=held
    assert runs[2]['rows'][0]['status']=='WIDENING'
    decision=decide(db,token,'approve','Analyst','Verified corrected input')
    state=inspect(db)
    assert [r['value'] for r in state['history']]==[1,2,5]
    assert state['current']['status']=='NEW_BREACH'
    assert state['runs']==runs and not state['reviews'] and state['next']==5
    assert decision['before'][1]['value']==4 and decision['after'][1]['value']==2
    assert decision['after'][-1]['revision_id']==token
    assert cycle.run_cycle(db_path=db)['rows'][0]['status']=='RESOLVED'


def test_reject_is_specific_and_new_observations_resume(held):
    db,cov,runs,token=held
    decide(db,token,'reject','Analyst','Source correction withdrawn')
    cov['data_ts_by_cycle']['5']='2026-01-02'
    result=cycle.run_cycle(db_path=db)
    assert result['skipped'][0]['reason']=='rejected_candidate'
    assert [r['value'] for r in inspect(db)['history']]==[1,4,5]
    assert not inspect(db)['reviews']
    assert cycle.run_cycle(db_path=db)['rows'][0]['status']=='RESOLVED'


def test_duplicate_decision_idempotent_and_conflicting_decision_refused(held):
    db,_,_,token=held
    first=decide(db,token,'approve','A','Verified')
    second=decide(db,token,'approve','A','Verified')
    assert second=={**first,'replayed':True}
    with pytest.raises(ValueError,match='different'):decide(db,token,'reject','A','Verified')
    assert len(inspect(db)['decisions'])==1


@pytest.mark.parametrize('who,reason',[('', 'verified'),('A',''),(None,'verified')])
def test_decisions_require_attribution(held,who,reason):
    db,_,_,token=held
    before=inspect(db)
    with pytest.raises(ValueError):decide(db,token,'approve',who,reason)
    assert inspect(db)==before


def test_stale_review_id_refused(held):
    with pytest.raises(ValueError,match='stale'):decide(held[0],'not-current','approve','A','Verified')


@pytest.mark.parametrize('failure',[RuntimeError,KeyboardInterrupt])
def test_failed_rebuild_rolls_back_decision_rows_and_hold(held,monkeypatch,failure):
    db,_,_,token=held;before=inspect(db)
    original=StateStore.upsert_current
    def fail(self,row):
        original(self,row)
        raise failure('after state write')
    monkeypatch.setattr(StateStore,'upsert_current',fail)
    with pytest.raises(failure):decide(db,token,'approve','A','Verified')
    assert inspect(db)==before


def test_backfill_is_sorted_by_reporting_date(tmp_path,monkeypatch):
    cov={'item_id':'x','entity':'X','metric':'r','covenant_type':'test','threshold':3,'direction':'below',
         'cycle_values':{'1':1,'3':5,'4':2},'data_ts_by_cycle':{'4':'2026-01-02'}}
    monkeypatch.setattr(cycle,'_load_watchlist',lambda:([cov],date(2026,1,1)))
    db=str(tmp_path/'backfill.db')
    for _ in range(4):cycle.run_cycle(db_path=db)
    token=inspect(db)['reviews'][0]['review_id']
    decision=decide(db,token,'approve','A','Verified missing period')
    assert [r['value'] for r in inspect(db)['history']]==[1,2,5]
    assert inspect(db)['current']['data_ts']==date(2026,1,3)
    assert decision['after'][1]['cycle']==4  # Known in cycle 4, reporting date Jan 2.


def test_definition_approval_creates_new_series(tmp_path,monkeypatch):
    cov={'item_id':'x','entity':'X','metric':'r','covenant_type':'test','threshold':3,'direction':'below',
         'cycle_values':{'1':1,'2':4,'3':5}}
    monkeypatch.setattr(cycle,'_load_watchlist',lambda:([cov],date(2026,1,1)))
    db=str(tmp_path/'definition.db');cycle.run_cycle(db_path=db)
    cov['threshold']=6;cycle.run_cycle(db_path=db)
    token=inspect(db)['reviews'][0]['review_id']
    with pytest.raises(ValueError,match='new replacement'):decide(db,token,'approve','A','New policy')
    decision=decide(db,token,'approve','A','New policy',replacement_id='x_v2')
    assert decision['after'][0]['status']=='BASELINE'
    assert inspect(db)['history'][0]['value']==1
    assert cycle.run_cycle(db_path=db)['skipped'][0]['reason']=='retired_definition'
    store=StateStore(db)
    try:assert store.get_current('x_v2')['threshold']==6
    finally:store.close()


def test_retry_after_correction_uses_original_cycle_history(held,tmp_path,monkeypatch):
    db,_,runs,token=held
    decide(db,token,'approve','A','Verified')
    before=inspect(db)
    monkeypatch.setattr(cycle,'run_cycle',lambda **kw:pytest.fail('cycle rerun'))
    from monitoring import live_data
    monkeypatch.setattr(live_data,'fetch',lambda *a:pytest.fail('provider fetch'))
    first=retry_triage(db,3,audit_dir=tmp_path/'audit')
    second=retry_triage(db,3,audit_dir=tmp_path/'audit')
    assert first['status']==second['status']=='completed'
    assert first['audit_path']!=second['audit_path']
    audit=json.loads(Path(first['audit_path']).read_text())
    assert [p['value'] for p in audit['history']['x']]==[1,4,5]
    assert audit['rows']==runs[2]['surfaced']
    assert audit['retry_context']['kind']=='explicit_cycle_retry'
    assert inspect(db)==before


def test_retry_model_failure_does_not_mutate_cycle(held,tmp_path,monkeypatch):
    from monitoring import triage
    db=held[0];before=inspect(db)
    def fail(_):raise RuntimeError('private')
    monkeypatch.setattr(triage,'_build_triage_stub',lambda rows:[fail])
    result=retry_triage(db,3,audit_dir=tmp_path/'audit')
    assert result['status']=='failed' and result['audit_path']
    assert inspect(db)==before


def test_legacy_missing_frozen_evidence_after_restatement_refused(held,tmp_path):
    db,_,_,token=held
    store=StateStore(db)
    try:
        saved=store.get_run(3);del saved['triage_history']
        store.con.execute('UPDATE cycle_runs SET payload=? WHERE cycle=3',[json.dumps(saved)])
    finally:store.close()
    decide(db,token,'approve','A','Verified')
    with pytest.raises(ValueError,match='legacy cycle'):retry_triage(db,3,audit_dir=tmp_path/'audit')


def test_concurrent_same_decision_applies_once(held):
    db,_,_,token=held
    code="from monitoring.recovery import decide; import sys; print(decide(sys.argv[1],sys.argv[2],'approve','A','Verified')['replayed'])"
    children=[subprocess.Popen([sys.executable,'-c',code,db,token],cwd=ROOT,
              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    results=[]
    for child in children:
        out,err=child.communicate(timeout=30);assert child.returncode==0,err;results.append(out.strip())
    assert sorted(results)==['False','True'] and len(inspect(db)['decisions'])==1


def test_approval_recomputes_dated_drift_not_only_thresholds(tmp_path,monkeypatch):
    cov={'item_id':'x','entity':'X','metric':'r','covenant_type':'test','threshold':10,'direction':'below',
         'cycle_values':{str(n):n for n in range(1,9)},'data_ts_by_cycle':{'9':'2026-01-04'}}
    cov['cycle_values']['9']=40
    monkeypatch.setattr(cycle,'_load_watchlist',lambda:([cov],date(2026,1,1)))
    db=str(tmp_path/'statistics.db')
    for _ in range(9):cycle.run_cycle(db_path=db)
    state=inspect(db);assert state['current']['drift_slope']==1
    result=decide(db,state['reviews'][0]['review_id'],'approve','A','Reviewed restatement')
    # Independent OLS: replacing y=4 with 40 at x=3 changes slope by
    # 36 * (3 - 3.5) / sum((x-3.5)^2) = -18/42.
    assert result['after'][-1]['drift_slope']==pytest.approx(1-18/42,abs=5e-6)
    assert inspect(db)['runs'][7]['rows'][0]['drift_slope']==1


def test_review_cli_and_retry_work_without_fetching(held,tmp_path):
    db,_,_,token=held
    args=[sys.executable,str(ROOT/'monitor.py'),'--db',db]
    pending=subprocess.run(args+['--reviews'],cwd=tmp_path,capture_output=True,text=True,check=True)
    assert json.loads(pending.stdout)[0]['review_id']==token
    approved=subprocess.run(args+['--approve-review',token,'--reviewer','Analyst',
        '--reason','Verified filing'],cwd=tmp_path,capture_output=True,text=True,check=True)
    assert json.loads(approved.stdout)['action']=='approve'
    retry=subprocess.run(args+['--retry-triage','3'],cwd=tmp_path,capture_output=True,text=True,check=True)
    assert 'original evidence, not current state' in retry.stdout
    assert inspect(db)['next']==5


def test_live_definition_replacement_matches_updated_watchlist(tmp_path,monkeypatch):
    from monitoring import live_data
    profile=live_data.load_profile(ROOT/'watchlists/stadler-annual.json')
    profile['items']=profile['items'][:1]
    reference=json.loads((ROOT/'references/monitoring/SRAIL.SW-2025-12-31.json').read_text())
    snapshot={'ticker':'SRAIL.SW','source':'yfinance','period':'2025-12-31','period_type':'annual',
              'currency':'CHF','monetary_unit':'base','values':reference['expected_fields']}
    monkeypatch.setattr(live_data,'fetch',lambda _:deepcopy(snapshot))
    path=tmp_path/'watchlist.json';path.write_text(json.dumps(profile));db=str(tmp_path/'live.db')
    cycle.run_cycle(db_path=db,watchlist_path=path)
    profile['items'][0]['threshold']=.9;path.write_text(json.dumps(profile))
    cycle.run_cycle(db_path=db,watchlist_path=path)
    store=StateStore(db)
    try:token=store.reviews()[0]['review_id']
    finally:store.close()
    decide(db,token,'approve','A','Approved revised analyst policy',replacement_id='stadler_current_ratio_v2')
    profile['items'][0]['item_id']='stadler_current_ratio_v2';path.write_text(json.dumps(profile))
    result=cycle.run_cycle(db_path=db,watchlist_path=path)
    assert result['skipped'][0]['reason']=='duplicate_observation'
    store=StateStore(db)
    try:assert store.full_state()[0]['retired_to']=='stadler_current_ratio_v2'
    finally:store.close()
