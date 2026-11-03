"""Confined job working copies and immutable source revalidation."""
import hashlib
import os
from pathlib import Path

from keystone.operation import sync_directory
from .catalog import Catalog, ManifestV2, read_confined, read_json, run_identity
from .job_contract import JobError, JobRecord, canonical, fingerprint
from .job_store import private_member


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def flush_tree(root):
    for path in sorted(Path(root).rglob('*'), key=lambda p: len(p.parts), reverse=True):
        private_member(path, directory=path.is_dir())
        if path.is_dir():
            sync_directory(path)
        else:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    sync_directory(root)


def matching_source(catalog, record):
    try:
        manifest = catalog.load()
        run = next(r for r in manifest.runs if r.id == record.request.source_run_id)
        if (fingerprint(run_identity(run)) != record.source.run_sha256
                or run.native_view != record.source.native_view
                or [a.model_dump() for a in run.artifacts] != [a.model_dump() for a in record.source.artifacts]):
            raise ValueError('Source registration changed.')
        return manifest, run
    except Exception:
        raise JobError('job_source_unavailable') from None


def prepare_inputs(store, record):
    if record.schema_version in {2, 3, 4}:
        from .onboarding.execution import prepare_inputs as prepare_dataset
        return prepare_dataset(store,record)
    catalog = Catalog(store.workspace)
    manifest, run = matching_source(catalog, record)
    if any(r.id == 'result-' + record.job_id[4:] for r in manifest.runs):
        raise JobError('job_recovery_unavailable', 409)
    if len(manifest.runs) >= 100:
        raise JobError('job_capacity_reached', 409)
    parent = store.root / 'jobs'
    parent.mkdir(mode=0o700, exist_ok=True)
    private_member(parent, directory=True)
    folder = parent / record.job_id
    folder.mkdir(mode=0o700, exist_ok=False)
    write_new(folder / 'job.json', (canonical(record.model_dump()) + '\n').encode())
    inputs = folder / 'inputs'
    inputs.mkdir(mode=0o700)
    for artifact in record.source.artifacts:
        write_new(inputs / 'runs' / run.id / artifact.name, catalog.read(run.id, artifact))
    raw = manifest.model_dump()
    raw.update(schema_version=2, runs=[run_identity(run)])
    write_new(inputs / 'catalog.json', (canonical(raw) + '\n').encode())
    matching_source(Catalog(inputs), record)
    matching_source(catalog, record)
    flush_tree(folder)
    sync_directory(parent)
    sync_directory(store.root)
    return folder


def read_job(folder):
    folder = Path(folder).absolute()
    if any(p.is_symlink() for p in [folder, *folder.parents]):
        raise ValueError('Unsafe job directory.')
    private_member(folder, directory=True)
    from .job_contract import parse_job_record
    record = parse_job_record(read_json(read_confined(folder, 'job.json', 65_536)))
    if folder.name != record.job_id:
        raise ValueError('Wrong job directory identity.')
    if record.schema_version in {2, 3, 4}:
        from .onboarding.execution import read_inputs
        read_inputs(folder,record)
    else:
        matching_source(Catalog(folder / 'inputs'), record)
    return record


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()
