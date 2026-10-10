"""Same-device additive upgrade/rollback check against a prior release snapshot.

Generate the input with the prior release's check_keystone_storage runner first.
No schema migration is introduced by Batch 3. Never point this at production state.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import shutil

from keystone.operation import execute
from keystone.storage import restore, verify, digest
from monitoring.reporting import load_snapshot
from state.store import StateStore
from agent3.bundles import read_bundle, replay
from agent4.state import VarianceStore
from agent4.close import deliver_run


def run_acceptance(snapshot, output):
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=False)
    manifest=verify(snapshot)
    before_hash=digest(Path(snapshot)/'manifest.json')
    upgraded=restore(snapshot,output/'upgrade')
    results={}
    def run(agent,args,identity,expected):
        code,_,record=execute(agent,args,identity,directory=output/'operations')
        if code not in expected:raise AssertionError(f'{agent}: unexpected {code}')
        results[identity]=record['status']
    model=next((upgraded/'research').glob('*/model.json'))
    shutil.copytree(model.parent,output/'research-copy')
    run('agent1',['--rebuild',str(output/'research-copy/model.json')],'rebuild',{3})
    original=load_snapshot(upgraded/'state/monitor.duckdb',9,upgraded/'audits')
    run('agent2',['--db',str(upgraded/'state/monitor.duckdb'),'--once'],'new-cycle',{0,3})
    with closing(StateStore(str(upgraded/'state/monitor.duckdb'))) as store:
        assert store.con.execute('SELECT count(*) FROM cycle_runs').fetchone()[0]==11
    for bundle in (upgraded/'news').glob('*/bundle.json'):
        assert replay(read_bundle(bundle))['verification']=='matched'
    results['agent3-retained-replay']='matched'
    run('agent4-report',['--db',str(upgraded/'state/variance.duckdb'),'--run-id','close-12',
                         '--output-dir',str(output/'reports')],'close-report',{0})
    with VarianceStore(upgraded/'state/variance.duckdb') as store:
        saved=deliver_run(store,'close-12',output/'json')
        assert Path(saved['path']).read_bytes()==(upgraded/'close-year/recovered/close-12.json').read_bytes()
    # Rollback is restoration of the pre-upgrade snapshot into NEW state. Never
    # open already-mutated state with an older binary as an assumed downgrade.
    rolled=restore(snapshot,output/'rollback')
    recovered=load_snapshot(rolled/'state/monitor.duckdb',9,rolled/'audits')
    for key in ('run','current','reviews','decisions','cycles'):
        assert original[key]==recovered[key]
    assert len(original['attempts'])==len(recovered['attempts'])==1
    with closing(StateStore(str(rolled/'state/monitor.duckdb'))) as store:
        assert store.con.execute('SELECT count(*) FROM cycle_runs').fetchone()[0]==10
    assert digest(Path(snapshot)/'manifest.json')==before_hash
    verify(snapshot)
    result=dict(status='passed',scope='same-device prior-state additive upgrade and snapshot rollback',
                snapshot_id=manifest['snapshot_id'],source_commit=manifest['code_commit'],
                checks=results,rollback_cycles=10,upgraded_cycles=11,
                original_snapshot_unchanged=True,schema_migration_introduced=False,
                clean_machine_tested=False,production_release_approved=False)
    (output/'acceptance.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot');parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(json.dumps(run_acceptance(args.snapshot,args.output),indent=2))
