"""Test-only real loopback server/worker rehearsal for fictional fresh closes."""
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
from keystone.workspace.onboarding import contracts as c,close_state
from keystone.workspace.onboarding.store import InputStore,create_workspace
from keystone.workspace.job_files import write_new
from test_native_reports import hashes
from test_workspace_fresh_close import package,request,correction
from workspace_onboarding_scenarios import HTTP


def rehearse(destination,port):
    root=Path(destination).absolute()
    if root.exists() or root.is_symlink() or not 1024<=port<=65535:
        raise ValueError('Choose a fresh ignored destination and local port.')
    before=hashes(ROOT/'fixtures/agent4')
    root.mkdir(mode=0o700)
    write_new(root/'source-before.json',c.canonical(before))
    workspace=create_workspace(root/'workspace','Fictional fresh-close backend rehearsal')
    origin='http://127.0.0.1:'+str(port)
    fd=os.open(root/'server.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    stream=os.fdopen(fd,'w')
    process=subprocess.Popen([sys.executable,'-m','keystone.workspace','serve','--workspace',str(workspace),
        '--port',str(port),'--enable-imports','--enable-job-admission','--enable-worker'],cwd=ROOT,
        stdout=stream,stderr=stream,stdin=subprocess.DEVNULL)
    try:
        api=None;deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Rehearsal server stopped; inspect its private log.')
            path=workspace/'control/access-token.key'
            if path.is_file():
                candidate=HTTP(origin,path.read_text().strip())
                try:
                    response=candidate.call('/api/execution',protected=False)
                    if response.status_code==200 and response.json()['worker_enabled']:
                        api=candidate;break
                except (URLError,ConnectionError):pass
            time.sleep(.1)
        if api is None:raise RuntimeError('Rehearsal readiness deadline exceeded.')
        session=SimpleNamespace(inputs=InputStore(workspace),token=api.token)
        cases=[];entity=dataset=None
        for index,source in enumerate((request(),correction())):
            entity,dataset,_,data,descriptor=package(session,source,entity=entity,dataset=dataset)
            key='tcp-close-input-'+str(index)
            response=api.call('/api/imports','POST',c.canonical(descriptor),key)
            assert response.status_code==201
            attempt=response.json()['import_attempt']['id']
            response=api.call('/api/imports/'+attempt+'/package','PUT',data,key)
            assert response.status_code==200,response.json()
            version=session.inputs.version(response.json()['version_id'])
            if index==0:assert not (workspace/'accounting').exists()
            job_request=dict(schema_version=2,workflow='close',timeout_seconds=60,source=dict(kind='dataset_version',
                dataset_id=dataset['id'],version_id=version['id'],contract_sha256=version['contract_sha256']))
            job_key='tcp-close-job-'+str(index)
            response=api.call('/api/jobs','POST',c.canonical(job_request),job_key)
            assert response.status_code==202,response.json()
            job=response.json()['job'];deadline=time.monotonic()+65
            while time.monotonic()<deadline:
                saved=api.call('/api/jobs/'+job['job_id']).json()['job']
                if saved['status'] not in {'queued','running'}:break
                time.sleep(.1)
            assert saved['status']=='review_required' and saved['execution']['attempt']==1,saved
            response=api.call('/api/jobs','POST',c.canonical(job_request),job_key)
            assert response.status_code==200 and response.json()['job']['job_id']==job['job_id']
            run_id='result-'+job['job_id'][4:]
            assert api.call('/api/runs/'+run_id+'/report-view',protected=False).status_code==403
            view=api.call('/api/runs/'+run_id+'/report-view')
            assert view.status_code==200 and view.json()['state']['financial_approval'] is False
            run=api.call('/api/runs/'+run_id).json()
            for artifact in run['artifacts']:
                delivered=api.call(artifact['url'])
                assert delivered.status_code==200 and c.sha(delivered.content)==artifact['sha256']
            receipt=json.loads((workspace/'control/operations'/job['operation_id']/'operation.json').read_text())
            assert receipt['model_control']['requests_reserved']==0 and receipt['live_data_enabled'] is False
            cases.append(dict(run_id=run_id,job_id=job['job_id'],version_id=version['id'],
                status=saved['status'],claimed_attempts=1,commit_sha256=saved['execution']['accounting_commit_sha256']))
        assert len(api.call('/api/workspace').json()['runs'])==2
        assert hashes(ROOT/'fixtures/agent4')==before
    finally:
        process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        stream.close()
    inputs=InputStore(workspace)
    with close_state.open_state(close_state.state_path(inputs,entity['id'])) as state:
        assert state.con.execute('SELECT count(*) FROM a4_runs').fetchone()[0]==2
        assert state.get_run('close-june')['bundle']['bound_tree']['actual_cents']==6500
        assert state.get_run('close-june-corrected')['bundle']['bound_tree']['actual_cents']==7500
    result=dict(schema_version=1,kind='keystone.fresh-close-backend-rehearsal',cases=cases,
        source_files_preserved=len(before),registered_reports=2,accounting_runs=2,
        provider_requests=0,model_requests_reserved=0,financial_approval=False,
        production_release_approved=False,
        browser_onboarding='pending_3C',independent_backup='pending')
    write_new(root/'receipt.json',c.canonical(result))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8801)
    args=parser.parse_args()
    print(json.dumps(rehearse(args.destination,args.port)))
