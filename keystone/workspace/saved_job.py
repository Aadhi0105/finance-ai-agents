"""Supervised, offline-only renderer/replayer for a closed saved-job profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess

from keystone.maintenance import ROOT, inherited_fds
from .catalog import ArtifactV2, Catalog, JobOrigin, ManifestV2, RunV2, read_json, run_identity
from .job_contract import now
from .job_files import flush_tree, matching_source, read_job, write_new
from .report_views.publish import register_views


def deny_network(*args, **kwargs):
    raise PermissionError('Saved-job profiles are offline only.')


def render(folder):
    record = read_job(folder)
    if record.schema_version in {2, 3, 4}:
        from .onboarding.execution import render as render_dataset
        return render_dataset(folder,record)
    catalog = Catalog(folder / 'inputs')
    source_manifest, source_run = matching_source(catalog, record)
    commit = subprocess.run(['git','rev-parse','HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=5, check=True)
    dirty = subprocess.run(['git','status','--porcelain'], cwd=ROOT, capture_output=True, text=True, timeout=5, check=True)
    producer_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    stage = folder / 'result'
    stage.mkdir(mode=0o700, exist_ok=False)
    run = run_identity(source_run)
    run.update(id='result-' + record.job_id[4:], title=('Saved rerun · ' + source_run.title)[:160],
               prepared_at=now(), job_origin=JobOrigin(job_id=record.job_id,
                source_catalog_run_id=source_run.id, source_run_sha256=record.source.run_sha256,
                request_sha256=record.request_sha256, profile=record.profile,
                producer_code_commit=commit.stdout.strip(), producer_worktree_dirty=bool(dirty.stdout),
                producer_sha256=producer_sha).model_dump())
    run.pop('native_view', None)
    target = stage / 'runs' / run['id']
    target.mkdir(parents=True, mode=0o700)
    excluded = {source_run.native_view.artifact_id, source_run.native_view.source_artifact_ids[1]}
    artifacts = []
    for artifact in source_run.artifacts:
        if artifact.id in excluded or artifact.kind in {'report', 'chart'}:
            continue
        write_new(target / artifact.name, catalog.read(source_run.id, artifact))
        artifacts.append(artifact)
    primary = next(a for a in artifacts if a.id == record.source.primary_artifact_id)
    primary_path = target / primary.name
    original = read_json(primary_path.read_bytes())
    workflow = record.request.workflow
    if workflow == 'research':
        import composer
        report_path = Path(composer.build_report(str(primary_path)))
        # Composer revalidates and updates only this private copy of model.json.
        artifacts = [a.model_copy(update={'bytes': primary_path.stat().st_size,
            'sha256': hashlib.sha256(primary_path.read_bytes()).hexdigest()}) if a.id == primary.id else a for a in artifacts]
        for index, path in enumerate(sorted((target / 'charts').glob('*.png'))):
            artifacts.append(artifact_for(path, target, 'rebuilt-chart-' + str(index), 'Rebuilt saved chart', 'chart'))
    elif workflow == 'monitoring':
        from monitoring.reporting import render_report
        report_path = target / 'report.html'
        write_new(report_path, render_report(original).encode())
    elif workflow in {'events','news'}:
        from agent3.bundles import read_bundle, replay, export_html
        bundle = read_bundle(primary_path)
        rebuilt = replay(bundle)
        if rebuilt['verification'] != 'matched':
            raise ValueError('Deterministic replay did not match.')
        verification = target / 'replay-verification.json'
        write_new(verification, (json.dumps(rebuilt, sort_keys=True, allow_nan=False) + '\n').encode())
        artifacts.append(artifact_for(verification, target, 'replay-verification', 'Current deterministic replay verification', 'evidence'))
        report_path = target / 'report.html'
        write_new(report_path, export_html(bundle, rebuilt).encode())
    else:
        from agent4.report import render_report
        from agent4.state import digest
        saved = dict(bundle=original, bundle_digest=digest(original))
        report_path = target / (source_run.source_run_id + '.html')
        write_new(report_path, render_report(saved, [saved]).encode())
    artifacts.append(artifact_for(report_path, target, 'rebuilt-report', 'Rebuilt saved report', 'report'))
    run.update(artifacts=[a.model_dump() for a in artifacts], report_id='rebuilt-report')
    run = RunV2.model_validate(run)
    raw = source_manifest.model_dump()
    raw.update(schema_version=2, prepared_at=now(), code_commit=commit.stdout.strip(),
               code_worktree_dirty=bool(dirty.stdout), preparer_sha256=producer_sha,
               runs=[run.model_dump()])
    register_views(stage, ManifestV2.model_validate(raw))
    Catalog(stage).load()
    flush_tree(stage)
    return 3  # All current synthetic native recipes retain an explicit review gate.


def artifact_for(path, root, ident, label, kind):
    data = path.read_bytes()
    return ArtifactV2(id=ident, name=str(path.relative_to(root)), label=label, kind=kind,
                      bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args(argv)
    try:
        if os.environ.get('KEYSTONE_SUPERVISED') != '1' or not inherited_fds():
            return 2
        record = read_job(args.directory)
        # A killed supervisor cannot leave this offline child alive indefinitely.
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.alarm(record.request.timeout_seconds)
        socket.socket.connect = deny_network
        socket.socket.connect_ex = deny_network
        socket.create_connection = deny_network
        socket.getaddrinfo = deny_network
        return render(args.directory)
    except Exception as error:
        try:
            write_new(args.directory / 'failure.json', json.dumps({'status':'failed','error_type':type(error).__name__}).encode())
        except Exception:
            pass
        return 2
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    raise SystemExit(main())
