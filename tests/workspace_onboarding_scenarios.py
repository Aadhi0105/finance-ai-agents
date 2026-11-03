"""Test-only protected TCP rehearsal, using five registered synthetic sources."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from keystone.workspace.catalog import Catalog
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.onboarding.store import InputStore,create_workspace
from test_native_reports import hashes
from test_workspace_onboarding import prepare


class Reply:
    def __init__(self,status,data,headers):self.status_code,self.content,self.headers=status,data,headers
    def json(self):return json.loads(self.content)


class HTTP:
    def __init__(self,origin,token):self.origin,self.token=origin,token
    def call(self,path,method='GET',data=None,key=None,protected=True):
        headers={'Origin':self.origin,'Content-Type':'application/json'}
        if protected:headers['Authorization']='Bearer '+self.token
        if key:headers['Idempotency-Key']=key
        request=Request(self.origin+path,data=data,headers=headers,method=method)
        try:
            with urlopen(request,timeout=75) as response:return Reply(response.status,response.read(),response.headers)
        except HTTPError as error:return Reply(error.code,error.read(),error.headers)
    def post(self,path,*,json,headers):
        return self.call(path,'POST',c.canonical(json),headers.get('Idempotency-Key'))


def rehearse(source,destination,port):
    source=Path(source).absolute();root=Path(destination).absolute()
    if root.exists() or root.is_symlink() or source in root.parents or not 1024<=port<=65535:raise ValueError('Choose a fresh isolated destination and local port.')
    catalog=Catalog(source);manifest=catalog.load()
    if manifest.classification!='synthetic' or {r.workflow for r in manifest.runs}!=set(c.FORMATS):
        raise ValueError('Only registered synthetic native examples are supported.')
    before=hashes(source)
    root.mkdir(mode=0o700)
    workspace=create_workspace(root/'workspace','Fictional backend onboarding rehearsal')
    origin='http://127.0.0.1:'+str(port)
    fd=os.open(root/'server.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    stream=os.fdopen(fd,'w')
    process=subprocess.Popen([sys.executable,'-m','keystone.workspace','serve','--workspace',str(workspace),
        '--port',str(port),'--enable-imports','--enable-job-admission','--enable-worker'],cwd=ROOT,
        stdout=stream,stderr=stream,stdin=subprocess.DEVNULL)
    try:
        api=None
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Test server stopped; inspect the private rehearsal log.')
            token_path=workspace/'control/access-token.key'
            if token_path.is_file():
                candidate=HTTP(origin,token_path.read_text().strip())
                try:
                    response=candidate.call('/api/execution',protected=False)
                    if response.status_code==200 and response.json()['worker_enabled']:api=candidate;break
                except (URLError,ConnectionError):pass
            time.sleep(.1)
        if api is None:raise RuntimeError('Test server readiness deadline exceeded.')
        for path in ('/api/workspace','/api/entities','/api/datasets','/api/imports','/api/jobs','/api/runs'):
            assert api.call(path,protected=False).status_code==403
        session=SimpleNamespace(inputs=InputStore(workspace),token=api.token)
        cases=[]
        for workflow in c.FORMATS:
            value,data,descriptor,policy=prepare(session,source,workflow,api=api)
            key='tcp-import-'+workflow
            response=api.call('/api/imports','POST',c.canonical(descriptor),key)
            assert response.status_code==201
            attempt=response.json()['import_attempt']['id']
            response=api.call('/api/imports/'+attempt+'/package','PUT',data,key)
            assert response.status_code==200 and response.json()['state']=='accepted'
            version=session.inputs.version(response.json()['version_id'])
            request=dict(schema_version=2,workflow=workflow,timeout_seconds=60,source=dict(kind='dataset_version',
                dataset_id=version['dataset_id'],version_id=version['id'],contract_sha256=version['contract_sha256']))
            job_key='tcp-job-'+workflow
            response=api.call('/api/jobs','POST',c.canonical(request),job_key)
            assert response.status_code==202
            job=response.json()['job'];deadline=time.monotonic()+65
            while time.monotonic()<deadline:
                saved=api.call('/api/jobs/'+job['job_id']).json()['job']
                if saved['status'] not in {'queued','running'}:break
                time.sleep(.1)
            assert saved['status']=='review_required' and saved['execution']['attempt']==1
            replay=api.call('/api/jobs','POST',c.canonical(request),job_key)
            assert replay.status_code==200 and replay.json()['job']['job_id']==job['job_id']
            runid='result-'+job['job_id'][4:]
            assert api.call('/api/runs/'+runid+'/report-view',protected=False).status_code==403
            view=api.call('/api/runs/'+runid+'/report-view')
            assert view.status_code==200 and view.json()['state']['financial_approval'] is False
            run=api.call('/api/runs/'+runid).json()
            for artifact in run['artifacts']:
                delivered=api.call(artifact['url'])
                assert delivered.status_code==200 and c.sha(delivered.content)==artifact['sha256']
                assert delivered.headers['Content-Disposition'].startswith('attachment;')
            cases.append(dict(workflow=workflow,import_id=attempt,version_id=version['id'],job_id=job['job_id'],
                              run_id=runid,status=saved['status'],claimed_attempts=1,financial_approval=False))
        assert hashes(source)==before
        final=api.call('/api/workspace').json()
        assert len(final['runs'])==5
        for case in cases:
            operation=workspace/'control/operations'/('web-'+case['job_id'][4:])/'operation.json'
            receipt=json.loads(operation.read_text())
            assert receipt['model_control']['requests_reserved']==0 and receipt['live_data_enabled'] is False
        result=dict(schema_version=1,kind='keystone.private-onboarding-backend-rehearsal',
            source_files_preserved=len(before),registered_reports=5,accepted_inputs=5,
            private_unauthenticated_reads='refused',provider_requests=0,model_requests_reserved=0,
            financial_approval=False,browser_onboarding='pending_3C',cases=cases)
        for name,value in [('source-before.json',before),('receipt.json',result)]:
            fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as file:file.write(c.canonical(value)+b'\n')
        return result
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        stream.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8798)
    args=parser.parse_args()
    result=rehearse(args.source,args.destination,args.port)
    print(json.dumps({k:v for k,v in result.items() if k!='cases'}))
