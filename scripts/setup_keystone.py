"""Stage a new local installation from reviewed source and offline dependency caches.

Never modifies an existing installation, chooses a workspace, or starts a worker.
Python and Node must already be installed. No package registry access is enabled.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from keystone.installation import LOCK,canonical,file_proofs,source_files,source_identity


def environment():
    # Provider credentials and package-index configuration are not inherited.
    value={k:v for k,v in os.environ.items() if k in {'PATH','HOME','USER','LOGNAME','TMPDIR','LANG','LC_ALL','SYSTEMROOT'}}
    value.update(AGENT_DATA_SOURCE='fixture',MPLBACKEND='Agg',PIP_CONFIG_FILE=os.devnull,PIP_DISABLE_PIP_VERSION_CHECK='1')
    return value


def save(path,value):
    fd,temporary=tempfile.mkstemp(prefix='.installation-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(),0o600);stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def new_destination(path):
    if path.exists() or path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError('New unlinked destination required')
    for parent in path.parents:
        if any((parent/name).exists() for name in ('workspace.json','inputs.sqlite3','installation.json','pyvenv.cfg')):
            raise ValueError('Destination is inside retained workspace or installation')


def stage(destination, wheelhouse, node, pnpm_js, *, development=False, source=ROOT, run=subprocess.run):
    import platform
    if platform.system()!='Darwin' or platform.machine()!='arm64' or sys.version_info[:2]!=(3,11):raise ValueError('Unsupported setup platform')
    destination=Path(destination).absolute();source=Path(source).absolute();wheelhouse=Path(wheelhouse).absolute()
    node=Path(node).absolute();pnpm_js=Path(pnpm_js).absolute()
    if destination.exists() or any(p.is_symlink() for p in (destination,*destination.parents,source,*source.parents,wheelhouse,node,pnpm_js)):
        raise ValueError('Use new, unlinked installation storage')
    new_destination(destination)
    if not wheelhouse.is_dir() or not node.is_file() or not pnpm_js.is_file():raise ValueError('Local install caches and tools required')
    identity=source_identity(source)
    if identity['sha256'] is None or identity['dirty'] and not development:raise ValueError('Use clean source or explicit development staging')
    proofs=file_proofs(source,source_files(source))
    destination.mkdir(parents=True,mode=0o700);app=destination/'app';app.mkdir(mode=0o700)
    record=dict(schema_version=1,kind='keystone.local-installation',status='preparing',created_at=datetime.now(timezone.utc).isoformat(),
                source_commit=identity['commit'],development=bool(identity['dirty']),source_files=proofs,
                network_install=False,workspace_selected=False,production_release_approved=False)
    save(destination/'installation.json',record)
    try:
        for name in proofs:
            target=app/name;target.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
            with target.open('xb') as stream:
                os.chmod(target,0o600);stream.write((source/name).read_bytes())
        if file_proofs(app,list(proofs))!=proofs or file_proofs(source,source_files(source))!=proofs:raise ValueError('Source changed while copying')
        env=environment();env['PATH']=str(node.parent)+os.pathsep+env.get('PATH',os.defpath)
        def execute(args,cwd=app):
            with (destination/'setup.log').open('ab') as log:
                os.chmod(log.name,0o600)
                return run([str(x) for x in args],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
        version=run([str(node),'--version'],env=env,capture_output=True,text=True,check=True,timeout=10).stdout.strip()
        manager=run([str(node),str(pnpm_js),'--version'],env=env,capture_output=True,text=True,check=True,timeout=10).stdout.strip()
        expected=json.loads((app/'web/package.json').read_text())['packageManager'].split('@')[1]
        if not version.startswith('v24.') or manager!=expected:raise ValueError('Unsupported local web tools')
        execute([sys.executable,'-m','venv',app/'.venv'])
        python=app/'.venv/bin/python'
        execute([python,'-m','pip','install','--require-hashes','--only-binary=:all:','--no-index','--find-links',wheelhouse,'-r',LOCK])
        execute([python,'-m','pip','check'])
        execute([node,pnpm_js,'install','--offline','--frozen-lockfile','--ignore-scripts'],app/'web')
        execute([node,pnpm_js,'run','build'],app/'web')
        execute([python,'-m','keystone.installation','doctor','--preparing'])
        if file_proofs(app,list(proofs))!=proofs:raise ValueError('Installed source changed')
        record.update(status='prepared',completed_at=datetime.now(timezone.utc).isoformat(),node_version=version,pnpm_version=manager)
        save(destination/'installation.json',record)
        return dict(status='prepared',installation=str(destination),development=record['development'],workspace_selected=False,production_release_approved=False)
    except BaseException:
        record.update(status='failed_preserved',completed_at=datetime.now(timezone.utc).isoformat())
        save(destination/'installation.json',record)
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--wheelhouse',type=Path,required=True)
    parser.add_argument('--node',type=Path,required=True)
    parser.add_argument('--pnpm-js',type=Path,required=True)
    parser.add_argument('--development',action='store_true',help='Explicitly stage saved uncommitted source; not a clean release')
    args=parser.parse_args(argv)
    try:print(json.dumps(stage(args.destination,args.wheelhouse,args.node,args.pnpm_js,development=args.development)));return 0
    except (Exception,KeyboardInterrupt):
        print(json.dumps(dict(error='installation_not_prepared',message='Preserve the previous installation. Inspect the new destination and its local setup log; correct prerequisites and retry with a new destination.',production_release_approved=False)));return 2


if __name__=='__main__':raise SystemExit(main())
