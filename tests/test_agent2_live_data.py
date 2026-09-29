"""Live observation contracts, independent issuer reference, and state integration."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path

import pytest
from monitoring import live_data as live
from scheduler.cycle import run_cycle
from state.store import StateStore

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'watchlists/stadler-annual.json'


@pytest.fixture
def snapshot():
    reference = json.loads((ROOT / 'references/monitoring/SRAIL.SW-2025-12-31.json').read_text())
    return {'ticker':'SRAIL.SW','source':'yfinance','period':'2025-12-31','period_type':'annual',
            'currency':'CHF','monetary_unit':'base','values':deepcopy(reference['expected_fields'])}


@pytest.fixture
def item():
    return live.load_profile(PROFILE)['items'][0]


def test_issuer_ratios(snapshot):
    items = live.load_profile(PROFILE)['items']
    expected = [4236715/4428274,160571/(42097+281),(433906+505737-664190)/(160571+117880)]
    for i, value in zip(items, expected):
        result = live.observation(i, snapshot, date(2026,9,29))
        assert result['value'] == pytest.approx(value)
        assert result['data_ts']==date(2025,12,31)
        assert result['evidence']['issuer_reconciliation']['status']=='matched'


@pytest.mark.parametrize('patch,reason', [
    ({'ticker':'OTHER'},'provider_identity_mismatch'),
    ({'source':'fixture'},'provider_identity_mismatch'),
    ({'currency':'EUR'},'currency_or_unit_mismatch'),
    ({'monetary_unit':'millions'},'currency_or_unit_mismatch'),
    ({'period_type':'quarterly'},'annual_period_required'),
    ({'period':'2027-01-01'},'future_period'),
    ({'period':'2020-12-31'},'stale_reporting_period'),
    ({'period':'2026-06-30'},'issuer_reference_required'),
    ({'error':'provider_timeout'},'provider_timeout'),
])
def test_unusable_inputs_are_unavailable(item,snapshot,patch,reason):
    result=live.observation(item,{**snapshot,**patch},date(2026,9,29))
    assert result['value'] is None and result['reason']==reason


@pytest.mark.parametrize('bad',[None,True,float('nan'),float('inf'),0,-1])
def test_invalid_denominator_never_produces_safe_reading(item,snapshot,bad):
    snapshot['values']['current_liabilities']=bad
    assert live.observation(item,snapshot,date(2026,9,29))['value'] is None


def test_correction_reference_mismatch_not_silently_used(item,snapshot):
    snapshot['values']['current_assets']+=100000
    assert live.observation(item,snapshot,date(2026,9,29))['reason']=='issuer_reconciliation_mismatch'


def test_live_cycle_replay_duplicates_and_source_separation(tmp_path,monkeypatch,snapshot):
    calls=[]
    monkeypatch.setattr(live,'fetch',lambda ticker: calls.append(ticker) or deepcopy(snapshot))
    db=str(tmp_path/'live.db')
    first=run_cycle(db_path=db,watchlist_path=PROFILE)
    assert len(calls)==1 and first['data_mode']=='yfinance'
    assert len(first['rows'])==3 and first['rows'][0]['breached']
    assert first['surfaced']==[]  # Existing baseline policy, full state still shows breach.
    replay=run_cycle(db_path=db,asof_cycle=1,watchlist_path=PROFILE)
    assert replay['replayed'] and len(calls)==1
    second=run_cycle(db_path=db,watchlist_path=PROFILE)
    assert second['status']=='no_new_observations'
    assert {s['reason'] for s in second['skipped']}=={'duplicate_observation'}
    assert 'not contractual covenants' in first['report']
    with pytest.raises(ValueError,match='source mismatch'):run_cycle(db_path=db)
    store=StateStore(db)
    try:
        assert len(store.get_history_series('stadler_current_ratio_v1'))==1
        evidence=store.get_observation_evidence('stadler_current_ratio_v1','2025-12-31')
        assert evidence['_evidence']['issuer_reconciliation']['status']=='matched'
    finally:store.close()


def test_fixture_database_refuses_live_fetch(tmp_path,monkeypatch):
    db=str(tmp_path/'fixture.db');run_cycle(db_path=db)
    monkeypatch.setattr(live,'fetch',lambda _:pytest.fail('network call'))
    with pytest.raises(ValueError,match='separate database'):run_cycle(db_path=db,watchlist_path=PROFILE)


def test_provider_outage_keeps_state_and_records_failure(tmp_path,monkeypatch,snapshot):
    db=str(tmp_path/'live.db')
    monkeypatch.setattr(live,'fetch',lambda _:deepcopy(snapshot))
    run_cycle(db_path=db,watchlist_path=PROFILE)
    monkeypatch.setattr(live,'fetch',lambda _: {'error':'provider_timeout'})
    result=run_cycle(db_path=db,watchlist_path=PROFILE)
    assert result['status']=='review_required' and not result['rows']
    store=StateStore(db)
    try:
        assert len(store.full_state())==3
        assert store.get_run(2)['observation_attempts'][0]['observation']['reason']=='provider_timeout'
    finally:store.close()


def test_definition_change_same_value_is_held(tmp_path,monkeypatch,snapshot):
    db=str(tmp_path/'live.db')
    monkeypatch.setattr(live,'fetch',lambda _:deepcopy(snapshot))
    run_cycle(db_path=db,watchlist_path=PROFILE)
    profile=live.load_profile(PROFILE);profile['items'][0]['definition_version']='v2'
    path=tmp_path/'profile.json';path.write_text(json.dumps(profile))
    result=run_cycle(db_path=db,watchlist_path=path)
    assert result['skipped'][0]['reason']=='definition_change_requires_review'
    assert run_cycle(db_path=db,watchlist_path=path)['skipped'][0]['reason']=='pending_review'


def test_contractual_claim_rejected(tmp_path):
    profile=live.load_profile(PROFILE);profile['items'][0]['threshold_basis']='contractual'
    path=tmp_path/'profile.json';path.write_text(json.dumps(profile))
    with pytest.raises(ValueError,match='contractual'):live.load_profile(path)


def test_provider_never_substitutes_balance_sheet_period(monkeypatch):
    import pandas as pd
    import yfinance
    from types import SimpleNamespace
    current=pd.Timestamp('2025-12-31');previous=pd.Timestamp('2024-12-31')
    fake=SimpleNamespace(financials=pd.DataFrame({current:[10,2]},index=['Operating Income','Interest Expense']),
        balance_sheet=pd.DataFrame({previous:[100,20]},index=['Current Assets','Current Liabilities']),
        cashflow=pd.DataFrame({current:[3]},index=['Depreciation And Amortization']),
        info={'financialCurrency':'CHF'})
    monkeypatch.setattr(yfinance,'Ticker',lambda _:fake)
    result=live.provider_snapshot('SRAIL.SW')
    assert result['period']=='2025-12-31'
    assert result['values']['current_assets'] is None
    assert result['values']['operating_income']==10


@pytest.mark.parametrize('denominator',[0,-1])
def test_generic_unreviewed_ratio_rejects_bad_denominator(item,snapshot,denominator):
    item.update(ticker='OTHER',require_issuer_reconciliation=False)
    snapshot['ticker']='OTHER';snapshot['values']['current_liabilities']=denominator
    assert live.observation(item,snapshot,date(2026,9,29))['value'] is None


def test_live_triage_retains_source_label(tmp_path,monkeypatch,snapshot):
    from monitoring.triage import HistorySnapshot,run_triage_record
    monkeypatch.setattr(live,'fetch',lambda _:deepcopy(snapshot))
    db=str(tmp_path/'live.db');result=run_cycle(db_path=db,watchlist_path=PROFILE)
    row=result['rows'][0]
    store=StateStore(db)
    try: history=HistorySnapshot(store,[row],1)
    finally:store.close()
    triage=run_triage_record(history,[row],cycle=1,audit_dir=tmp_path/'audit')
    assert 'live yfinance' in triage['commentary'] and 'bundled fixtures' not in triage['commentary']
    assert json.loads(Path(triage['audit_path']).read_text())['data_mode']=='yfinance'


def test_profile_requires_explicit_review_choice(tmp_path):
    profile=live.load_profile(PROFILE)
    del profile['items'][0]['require_issuer_reconciliation']
    path=tmp_path/'profile.json';path.write_text(json.dumps(profile))
    with pytest.raises(ValueError,match='explicitly'):live.load_profile(path)


def test_failed_commit_does_not_bind_source(tmp_path,monkeypatch,snapshot):
    db=str(tmp_path/'live.db')
    monkeypatch.setattr(live,'fetch',lambda _:deepcopy(snapshot))
    monkeypatch.setattr(StateStore,'write_run',lambda *a: (_ for _ in ()).throw(RuntimeError('injected')))
    with pytest.raises(RuntimeError):run_cycle(db_path=db,watchlist_path=PROFILE)
    store=StateStore(db)
    try: assert store.source_mode() is None and store.full_state()==[]
    finally:store.close()


def test_cli_outage_returns_review_exit(tmp_path,monkeypatch):
    import runpy,sys
    db=str(tmp_path/'live.db')
    monkeypatch.setattr(live,'fetch',lambda _: {'error':'provider_timeout'})
    monkeypatch.setattr(sys,'argv',['monitor.py','--once','--data-source','yfinance',
                                  '--watchlist',str(PROFILE),'--db',db])
    with pytest.raises(SystemExit) as exc:runpy.run_path(str(ROOT/'monitor.py'),run_name='__main__')
    assert exc.value.code==3
    store=StateStore(db)
    try: assert store.get_run(1)['status']=='review_required'
    finally:store.close()
