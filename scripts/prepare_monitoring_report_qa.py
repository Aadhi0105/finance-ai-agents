"""Fresh, private synthetic monitoring browser cases; never a workspace API action."""
import argparse
import copy
from datetime import date, datetime, timezone
import hashlib
from html import escape
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from keystone.workspace.catalog import Catalog, ManifestV2
from keystone.workspace.report_views.publish import register_views
from keystone.workspace.report_views.values import canonical


def correction_cases(destination):
    """Exercise the real deterministic fixture engine and existing decision API."""
    from scheduler import cycle
    from monitoring.reporting import load_snapshot
    from monitoring.recovery import decide
    from state.store import StateStore, _json_date
    cov = dict(item_id='qa_ratio', entity='Synthetic QA entity', metric='current_ratio', covenant_type='qa',
        threshold=3, direction='below', cycle_values={'1':1,'2':4,'3':5,'4':2,'5':2},
        data_ts_by_cycle={'4':'2026-01-02'})
    original = cycle._load_watchlist
    cases = {}
    try:
        cycle._load_watchlist = lambda: ([cov], date(2026,1,1))
        with TemporaryDirectory(prefix='qa-engine-', dir=destination) as temp:
            db = str(Path(temp)/'monitor.db')
            def snapshot(n):
                return json.loads(json.dumps(load_snapshot(db, cycle=n, audit_dir=temp), default=_json_date))
            def token():
                store = StateStore(db)
                try: return store.reviews()[0]['review_id']
                finally: store.close()
            cycle.run_cycle(db_path=db); cases['monitor-baseline'] = snapshot(1)
            for _ in range(3): cycle.run_cycle(db_path=db)
            cases['monitor-pending'] = snapshot(3)
            decide(db, token(), 'approve', 'QA local analyst', 'Synthetic corrected source')
            cases['monitor-approved'] = snapshot(3)
            cov['threshold'] = 7
            cycle.run_cycle(db_path=db)
            decide(db, token(), 'approve', 'QA local analyst', 'Synthetic new definition', replacement_id='qa_ratio_v2')
            cases['monitor-replaced'] = snapshot(3)
    finally:
        cycle._load_watchlist = original
    return cases


def prepare(workspace, destination):
    from keystone.maintenance import gate
    workspace, destination = Path(workspace).absolute(), Path(destination).absolute()
    if destination.exists() or destination.is_symlink(): raise FileExistsError('Choose a fresh QA destination.')
    if workspace.resolve() in [destination.resolve(), *destination.resolve().parents]: raise ValueError('Destination must be outside the source workspace.')
    if any(p.is_symlink() for p in [destination,*destination.parents]): raise ValueError('Symlink destinations are not supported.')
    old_mask = os.umask(0o077)
    try:
        with gate(exclusive=True):
            catalog = Catalog(workspace); manifest = catalog.load(); raw = manifest.model_dump()
            raw.update(schema_version=2, prepared_at=datetime.now(timezone.utc).isoformat(),
                code_commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip(),
                code_worktree_dirty=bool(subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True,check=True).stdout),
                preparer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
            destination.mkdir(parents=True,exist_ok=False)
            source_hashes = {'catalog.json':hashlib.sha256((workspace/'catalog.json').read_bytes()).hexdigest()}
            seed = None
            for run, output in zip(manifest.runs, raw['runs']):
                reg = getattr(run,'native_view',None)
                skip = {reg.artifact_id,reg.source_artifact_ids[1]} if reg else set()
                output.pop('native_view',None); output['artifacts'] = [a.model_dump() for a in run.artifacts if a.id not in skip]
                for artifact in run.artifacts:
                    data = catalog.read(run.id,artifact)
                    source_hashes[f'runs/{run.id}/{artifact.name}'] = hashlib.sha256(data).hexdigest()
                    if artifact.id in skip: continue
                    path = destination/'runs'/run.id/artifact.name
                    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                    if run.workflow=='monitoring' and artifact.name=='snapshot.json':seed=(run,json.loads(data))
            if seed is None: raise ValueError('A registered synthetic monitoring snapshot is required.')
            run, source = seed
            cases = correction_cases(destination)
            for ident in ['monitor-quiet','monitor-no-new','monitor-missing','monitor-pages']:
                cases[ident] = copy.deepcopy(source)
            cases['monitor-quiet']['run']['surfaced'] = []
            cases['monitor-no-new']['run'].update(rows=[],surfaced=[],triage_history={})
            cases['monitor-missing']['run']['rows'][0].update(metric='unregistered_metric',breached=None)
            cases['monitor-missing']['run']['triage_history'] = {}
            cases['monitor-missing']['unreadable_audits'] = 1
            many = cases['monitor-pages']['run']
            seed_rows = copy.deepcopy(many['rows'])
            many['rows'] = [{**copy.deepcopy(seed_rows[i%4]),'item_id':'qa-item-'+str(i),'entity':'Synthetic entity '+str(i)} for i in range(32)]
            many['surfaced'] = []
            # Histories refer to original item IDs, so do not attach them to invented IDs.
            many['triage_history'] = {}
            for ident, source in cases.items():
                folder = destination/'runs'/ident; folder.mkdir(parents=True)
                html = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Synthetic QA</title><h1>'+escape(ident)+
                    '</h1><p>Controlled synthetic UI acceptance fixture. No verified company facts or authenticated approval.</p></html>').encode()
                snapshot = canonical(source)+b'\n'
                (folder/'report.html').write_bytes(html);(folder/'snapshot.json').write_bytes(snapshot)
                output = run.model_dump();output.pop('native_view',None)
                output.update(id=ident,title='Synthetic QA · '+ident,source_run_id=str(source['run']['cycle']),
                    prepared_at=datetime.now(timezone.utc).isoformat(),period='Synthetic selected cycle '+str(source['run']['cycle']),
                    summary='Controlled synthetic monitoring acceptance case.',metrics=[],checks=['Synthetic QA only'],report_id='file-0',
                    artifacts=[dict(id='file-'+str(i),name=name,label=label,kind=kind,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
                        for i,(name,label,kind,data) in enumerate([('report.html','QA fixture description','report',html),('snapshot.json','Controlled synthetic snapshot','evidence',snapshot)])])
                raw['runs'].append(output)
            register_views(destination,ManifestV2.model_validate(raw))
            for relative,expected in source_hashes.items():
                assert hashlib.sha256((workspace/relative).read_bytes()).hexdigest()==expected,'Source evidence changed'
            return dict(workspace=str(destination),source_files_unchanged=len(source_hashes),cases=list(cases),production_release_approved=False)
    finally:
        os.umask(old_mask)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.workspace,args.destination)))
