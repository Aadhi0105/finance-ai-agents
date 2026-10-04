"""State integrity, close acceptance and failure/recovery boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import duckdb
import pytest

from agent4.close import execute_close, deliver_run, _periods
from agent4.state import VarianceStore, canonical, digest


def row(line='sales', period='2026-01-31', amount=10000):
    return dict(line=line, period=period, amount_cents=amount)


def request(run_id='close-june', close='2026-06-30'):
    periods = _periods(2026, 'monthly')
    return dict(run_id=run_id, entity='Example Ltd', close_period=close, frequency='monthly',
        budget=dict(version='budget-2026', approved=True, source='approved-budget.csv',
            rows=[row(line,p,amount) for p in periods for line,amount in [('sales',10000),('cost',4000)]]),
        actuals=dict(version='actual-june',source='closed-ledger.csv',
            rows=[row(line,p,amount) for p in periods if p<=close for line,amount in [('sales',11000),('cost',4500)]]),
        tree=dict(name='Profit',node_id='profit',root_measure='profit',children=[
            dict(name='Sales',node_id='sales',sign='add',leaf=dict(type='revenue')),
            dict(name='Cost',node_id='cost',sign='subtract',leaf=dict(type='fixed_cost'))]))


@pytest.fixture
def store(tmp_path):
    with VarianceStore(tmp_path/'state.duckdb') as s:
        yield s


@pytest.mark.parametrize('kind',['budget','actuals','reforecast'])
def test_versions_idempotent_immutable_unique(store, kind):
    def write(rows,version='v1'):
        if kind == 'reforecast':
            return store.record_reforecast('2026-01-31',rows,version)
        return getattr(store,'set_budget' if kind=='budget' else 'append_actuals')(version,rows)
    rows = [dict(line='sales',landing_cents=100,prob_hit=None,probability_reason='too little history')] if kind=='reforecast' else [row()]
    write(rows); write(deepcopy(rows))
    assert len(store.versions(kind))==1
    changed=deepcopy(rows);changed[0]['landing_cents' if kind=='reforecast' else 'amount_cents']=999
    with pytest.raises(ValueError,match='conflict'):write(changed)
    with pytest.raises(ValueError,match='duplicate'):write(rows+rows,'v2')
    assert len(store.versions(kind))==1
    if kind=='reforecast':
        trail=store.reforecast_walk('sales')
        assert trail[0]['version']=='v1' and trail[0]['prob_hit'] is None
        assert trail[0]['probability_status']=='unavailable'
        json.dumps(trail,allow_nan=False)


@pytest.mark.parametrize('prob',[float('nan'),float('inf'),True,-0.1,1.1,'0.5'])
def test_bad_probability_no_partial_write(store,prob):
    with pytest.raises(ValueError):
        store.record_reforecast('2026-01-31',[dict(line='A',landing_cents=100,prob_hit=.5),dict(line='B',landing_cents=100,prob_hit=prob)],'v')
    assert store.versions('reforecast')==[]


@pytest.mark.parametrize('rows', [[],[row(period='Q1')],[row(line=' ')],[row(amount=True)], [row(amount=2**63)], [dict(row(),extra=1)]])
def test_invalid_observations_atomic(store,rows):
    with pytest.raises((ValueError,TypeError)):store.append_actuals('bad',rows)
    assert store.versions('actuals')==[]


def test_effective_restated_snapshot_and_entity_isolation(store):
    store.append_actuals('a1',[row(),row('cost',amount=4000)],metadata={'entity':'A'})
    store.append_actuals('b1',[row(amount=999)],metadata={'entity':'B'})
    store.append_actuals('a2',[row(amount=12000)],metadata={'entity':'A'})
    assert store.get_actuals('a1')==[row('cost',amount=4000),row()]
    assert store.get_actuals('a2')==[row('cost',amount=4000),row(amount=12000)]
    assert [r['source_version'] for r in store.actuals_snapshot('a2')]==['a1','a2']
    assert store.actuals_delta('a2')==[row(amount=12000)]
    with pytest.raises(ValueError):store.versions('actuals; DROP TABLE a4_rows')
    with pytest.raises(ValueError):store.get_actuals('missing')


class FailingConnection:
    def __init__(self, connection, match, occurrence=1, error=RuntimeError):
        self.connection=connection;self.match=match;self.occurrence=occurrence;self.error=error
    def execute(self, sql, *args, **kwargs):
        if self.match in sql:
            self.occurrence-=1
            if self.occurrence==0:
                raise self.error('injected write failure')
        return self.connection.execute(sql,*args,**kwargs)
    def __getattr__(self,name):return getattr(self.connection,name)


@pytest.mark.parametrize('match,occurrence',[('INSERT INTO a4_versions',1),('INSERT INTO a4_rows',2),('COMMIT',1)])
def test_state_write_failure_rolls_back_header_and_rows(store,match,occurrence):
    original=store.con
    store.con=FailingConnection(original,match,occurrence)
    with pytest.raises(RuntimeError):store.set_budget('v',[row(),row('cost')])
    store.con=original
    assert store.versions('budget')==[]
    assert store.con.execute('SELECT count(*) FROM a4_rows').fetchone()[0]==0
    store.set_budget('v',[row(),row('cost')])
    assert store.version_info('budget','v')['rows']==2


def test_populated_legacy_db_preserved(tmp_path):
    path=tmp_path/'old.duckdb'
    con=duckdb.connect(str(path));con.execute('CREATE TABLE actuals(version VARCHAR)');con.execute("INSERT INTO actuals VALUES ('old')");con.close()
    with pytest.raises(ValueError,match='migration'):VarianceStore(path)
    con=duckdb.connect(str(path));assert con.execute('SELECT * FROM actuals').fetchall()==[('old',)];con.close()


def test_complete_close_replay_and_frozen_restatement(store,tmp_path):
    req=request()
    first=execute_close(store,req)
    assert first['status']=='committed'
    bundle=first['bundle'];report=bundle['report']
    assert report['reconciliation']['passed'] and report['source_reconciliation']=='matched'
    assert report['full_hierarchy']['actual_cents']==6500
    root_forecast=report['reforecasts']['profit']
    assert root_forecast['inputs']['ytd_cents']==39000
    assert root_forecast['inputs']['full_year_budget_cents']==72000
    assert root_forecast['inputs']['budget_phasing_cents']==[6000]*12
    assert store.reforecast_walk('profit')[0]['result']=={k:v for k,v in root_forecast.items() if k!='input_basis'}
    assert bundle['lineage']['completeness'].startswith('all leaf')
    assert execute_close(store,req)['status']=='replayed'
    assert len(store.versions('actuals'))==1
    changed=deepcopy(req);changed['entity']='Other'
    with pytest.raises(ValueError,match='run_id conflict'):execute_close(store,changed)
    revised=deepcopy(req);revised.update(run_id='corrected',supersedes=req['run_id'])
    revised['actuals']=dict(version='restated',source='restatement.csv',rows=[row(amount=12000)])
    execute_close(store,revised)
    assert len(store.get_actuals('restated'))==12
    assert store.get_run(req['run_id'])['bundle']==bundle
    delivered=deliver_run(store,req['run_id'],tmp_path/'reports')
    original_bytes=Path(delivered['path']).read_bytes()
    assert json.loads(original_bytes)==bundle
    assert deliver_run(store,req['run_id'],tmp_path/'reports')['status']=='delivered'
    assert Path(delivered['path']).read_bytes()==original_bytes
    assert len(store.reforecast_walk('profit'))==2


@pytest.mark.parametrize('mutation', ['unapproved','missing-budget','missing-actual','unknown-line','future','bad-close','bad-tree','bad-cents'])
def test_invalid_close_leaves_no_state(store,mutation):
    req=request()
    if mutation=='unapproved':req['budget']['approved']=False
    if mutation=='missing-budget':req['budget']['rows'].pop()
    if mutation=='missing-actual':req['actuals']['rows'].pop(0)
    if mutation=='unknown-line':req['actuals']['rows'][0]['line']='unknown'
    if mutation=='future':req['actuals']['rows'].append(row(period='2026-07-31'))
    if mutation=='bad-close':req['close_period']='2026-06-15'
    if mutation=='bad-tree':req['tree']['children'][0]['history']=[123]
    if mutation=='bad-cents':req['actuals']['rows'][0]['amount_cents']=True
    with pytest.raises(ValueError):execute_close(store,req)
    assert all(store.versions(k)==[] for k in ('budget','actuals','reforecast'))
    assert store.get_run(req['run_id']) is None


@pytest.mark.parametrize('match,occurrence,error',[
    ('INSERT INTO a4_versions',2,RuntimeError),('INSERT INTO a4_rows',25,RuntimeError),
    ('INSERT INTO a4_versions',3,RuntimeError),('INSERT INTO a4_runs',1,RuntimeError),
    ('COMMIT',1,RuntimeError),('INSERT INTO a4_runs',1,KeyboardInterrupt)])
def test_interrupted_close_has_no_partial_accounting(store,match,occurrence,error):
    original=store.con;store.con=FailingConnection(original,match,occurrence,error)
    with pytest.raises(error):execute_close(store,request())
    store.con=original
    assert all(store.versions(k)==[] for k in ('budget','actuals','reforecast'))
    assert store.get_run('close-june') is None
    assert execute_close(store,request())['status']=='committed'


def test_commentary_gate_failure_rolls_back_sources(store,monkeypatch):
    import agent4.close as close
    def fail(*args,**kwargs):raise ValueError('publication gate failed')
    monkeypatch.setattr(close,'board_pack',fail)
    with pytest.raises(ValueError,match='publication'):execute_close(store,request())
    assert store.versions('actuals')==[] and store.versions('budget')==[]


def test_delivery_failure_recovery_and_no_overwrite(store,tmp_path,monkeypatch):
    req=request();execute_close(store,req)
    import agent4.close as close
    original=close.os.replace
    def fail(*args):raise OSError('disk failure')
    monkeypatch.setattr(close.os,'replace',fail)
    with pytest.raises(OSError):deliver_run(store,req['run_id'],tmp_path/'out')
    assert store.delivery_history(req['run_id'])[-1]['status']=='failed'
    assert store.get_run(req['run_id']) is not None
    assert not list((tmp_path/'out').glob('*.json'))
    monkeypatch.setattr(close.os,'replace',original)
    result=deliver_run(store,req['run_id'],tmp_path/'out')
    Path(result['path']).write_text('conflicting file')
    with pytest.raises(ValueError,match='conflicts'):deliver_run(store,req['run_id'],tmp_path/'out')
    assert Path(result['path']).read_text()=='conflicting file'
    deliver_run(store,req['run_id'],tmp_path/'recovery')
    assert len(store.versions('reforecast'))==1


def test_stale_close_requires_explicit_correction(store):
    req=request();execute_close(store,req)
    duplicate=deepcopy(req);duplicate['run_id']='another'
    with pytest.raises(ValueError,match='already committed'):execute_close(store,duplicate)
    duplicate['close_period']='2026-05-31'
    with pytest.raises(ValueError,match='stale'):execute_close(store,duplicate)
    duplicate['close_period']='2026-06-30';duplicate['supersedes']='wrong'
    with pytest.raises(ValueError):execute_close(store,duplicate)
    duplicate.update(supersedes='close-june');execute_close(store,duplicate)
    newer=deepcopy(req);newer['run_id']='july';newer['close_period']='2026-07-31'
    newer['actuals']=dict(version='july',source='july.csv',rows=[row(period='2026-07-31'),row('cost',period='2026-07-31',amount=4000)])
    assert execute_close(store,newer)['status']=='committed'
    assert len(store.get_actuals('july'))==14


def test_held_forecast_preserved_in_walk(store):
    req=request()
    for r in req['budget']['rows']:
        if r['line']=='sales':r['amount_cents']=0
    result=execute_close(store,req)
    rf=result['bundle']['report']['reforecasts']['sales']
    assert rf['publication_status']=='held_invalid_inputs'
    saved=store.reforecast_walk('sales')[0]
    assert saved['status']=='held' and saved['landing_cents'] is None
    assert saved['prob_hit'] is None and saved['result']['error']


def test_saved_evidence_integrity(store,tmp_path):
    execute_close(store,request())
    store.con.execute("UPDATE a4_runs SET bundle='{}' WHERE run_id='close-june'")
    with pytest.raises(ValueError,match='integrity'):deliver_run(store,'close-june',tmp_path)


def test_cli_commit_replay_failure_and_recovery(tmp_path):
    input_path=tmp_path/'input.json';input_path.write_text(json.dumps(request()))
    db=tmp_path/'cli.duckdb';output=tmp_path/'out';output.write_text('not a directory')
    cmd=[sys.executable,'-m','agent4.close','--db',str(db),'--output-dir',str(output)]
    failed=subprocess.run(cmd+['--input',str(input_path)],capture_output=True,text=True)
    assert failed.returncode==3,failed.stderr
    assert json.loads(failed.stdout)['status']=='committed_delivery_failed'
    output.unlink()
    recovered=subprocess.run(cmd+['--recover','close-june'],capture_output=True,text=True)
    assert recovered.returncode==0,recovered.stderr
    assert json.loads(recovered.stdout)['close_status']=='recovered'
    replay=subprocess.run(cmd+['--input',str(input_path)],capture_output=True,text=True)
    assert replay.returncode==0 and json.loads(replay.stdout)['close_status']=='replayed'
    invalid=subprocess.run(cmd+['--recover','missing'],capture_output=True,text=True)
    assert invalid.returncode==2


def test_attempts_survive_rollback_and_record_replay(store):
    req=request();req['actuals']['rows'].pop()
    with pytest.raises(ValueError):execute_close(store,req)
    assert [r['status'] for r in store.attempt_history(req['run_id'])]==['started','failed']
    execute_close(store,request());execute_close(store,request())
    events=store.attempt_history(req['run_id'])
    assert [r['status'] for r in events]==['started','failed','started','committed','started','replayed']
    assert len({r['attempt_id'] for r in events})==3


def test_corrupted_source_version_rejected(store):
    store.set_budget('v',[row()])
    store.con.execute("UPDATE a4_rows SET amount_cents=10001 WHERE kind='budget'")
    with pytest.raises(ValueError,match='integrity'):store.get_budget('v')
    with pytest.raises(ValueError,match='integrity'):store.set_budget('v',[row()])


def test_probability_endpoints_strict_json_and_integrity(store):
    store.record_reforecast('2026-12-31',[dict(line='A',landing_cents=100,prob_hit=1),dict(line='B',landing_cents=0,prob_hit=0)],'closed')
    assert store.reforecast_walk('A')[0]['prob_hit']==1
    assert store.reforecast_walk('B')[0]['prob_hit']==0


@pytest.mark.parametrize('frequency',['quarterly','annual'])
def test_reporting_cadence_and_closed_year(store,frequency):
    req=request(close='2026-12-31');req['frequency']=frequency
    periods=_periods(2026,frequency)
    req['budget']['rows']=[r for r in req['budget']['rows'] if r['period'] in periods]
    req['actuals']['rows']=[r for r in req['actuals']['rows'] if r['period'] in periods]
    result=execute_close(store,req)
    assert result['bundle']['report']['reforecasts']['profit']['publication_status']=='deterministic'
    assert store.reforecast_walk('profit')[0]['prob_hit']==1


def test_new_close_cannot_discard_newer_restatement(store):
    req=request();execute_close(store,req)
    store.append_actuals('newer',[row(amount=13000)],metadata={'entity':req['entity'],'currency':'EUR','frequency':'monthly','source':'amendment'})
    revised=deepcopy(req);revised.update(run_id='correction',supersedes=req['run_id'])
    with pytest.raises(ValueError,match='stale actuals basis'):execute_close(store,revised)
    assert store.get_run('correction') is None


def test_concurrent_close_head_conflict_rolls_back_loser(tmp_path):
    # Two independent connections to the same database: both attempts see an empty
    # entity head before committing. The unique head serializes that race.
    from agent4.close import _freshness
    path=tmp_path/'concurrent.duckdb'
    with VarianceStore(path) as first, VarianceStore(path) as second:
        with pytest.raises(duckdb.TransactionException):
            with first.transaction():
                _freshness(first,request())
                with second.transaction():
                    _freshness(second,request(run_id='other'))
        assert second.con.execute('SELECT run_id FROM a4_heads').fetchone()[0]=='other'
        with first.transaction():
            assert first.con.execute('SELECT count(*) FROM a4_heads').fetchone()[0]==1


def test_reopen_and_regenerate_after_new_budget(tmp_path):
    path=tmp_path/'saved.duckdb'
    with VarianceStore(path) as store:
        original=execute_close(store,request())
        newer=request(run_id='rebudget');newer['supersedes']='close-june'
        newer['budget']['version']='budget-revised'
        for r in newer['budget']['rows']:r['amount_cents']+=100
        execute_close(store,newer)
    with VarianceStore(path) as store:
        restored=deliver_run(store,'close-june',tmp_path/'recovered')
        assert json.loads(Path(restored['path']).read_text())==original['bundle']
        assert store.get_budget('budget-2026')[0]['amount_cents']==4000
        assert store.get_budget('budget-revised')[0]['amount_cents']==4100


def test_delivery_receipt_failure_keeps_complete_artifact(store,tmp_path,monkeypatch):
    execute_close(store,request())
    original=store.delivery_event
    def fail(run_id,status,detail):
        if status=='delivered':raise RuntimeError('receipt unavailable')
        return original(run_id,status,detail)
    monkeypatch.setattr(store,'delivery_event',fail)
    with pytest.raises(RuntimeError):deliver_run(store,'close-june',tmp_path)
    saved=(tmp_path/'close-june.json').read_bytes()
    monkeypatch.setattr(store,'delivery_event',original)
    deliver_run(store,'close-june',tmp_path)
    assert (tmp_path/'close-june.json').read_bytes()==saved


def test_incomplete_prior_year_history_is_disclosed(store):
    req=request()
    req['actuals']['rows'].append(row(period='2025-12-31'))
    result=execute_close(store,req)
    assert result['bundle']['lineage']['excluded_incomplete_history_periods']==['2025-12-31']
    assert '2025-12-31' not in result['bundle']['lineage']['history_periods']
