"""Read-only local release diagnostics; no credentials, provider calls or remediation."""
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

from keystone.maintenance import ROOT


def inspect_environment():
    lock = ROOT / 'requirements-macos-arm64-py311.lock'
    mismatches = []
    for line in lock.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        name, version = line.split()[0].split('==')
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            actual = None
        if actual != version:
            mismatches.append({'package':name, 'expected':version, 'installed':actual})
    supported = platform.system() == 'Darwin' and platform.machine() == 'arm64' and sys.version_info[:2] == (3,11)
    checks = []
    for name in ('state/operations', '.env'):
        path = ROOT / name
        if path.exists() or path.is_symlink():
            checks.append({'name':name, 'private':not path.is_symlink() and not bool(path.stat().st_mode & 0o077)})
    identity = subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,timeout=3)
    dirty = subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True,timeout=3)
    return dict(schema_version=1, platform=platform.system(), architecture=platform.machine(),
                os_version=platform.mac_ver()[0], python=platform.python_version(),
                pilot_platform_matches=supported, dependency_mismatches=mismatches,
                lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(),
                code_commit=identity.stdout.strip() if identity.returncode==0 else None,
                worktree_dirty=bool(dirty.stdout.strip()) if dirty.returncode==0 else None,
                selected_path_checks=checks,
                status='ready_for_local_checks' if supported and not mismatches and all(c['private'] for c in checks) else 'review_required',
                production_release_approved=False,
                limitations=['Existing reports/inputs and network exposure require separate deployment review.',
                             'Version matching does not prove installed bytes match wheel hashes.',
                             'Clean virtual environment is not clean-machine disaster recovery.'])


def inspect_operation(operation_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', operation_id):
        raise ValueError('Invalid operation ID.')
    directory=ROOT/'state'/'operations'/operation_id
    record=json.loads((directory/'operation.json').read_text())
    if record.get('schema_version') != 1:
        raise ValueError('Unsupported operation schema.')
    if record['status'] in ('admitted','running'):
        record=dict(record, status='unresolved', next_action='May be active or interrupted. Inspect worker and agent evidence; a PID alone is not proof of liveness. Do not delete locks or repeat the operation.')
    usage_path=directory/'usage.json'
    usage=json.loads(usage_path.read_text()) if usage_path.exists() else None
    return {'operation':record,'usage':usage,'cost_status':'unpriced','financial_approval':False}
