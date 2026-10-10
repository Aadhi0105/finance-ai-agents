"""Local backup safety and restored evidence; no provider/model calls."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import duckdb
import pytest

from keystone.contracts import validate_plan, release_holds
from keystone.maintenance import gate
from keystone.storage import snapshot, restore, verify, digest, canonical
from monitoring.reporting import load_snapshot
from monitoring.recovery import retry_triage, decide
from state.store import StateStore
from scheduler.cycle import run_cycle
from test_agent2_recovery import held


def plan_for(entries):
    return dict(schema_version=1,scope='isolated synthetic acceptance',sources=entries,
        datasets=[dict(id='fixture',source='controlled fixtures',classification='synthetic',period='2026',
            currency='EUR',units='declared by fixture',permission='synthetic_only',permission_evidence='test fixture',
            freshness_policy='frozen acceptance',source_names=[e['name'] for e in entries])])


def entry(path,name='evidence',kind='tree',role='inputs'):
    return dict(path=str(Path(path).resolve()),name=name,kind=kind,role=role)


@pytest.fixture
def basic(tmp_path):
    source=tmp_path/'input';source.mkdir();(source/'a.json').write_text('{"value":12}')
    return plan_for([entry(source)])


def test_roundtrip_and_no_overwrite(basic,tmp_path):
    snap=snapshot(basic,tmp_path/'backups',quiescent=True);m=verify(snap)
    dest=restore(snap,tmp_path/'restored')
    assert (dest/'evidence/a.json').read_text()=='{"value":12}'
    assert json.loads((dest/'restore-receipt.json').read_text())['snapshot_id']==m['snapshot_id']
    with pytest.raises(ValueError,match='new destination'):restore(snap,dest)
    assert verify(snap)==m


@pytest.mark.parametrize('mutation',['corrupt','missing','extra','manifest','symlink'])
def test_corrupt_snapshot_never_publishes_restore(basic,tmp_path,mutation):
    snap=snapshot(basic,tmp_path/'backups',quiescent=True)
    p=snap/'data/evidence/a.json'
    if mutation=='corrupt':p.write_text('bad')
    if mutation=='missing':p.unlink()
    if mutation=='extra':(snap/'data/extra').write_text('extra')
    if mutation=='manifest':(snap/'manifest.json').write_text('{}')
    if mutation=='symlink':p.unlink();p.symlink_to(Path(basic['sources'][0]['path'])/'a.json')
    with pytest.raises((ValueError,OSError)):restore(snap,tmp_path/'restored')
    assert not (tmp_path/'restored').exists()


@pytest.mark.parametrize('name',['../bad','/absolute','a/../b','a//b','a\\b'])
def test_unsafe_inventory_path(basic,name):
    basic['sources'][0]['name']=name
    with pytest.raises(ValueError):validate_plan(basic)


@pytest.mark.parametrize('kind',['secret','symlink','hardlink','unlisted_database'])
def test_unsafe_source_refused(basic,tmp_path,kind):
    src=Path(basic['sources'][0]['path'])
    if kind=='secret':(src/'.env').write_text('SECRET=never copied')
    if kind=='symlink':(src/'link').symlink_to(src/'a.json')
    if kind=='hardlink':(src/'link').hardlink_to(src/'a.json')
    if kind=='unlisted_database':(src/'other.duckdb').write_bytes(b'fake')
    with pytest.raises(ValueError):snapshot(basic,tmp_path/'backups',quiescent=True)
    assert not list((tmp_path/'backups').glob('[!.]*'))


def test_gate_blocks_backup_and_cli(basic,tmp_path):
    with gate():
        with pytest.raises(RuntimeError,match='busy'):snapshot(basic,tmp_path/'backups',quiescent=True)
    with gate(exclusive=True):
        result=subprocess.run([sys.executable,'run.py','--offline','ASML.AS','--output',str(tmp_path/'report')],capture_output=True)
        assert result.returncode!=0 and not (tmp_path/'report').exists()


def test_quiescence_and_overlapping_destination_required(basic,tmp_path):
    with pytest.raises(ValueError,match='quiescent'):snapshot(basic,tmp_path/'backups')
    with pytest.raises(ValueError,match='overlaps'):snapshot(basic,Path(basic['sources'][0]['path'])/'backup',quiescent=True)


def test_failed_copy_preserves_last_snapshot(basic,tmp_path,monkeypatch):
    import keystone.storage as s
    old=snapshot(basic,tmp_path/'backups',quiescent=True)
    def fail(*a):raise OSError('simulated disk failure')
    monkeypatch.setattr(s,'copy_file',fail)
    with pytest.raises(OSError):snapshot(basic,tmp_path/'backups',quiescent=True)
    assert verify(old) and list((tmp_path/'backups').iterdir())==[old]


def test_mutation_during_copy_rejected(basic,tmp_path,monkeypatch):
    import keystone.storage as s
    original=s.copy_file
    def mutate(src,dst):
        original(src,dst);src.write_text('changed')
    monkeypatch.setattr(s,'copy_file',mutate)
    with pytest.raises(ValueError,match='changed'):snapshot(basic,tmp_path/'backups',quiescent=True)
    assert list((tmp_path/'backups').iterdir())==[]


def test_permissions_unknowns_and_forged_synthetic_contract(basic):
    d=basic['datasets'][0];d.update(classification='public_provider',permission='pending',period='unknown')
    validate_plan(basic)
    assert len(release_holds(basic))==2
    d['permission']='synthetic_only'
    with pytest.raises(ValueError):validate_plan(basic)


def test_agent2_restored_audits_and_corrections(held,tmp_path):
    db,_,_,token=held
    audit=tmp_path/'audits';retry_triage(db,3,audit_dir=audit)
    decide(db,token,'approve','Analyst','Verified fixture correction')
    before=load_snapshot(db,3,audit)
    assert len(before['attempts'])==1
    plan=plan_for([entry(db,'state/monitor.duckdb','database','agent2_state'),entry(audit,'audits','tree','agent2_audits')])
    snap=snapshot(plan,tmp_path/'backups',quiescent=True)
    dest=restore(snap,tmp_path/'restored')
    after=load_snapshot(dest/'state/monitor.duckdb',3,dest/'audits')
    for key in ('run','current','reviews','decisions','cycles'):assert before[key]==after[key]
    assert len(after['attempts'])==1
    # A foreign path with even the same cycle digest must remain excluded.
    other=dest/'audits/cycle-forged';other.mkdir()
    record=deepcopy(after['attempts'][0]);record['retry_context']['db_path']='/unrelated/database'
    (other/'model.json').write_text(json.dumps(record))
    assert len(load_snapshot(dest/'state/monitor.duckdb',3,dest/'audits')['attempts'])==1
    assert digest(snap/'data/state/monitor.duckdb')==verify(snap)['files']['state/monitor.duckdb']['sha256']


def test_agent4_saved_json_survives_restore(tmp_path):
    from agent4.close import execute_close,deliver_run
    from agent4.state import VarianceStore
    from agent4.report import export_reports
    req=json.loads(Path('fixtures/agent4/close-june.json').read_text())
    db=tmp_path/'variance.duckdb';out=tmp_path/'out'
    with VarianceStore(db) as store:
        execute_close(store,req);deliver_run(store,'close-june',out)
    original=(out/'close-june.json').read_bytes()
    snap=snapshot(plan_for([entry(db,'state/variance.duckdb','database','agent4_state'),entry(out,'reports','tree','agent4_evidence')]),tmp_path/'backups',quiescent=True)
    dest=restore(snap,tmp_path/'restored')
    with VarianceStore(dest/'state/variance.duckdb') as store:
        deliver_run(store,'close-june',dest/'new-report');export_reports(store,'close-june',dest/'html')
    assert (dest/'new-report/close-june.json').read_bytes()==original


def test_agent3_restored_calendar_index_and_replay(tmp_path):
    from agent3.catalyst_state import CatalystStore
    from agent3.bundles import replay,read_bundle
    db=tmp_path/'catalyst.duckdb';out=tmp_path/'news'
    result=subprocess.run([sys.executable,'-m','agent3.run_news','ASML.AS','--alias','ASML','--scorer','stub','--demo',
       '--fixture','fixtures/news.json','--as-of','2026-01-28T23:59:00Z','--db',str(db),'--output-dir',str(out)],capture_output=True,text=True)
    assert result.returncode==3,result.stderr
    store=CatalystStore(db)
    store.upsert_catalyst('c1','ASML','earnings','2026-10-01')
    store.upsert_catalyst('c1','ASML','earnings','2026-10-02',reason='fixture correction')
    calendar=store.con.execute('SELECT * FROM catalyst_calendar').fetchall()
    revisions=store.con.execute('SELECT * FROM calendar_revisions').fetchall();store.close()
    snap=snapshot(plan_for([entry(db,'state/catalyst.duckdb','database','agent3_state'),entry(out,'news','tree','agent3_evidence')]),tmp_path/'backups',quiescent=True)
    dest=restore(snap,tmp_path/'restored');store=CatalystStore(dest/'state/catalyst.duckdb')
    assert store.con.execute('SELECT * FROM catalyst_calendar').fetchall()==calendar
    assert store.con.execute('SELECT * FROM calendar_revisions').fetchall()==revisions
    bundles=store.bundles();store.close()
    assert len(bundles)==1
    assert Path(bundles[0]['bundle_path']).is_relative_to(dest)
    assert replay(read_bundle(bundles[0]['bundle_path']))['verification']=='matched'


def test_missing_indexed_bundle_refuses_restore(tmp_path):
    from agent3.catalyst_state import CatalystStore
    db=tmp_path/'c.duckdb';s=CatalystStore(db)
    s.con.execute("INSERT INTO run_bundles VALUES ('missing','hash','input','/missing/bundle.json','held',CURRENT_TIMESTAMP,'no_summary')")
    s.close()
    snap=snapshot(plan_for([entry(db,'state/c.duckdb','database','agent3_state')]),tmp_path/'backups',quiescent=True)
    with pytest.raises(ValueError,match='missing'):restore(snap,tmp_path/'restored')
    assert not (tmp_path/'restored').exists()


def test_restore_failure_leaves_original_snapshot_intact(basic,tmp_path,monkeypatch):
    import keystone.storage as s
    snap=snapshot(basic,tmp_path/'backups',quiescent=True);before=verify(snap)
    def fail(*a):raise OSError('simulated restore disk failure')
    monkeypatch.setattr(s,'copy_file',fail)
    with pytest.raises(OSError):restore(snap,tmp_path/'restored')
    assert not (tmp_path/'restored').exists() and verify(snap)==before


def test_empty_tree_and_reserved_names(basic,tmp_path):
    (Path(basic['sources'][0]['path'])/'a.json').unlink()
    snap=snapshot(basic,tmp_path/'backups',quiescent=True)
    assert (restore(snap,tmp_path/'restored')/'evidence').is_dir()
    basic['sources'][0]['name']='restore-receipt.json'
    with pytest.raises(ValueError,match='Reserved'):validate_plan(basic)


def test_external_duckdb_writer_blocks_capture(tmp_path):
    db=tmp_path/'active.duckdb'
    child=subprocess.Popen([sys.executable,'-u','-c',
        'import duckdb,sys; c=duckdb.connect(sys.argv[1]); c.execute("CREATE TABLE t(i INT)"); print("ready",flush=True); sys.stdin.readline()',str(db)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        assert child.stdout.readline().strip()=='ready'
        with pytest.raises(duckdb.Error):snapshot(plan_for([entry(db,'state/active.duckdb','database','agent4_state')]),tmp_path/'backups',quiescent=True)
        assert not list((tmp_path/'backups').glob('[!.]*'))
    finally:
        child.communicate('\n',timeout=10)


def test_cli_inventory_reports_pending_without_approval(tmp_path,basic):
    basic['datasets'][0].update(classification='public_provider',permission='pending')
    p=tmp_path/'plan.json';p.write_text(json.dumps(basic))
    result=subprocess.run([sys.executable,'-m','keystone','validate-plan',str(p)],capture_output=True,text=True)
    assert result.returncode==0
    value=json.loads(result.stdout)
    assert value['release_approved'] is False and value['permission_holds']


def test_multiple_restores_preserve_original_origin(held,tmp_path):
    db,_,_,_=held;a=tmp_path/'audits';retry_triage(db,3,audit_dir=a)
    p=plan_for([entry(db,'state/m.duckdb','database','agent2_state'),entry(a,'audits','tree','agent2_audits')])
    first=restore(snapshot(p,tmp_path/'b1',quiescent=True),tmp_path/'r1')
    p2=plan_for([entry(first/'state/m.duckdb','state/m.duckdb','database','agent2_state'),entry(first/'audits','audits','tree','agent2_audits')])
    second=restore(snapshot(p2,tmp_path/'b2',quiescent=True),tmp_path/'r2')
    assert len(load_snapshot(second/'state/m.duckdb',3,second/'audits')['attempts'])==1
