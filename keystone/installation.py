"""Read-only installation identity and schema checks; standard library only.

This module is usable before installing the application's optional web runtime.
It performs no dependency installation, migration, financial work or repair.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import stat
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
LOCK='requirements-web-macos-arm64-py311.lock'
HASH=r'[a-f0-9]{64}'
MAX_FILES=5000
MAX_BYTES=100_000_000
RUNTIME_SUFFIXES={'.py','.json','.yaml','.yml','.lock','.ts','.tsx','.css','.html','.txt','.mjs'}

def runtime_member(name):return Path(name).suffix in RUNTIME_SUFFIXES and not name.startswith(('tests/','web/tests/'))


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(data):return hashlib.sha256(data).hexdigest()

def bounded(path,limit):
    info=path.lstat()
    if any(p.is_symlink() for p in (path,*path.parents)) or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:raise ValueError('Unsafe or oversized member')
    with path.open('rb') as stream:data=stream.read(limit+1)
    if len(data)>limit:raise ValueError('Read bound')
    return data


def requirements(root=ROOT):
    """Only this release's two fixed hash locks; no arbitrary include resolution."""
    rows={}
    for name in ('requirements-macos-arm64-py311.lock',LOCK):
        for line in (root/name).read_text().splitlines():
            if not line or line.startswith('#') or line=='-r requirements-macos-arm64-py311.lock':continue
            match=re.fullmatch(r'([A-Za-z0-9_.-]{1,80})==([A-Za-z0-9_.+!-]{1,80}) --hash=sha256:('+HASH+')',line)
            if not match:raise ValueError('Unsupported frozen requirement')
            package,version,digest=match.groups()
            if package.lower() in rows:raise ValueError('Duplicate frozen package')
            rows[package.lower()]=(version,digest)
    return rows


def runtime(root=ROOT):
    mismatches=[]
    for name,(expected,_) in requirements(root).items():
        try:actual=metadata.version(name)
        except metadata.PackageNotFoundError:actual=None
        if actual is not None and not re.fullmatch(r'[A-Za-z0-9_.+!-]{1,80}',actual):actual='unavailable'
        if actual!=expected:mismatches.append(dict(package=name,expected=expected,installed=actual))
    return dict(platform=platform.system(),architecture=platform.machine(),python=platform.python_version(),
        supported=platform.system()=='Darwin' and platform.machine()=='arm64' and sys.version_info[:2]==(3,11),
        dependency_mismatches=mismatches,lock_sha256=sha(canonical([[name,sha((root/name).read_bytes())]
            for name in ('requirements-macos-arm64-py311.lock',LOCK)])))


def source_files(root=ROOT):
    """Tracked and non-ignored source only; copied installations use a fixed manifest."""
    if (root/'.git').exists():
        result=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root,capture_output=True,timeout=5)
        if result.returncode:raise ValueError('Source inventory unavailable')
        names=sorted(set(result.stdout.decode().split('\0'))-{''})
    else:
        receipt=json.loads(bounded(root.parent/'installation.json',1_500_000))
        if root.name!='app' or receipt.get('kind')!='keystone.local-installation':raise ValueError()
        names=list(receipt['source_files'])
    if len(names)>MAX_FILES:raise ValueError()
    return names


def file_proofs(root,names):
    proofs={};total=0
    for name in sorted(names):
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or not p.parts or any(x in {'.git','.venv','node_modules','output'} for x in p.parts):
            if name=='output/.gitkeep':continue
            raise ValueError('Unsupported source member')
        if p.name.startswith('.env') or p.suffix in {'.key','.pem','.p12','.pfx'}:raise ValueError('Secret source member')
        path=root/p
        if any(parent.is_symlink() for parent in [path,*path.parents]):raise ValueError('Linked source')
        info=path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('Unsafe source')
        total+=info.st_size
        if total>MAX_BYTES or len(proofs)>=MAX_FILES:raise ValueError('Source bound')
        data=bounded(path,info.st_size)
        if len(data)!=info.st_size:raise ValueError('Changing source')
        proofs[name]=dict(bytes=len(data),sha256=sha(data))
    return proofs


def source_identity(root=ROOT,*,allow_preparing=False):
    try:
        names=source_files(root)
        proofs=file_proofs(root,[n for n in names if runtime_member(n)])
        digest=sha(canonical(proofs))
        if (root/'.git').exists():
            head=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True,timeout=3)
            dirty=subprocess.run(['git','status','--porcelain'],cwd=root,capture_output=True,text=True,timeout=3)
            commit=head.stdout.strip()
            if not re.fullmatch(r'[a-f0-9]{40}',commit) or dirty.returncode:raise ValueError()
            return dict(mode='checkout',commit=commit,dirty=bool(dirty.stdout.strip()),sha256=digest)
        receipt=json.loads(bounded(root.parent/'installation.json',1_500_000))
        if (receipt.get('schema_version')!=1 or receipt.get('status') not in ({'prepared','preparing'} if allow_preparing else {'prepared'})
                or type(receipt.get('development')) is not bool or not re.fullmatch(r'[a-f0-9]{40}',receipt.get('source_commit',''))):raise ValueError('Unprepared installation')
        expected={n:v for n,v in receipt['source_files'].items() if runtime_member(n)}
        # Extra executable source in a staged application is not covered by its
        # manifest. Prune fixed generated/private runtime roots before walking.
        seen=0
        for folder,dirs,files in os.walk(root,followlinks=False):
            relative=Path(folder).relative_to(root)
            dirs[:]=[d for d in dirs if d not in {'.venv','node_modules','__pycache__','.git'}
                      and str(relative/d) not in {'web/dist','output','state/launcher','state/workspaces','state/operations','state/workspace-jobs'}]
            if any((Path(folder)/d).is_symlink() for d in dirs):raise ValueError('Linked staged source')
            for name in files:
                seen+=1
                if seen>MAX_FILES:raise ValueError('Staged source bound')
                member=str(relative/name)
                if member.startswith('state/.keystone-maintenance.lock'):continue
                if runtime_member(member) and member not in expected:raise ValueError('Unregistered staged source')
        if proofs!=expected:raise ValueError('Staged source changed')
        return dict(mode='staged',commit=receipt['source_commit'],dirty=receipt['development'],sha256=digest)
    except Exception:return dict(mode='unavailable',commit=None,dirty=None,sha256=None)


def frontend_source(root=ROOT):
    names=['web/'+p for p in ('package.json','pnpm-lock.yaml','tsconfig.json','vite.config.ts','index.html','scripts/build.mjs')]
    names += [str(p.relative_to(root)) for p in (root/'web/src').rglob('*') if p.is_file()]
    proofs=file_proofs(root,names)
    return sha(json.dumps([[n,v['sha256']] for n,v in sorted(proofs.items())],separators=(',',':'),ensure_ascii=False).encode())


def frontend_identity(frontend,root=ROOT):
    try:
        stamp=json.loads(bounded(frontend/'build.json',256_000))
        if set(stamp)!={'schema_version','kind','source_sha256','built_at','files'} or stamp['schema_version']!=1 or stamp['kind']!='keystone.frontend-build':raise ValueError()
        if not re.fullmatch(HASH,stamp['source_sha256']) or len(stamp['built_at'])>80 or datetime.fromisoformat(stamp['built_at']).utcoffset() is None:raise ValueError()
        files=stamp['files']
        if not isinstance(files,dict) or 'index.html' not in files or not 2<=len(files)<=1000:raise ValueError()
        total=0
        for name,digest in files.items():
            if name!='index.html' and not re.fullmatch(r'assets/[A-Za-z0-9_-]+\.(js|css)',name):raise ValueError()
            path=frontend/name
            if any(p.is_symlink() for p in (path,*path.parents)) or not re.fullmatch(HASH,digest):raise ValueError()
            total+=path.stat().st_size
            if total>20_000_000 or sha(bounded(path,20_000_000))!=digest:raise ValueError()
        return dict(state='matched' if stamp['source_sha256']==frontend_source(root) else 'stale',source_sha256=stamp['source_sha256'],built_at=stamp['built_at'])
    except Exception:return dict(state='unavailable',source_sha256=None,built_at=None)


def compatibility(workspace):
    """Schema identity only, not an integrity audit or automatic migration."""
    versions={};state='compatible'
    try:
        root=Path(workspace).absolute()
        if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError()
        for key,name,expected in [('inputs','inputs.sqlite3',1),('jobs','control/jobs.sqlite3',2)]:
            path=root/name
            if key=='jobs' and not path.exists() and not (root/'control').exists():
                versions[key]=None;continue  # Newly prepared, never-opened workspace.
            info=path.lstat()
            if any(p.is_symlink() for p in (path,*path.parents)) or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>64_000_000:raise ValueError()
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)) as con:
                actual=con.execute('PRAGMA user_version').fetchone()[0]
                app=con.execute('PRAGMA application_id').fetchone()[0]
                if app!=({'inputs':0x4B534931,'jobs':0x4B534A31}[key]):raise ValueError()
            versions[key]=actual
            if actual!=expected:state='migration_required' if key=='jobs' and actual==1 and state=='compatible' else 'unsupported'
        catalog_path=root/'reports/catalog.json'
        if any(p.is_symlink() for p in (catalog_path,*catalog_path.parents)) or catalog_path.stat().st_size>2_000_000:raise ValueError()
        with catalog_path.open('rb') as stream:data=stream.read(2_000_001)
        if len(data)>2_000_000:raise ValueError()
        catalog=json.loads(data)
        versions['catalog']=catalog.get('schema_version')
        if type(versions['catalog']) is not int or versions['catalog']!=3:state='unsupported'
    except Exception:state='unavailable'
    return dict(state=state,versions={k:versions.get(k) for k in ('inputs','jobs','catalog')},expected=dict(inputs=1,jobs=2,catalog=3),automatic_migration=False)


def observe(inputs,started,frontend):
    current=source_identity();env=runtime();web=frontend_identity(frontend);compat=compatibility(inputs.root)
    try:
        info=inputs.root.lstat()
        if ((info.st_dev,info.st_ino)!=inputs._root_identity or info.st_mode&0o077 or info.st_uid!=os.getuid()
                or inputs.read('workspace.json',65536)!=canonical(inputs.descriptor)):raise ValueError()
    except Exception:compat=dict(state='unavailable',versions=dict(inputs=None,jobs=None,catalog=None),expected=dict(inputs=1,jobs=2,catalog=3),automatic_migration=False)
    changed=started['sha256'] is None or current['sha256'] is None or started['sha256']!=current['sha256']
    state='attention' if changed or not env['supported'] or env['dependency_mismatches'] or web['state']!='matched' or compat['state']!='compatible' else 'checked'
    return dict(schema_version=1,kind='keystone.installation',workspace_id=inputs.descriptor['id'],observed_at=datetime.now(timezone.utc).isoformat(),state=state,
        running_source=started,current_source=current,restart_required=changed,runtime=env,frontend=web,compatibility=compat,
        automatic_update=False,automatic_migration=False,financial_approval=False,production_release_approved=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('doctor');p.add_argument('--preparing',action='store_true',help='Installer-only check before publishing a new preparation receipt')
    p=sub.add_parser('workspace-check');p.add_argument('--workspace',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.action=='doctor':
            value=dict(schema_version=1,kind='keystone.installation-doctor',source=source_identity(allow_preparing=args.preparing),runtime=runtime(),
                       frontend=frontend_identity(ROOT/'web/dist'),production_release_approved=False)
            ready=value['source']['sha256'] is not None and value['runtime']['supported'] and not value['runtime']['dependency_mismatches'] and value['frontend']['state']=='matched'
        else:value=compatibility(args.workspace);ready=value['state']=='compatible'
        print(json.dumps(value,indent=2));return 0 if ready else 3
    except Exception:
        print(json.dumps(dict(error='installation_check_unavailable',production_release_approved=False)));return 2


if __name__=='__main__':raise SystemExit(main())
