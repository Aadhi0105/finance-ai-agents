"""Prepare an offline analyst rehearsal; never grants production or human approval.

Uses new disposable directories only. Run serially with other checkout workflows.
The same-candidate recovery exercise is not an upgrade or disaster-recovery claim.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import uuid
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / 'docs/production/v1/acceptance-matrix.md'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def gate_records(text):
    records = []
    for line in text.splitlines():
        if not line.startswith('| V1-'):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if len(cells) != 6 or not re.fullmatch(r'V1-[A-Z0-9]+-\d{3}', cells[0]):
            raise ValueError('Malformed acceptance row')
        records.append(dict(id=cells[0], requirement=cells[1], baseline_status=cells[5],
                            candidate_status='not assessed', evidence=[], reviewer=None,
                            reviewed_at=None))
    ids = [r['id'] for r in records]
    if len(ids) != 26 or len(set(ids)) != len(ids):
        raise ValueError('Acceptance matrix changed; review pilot schema before proceeding')
    return records


def pending_manifest(environment, gates):
    return dict(schema_version=1, kind='keystone.pilot-preparation',
                created_at=datetime.now(timezone.utc).isoformat(), environment=environment,
                candidate_commit=environment['code_commit'],
                candidate_worktree_dirty=environment['worktree_dirty'],
                candidate_scope='offline synthetic four-agent rehearsal; retained references are historical',
                production_accepted_capabilities=[], gates=gates,
                human_uat=dict(status='not started', analyst=None, completed_at=None),
                financial_signoff=None, release_signoff=None,
                release_decision='not eligible', production_release_approved=False,
                independent_backup_tested=False, clean_machine_recovery_tested=False,
                source_permissions_approved=False, company_fp_and_a_accepted=False)


def tree_size(path):
    files = [p for p in Path(path).rglob('*') if p.is_file() and not p.is_symlink()]
    return dict(files=len(files), bytes=sum(p.stat().st_size for p in files))


def prepare_operator_pack(output):
    """Concrete manual commands for fresh operator copies; never executes them."""
    from keystone.storage import restore
    output = Path(output)
    snapshot_path = next((output / 'storage/snapshots').iterdir())
    workspace = restore(snapshot_path, output / 'analyst-workspace')
    model = next((workspace / 'research').glob('*/model.json'))
    shutil.copytree(model.parent, output / 'analyst-rebuild')
    bundle = next((workspace / 'news').glob('*/bundle.json'))
    prefix = 'uat-' + uuid.uuid4().hex[:12]
    python = sys.executable
    def controlled(agent, suffix, args):
        return shlex.join([python, '-m', 'keystone.operation', agent, '--operation-id',
                          prefix + '-' + suffix, '--', *map(str, args)])
    research = controlled('agent1', 'research', ['--rebuild', output / 'analyst-rebuild/model.json'])
    tasks = [
        ('UAT-01', 'Check the environment', shlex.join([python, '-m', 'keystone', 'doctor']),
         'Ready for local checks; explain why this is not production approval.'),
        ('UAT-02', 'Rebuild and review research', research,
         'Exit 3 / review_required. Open analyst-rebuild/report_REVIEW.html; identify a hold and trace a number to model.json.'),
        ('UAT-03', 'Refuse an accidental repeated operation', research,
         'Exit 2 / FileExistsError refusal; original operation receipt unchanged. Do not delete the receipt or lock.'),
        ('UAT-04', 'Inspect the research operation', shlex.join([python, '-m', 'keystone', 'inspect-operation', prefix + '-research']),
         'Review-required receipt, saved evidence location and zero reserved paid calls.'),
        ('UAT-05', 'Retrieve monitoring history', controlled('agent2', 'monitor',
         ['--db', workspace / 'state/monitor.duckdb', '--report', output / 'analyst-monitor.html',
          '--report-cycle', '9', '--audit-dir', workspace / 'audits']),
         'Open analyst-monitor.html. Find cycle 9, distinguish financial breach from triage status, locate saved audit.'),
        ('UAT-06', 'Replay held news evidence', controlled('agent3-bundles', 'news',
         [bundle, '--output', output / 'analyst-news.json', '--html', output / 'analyst-news.html']),
         'Replay matched; open analyst-news.html. Explain saved fixture cutoff and why stub tone is not accepted sentiment.'),
        ('UAT-07', 'Recover a saved close report', controlled('agent4-report', 'close',
         ['--db', workspace / 'state/variance.duckdb', '--run-id', 'close-12', '--output-dir', output / 'analyst-close']),
         'Open regenerated close report. Identify original run ID and synthetic-company label; do not submit another close.'),
        ('UAT-08', 'Restore to a new local directory', shlex.join([python, '-m', 'keystone', 'restore',
         str(snapshot_path), '--destination', str(output / 'analyst-restored')]),
         'Successful local restore with restore-receipt.json. A second identical command refuses the existing destination. Explain why same-device restore is not disaster recovery.'),
    ]
    records = [dict(id=i, task=t, command=c, expected=e, actual=None, status='not started',
                    evidence=None, assistance=None, elapsed_seconds=None) for i,t,c,e in tasks]
    candidate = json.loads((output / 'pilot.json').read_text())
    (output / 'analyst-results.json').write_text(json.dumps(dict(analyst=None, candidate_commit=candidate['candidate_commit'],
        candidate_worktree_dirty=candidate['candidate_worktree_dirty'],
        scope='offline rehearsal only', tasks=records, financial_approval=False, production_release_approved=False), indent=2))
    lines = ['# Manual analyst rehearsal', '', 'Run each command separately from the repository directory.',
             'Record observations in analyst-results.json. Stop and record unexpected outcomes; do not force a pass.',
             'Exit 3 can be an expected financial hold. Do not paste all tasks as one script.',
             'These commands refer to this local preparation and Python environment; prepare a new pack if either moves.', '']
    for i,t,c,e in tasks:
        lines += [f'## {i}: {t}', '', '```bash', c, '```', '', e, '']
    (output / 'analyst-tasks.md').write_text('\n'.join(lines))


def run_acceptance(output):
    from keystone.environment import inspect_environment
    from scripts.check_keystone_storage import run_acceptance as storage
    from scripts.check_keystone_upgrade import run_acceptance as recovery
    from keystone.storage import snapshot, verify, restore
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(output, 0o700)
    manifest = pending_manifest(inspect_environment(), gate_records(MATRIX.read_text()))
    sources = ['scripts/check_keystone_pilot.py', 'scripts/check_keystone_storage.py',
               'scripts/check_keystone_upgrade.py', 'requirements-macos-arm64-py311.lock',
               'docs/production/v1/acceptance-matrix.md']
    manifest['source_hashes'] = {name: sha(ROOT / name) for name in sources}
    manifest['rehearsal'] = dict(status='running', steps=[], workload='one storage/recovery preparation run',
                                 human_uat_completed=False, capacity_accepted=False)
    receipt = output / 'pilot.json'
    receipt.write_text(json.dumps(manifest, indent=2))
    started = time.monotonic()
    previous = {key: os.environ.get(key) for key in ('AGENT_DATA_SOURCE', 'AGENT_STATS_VIA_MCP', 'LM_DICTIONARY_CSV')}
    os.environ.update(AGENT_DATA_SOURCE='fixture', AGENT_STATS_VIA_MCP='0', LM_DICTIONARY_CSV='')
    try:
        if manifest['environment']['status'] != 'ready_for_local_checks':
            raise ValueError('Resolve doctor holds before rehearsal')
        for name, action in [('storage', lambda: storage(output / 'storage')),
                             ('same_candidate_recovery', lambda: recovery(next((output / 'storage/snapshots').iterdir()), output / 'recovery'))]:
            step_started = time.monotonic()
            result = action()
            if result['status'] != 'passed':
                raise AssertionError('Rehearsal step did not pass')
            manifest['rehearsal']['steps'].append(dict(name=name, status='passed',
                seconds=round(time.monotonic()-step_started, 3), size=tree_size(output / ('storage' if name == 'storage' else 'recovery'))))
            receipt.write_text(json.dumps(manifest, indent=2))
        # Verify the controlled-operation receipts survive a separate local backup.
        operations = output / 'recovery/operations'
        plan = dict(schema_version=1, scope='synthetic operation history', sources=[dict(
            name='operations', path=str(operations), kind='tree', role='logs')], datasets=[dict(
            id='operations', source='offline rehearsal', classification='synthetic', period='rehearsal',
            currency='not applicable', units='not applicable', permission='synthetic_only',
            permission_evidence='synthetic local test', freshness_policy='saved receipts', source_names=['operations'])])
        saved = snapshot(plan, output / 'receipt-snapshots', quiescent=True)
        verify(saved)
        restored = restore(saved, output / 'restored-receipts')
        for path in operations.rglob('*.json'):
            if path.read_bytes() != (restored / 'operations' / path.relative_to(operations)).read_bytes():
                raise AssertionError('Restored operation receipt differs')
        receipts = [json.loads(p.read_text()) for p in operations.glob('*/operation.json')]
        if len(receipts) != 3 or any(r['model_control']['requests_reserved'] for r in receipts):
            raise AssertionError('Unexpected operation count or paid usage')
        prepare_operator_pack(output)
        if any(sha(ROOT / name) != digest for name, digest in manifest['source_hashes'].items()):
            raise AssertionError('Rehearsal source changed during execution')
        manifest['rehearsal'].update(status='passed', operation_receipts_restored=len(receipts),
                                     paid_requests_reserved=0, live_retrieval_requested=False)
    except (Exception, KeyboardInterrupt) as exc:
        manifest['rehearsal'].update(status='failed', error_type=type(exc).__name__)
        raise
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        manifest['rehearsal'].update(seconds=round(time.monotonic()-started, 3), generated_size=tree_size(output))
        manifest['rehearsal']['measurement_limits'] = 'One run; includes duplicate recovery copies, excludes install/cache space and human time. Not capacity, RPO or disaster RTO acceptance.'
        receipt.write_text(json.dumps(manifest, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    result = run_acceptance(args.output)
    print(json.dumps(dict(status=result['rehearsal']['status'], receipt=str(Path(args.output)/'pilot.json'),
                         human_uat='not started', production_release_approved=False)))


if __name__ == '__main__':
    main()
