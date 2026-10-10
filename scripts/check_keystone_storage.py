"""Offline all-agent local snapshot/restore rehearsal, not device-loss acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def check(value,message):
    if not value:raise AssertionError(message)


def run_acceptance(output):
    from keystone.storage import snapshot,restore,verify,digest
    from scheduler.cycle import run_cycle
    from monitoring.recovery import retry_triage
    from monitoring.reporting import load_snapshot,export_report
    from agent3.catalyst_state import CatalystStore
    from agent3.bundles import read_bundle,replay
    from agent4.state import VarianceStore
    from agent4.close import deliver_run
    from agent4.report import export_reports
    from scripts.check_agent4_closure import run_acceptance as close_year
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    source=output/'source';source.mkdir();state=source/'state';state.mkdir()
    env=dict(os.environ,AGENT_DATA_SOURCE='fixture',AGENT_STATS_VIA_MCP='0',MPLBACKEND='Agg')
    def cli(args,expected):
        result=subprocess.run([sys.executable,*args],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
        check(result.returncode==expected,f'Unexpected command outcome: {args[0]} ({result.returncode})')
    cli(['run.py','--offline','ASML.AS','--output',str(source/'research')],3)
    monitor=state/'monitor.duckdb'
    for _ in range(10):run_cycle(db_path=str(monitor))
    retry_triage(str(monitor),9,audit_dir=source/'audits')
    monitoring=load_snapshot(monitor,9,source/'audits')
    cli(['-m','agent3.run_news','ASML.AS','--alias','ASML','--scorer','stub','--demo','--fixture','fixtures/news.json',
         '--as-of','2026-01-28T23:59:00Z','--db',str(state/'catalyst.duckdb'),'--output-dir',str(source/'news')],3)
    store=CatalystStore(state/'catalyst.duckdb')
    store.upsert_catalyst('fixture-event','ASML','earnings','2026-10-01')
    store.upsert_catalyst('fixture-event','ASML','earnings','2026-10-02',reason='synthetic correction')
    calendar=store.con.execute('SELECT * FROM catalyst_calendar').fetchall()
    revisions=store.con.execute('SELECT * FROM calendar_revisions').fetchall();store.close()
    old_transport=os.environ.get('AGENT_STATS_VIA_MCP');os.environ['AGENT_STATS_VIA_MCP']='0'
    try:close_year(source/'close-year')
    finally:
        if old_transport is None:os.environ.pop('AGENT_STATS_VIA_MCP',None)
        else:os.environ['AGENT_STATS_VIA_MCP']=old_transport
    (source/'close-year/state.duckdb').rename(state/'variance.duckdb')
    (source/'close-year/gap-state.duckdb').rename(state/'gap.duckdb')
    # Preserve exact source fixtures/references as configuration evidence.
    import shutil
    shutil.copytree(ROOT/'fixtures',source/'inputs')
    shutil.copytree(ROOT/'references',source/'references')
    entries=[]
    for filename,role in [('monitor.duckdb','agent2_state'),('catalyst.duckdb','agent3_state'),('variance.duckdb','agent4_state'),('gap.duckdb','agent4_state')]:
        entries.append(dict(name='state/'+filename,path=str(state/filename),kind='database',role=role))
    for name,role in [('research','agent1_evidence'),('audits','agent2_audits'),('news','agent3_evidence'),('close-year','agent4_evidence'),('inputs','inputs'),('references','configuration')]:
        entries.append(dict(name=name,path=str(source/name),kind='tree',role=role))
    plan=dict(schema_version=1,scope='four-agent synthetic local recovery rehearsal',sources=entries,
              datasets=[dict(id='fixtures',source='repository controlled fixtures and retained references',classification='synthetic',period='fixture-specific',currency='fixture-specific',units='fixture-specific',permission='synthetic_only',permission_evidence='local test only, no redistribution',freshness_policy='frozen fixture cutoff',source_names=[e['name'] for e in entries if e['name']!='references']),
                dict(id='references',source='retained issuer/provider reference metadata',classification='issuer',period='reference-specific',currency='reference-specific',units='reference-specific',permission='pending',permission_evidence='production rights not reviewed',freshness_policy='historical references only',source_names=['references'])])
    (output/'inventory.json').write_text(json.dumps(plan,indent=2))
    started=time.monotonic();snap=snapshot(plan,output/'snapshots',quiescent=True);capture_seconds=time.monotonic()-started
    m=verify(snap)
    source.rename(output/'original-unavailable')
    check(not source.exists(),'original source remains available')
    started=time.monotonic();dest=restore(snap,output/'restored');restore_seconds=time.monotonic()-started
    model=next((dest/'research').glob('*/model.json'));model_hash=digest(model)
    rebuild_dir=output/'rebuilt-research';shutil.copytree(model.parent,rebuild_dir)
    cli(['run.py','--rebuild',str(rebuild_dir/'model.json')],3)
    check(digest(model)==model_hash,'original Agent 1 evidence changed')
    after=load_snapshot(dest/'state/monitor.duckdb',9,dest/'audits')
    for key in ('run','current','reviews','decisions','cycles'):check(after[key]==monitoring[key],'Agent 2 restored state mismatch')
    check(len(after['attempts'])==len(monitoring['attempts'])==1,'Agent 2 audit missing')
    export_report(dest/'state/monitor.duckdb',output/'monitor.html',cycle=9,audit_dir=dest/'audits')
    store=CatalystStore(dest/'state/catalyst.duckdb')
    check(store.con.execute('SELECT * FROM catalyst_calendar').fetchall()==calendar,'calendar mismatch')
    check(store.con.execute('SELECT * FROM calendar_revisions').fetchall()==revisions,'revision mismatch')
    for b in store.bundles():check(replay(read_bundle(b['bundle_path']))['verification']=='matched','Agent 3 replay mismatch')
    store.close()
    with VarianceStore(dest/'state/variance.duckdb') as store:
        check(store.con.execute('SELECT count(*) FROM a4_runs').fetchone()[0]==14,'Agent 4 closes missing')
        delivered=deliver_run(store,'close-12',output/'recovered-close')
        check(Path(delivered['path']).read_bytes()==(dest/'close-year/recovered/close-12.json').read_bytes(),'Agent 4 bytes differ')
        html=export_reports(store,'close-12',output/'restored-reports')
    require_fields={'request','bound_tree','report','sources'}
    original_parity=json.loads((dest/'close-year/parity.json').read_text())
    for database,run_ids in [('variance.duckdb',[k for k in original_parity if k!='gap-close']),('gap.duckdb',['gap-close'])]:
        with VarianceStore(dest/'state'/database) as store:
            for run_id in run_ids:
                value=store.get_run(run_id)['bundle']
                check({k:value[k] for k in require_fields}==original_parity[run_id],'Agent 4 saved evidence mismatch')
    summary=dict(status='passed',scope='same-device local fixture rehearsal; existing runtime',snapshot=str(snap),
                 restored=str(dest),files=len(m['files']),capture_seconds=round(capture_seconds,3),restore_seconds=round(restore_seconds,3),
                 checks=['Agent 1 review-preserving rebuild','Agent 2 state/audit export','Agent 3 calendar/revisions/index/replay','Agent 4 14 closes plus gap, exact JSON and HTML recovery'],
                 independent_device_tested=False,source_permissions_approved=False,production_release_approved=False,html=html['html_path'])
    (output/'acceptance.json').write_text(json.dumps(summary,indent=2));return summary


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir');args=p.parse_args()
    if args.output_dir:out=Path(args.output_dir)
    else:
        base=ROOT/'output/production-storage';base.mkdir(parents=True,exist_ok=True)
        out=Path(tempfile.mkdtemp(prefix='acceptance-',dir=base))/'run'
    print(json.dumps(run_acceptance(out),indent=2))


if __name__=='__main__':main()
