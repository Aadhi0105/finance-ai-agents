"""Import fictional 4D volume cases into a fresh loopback workspace; starts no jobs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.request import Request, build_opener, ProxyHandler
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.onboarding.store import InputStore
from keystone.workspace.job_files import write_new
from scripts.fresh_workflow_acceptance_cases import WORKFLOWS, package, entity


def prepare(workspace, port):
    workspace = Path(workspace).resolve()
    if ROOT/'output' not in workspace.parents or not 1024 <= port <= 65535:
        raise ValueError('Use an isolated local demonstration')
    inputs = InputStore(workspace); origin = f'http://127.0.0.1:{port}'
    token = (workspace/'control/access-token.key').read_text().strip()
    opener = build_opener(ProxyHandler({}))
    def call(path, value=None, method=None, key=None):
        req = Request(origin+path, data=c.canonical(value) if value is not None else None,
                      method=method or ('POST' if value is not None else 'GET'),
                      headers={'Authorization':'Bearer '+token, 'Origin':origin,
                               'Content-Type':'application/json', **({'Idempotency-Key':key} if key else {})})
        with opener.open(req, timeout=70) as response: return json.load(response)
    if call('/api/workspace')['workspace_id'] != inputs.descriptor['id']:
        raise ValueError('Workspace/server mismatch')
    destination = workspace.parent/'prepared-inputs.json'
    if (destination.exists() or call('/api/entities?limit=1')['items']
            or call('/api/datasets?limit=1')['items']):
        raise ValueError('Use a fresh empty workspace; preserve previous evidence')
    results = []
    for w in WORKFLOWS:
        e = call('/api/entities', entity(w)); value = package(w)
        d = call('/api/datasets',dict(entity_id=e['id'], title='4D maximum-volume '+w+' · fictional',
                                     workflow=w, payload_format=value['payload_format']))
        value['dataset']['entity_id'] = value['payload']['entity_id'] = e['id']
        evidence = b'Fictional 4D engineering preview only; no real-company or provider rights claimed.'
        policy = dict(schema_version=1, id='permission-'+uuid.uuid4().hex,
                      workspace_id=inputs.descriptor['id'], entity_id=e['id'],
                      payload_sha256=c.fingerprint(value['payload']), category='synthetic',
                      provider_or_owner=value['sources'][0]['provider_or_owner'],
                      intended_use='private_personal_evaluation', evidence_sha256=c.sha(evidence),
                      reviewed_by='Fictional 4D preview operator', reviewed_at=datetime.now(timezone.utc).isoformat(), expires_at=None,
                      rights=dict(local_retention='allowed', local_processing='allowed', local_backup='allowed',
                                  model_transfer='denied', sharing='denied'))
        inputs.install_permission(policy,evidence)
        for source in value['sources']: source['permission_record_id'] = policy['id']
        inspection = call('/api/datasets/'+d['id']+'/inspect',value)
        key = '4d-preview-'+uuid.uuid4().hex
        attempt = call('/api/imports',inspection['descriptor'],key=key)['import_attempt']
        receipt = call('/api/imports/'+attempt['id']+'/package',value,method='PUT',key=key)
        raw = c.canonical(value); write_new(workspace.parent/(w+'-input.json'),raw)
        results.append(dict(workflow=w,dataset_id=d['id'],version_id=receipt['version_id'],
                            package_bytes=len(raw),package_sha256=c.sha(raw),payload_sha256=c.fingerprint(value['payload']),
                            url=origin+'/#/inputs/'+d['id']+'/versions/'+receipt['version_id']))
    result = dict(workspace_id=inputs.descriptor['id'],classification='synthetic',processing_started=False,inputs=results)
    write_new(destination,c.canonical(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True); parser.add_argument('--port',type=int,required=True)
    args = parser.parse_args(); print(json.dumps(prepare(args.workspace,args.port),indent=2))
