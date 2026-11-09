"""Read-only protected HTTP/evidence verification of the fictional 4D preview."""
import argparse
import json
from pathlib import Path
import sys
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from keystone.workspace.catalog import Catalog
from keystone.workspace.onboarding import contracts as c


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('The local evidence check does not follow redirects')


def verify(workspace,port):
    workspace = Path(workspace).resolve()
    if ROOT/'output' not in workspace.parents or not 1024 <= port <= 65535:
        raise ValueError('Use an isolated local demonstration')
    catalog = Catalog(workspace/'reports'); manifest = catalog.load()
    if {r.workflow for r in manifest.runs} != {'research','monitoring','events','news'} or len(manifest.runs) != 4:
        raise ValueError('Expected four completed fictional workflow results')
    origin = f'http://127.0.0.1:{port}'
    token = (workspace/'control/access-token.key').read_text().strip()
    opener = build_opener(ProxyHandler({}),NoRedirect())
    def read(path):
        if not path.startswith('/api/') or path.startswith('//'):
            raise ValueError('Only local protected API paths are accepted')
        with opener.open(Request(origin+path,headers={'Authorization':'Bearer '+token,'Origin':origin}),timeout=30) as response:
            if response.headers.get('Cache-Control') != 'no-store': raise ValueError('Private cache boundary changed')
            return response.read()
    if json.loads(read('/api/workspace'))['workspace_id'] != manifest.workspace_id:
        raise ValueError('Workspace/server mismatch')
    jobs = json.loads(read('/api/jobs'))['jobs']
    if (len(jobs) != 4 or {job['job_id'] for job in jobs} != {run.input_origin.job_id for run in manifest.runs}
            or any(job['status'] != 'review_required' for job in jobs)):
        raise ValueError('Expected exactly the four original completed demonstration jobs')
    results = []
    for run in manifest.runs:
        if run.input_origin.classification != 'synthetic':
            raise ValueError('Use only the fictional demonstration results')
        public = json.loads(read('/api/runs/'+run.id))
        job = json.loads(read('/api/jobs/'+run.input_origin.job_id))['job']
        view = json.loads(read('/api/runs/'+run.id+'/report-view'))
        if job['status'] != 'review_required' or job['execution']['attempt'] != 1 or view['state']['financial_approval'] is not False:
            raise ValueError('Result outcome changed')
        artifacts = {}
        for artifact in run.artifacts:
            listed = next(a for a in public['artifacts'] if a['id'] == artifact.id)
            path = '/api/runs/'+run.id+'/files/'+artifact.name
            if listed['url'] != path: raise ValueError('Unexpected artifact URL')
            data = read(path)
            if len(data) != artifact.bytes or c.sha(data) != artifact.sha256 or data != catalog.read(run.id,artifact):
                raise ValueError('Protected download differs from saved evidence')
            artifacts[artifact.name] = dict(bytes=len(data),sha256=c.sha(data))
        results.append(dict(workflow=run.workflow,run_id=run.id,job_id=run.input_origin.job_id,
                            attempt=1,financial_approval=False,artifacts=artifacts))
    return dict(schema_version=1,workspace_id=manifest.workspace_id,
                protected_downloads_verified=sum(len(r['artifacts']) for r in results),runs=results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True); parser.add_argument('--port',type=int,required=True)
    args = parser.parse_args(); print(json.dumps(verify(args.workspace,args.port),indent=2))
