"""Prepare fictional local-research inputs through the protected HTTP interface.

Operator-only demonstration helper; never fetches data or starts financial jobs.
The running server and supplied workspace must match. Credentials stay in memory.
"""
import argparse
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys
from urllib.request import Request,build_opener,ProxyHandler
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.onboarding.store import InputStore


def prepare(workspace,port):
    workspace=Path(workspace).resolve()
    if ROOT/'output' not in workspace.parents:raise ValueError('Demonstrations require an isolated output workspace')
    inputs=InputStore(workspace)
    token=(workspace/'control/access-token.key').read_text().strip()
    origin=f'http://127.0.0.1:{port}'
    opener=build_opener(ProxyHandler({}))
    def call(path,value=None,method=None,key=None):
        data=c.canonical(value) if value is not None else None
        req=Request(origin+path,data=data,method=method or ('POST' if data else 'GET'),
            headers={'Authorization':'Bearer '+token,'Origin':origin,'Content-Type':'application/json',**({'Idempotency-Key':key} if key else {})})
        with opener.open(req,timeout=70) as response:return json.load(response)
    if call('/api/workspace')['workspace_id']!=inputs.descriptor['id']:raise ValueError('Server/workspace mismatch')
    if (any((workspace.parent/name).exists() for name in ('complete-kit.json','missing-cash-kit.json'))
            or call('/api/entities?limit=1')['items'] or call('/api/datasets?limit=1')['items']):
        raise ValueError('Use a fresh empty demonstration workspace; preserve existing evidence')
    entity=call('/api/entities',dict(name='Northstar Components · fictional',kind='company',ticker='NSTAR',members=[]))
    dataset=call('/api/datasets',dict(entity_id=entity['id'],title='New annual company analysis · fictional',workflow='research',payload_format=c.FRESH_RESEARCH))
    result=[]
    for partial in (False,True):
        value=json.loads((ROOT/'docs/webapp/fresh-analysis/examples/complete-kit.json').read_text())
        value['dataset']['entity_id']=value['payload']['entity_id']=entity['id']
        quote_day=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat()
        value['payload']['quote']['as_of']=quote_day;value['sources'][1].update(period_start=quote_day,period_end=quote_day)
        if partial:value['payload']['periods'][-1]['observations']['cash_and_equivalents']=dict(value=None,source_id=None,locator=None,missing_reason='not_provided')
        evidence=b'Fictional engineering demonstration only. No real-company or provider permission claimed.'
        policy=dict(schema_version=1,id='permission-'+uuid.uuid4().hex,workspace_id=inputs.descriptor['id'],entity_id=entity['id'],payload_sha256=c.fingerprint(value['payload']),
            category='synthetic',provider_or_owner=value['sources'][0]['provider_or_owner'],intended_use='private_personal_evaluation',evidence_sha256=c.sha(evidence),reviewed_by='Fictional preview operator',
            reviewed_at=datetime.now(timezone.utc).isoformat(),expires_at=None,rights=dict(local_retention='allowed',local_processing='allowed',local_backup='allowed',model_transfer='denied',sharing='denied'))
        inputs.install_permission(policy,evidence)
        for source in value['sources']:source['permission_record_id']=policy['id']
        descriptor=call('/api/datasets/'+dataset['id']+'/inspect',value)['descriptor'];key='preview-'+uuid.uuid4().hex
        attempt=call('/api/imports',descriptor,key=key)['import_attempt']
        receipt=call('/api/imports/'+attempt['id']+'/package',value,method='PUT',key=key)
        target=workspace.parent/('missing-cash-kit.json' if partial else 'complete-kit.json')
        from keystone.workspace.job_files import write_new
        write_new(target,c.canonical(value))
        result.append(dict(case='missing_cash' if partial else 'complete',version_id=receipt['version_id'],url=origin+'/#/inputs/'+dataset['id']+'/versions/'+receipt['version_id']))
    return dict(workspace_id=inputs.descriptor['id'],inputs=result,processing_started=False,classification='synthetic')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.workspace,args.port),indent=2))
