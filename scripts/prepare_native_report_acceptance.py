"""Combine registered synthetic QA runs into a fresh private acceptance workspace.

No scan of output/, source mutation, provider request or execution endpoint.
Duplicate run IDs must have identical original evidence and catalogue metadata.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from keystone.maintenance import gate
from keystone.workspace.catalog import Catalog,ManifestV2,read_confined
from keystone.workspace.report_views.publish import register_views
from keystone.workspace.report_views.values import canonical


def prepare(workspaces,destination):
    workspaces=[Path(w).absolute() for w in workspaces];destination=Path(destination).absolute()
    if not workspaces:raise ValueError('At least one registered synthetic workspace is required.')
    if destination.exists() or destination.is_symlink():raise FileExistsError('Choose a fresh destination.')
    if any(w.resolve() in [destination.resolve(),*destination.resolve().parents] for w in workspaces):raise ValueError('Destination must be outside all source workspaces.')
    if any(p.is_symlink() for p in [destination,*destination.parents]):raise ValueError('Symlink destinations are not supported.')
    mask=os.umask(0o077)
    try:
        with gate(exclusive=True):
            selected={};source_checks={};raw=None
            for workspace in workspaces:
                catalog=Catalog(workspace);manifest=catalog.load()
                if raw is None:raw=manifest.model_dump()
                source_checks[workspace]={'catalog.json':hashlib.sha256(read_confined(workspace,'catalog.json',2_000_000)).hexdigest()}
                for run in manifest.runs:
                    reg=getattr(run,'native_view',None)
                    excluded={reg.artifact_id,reg.source_artifact_ids[1]} if reg else set()
                    original=run.model_dump();original.pop('native_view',None)
                    original['artifacts']=[a.model_dump() for a in run.artifacts if a.id not in excluded]
                    fingerprint=canonical(original)
                    if run.id in selected and selected[run.id][0]!=fingerprint:raise ValueError('Conflicting registered run identity: '+run.id)
                    for artifact in run.artifacts:
                        data=catalog.read(run.id,artifact)
                        source_checks[workspace][f'runs/{run.id}/{artifact.name}']=hashlib.sha256(data).hexdigest()
                    selected.setdefault(run.id,(fingerprint,catalog,run,original,excluded))
            raw.update(schema_version=2,prepared_at=datetime.now(timezone.utc).isoformat(),
                code_commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip(),
                code_worktree_dirty=bool(subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True,check=True).stdout),
                preparer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),runs=[x[3] for x in selected.values()])
            # Check aggregate inventory bounds before writing any destination.
            manifest=ManifestV2.model_validate(raw)
            destination.mkdir(parents=True,exist_ok=False)
            for _,catalog,run,_,excluded in selected.values():
                for artifact in run.artifacts:
                    if artifact.id in excluded:continue
                    target=destination/'runs'/run.id/artifact.name
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with target.open('xb') as out:out.write(catalog.read(run.id,artifact))
            register_views(destination,manifest)
            for workspace,files in source_checks.items():
                for name,expected in files.items():
                    if hashlib.sha256(read_confined(workspace,name,20_000_000)).hexdigest()!=expected:raise ValueError('Source changed during preparation')
            return dict(workspace=str(destination),runs=len(selected),source_files_checked={str(p):len(v) for p,v in source_checks.items()},
                classification='synthetic',production_release_approved=False)
    finally:os.umask(mask)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,action='append',required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.workspace,args.destination)))
