"""TEST ONLY: seven offline inputs through HTTP, worker, download and relocation.

All source policies are fictional attestations. No fault controls are exposed in
the production API. A new isolated output directory is required on every run.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.error import URLError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from keystone import storage
from keystone.workspace.catalog import Catalog
from keystone.workspace.job_store import JobStore
from keystone.workspace.job_files import write_new
from keystone.workspace.onboarding import contracts as c,close_state
from keystone.workspace.onboarding.store import InputStore,create_workspace
from keystone.workspace.onboarding.recovery import restore_private,release_restored_job
from test_native_reports import hashes
from test_workspace_onboarding import prepare
from test_workspace_fresh_close import package,request,correction
from workspace_onboarding_scenarios import HTTP


class Server:
    def __init__(self,workspace,port,log,worker=True):
        self.root=Path(workspace);self.origin=f'http://127.0.0.1:{port}'
        self.log=open(log,'x');os.chmod(log,0o600)
        flags=['--enable-imports','--enable-job-admission']+(['--enable-worker'] if worker else [])
        self.process=subprocess.Popen([sys.executable,'-m','keystone.workspace','serve','--workspace',str(workspace),
            '--port',str(port),*flags],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=self.log,stderr=self.log)
        try:
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                if self.process.poll() is not None:raise RuntimeError('Acceptance server stopped; inspect its local log')
                path=self.root/'control/access-token.key'
                if path.is_file():
                    api=HTTP(self.origin,path.read_text().strip())
                    try:
                        value=api.call('/api/execution',protected=False)
                        if value.status_code==200 and value.json()['worker_enabled']==worker:
                            self.api=api;break
                    except (URLError,ConnectionError):pass
                time.sleep(.1)
            else:raise RuntimeError('Acceptance readiness deadline exceeded')
        except BaseException:self.close();raise
    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
        self.log.close()


def wait_job(api,ident):
    deadline=time.monotonic()+65
    while time.monotonic()<deadline:
        r=api.call('/api/jobs/'+ident);assert r.status_code==200
        job=r.json()['job']
        if job['status'] not in {'queued','running'}:return job
        time.sleep(.1)
    raise RuntimeError('Acceptance job deadline exceeded')


def submit(api,version,key):
    body=dict(schema_version=2,workflow=version['contract']['metadata']['workflow'],timeout_seconds=60,
        source=dict(kind='dataset_version',dataset_id=version['dataset_id'],version_id=version['id'],
                    contract_sha256=version['contract_sha256']))
    response=api.call('/api/jobs','POST',c.canonical(body),key)
    assert response.status_code==202,response.json()
    ident=response.json()['job']['job_id']
    replay=api.call('/api/jobs','POST',c.canonical(body),key)
    assert replay.status_code==200 and replay.json()['job']['job_id']==ident
    return ident


def check_report(api,ident,version):
    job=api.call('/api/jobs/'+ident).json()['job']
    assert job['status']=='review_required' and job['execution']['attempt']==1
    run_id='result-'+ident[4:]
    for path in ('/api/runs/'+run_id,'/api/runs/'+run_id+'/report-view'):
        assert api.call(path,protected=False).status_code==403
        assert api.call(path,'HEAD',protected=False).status_code==403
    view=api.call('/api/runs/'+run_id+'/report-view');assert view.status_code==200
    assert view.json()['state']['financial_approval'] is False
    assert view.json()['state']['data_classification']=='synthetic'
    run=api.call('/api/runs/'+run_id).json()
    assert run['input_origin']['version_id']==version['id']
    files={}
    for artifact in run['artifacts']:
        downloaded=api.call(artifact['url'])
        assert downloaded.status_code==200 and c.sha(downloaded.content)==artifact['sha256']
        assert downloaded.headers['Content-Disposition'].startswith('attachment;')
        assert api.call(artifact['url'],protected=False).status_code==403
        files[artifact['name']]=artifact['sha256']
    base=f"/api/datasets/{version['dataset_id']}/versions/{version['id']}/files/"
    for name,proof in version['files'].items():
        response=api.call(base+name)
        assert response.status_code==200 and c.sha(response.content)==proof['sha256']
        assert api.call(base+name,protected=False).status_code==403
    return dict(job_id=ident,run_id=run_id,version_id=version['id'],workflow=run['workflow'],
                files=files,status=job['status'],claimed_attempts=1,financial_approval=False)


def rehearse(source,destination,port=8852):
    source=Path(source).absolute();root=Path(destination).absolute()
    if (root.exists() or root.is_symlink() or ROOT/'output' not in root.parents
            or any(p.is_symlink() for p in root.parents) or source in root.parents):
        raise ValueError('Choose a fresh isolated output destination')
    manifest=Catalog(source).load()
    if manifest.classification!='synthetic' or {r.workflow for r in manifest.runs}!=set(c.FORMATS):
        raise ValueError('Use registered synthetic source families only')
    before=hashes(source);root.mkdir(mode=0o700)
    write_new(root/'acceptance.json',c.canonical(dict(kind='keystone.test-only-private-acceptance-3d',classification='synthetic')))
    (root/'packages').mkdir(mode=0o700)
    workspace=create_workspace(root/'workspace','Fictional 3D acceptance workspace')
    server=Server(workspace,port,root/'original-server.log')
    versions=[];cases=[];metadata_timings=[]
    try:
        api=server.api;session=SimpleNamespace(inputs=InputStore(workspace),token=api.token)
        for route in ('/api/workspace','/api/entities','/api/datasets','/api/imports','/api/jobs','/api/runs'):
            assert api.call(route,protected=False).status_code==403
        entity=dataset=None
        for label in [*c.FORMATS,'fresh-close','close-correction']:
            started=time.monotonic()
            if label in c.FORMATS:
                value,data,descriptor,_=prepare(session,source,label,api=api)
            else:
                entity,dataset,_,data,descriptor=package(session,request() if label=='fresh-close' else correction(),entity=entity,dataset=dataset)
                value=c.bounded_json(data)
            write_new(root/'packages'/(label+'.json'),data)
            inspection=api.call('/api/datasets/'+descriptor['dataset_id']+'/inspect','POST',data)
            assert inspection.status_code==200 and inspection.json()['descriptor']==descriptor
            old_jobs=api.call('/api/jobs').json()['jobs']
            key='acceptance-input-'+label
            reserved=api.call('/api/imports','POST',c.canonical(descriptor),key)
            assert reserved.status_code==201
            attempt=reserved.json()['import_attempt']['id']
            accepted=api.call('/api/imports/'+attempt+'/package','PUT',data,key)
            assert accepted.status_code==200 and accepted.json()['state']=='accepted'
            repeated=api.call('/api/imports','POST',c.canonical(descriptor),key)
            assert repeated.status_code==200 and repeated.json()['import_attempt']['id']==attempt
            assert api.call('/api/imports/'+attempt+'/package','PUT',data,key).json()==accepted.json()
            assert len(api.call('/api/jobs').json()['jobs'])==len(old_jobs)
            version=session.inputs.version(accepted.json()['version_id']);versions.append(version)
            if label=='fresh-close':assert not (workspace/'accounting').exists()
            job=submit(api,version,'acceptance-job-'+label)
            assert wait_job(api,job)['status']=='review_required'
            case=check_report(api,job,version);case.update(label=label,import_id=attempt,elapsed_seconds=round(time.monotonic()-started,3))
            cases.append(case)
        # More than two UI pages of real private identity/dataset records. These
        # deliberately empty datasets do not imply any accepted input or report.
        for index in range(54):
            r=api.call('/api/entities','POST',c.canonical(dict(name=f'Fictional volume entity {index:02d}')))
            assert r.status_code==200,r.json()
            d=api.call('/api/datasets','POST',c.canonical(dict(entity_id=r.json()['id'],title=f'Volume dataset {index:02d}',
                workflow='monitoring',payload_format=c.FORMATS['monitoring'])))
            assert d.status_code==200,d.json()
        pages=[];cursor=None
        while True:
            started=time.monotonic()
            page=api.call('/api/datasets?limit=25'+('&before='+cursor if cursor else '')).json()
            metadata_timings.append(time.monotonic()-started);pages.append([v['id'] for v in page['items']])
            cursor=page['next_cursor']
            if cursor is None:break
        assert len(pages)==3 and len({x for page in pages for x in page})==60
        old_token=api.token
    finally:server.close()
    # Queue work with the worker explicitly off, then model an interrupted
    # claimed attempt. Fault preparation is local test code, outside the API.
    server=Server(workspace,port,root/'queued-server.log',worker=False)
    try:
        unknown=submit(server.api,versions[0],'restored-interrupted-research')
        held=submit(server.api,versions[0],'restored-held-research')
        released=submit(server.api,versions[1],'restored-reviewed-monitoring')
    finally:server.close()
    store=JobStore(workspace/'control',workspace/'reports',worker=True)
    try:assert store.claim_next().job_id==unknown
    finally:store.close()
    inputs=InputStore(workspace);plan=inputs.backup_plan()
    lease=JobStore(workspace/'control',workspace/'reports')
    try:snapshot=storage.snapshot(plan,root/'snapshots',quiescent=True,verify_source=lambda: inputs.backup_plan()==plan or (_ for _ in ()).throw(ValueError('changed')))
    finally:lease.close()
    saved_inputs=hashes(workspace/'inputs');saved_reports=hashes(workspace/'reports')
    # Make the old absolute source unavailable without deleting any evidence.
    workspace.rename(root/'original-preserved')
    restored=restore_private(snapshot,root/'restored-workspace')
    assert hashes(restored/'inputs')==saved_inputs and hashes(restored/'reports')==saved_reports
    assert not (restored/'control/access-token.key').exists()
    server=Server(restored,port,root/'restored-server.log')
    try:
        api=server.api
        assert api.token!=old_token
        stale=HTTP(api.origin,old_token)
        assert stale.call('/api/workspace').status_code==403
        for before_case,version in zip(cases,versions):
            after=check_report(api,before_case['job_id'],version)
            assert after['files']==before_case['files']
        for ident in (held,released):
            job=api.call('/api/jobs/'+ident).json()['job']
            assert job['restoration_hold'] and job['status']=='queued' and job['execution']['attempt']==0
        assert api.call('/api/jobs/'+unknown).json()['job']['status']=='outcome_unknown'
    finally:server.close()
    store=JobStore(restored/'control',restored/'reports',worker=True)
    try:assert release_restored_job(store,released,'Reviewed the restored synthetic monitoring input')['processing_started'] is False
    finally:store.close()
    server=Server(restored,port,root/'released-server.log')
    try:
        assert wait_job(server.api,released)['execution']['attempt']==1
        assert server.api.call('/api/jobs/'+held).json()['job']['execution']['attempt']==0
        assert server.api.call('/api/jobs/'+unknown).json()['job']['execution']['attempt']==1
    finally:server.close()
    restored_inputs=InputStore(restored)
    with close_state.open_state(close_state.state_path(restored_inputs,entity['id'])) as state:
        assert state.con.execute('SELECT count(*) FROM a4_runs').fetchone()[0]==2
        for ident,actual,variance in [('close-june',6500,500),('close-june-corrected',7500,1500)]:
            bundle=state.get_run(ident)['bundle']
            assert bundle['bound_tree']['budget_cents']==6000 and bundle['bound_tree']['actual_cents']==actual
            assert bundle['report']['full_hierarchy']['total_variance_cents']==variance
    assert hashes(source)==before
    operations=list((restored/'control/operations').glob('*/operation.json'))
    assert len(operations)==8
    for p in operations:
        r=json.loads(p.read_text())
        assert r['model_control']['requests_reserved']==0 and r['live_data_enabled'] is False
    result=dict(schema_version=1,kind='keystone.private-onboarding-acceptance-3d',cases=cases,
        restored_workspace=str(restored),snapshot_id=storage.verify(snapshot)['snapshot_id'],source_files_preserved=len(before),
        accepted_versions=7,registered_reports=8,accounting_runs=2,dataset_pages=[len(p) for p in pages],
        metadata_max_seconds=round(max(metadata_timings),3),queued_held_job=held,interrupted_job=unknown,released_job=released,
        queued_attempts_after_restore=0,released_attempts=1,provider_requests=0,model_requests_reserved=0,
        source_hashes=c.fingerprint(before),financial_approval=False,production_release_approved=False,
        independent_backup='deferred',clean_machine_recovery='not_tested',human_interpretation='pending')
    write_new(root/'receipt.json',c.canonical(result));write_new(root/'source-before.json',c.canonical(before))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8852)
    args=parser.parse_args();result=rehearse(args.source,args.destination,args.port)
    print(json.dumps({k:v for k,v in result.items() if k!='cases'}))
