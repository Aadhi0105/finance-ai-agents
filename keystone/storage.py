"""Explicit-inventory local snapshots and new-directory restoration.

No automatic discovery, deletion/retention, encryption, upload, or source approval.
Quiescence is required for API/other-checkout writers outside the CLI gate.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.metadata
import platform
import json
import os
import shutil
import stat
import subprocess
import tempfile
import uuid

import duckdb
from filelock import FileLock
from keystone.contracts import relative, validate_plan, release_holds
from keystone.maintenance import ROOT, gate


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        os.chmod(path, 0o600)
        f.write(canonical(value)); f.flush(); os.fsync(f.fileno())


def safe_source(path):
    p = Path(path)
    if any(x.is_symlink() for x in [p, *p.parents]):
        raise ValueError('Symlink source refused')
    if not (p.is_file() or p.is_dir()):
        raise ValueError('Missing or special source refused')
    if p.is_file() and (p.stat().st_nlink != 1 or not stat.S_ISREG(p.stat().st_mode)):
        raise ValueError('Hardlink/special file refused')


def prohibited(path):
    name = path.name.lower()
    return name == '.env' or name.startswith('.env.') or path.suffix.lower() in {'.key','.pem','.p12','.pfx'} or name in {'credentials','credentials.json','secrets.json'} or any(x in {'.git','.venv','.aws','.ssh'} for x in path.parts)


def inventory(plan):
    files = {}; excluded = []
    for entry in plan['sources']:
        src = Path(entry['path']); safe_source(src)
        if prohibited(src):
            raise ValueError('Secret/environment source refused')
        if (entry['kind'] == 'tree') != src.is_dir():
            raise ValueError('Source kind does not match filesystem')
        paths = sorted(src.rglob('*')) if src.is_dir() else [src]
        for p in paths:
            safe_source(p)
            if prohibited(p):
                raise ValueError('Secret/environment source refused; choose a narrower inventory')
            if p.is_dir(): continue
            if p.name.endswith('.lock'):
                excluded.append(str(p)); continue
            if p.name.endswith('.wal') or (entry['kind'] != 'database' and p.suffix == '.duckdb'):
                raise ValueError('Declare databases separately; WAL is not a backup input')
            name = str(relative(entry['name']) / p.relative_to(src)) if src.is_dir() else entry['name']
            files[name] = p
    return files, excluded


def fingerprint(files):
    return {name: {'size':p.stat().st_size,'sha256':digest(p)} for name,p in files.items()}


def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with src.open('rb') as a, dst.open('xb') as b:
        os.chmod(dst,0o600); shutil.copyfileobj(a,b); b.flush(); os.fsync(b.fileno())


def flush_tree(root):
    for p in sorted(root.rglob('*'), key=lambda p:len(p.parts), reverse=True):
        if p.is_dir(): sync_dir(p)
    sync_dir(root)


def verify(snapshot):
    root = Path(snapshot); safe_source(root)
    for p in root.rglob('*'): safe_source(p)
    manifest_path = root/'manifest.json'; seal = root/'manifest.sha256'
    if digest(manifest_path) != seal.read_text().strip():
        raise ValueError('Manifest integrity mismatch')
    m = json.loads(manifest_path.read_text())
    if type(m.get('schema_version')) is not int or m.get('schema_version') != 1 or not isinstance(m.get('files'), dict):
        raise ValueError('Unsupported manifest')
    validate_plan(m['plan'])
    actual = {str(p.relative_to(root/'data')) for p in (root/'data').rglob('*') if p.is_file()}
    if actual != set(m['files']): raise ValueError('Missing or extra snapshot files')
    if {p.name for p in root.iterdir()} != {'manifest.json','manifest.sha256','data'}:
        raise ValueError('Unexpected snapshot content')
    for name, record in m['files'].items():
        relative(name)
        p = root/'data'/name
        if p.stat().st_size != record['size'] or digest(p) != record['sha256']:
            raise ValueError('Snapshot member integrity mismatch')
    return m


def snapshot(plan, destination, *, quiescent=False):
    validate_plan(plan)
    if not quiescent: raise ValueError('Explicit quiescent acknowledgement required')
    dest = Path(destination).absolute()
    for entry in plan['sources']:
        source = Path(entry['path']).resolve()
        if dest.resolve() == source or source in dest.resolve().parents or dest.resolve() in source.parents:
            raise ValueError('Snapshot destination overlaps a source')
    dest.mkdir(parents=True, exist_ok=True, mode=0o700); safe_source(dest)
    stage = None
    with gate(exclusive=True), ExitStack() as stack:
        # Hold native exclusive writer connections until publication; CHECKPOINT
        # removes WAL dependence. Also honour Agent 2's application file lock.
        for entry in sorted(plan['sources'], key=lambda x:x['path']):
            if entry['kind'] == 'database':
                p=Path(entry['path']);safe_source(p)
                stack.enter_context(FileLock(str(p)+'.lock',timeout=0))
                con=duckdb.connect(str(p));stack.callback(con.close)
                con.execute('CHECKPOINT')
        before, excluded = inventory(plan); hashes=fingerprint(before)
        stage=Path(tempfile.mkdtemp(prefix='.incomplete-',dir=dest))
        try:
            (stage/'data').mkdir(mode=0o700)
            for name,p in before.items(): copy_file(p,stage/'data'/name)
            after, excluded_after=inventory(plan)
            if fingerprint(after)!=hashes or excluded_after!=excluded:
                raise ValueError('Source changed during snapshot; no snapshot published')
            git=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
            m={'schema_version':1,'snapshot_id':uuid.uuid4().hex,'created_at':datetime.now(timezone.utc).isoformat(),
               'plan':plan,'files':hashes,'excluded_lock_files':excluded,'code_commit':git.stdout.strip() if git.returncode==0 else None,
               'worktree_dirty':bool(subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True).stdout.strip()),
               'runtime':{'python':platform.python_version(),'platform':platform.platform(),
                          'duckdb':importlib.metadata.version('duckdb'),'filelock':importlib.metadata.version('filelock')},
               'source_hashes':{str(p.relative_to(ROOT)):digest(p) for folder in ('keystone','agent','tools','validation','monitoring','scheduler','state','agent3','agent4','mcp_server','scripts') for p in sorted((ROOT/folder).glob('*.py'))},
               'entrypoint_hashes':{name:digest(ROOT/name) for name in ('run.py','monitor.py','composer.py','requirements.txt')},
               'protection':'local_snapshot_only','permission_holds':release_holds(plan)}
            write_json(stage/'manifest.json',m)
            with (stage/'manifest.sha256').open('x') as f:
                os.chmod(f.name,0o600);f.write(digest(stage/'manifest.json')+'\n');f.flush();os.fsync(f.fileno())
            verify(stage);flush_tree(stage)
            target=dest/m['snapshot_id'];os.rename(stage,target);stage=None;sync_dir(dest)
            return target
        finally:
            if stage is not None: shutil.rmtree(stage)


def relocate(stage, final, m):
    """Audited mutable index metadata only; never rewrite original saved evidence."""
    changes=[]
    def mapped(old):
        for e in m['plan']['sources']:
            source=Path(e['path'])
            if old == source: return Path(e['name'])
            if e['kind']=='tree' and source in old.parents:
                return Path(e['name'])/old.relative_to(source)
        return None
    for e in m['plan']['sources']:
        if e['kind']!='database':continue
        p=stage/e['name'];con=duckdb.connect(str(p))
        try:
            if e['role']=='agent2_state':
                # Explicit provenance, used only alongside the original cycle digest.
                row=con.execute("SELECT value FROM monitor_metadata WHERE key='restored_audit_origins'").fetchone()
                origins=json.loads(row[0]) if row else []
                origins=sorted(set(origins+[e['path']]))
                con.execute("INSERT OR REPLACE INTO monitor_metadata VALUES ('restored_audit_origins', ?)",[canonical(origins)])
                changes.append({'database':e['name'],'kind':'agent2_audit_origins','origins':origins})
            if e['role']=='agent3_state':
                from agent3.bundles import read_bundle
                for run_id,old,expected_hash,expected_inputs in con.execute('SELECT run_id,bundle_path,bundle_sha256,content_fingerprint FROM run_bundles').fetchall():
                    rel=mapped(Path(old))
                    if rel is None or str(rel) not in m['files']:
                        raise ValueError('Indexed Agent 3 bundle missing from inventory')
                    bundle=read_bundle(stage/rel)
                    if bundle['attempt_id'] != run_id or bundle['bundle_sha256'] != expected_hash or bundle['content_fingerprint'] != expected_inputs:
                        raise ValueError('Indexed bundle identity mismatch')
                    con.execute('UPDATE run_bundles SET bundle_path=? WHERE run_id=?',[str(final/rel),run_id])
                    changes.append({'database':e['name'],'kind':'agent3_bundle_path','run_id':run_id,'from':old,'to':str(final/rel)})
            con.execute('CHECKPOINT')
        finally:con.close()
    return changes


def restore(source, destination):
    source=Path(source).absolute();dest=Path(destination).absolute()
    if dest.exists() or dest.is_symlink(): raise ValueError('Restore requires a new destination')
    if source.resolve() in dest.resolve().parents:raise ValueError('Restore destination overlaps snapshot')
    dest.parent.mkdir(parents=True,exist_ok=True);safe_source(dest.parent)
    stage=None
    with gate(exclusive=True), FileLock(str(dest)+'.restore.lock',timeout=0):
        if dest.exists():raise ValueError('Restore destination already exists')
        m=verify(source)
        stage=Path(tempfile.mkdtemp(prefix='.restore-',dir=dest.parent))
        try:
            for entry in m['plan']['sources']:
                if entry['kind']=='tree':(stage/entry['name']).mkdir(parents=True,exist_ok=True,mode=0o700)
            for name in m['files']:copy_file(source/'data'/name,stage/name)
            if fingerprint({name:stage/name for name in m['files']})!=m['files']:
                raise ValueError('Restored bytes differ from snapshot')
            changes=relocate(stage,dest,m)
            # Verify source again to detect changes during restore.
            if verify(source)!=m:raise ValueError('Snapshot changed during restore')
            receipt={'schema_version':1,'snapshot_id':m['snapshot_id'],'snapshot_manifest_sha256':digest(source/'manifest.json'),
                     'restored_at':datetime.now(timezone.utc).isoformat(),'changes':changes,
                     'files':fingerprint({name:stage/name for name in m['files']}),
                     'protection':'local_restore_test_only','permission_holds':m['permission_holds']}
            write_json(stage/'restore-receipt.json',receipt)
            flush_tree(stage)
            if dest.exists() or dest.is_symlink():raise ValueError('Restore destination changed during restore')
            os.rename(stage,dest);stage=None;sync_dir(dest.parent)
            return dest
        finally:
            if stage is not None:shutil.rmtree(stage)
