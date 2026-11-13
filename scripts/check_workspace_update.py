"""Rehearse a local candidate and previous code against separate snapshot copies.

Trusted local source/runtime paths are explicit operator inputs. No installation
is activated, authoritative workspace selected, or queued request released.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import Request,ProxyHandler,HTTPRedirectHandler,build_opener

from keystone.installation import canonical,source_identity,sha
from keystone import storage
from keystone.workspace.onboarding.recovery import restore_private
from scripts.setup_keystone import environment,save,new_destination
ROOT=Path(__file__).resolve().parents[1]

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*_args,**_kwargs):return None


def source(value):
    root=Path(value).absolute();identity=source_identity(root)
    if identity['sha256'] is None:raise ValueError('Source identity unavailable')
    return root,identity


def run_check(python,root,args,log):
    with log.open('ab') as stream:
        os.chmod(stream.name,0o600)
        result=subprocess.run([str(python),*args],cwd=root,env=environment(),stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    if result.returncode:raise ValueError('Retained candidate check failed')


def initialise(python,root,workspace,log):
    # Normal startup on the NEW copy only. Worker/import/job admission all remain
    # disabled. Existing restoration holds are preserved.
    code='from keystone.workspace.onboarding.service import PrivateAdmission; import sys; s=PrivateAdmission(sys.argv[1],"http://127.0.0.1:8765"); s.close()'
    run_check(python,root,['-c',code,str(workspace)],log)


def readiness_matches(value,workspace_id,identity):
    return (type(value.get('schema_version')) is int and value['schema_version']==1
        and value.get('kind')=='keystone.installation' and value.get('workspace_id')==workspace_id
        and value.get('state')=='checked' and value.get('restart_required') is False
        and value.get('running_source')==identity and value.get('current_source')==identity
        and value.get('frontend',{}).get('state')=='matched'
        and value.get('compatibility',{}).get('state')=='compatible'
        and all(value.get(k) is False for k in ('automatic_update','automatic_migration','financial_approval','production_release_approved')))


def check_web(python,root,workspace,log):
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin='http://127.0.0.1:'+str(port)
    opener=build_opener(ProxyHandler({}),NoRedirect())
    expected=source_identity(root);workspace_id=json.loads((workspace/'workspace.json').read_text())['id']
    with log.open('ab') as stream:
        os.chmod(stream.name,0o600)
        child=subprocess.Popen([str(python),'-m','keystone.workspace','serve','--workspace',str(workspace),'--port',str(port)],
            cwd=root,env=environment(),stdout=stream,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if child.poll() is not None:raise ValueError('Candidate server stopped')
                try:
                    with opener.open(Request(origin+'/api/execution',headers={'Origin':origin}),timeout=1) as response:
                        public=response.read(32_001)
                        if len(public)>32_000:raise ValueError()
                        caps=json.loads(public)
                    if (caps.get('classification')!='private' or caps.get('local_token_required') is not True
                            or caps.get('installation_supported') is not True
                            or any(caps.get(k) is not False for k in ('worker_enabled','admission_enabled','imports_enabled','live_data_enabled','paid_models_enabled','financial_approval'))):raise ValueError()
                    key=(workspace/'control/access-token.key').read_text().strip()
                    request=Request(origin+'/api/installation',headers={'Origin':origin,'Authorization':'Bearer '+key})
                    with opener.open(request,timeout=1) as response:
                        raw=response.read(32_001)
                        if len(raw)>32_000 or response.headers.get('Cache-Control')!='no-store':raise ValueError()
                        result=json.loads(raw)
                    if child.poll() is not None or not readiness_matches(result,workspace_id,expected):raise ValueError()
                    return dict(status='checked',worker_started=False,financial_approval=False)
                except (OSError,ValueError):time.sleep(.1)
            raise ValueError('Candidate readiness unavailable')
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=30)
                except subprocess.TimeoutExpired:child.kill();child.wait()


def rehearse(snapshot,candidate_source,candidate_python,previous_source,previous_python,output):
    output=Path(output).absolute()
    if output.exists() or output.is_symlink() or any(p.is_symlink() for p in output.parents):raise ValueError('New rehearsal destination required')
    new_destination(output)
    candidate,identity=source(candidate_source);previous,old=source(previous_source)
    snapshot=Path(snapshot).absolute();candidate_python=Path(candidate_python).absolute();previous_python=Path(previous_python).absolute()
    for protected in (snapshot,candidate,previous):
        if output==protected or protected in output.parents or output in protected.parents:raise ValueError('Rehearsal storage overlaps protected evidence')
    if not candidate_python.is_file() or not previous_python.is_file():raise ValueError('Existing runtimes required')
    manifest=storage.verify(snapshot);snapshot_sha=storage.digest(Path(snapshot)/'manifest.json')
    if candidate==previous:raise ValueError('Use distinct candidate and previous source directories')
    output.mkdir(mode=0o700,parents=True)
    record=dict(schema_version=1,kind='keystone.update-rehearsal',status='running',snapshot_id=manifest['snapshot_id'],snapshot_manifest_sha256=snapshot_sha,
        candidate_source=identity,previous_source=old,orchestrator_source=source_identity(ROOT),candidate='not_checked',rollback='not_checked',web='not_checked',
        active_installation_changed=False,authoritative_workspace_selected=False,independent_recovery=False,financial_approval=False,production_release_approved=False)
    save(output/'rehearsal.json',record)
    try:
        trial=restore_private(snapshot,output/'candidate-workspace')
        try:
            run_check(candidate_python,candidate,['-m','keystone.installation','doctor'],output/'candidate.log')
            run_check(candidate_python,candidate,['-m','keystone.installation','workspace-check','--workspace',str(trial)],output/'candidate.log')
            initialise(candidate_python,candidate,trial,output/'candidate.log')
            run_check(candidate_python,candidate,['-m','keystone.workspace','audit-private','--workspace',str(trial)],output/'candidate.log')
            check_web(candidate_python,candidate,trial,output/'candidate.log');record['web']='checked'
            record['candidate']='checked'
        except Exception:record['candidate']='failed_preserved'
        # Recovery always starts from the pre-update snapshot, never from the
        # candidate's possibly migrated or partially-written copy.
        recovered=restore_private(snapshot,output/'rollback-workspace')
        try:
            initialise(previous_python,previous,recovered,output/'previous.log')
            run_check(previous_python,previous,['-m','keystone.workspace','audit-private','--workspace',str(recovered)],output/'previous.log')
            record['rollback']='checked'
        except Exception:record['rollback']='failed_preserved'
        if (storage.verify(snapshot)!=manifest or storage.digest(Path(snapshot)/'manifest.json')!=snapshot_sha
                or source_identity(candidate)!=identity or source_identity(previous)!=old or source_identity(ROOT)!=record['orchestrator_source']):raise ValueError('Rehearsal identity changed')
        record['status']='passed' if record['candidate']=='checked' and record['rollback']=='checked' and record['web']=='checked' else 'failed_preserved'
        return record
    except BaseException:
        record['status']='failed_preserved';raise
    finally:save(output/'rehearsal.json',record)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot','candidate-source','candidate-python','previous-source','previous-python','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        value=rehearse(args.snapshot,args.candidate_source,args.candidate_python,args.previous_source,args.previous_python,args.output)
        print(json.dumps(dict(status=value['status'],candidate=value['candidate'],rollback=value['rollback'],
                             authoritative_workspace_selected=False,production_release_approved=False)))
        return 0 if value['status']=='passed' else 2
    except Exception:
        print(json.dumps(dict(error='update_rehearsal_not_passed',message='Preserve previous code, runtime, snapshot and the new rehearsal evidence. No active installation or authoritative workspace was selected.',production_release_approved=False)));return 2


if __name__=='__main__':raise SystemExit(main())
