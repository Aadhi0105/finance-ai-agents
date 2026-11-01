"""Fresh, private synthetic financial-close browser cases; never a workspace API action."""
import argparse
import copy
from datetime import datetime, timezone
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


def close_cases(destination):
    """Retain actual deterministic close outputs from disposable synthetic state."""
    from agent4.close import execute_close, _periods
    from agent4.state import VarianceStore
    fixture = json.loads((ROOT/'fixtures/agent4/close-june.json').read_text())
    fixture.update(data_kind='synthetic', run_id='qa-original')
    cases = {}
    with TemporaryDirectory(prefix='qa-close-',dir=destination) as temp:
        with VarianceStore(Path(temp)/'close.duckdb') as state:
            cases['close-original'] = execute_close(state,fixture)['bundle']
            corrected=copy.deepcopy(fixture)
            corrected.update(run_id='qa-corrected',supersedes='qa-original')
            corrected['actuals']=dict(version='qa-restated',source='synthetic-correction',rows=[dict(line='sales',period='2026-01-31',amount_cents=12000)])
            cases['close-corrected']=execute_close(state,corrected)['bundle']
            for kind in ['loss','zero','cost','held','uncertainty','yearend','many']:
                req=copy.deepcopy(fixture)
                req.update(entity='Synthetic '+kind,run_id='qa-'+kind)
                req['budget']['version']='qa-'+kind+'-budget'
                req['actuals']['version']='qa-'+kind+'-actuals'
                if kind=='loss':
                    for row in req['budget']['rows']:
                        if row['line']=='cost':row['amount_cents']=20000
                    for row in req['actuals']['rows']:
                        if row['line']=='cost':row['amount_cents']=25000
                if kind=='zero':
                    for row in req['actuals']['rows']:row['amount_cents']=10000 if row['line']=='sales' else 4000
                if kind in ['cost','held']:
                    req['tree']=dict(name='Standalone cost',node_id='cost',root_measure='cost',leaf=dict(type='fixed_cost'))
                    for panel in ['budget','actuals']:req[panel]['rows']=[r for r in req[panel]['rows'] if r['line']=='cost']
                    if kind=='held':
                        for row in req['budget']['rows']:row['amount_cents']=0
                if kind=='uncertainty':
                    for i,period in enumerate(_periods(2025,'monthly')):
                        for line,amount in [('sales',10000),('cost',4000)]:
                            req['budget']['rows'].append(dict(line=line,period=period,amount_cents=amount))
                            req['actuals']['rows'].append(dict(line=line,period=period,amount_cents=amount+(-1 if i%2 else 1)*(i+1)*50))
                if kind=='yearend':
                    req['close_period']='2026-12-31'
                    req['actuals']['rows']=[dict(line=line,period=period,amount_cents=amount) for period in _periods(2026,'monthly') for line,amount in [('sales',11000),('cost',4500)]]
                if kind=='many':
                    req['tree']['children']=[dict(name=f'Division {i+1:02d} — synthetic long account name for maintenance services',node_id='account-'+str(i),sign='add',leaf=dict(type='revenue')) for i in range(32)]
                    for panel in ['budget','actuals']:
                        req[panel]['rows']=[dict(line=n['node_id'],period=period,amount_cents=10000 if panel=='budget' else 10000+i*17) for i,n in enumerate(req['tree']['children']) for period in _periods(2026,'monthly') if panel=='budget' or period<='2026-06-30']
                cases['close-'+kind]=execute_close(state,req)['bundle']
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
                    if run.workflow=='close' and artifact.name==run.source_run_id+'.json':seed=(run,json.loads(data))
            if seed is None: raise ValueError('A registered saved synthetic close is required.')
            run, source = seed
            cases = close_cases(destination)
            for ident, source in cases.items():
                folder = destination/'runs'/ident; folder.mkdir(parents=True)
                html = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Synthetic QA</title><h1>'+escape(ident)+
                    '</h1><p>Controlled synthetic UI acceptance fixture. No verified company facts or authenticated approval.</p></html>').encode()
                snapshot = canonical(source)+b'\n'
                (folder/'report.html').write_bytes(html);(folder/(source['run_id']+'.json')).write_bytes(snapshot)
                output = run.model_dump();output.pop('native_view',None)
                output.update(id=ident,title='Synthetic QA · '+ident,source_run_id=source['run_id'],entity=source['request']['entity'],
                    prepared_at=datetime.now(timezone.utc).isoformat(),period='Synthetic close '+source['request']['close_period'],
                    summary='Controlled synthetic financial-close acceptance case.',metrics=[],checks=['Synthetic QA only'],report_id='file-0',
                    artifacts=[dict(id='file-'+str(i),name=name,label=label,kind=kind,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
                        for i,(name,label,kind,data) in enumerate([('report.html','QA fixture description','report',html),(source['run_id']+'.json','Controlled synthetic saved close','evidence',snapshot)])])
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
