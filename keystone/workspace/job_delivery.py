"""Verify successful saved work, then atomically append one registered native run."""
import os
from pathlib import Path
import uuid

from keystone.operation import request_fingerprint, sync_directory
from .catalog import Catalog, ManifestV2, parse_manifest, read_confined, read_json, run_identity
from .job_contract import JobError, fingerprint
from .job_execution import PreparedResult
from .job_files import digest_bytes, flush_tree, matching_source, write_new
from .job_store import private_member


def operation_proof(store, record, *, committed_close=False,committed_local=False):
    relative = f'operations/{record.operation_id}/operation.json'
    data = read_confined(store.root, relative, 65_536)
    private_member(store.root / relative)
    saved = read_json(data)
    # Preserve the executed argument fingerprint after an explicit local restore
    # into a new control directory. This old path is provenance only, never opened.
    original_folder = saved.get('saved_job_input')
    if (not isinstance(original_folder, str) or len(original_folder) > 4096
            or not Path(original_folder).is_absolute() or Path(original_folder).name != record.job_id
            or Path(original_folder).parent.name != 'jobs'):
        raise JobError('job_recovery_unavailable', 409)
    expected = request_fingerprint('workspace-saved', [original_folder], False, False,
        record.request.timeout_seconds, record.max_requests, record.max_output_tokens)
    committed=(committed_close and record.schema_version==3) or (committed_local and record.schema_version in {4,5})
    orphaned = committed and saved.get('status') in {'admitted','running'}
    usage_ok = not any(saved.get('model_control', {}).get(k) != 0
                       for k in ('requests_reserved','output_tokens_reserved','unknown_usage_calls'))
    if orphaned:
        # An abruptly lost supervisor may never write its final receipt. Preserve
        # those bytes and verify the separate disabled usage ledger instead.
        usage = read_json(read_confined(store.root,f'operations/{record.operation_id}/usage.json',65536))
        usage_ok = (usage.get('enabled') is False and usage.get('calls') == []
                    and usage.get('requests_reserved') == usage.get('output_tokens_reserved') == 0
                    and usage.get('max_requests') == record.max_requests
                    and usage.get('max_output_tokens') == record.max_output_tokens)
    if (saved.get('operation_id') != record.operation_id or saved.get('agent') != 'workspace-saved'
            or saved.get('request_sha256') != expected
            or (saved.get('status') not in {'completed','review_required'} or type(saved.get('exit_code')) is not int
                or saved['exit_code'] not in {0,3}) and not (committed
                    and (saved.get('status') in {'failed_inspect_state','outcome_unknown'} or orphaned))
            or any(saved.get(k) is not False for k in ('paid_calls_enabled','live_data_enabled','financial_approval'))
            or not usage_ok):
        raise JobError('job_recovery_unavailable', 409)
    return ({**saved,'status':'outcome_unknown'} if orphaned else saved), digest_bytes(data)


def verified_result(store, record, expected=None):
    if record.schema_version in {2, 3, 4, 5}:
        from .onboarding.execution import verified_result as verified_dataset
        return verified_dataset(store,record,expected)
    folder = store.root / 'jobs' / record.job_id
    stage = folder / 'result'
    catalog = Catalog(stage)
    manifest = catalog.load()
    if len(manifest.runs) != 1:
        raise JobError('job_recovery_unavailable', 409)
    run = manifest.runs[0]
    origin = run.job_origin
    if (run.id != 'result-' + record.job_id[4:] or run.workflow != record.request.workflow
            or origin is None or origin.job_id != record.job_id
            or origin.source_catalog_run_id != record.source.run_id
            or origin.source_run_sha256 != record.source.run_sha256
            or origin.request_sha256 != record.request_sha256 or origin.profile != record.profile):
        raise JobError('job_recovery_unavailable', 409)
    inputs = Catalog(folder / 'inputs')
    _, source_run = matching_source(inputs, record)
    old_primary = next(a for a in source_run.artifacts if a.id == record.source.primary_artifact_id)
    new_primary = next(a for a in run.artifacts if a.id == run.native_view.source_artifact_ids[0])
    original = inputs.read(source_run.id, old_primary)
    rebuilt = catalog.read(run.id, new_primary)
    if record.request.workflow == 'research':
        before, after = read_json(original), read_json(rebuilt)
        excluded = {'artifacts', 'validation', 'note'}
        if {k:v for k,v in before.items() if k not in excluded} != {k:v for k,v in after.items() if k not in excluded}:
            raise JobError('job_recovery_unavailable', 409)
    elif original != rebuilt:
        raise JobError('job_recovery_unavailable', 409)
    if (run.agent, run.entity, run.period, run.source_run_id, run.execution_status, run.review_status) != (
            source_run.agent, source_run.entity, source_run.period, source_run.source_run_id,
            source_run.execution_status, source_run.review_status):
        raise JobError('job_recovery_unavailable', 409)
    saved, receipt_sha = operation_proof(store, record)
    result = PreparedResult(run_id=run.id, manifest_sha256=digest_bytes(read_confined(stage,'catalog.json',2_000_000)),
        run_sha256=fingerprint(run_identity(run)), operation_receipt_sha256=receipt_sha)
    if expected is not None and result != expected:
        raise JobError('job_recovery_unavailable', 409)
    return result, run, saved


def publish_result(store, record, expected):
    """Caller holds the cooperative mutator lease; originals are never overwritten."""
    result, run, _ = verified_result(store, record, expected)
    root = store.workspace
    old_bytes = read_confined(root, 'catalog.json', 2_000_000)
    catalog = Catalog(root)
    current = catalog.load()
    registered = next((r for r in current.runs if r.id == run.id), None)
    if registered is not None:
        if fingerprint(run_identity(registered)) != result.run_sha256:
            raise JobError('job_recovery_unavailable', 409)
        return run.id
    raw = read_json(old_bytes)
    raw['runs'].append(run_identity(run))
    complete = parse_manifest(raw)
    from .job_contract import canonical
    inventory_bytes = (canonical(raw) + '\n').encode()
    if (len({r.id for r in complete.runs}) != len(complete.runs)
            or len(inventory_bytes) > 2_000_000
            or sum(a.bytes for r in complete.runs for a in r.artifacts) > 100_000_000):
        raise JobError('job_capacity_reached', 409)
    runs = root / 'runs'
    private_member(runs, directory=True)
    target = runs / run.id
    stage = Catalog(store.root / 'jobs' / record.job_id / 'result')
    if target.exists() or target.is_symlink():
        # An interrupted folder promotion is recoverable only with exact bytes
        # and no additional entries; never remove or overwrite a conflicting run.
        private_member(target, directory=True)
        actual = {str(p.relative_to(target)) for p in target.rglob('*') if p.is_file() or p.is_symlink()}
        if actual != {a.name for a in run.artifacts}:
            raise JobError('job_recovery_unavailable', 409)
        for artifact in run.artifacts:
            catalog.read(run.id, artifact)
    else:
        pending = runs / ('.pending-' + uuid.uuid4().hex)
        pending.mkdir(mode=0o700)
        for artifact in run.artifacts:
            write_new(pending / artifact.name, stage.read(run.id, artifact))
        flush_tree(pending)
        os.rename(pending, target)
        sync_directory(runs)
    # All registered artifacts and native source bindings are validated before
    # the inventory becomes visible. Readers see either the old or complete list.
    pending_catalog = root / ('.catalog-' + uuid.uuid4().hex)
    write_new(pending_catalog, inventory_bytes)
    _replace_inventory(root, pending_catalog, old_bytes)
    Catalog(root).load()
    return run.id


def _replace_inventory(root, pending, old_bytes):
    if read_confined(root, 'catalog.json', 2_000_000) != old_bytes:
        raise JobError('job_recovery_unavailable', 409)
    os.replace(pending, root / 'catalog.json')
    sync_directory(root)
