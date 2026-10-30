"""Operator-only native projection into a fresh, private workspace.

Only explicitly registered files are copied. Existing sources are never edited.
The final catalogue is published after every adapter and binding check succeeds.
"""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path

from ..catalog import ArtifactV2, Catalog, ManifestV2, RunV2, read_json
from .delivery import validate_registration
from .errors import NativeViewError
from .projection import build_view
from .series import prepare_series
from .sources import adapter_for
from .validation import validate_view
from .values import canonical


def _artifact(folder, ident, name, label, kind, value):
    data = canonical(value) + b'\n'
    with (folder / name).open('xb') as output:
        output.write(data)
    return ArtifactV2(id=ident, name=name, label=label, kind=kind,
                      sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))


def register_views(destination, manifest):
    """For a newly created, unpublished destination only; never an API operation."""
    destination = Path(destination)
    if (destination / 'catalog.json').exists() or (destination / 'catalog.json').is_symlink():
        raise FileExistsError('Native registration requires an unpublished destination.')
    result = manifest.model_dump()
    result['schema_version'] = 2
    for raw_run in result['runs']:
        raw_run.pop('native_view', None)
        run = RunV2.model_validate(raw_run)
        expected_name = {'research': 'model.json', 'monitoring': 'snapshot.json',
                         'events': 'bundle.json', 'news': 'bundle.json',
                         'close': run.source_run_id + '.json'}[run.workflow]
        primary = next((a for a in run.artifacts if a.kind == 'evidence' and a.name == expected_name), None)
        if primary is None or any(a.id in {'native-view', 'native-series'} or a.name in {'native-report.json', 'native-series.json'} for a in run.artifacts):
            raise NativeViewError()
        catalog = Catalog(destination)
        source = read_json(catalog.read(run.id, primary))
        folder = destination / 'runs' / run.id
        retained = prepare_series(run, source, primary)
        series = _artifact(folder, 'native-series', 'native-series.json', 'Retained native chart series', 'evidence', retained)
        view = build_view(run, source, retained, [primary, series])
        validate_view(view, run, source, retained, [primary, series])
        native = _artifact(folder, 'native-view', 'native-report.json', 'Native report view', 'report_view', view)
        adapter, version, _ = adapter_for(run)
        raw_run['artifacts'] += [series.model_dump(), native.model_dump()]
        raw_run['native_view'] = dict(artifact_id=native.id, view_schema_version=1, adapter_id=adapter,
                                     adapter_version=version, source_artifact_ids=[primary.id, series.id])
        validate_registration(RunV2.model_validate(raw_run))
    complete = ManifestV2.model_validate(result)
    catalog = Catalog(destination)
    for run in complete.runs:
        for artifact in run.artifacts:
            catalog.read(run.id, artifact)
    # Atomic rename in the same private directory. A partial adapter run has no catalogue.
    temp = destination / 'catalog.pending.json'
    with temp.open('xb') as output:
        output.write(canonical(complete.model_dump()) + b'\n')
        output.flush()
        os.fsync(output.fileno())
    os.replace(temp, destination / 'catalog.json')
    return complete


def project_workspace(workspace, destination):
    from keystone.maintenance import gate
    source_root, destination = Path(workspace).absolute(), Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Choose a new workspace destination.')
    # Do not create output within the original evidence tree, even through a symlink.
    resolved = destination.resolve()
    if resolved == source_root.resolve() or source_root.resolve() in resolved.parents:
        raise ValueError('Choose a destination outside the source workspace.')
    if any(p.is_symlink() for p in [destination, *destination.parents]):
        raise ValueError('Destination ancestors must not be symbolic links.')
    old_mask = os.umask(0o077)
    try:
        with gate(exclusive=True):
            catalog = Catalog(source_root)
            manifest = catalog.load()
            raw = manifest.model_dump()
            raw['schema_version'] = 2
            raw['prepared_at'] = datetime.now(timezone.utc).isoformat()
            # Preserve original run preparation/provenance; identify this projection code.
            from ..prepare import ROOT
            import subprocess
            commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=False)
            raw['code_commit'] = commit.stdout.strip() or None
            raw['code_worktree_dirty'] = bool(subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT,
                capture_output=True, text=True, check=False).stdout.strip())
            raw['preparer_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            destination.mkdir(parents=True, exist_ok=False)
            for run, output_run in zip(manifest.runs, raw['runs']):
                reg = getattr(run, 'native_view', None)
                excluded = {reg.artifact_id, reg.source_artifact_ids[1]} if reg else set()
                output_run.pop('native_view', None)
                output_run['artifacts'] = [a.model_dump() for a in run.artifacts if a.id not in excluded]
                for artifact in run.artifacts:
                    if artifact.id in excluded:
                        continue
                    data = catalog.read(run.id, artifact)
                    target = destination / 'runs' / run.id / artifact.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('xb') as output:
                        output.write(data)
            register_views(destination, ManifestV2.model_validate(raw))
            Catalog(destination).load()
        return destination
    finally:
        os.umask(old_mask)
