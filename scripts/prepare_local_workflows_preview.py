"""Prepare fictional 4C inputs through protected loopback HTTP; starts no jobs."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
from urllib.request import Request,build_opener,ProxyHandler
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.onboarding.store import InputStore
from keystone.workspace.onboarding.local_workflows.contracts import FORMATS
from keystone.workspace.job_files import write_new


def prepare(workspace,port):
    workspace=Path(workspace).resolve()
    if ROOT/'output' not in workspace.parents or not 1024<=port<=65535:raise ValueError('Use an isolated local demonstration')
    inputs=InputStore(workspace);origin=f'http://127.0.0.1:{port}'
    token=(workspace/'control/access-token.key').read_text().strip();opener=build_opener(ProxyHandler({}))
    def call(path,value=None,method=None,key=None):
        req=Request(origin+path,data=c.canonical(value) if value is not None else None,method=method or ('POST' if value is not None else 'GET'),
            headers={'Authorization':'Bearer '+token,'Origin':origin,'Content-Type':'application/json',**({'Idempotency-Key':key} if key else {})})
        with opener.open(req,timeout=70) as response:return json.load(response)
    if call('/api/workspace')['workspace_id']!=inputs.descriptor['id']:raise ValueError('Workspace/server mismatch')
    if (call('/api/entities?limit=1')['items'] or call('/api/datasets?limit=1')['items']
            or any((workspace.parent/(w+'-input.json')).exists() for w in FORMATS)):
        raise ValueError('Use a fresh empty fictional workspace; preserve existing evidence')
    results=[]
    for w,format_ in FORMATS.items():
        entity=call('/api/entities',dict(name='Northstar peer group · fictional' if w=='events' else 'Northstar Components · '+w+' · fictional',
            kind='group' if w=='events' else 'company',ticker=None if w=='events' else 'NSTAR',members=['NSTAR'] if w=='events' else []))
        dataset=call('/api/datasets',dict(entity_id=entity['id'],title='New local '+w+' · fictional',workflow=w,payload_format=format_))
        package=json.loads((ROOT/'fixtures/local_workflows'/(w+'.json')).read_text())
        package['dataset']['entity_id']=package['payload']['entity_id']=entity['id']
        evidence=b'Fictional engineering preview only; no real issuer, provider, dictionary or text rights claimed.'
        policy=dict(schema_version=1,id='permission-'+uuid.uuid4().hex,workspace_id=inputs.descriptor['id'],entity_id=entity['id'],payload_sha256=c.fingerprint(package['payload']),
            category='synthetic',provider_or_owner=package['sources'][0]['provider_or_owner'],intended_use='private_personal_evaluation',evidence_sha256=c.sha(evidence),reviewed_by='Fictional preview operator',
            reviewed_at=datetime.now(timezone.utc).isoformat(),expires_at=None,rights=dict(local_retention='allowed',local_processing='allowed',local_backup='allowed',model_transfer='denied',sharing='denied'))
        inputs.install_permission(policy,evidence)
        for s in package['sources']:s['permission_record_id']=policy['id']
        descriptor=call('/api/datasets/'+dataset['id']+'/inspect',package)['descriptor'];key='preview-'+uuid.uuid4().hex
        attempt=call('/api/imports',descriptor,key=key)['import_attempt']
        receipt=call('/api/imports/'+attempt['id']+'/package',package,method='PUT',key=key)
        write_new(workspace.parent/(w+'-input.json'),c.canonical(package))
        results.append(dict(workflow=w,dataset_id=dataset['id'],version_id=receipt['version_id'],url=origin+'/#/inputs/'+dataset['id']+'/versions/'+receipt['version_id']))
    return dict(workspace_id=inputs.descriptor['id'],inputs=results,processing_started=False,classification='synthetic')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.workspace,args.port),indent=2))
