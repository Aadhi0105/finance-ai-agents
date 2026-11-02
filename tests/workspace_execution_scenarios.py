"""TEST ONLY: isolated, offline browser acceptance with closed failure scenarios.

No fault endpoint or production CLI flag is added. This executable refuses roots
without its private acceptance marker. All processing uses the existing worker,
supervisor and saved-evidence profiles; only named boundaries are interrupted.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keystone.maintenance import gate, inherited_fds
from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog, ManifestV2, run_identity
from keystone.workspace.job_contract import canonical
from keystone.workspace.job_files import write_new
from keystone.workspace.job_store import private_member
from keystone.workspace.jobs import Admission
from keystone.workspace.worker_process import WorkerProcess

KIND = 'keystone.test-only-execution-acceptance-v1'
FAULTS = ('none', 'lost_ack', 'slow_ack', 'source_changed', 'processing_failed',
          'timeout', 'pause', 'delivery_before', 'delivery_after', 'crash_after_registration')


def read_root(root):
    root = Path(root).absolute()
    if any(p.is_symlink() for p in [root, *root.parents]):
        raise ValueError('Acceptance roots cannot use symlinks.')
    private_member(root, directory=True)
    marker = root / 'acceptance.json'
    private_member(marker)
    data = json.loads(marker.read_text())
    if data.get('kind') != KIND or data.get('classification') != 'synthetic':
        raise ValueError('A prepared synthetic acceptance root is required.')
    private_member(root / 'workspace', directory=True)
    return root


def prepare(source, destination):
    """Copy exactly five registered synthetic families; never modify the source."""
    source, root = Path(source).absolute(), Path(destination).absolute()
    if root.exists() or root.is_symlink():
        raise FileExistsError('Choose a fresh acceptance destination.')
    if any(p.is_symlink() for p in [root, *root.parents]) or source.resolve() in root.resolve().parents:
        raise ValueError('Use an independent, non-symlink destination.')
    with gate(exclusive=True):
        catalog = Catalog(source)
        manifest = catalog.load()
        selected = [next(r for r in manifest.runs if r.id == family + '-example')
                    for family in ('research', 'monitoring', 'events', 'news', 'close')]
        if any(getattr(r, 'native_view', None) is None for r in selected):
            raise ValueError('Registered native sources are required.')
        raw = manifest.model_dump()
        raw['runs'] = [run_identity(r) for r in selected]
        ManifestV2.model_validate(raw)
        before = hashlib.sha256((source / 'catalog.json').read_bytes()).hexdigest()
        root.mkdir(parents=True, mode=0o700)
        workspace = root / 'workspace'
        workspace.mkdir(mode=0o700)
        (workspace / 'runs').mkdir(mode=0o700)
        hashes = {}
        for run in selected:
            for artifact in run.artifacts:
                relative = 'runs/' + run.id + '/' + artifact.name
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                data = catalog.read(run.id, artifact)
                write_new(target, data)
                hashes[relative] = hashlib.sha256(data).hexdigest()
        write_new(workspace / 'catalog.json', (canonical(raw) + '\n').encode())
        Catalog(workspace).load()
        if hashlib.sha256((source / 'catalog.json').read_bytes()).hexdigest() != before:
            raise ValueError('Source registration changed during preparation.')
        write_new(root / 'acceptance.json', (canonical(dict(kind=KIND, classification='synthetic',
            original_runs=raw['runs'], original_files=hashes, source_catalog_sha256=before)) + '\n').encode())
    return read_root(root)


class ScenarioAdmission(Admission):
    def __init__(self, root, origin, fault):
        self.acceptance_root = read_root(root)
        if fault not in FAULTS:
            raise ValueError('Unknown acceptance scenario.')
        self.fault = fault
        super().__init__(self.acceptance_root / 'workspace', self.acceptance_root / 'control', origin, enable_worker=True)

    def start_worker(self):
        if self.worker is not None:
            return
        original = subprocess.Popen
        def spawn(command, **kwargs):
            if command[:3] != [sys.executable, '-m', 'keystone.workspace.worker']:
                raise ValueError('Unexpected test worker command.')
            fixed = [sys.executable, str(Path(__file__).resolve()), 'worker',
                     '--root', str(self.acceptance_root), '--fault', self.fault, '--', *command[3:]]
            return original(fixed, **kwargs)
        # Only construction is patched. Production lifecycle/readiness and the
        # child's native worker main retain their existing leases and handlers.
        with patch('keystone.workspace.worker_process.subprocess.Popen', spawn):
            self.worker = WorkerProcess(self.catalog.root, self.store.root)
        path = self.acceptance_root / 'worker-pid.json'
        path.write_text(json.dumps({'pid': self.worker.process.pid}))
        path.chmod(0o600)


def scenario_app(root, origin, fault='none'):
    service = ScenarioAdmission(root, origin, fault)
    app = create_app(service.catalog.root, admission=service)
    acknowledgement_used = (Path(root) / (fault + '.json')).exists()
    @app.middleware('http')
    async def acknowledgement(request, call_next):
        nonlocal acknowledgement_used
        response = await call_next(request)
        if (not acknowledgement_used and request.method == 'POST' and request.url.path == '/api/jobs'
                and response.status_code == 202 and fault in {'lost_ack', 'slow_ack'}):
            acknowledgement_used = True
            write_new(Path(root) / (fault + '.json'), b'{"admission_committed":true}\n')
            if fault == 'lost_ack':
                from fastapi.responses import Response
                headers = {k:v for k,v in response.headers.items() if k.lower() not in {'content-length','content-type'}}
                return Response('Test acknowledgement unavailable.', status_code=502, headers=headers)
            await asyncio.sleep(3)
        return response
    return app, service


def configure_worker(root, fault):
    from keystone import operation
    from keystone.workspace import worker, job_delivery
    if fault in {'processing_failed', 'timeout'}:
        operation.ENTRYPOINTS['workspace-saved'] = [str(Path(__file__).resolve()),
            'child-delay' if fault == 'timeout' else 'child-fail', '--root', str(root)]
    if fault in {'delivery_before', 'delivery_after', 'crash_after_registration'}:
        original = job_delivery._replace_inventory
        def interrupted(*args):
            if fault != 'delivery_before':
                original(*args)
            if fault == 'crash_after_registration':
                os._exit(23)
            raise OSError('Test-only delivery interruption.')
        job_delivery._replace_inventory = interrupted
    if fault in {'source_changed', 'pause'}:
        original = worker.prepare_inputs
        def prepared(store, record):
            if fault == 'pause':
                marker = root / 'paused.json'
                if not marker.exists():
                    write_new(marker, (canonical({'job_id': record.job_id}) + '\n').encode())
                until = time.monotonic() + 45
                while not (root / 'release').exists():
                    if time.monotonic() > until:
                        raise TimeoutError('Test pause expired.')
                    time.sleep(.05)
                return original(store, record)
            path = store.workspace / 'catalog.json'
            saved = path.read_bytes()
            data = json.loads(saved)
            next(r for r in data['runs'] if r['id'] == record.source.run_id)['summary'] = 'Test-only changed source metadata.'
            try:
                path.write_text(canonical(data) + '\n')
                return original(store, record)
            finally:
                path.write_bytes(saved)
        worker.prepare_inputs = prepared


def verify(root):
    root = read_root(root)
    marker = json.loads((root / 'acceptance.json').read_text())
    manifest = Catalog(root / 'workspace').load()
    assert [run_identity(r) for r in manifest.runs[:5]] == marker['original_runs']
    for name, expected in marker['original_files'].items():
        assert hashlib.sha256((root / 'workspace' / name).read_bytes()).hexdigest() == expected
    import sqlite3
    con = sqlite3.connect((root / 'control/jobs.sqlite3').as_uri() + '?mode=ro', uri=True)
    try:
        rows = con.execute('SELECT j.record_json,x.record_json FROM jobs j JOIN executions x ON j.job_id=x.job_id ORDER BY j.sequence').fetchall()
    finally:
        con.close()
    jobs = []
    for raw, execution in rows:
        record, state = json.loads(raw), json.loads(execution)
        assert not any(record[k] for k in ('live_data_enabled', 'paid_models_enabled', 'financial_approval'))
        assert state['attempt'] in {0, 1}
        proof = root / 'control/operations' / record['operation_id'] / 'operation.json'
        if proof.exists():
            op = json.loads(proof.read_text())
            assert op['model_control']['requests_reserved'] == 0
        jobs.append(dict(job_id=record['job_id'], operation_id=record['operation_id'],
            workflow=record['request']['workflow'], status=state['status'], attempt=state['attempt'],
            result=state['result']['run_id'] if state['result'] else None))
    receipt = dict(kind=KIND, original_runs_preserved=5, original_files_preserved=len(marker['original_files']),
                   registered_runs=len(manifest.runs), jobs=jobs, financial_approval=False,
                   production_release_approved=False)
    path = root / 'verified.json'
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    path.chmod(0o600)
    return receipt


def history(root, port, count):
    """Populate bounded failed-job history through actual protected local HTTP."""
    from urllib.request import Request, build_opener, ProxyHandler
    if not 1024 <= port <= 65535 or not 1 <= count <= 35:
        raise ValueError('Use an unprivileged local port and 1–35 history cases.')
    root = read_root(root)
    private_member(root / 'control/access-token.key')
    secret = (root / 'control/access-token.key').read_text().strip()
    origin = f'http://127.0.0.1:{port}'
    opener = build_opener(ProxyHandler({}))
    def request(path, body=None, key=None):
        headers = {'Authorization':'Bearer '+secret, 'Origin':origin}
        if key: headers.update({'Content-Type':'application/json','Idempotency-Key':key})
        with opener.open(Request(origin+path, data=body, headers=headers), timeout=15) as response:
            return json.load(response)
    identities = []
    for i in range(count):
        admitted = request('/api/jobs', canonical(dict(schema_version=1,workflow='close',
            source_run_id='close-example',timeout_seconds=30)).encode(), f'acceptance-history-{i:03d}')
        ident = admitted['job']['job_id']
        until = time.monotonic()+30
        while time.monotonic() < until:
            saved = request('/api/jobs/'+ident)['job']
            if saved['status'] not in {'queued','running'}: break
            time.sleep(.05)
        if saved['status'] != 'failed' or saved['execution']['attempt'] != 1:
            raise ValueError('History rehearsal requires the processing_failed scenario.')
        identities.append(ident)
    if len(set(identities)) != count: raise ValueError('History identities overlapped.')
    write_new(root/'history-http.json', (canonical({'jobs':identities,'status':'failed'})+'\n').encode())
    return dict(history_jobs=count, financial_approval=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('--source', type=Path, required=True); prep.add_argument('--destination', type=Path, required=True)
    serve = sub.add_parser('serve'); serve.add_argument('--root', type=Path, required=True); serve.add_argument('--port', type=int, default=8797); serve.add_argument('--fault', choices=FAULTS, default='none')
    volume = sub.add_parser('history'); volume.add_argument('--root', type=Path, required=True); volume.add_argument('--port', type=int, default=8797); volume.add_argument('--count', type=int, default=30)
    child = sub.add_parser('worker'); child.add_argument('--root', type=Path, required=True); child.add_argument('--fault', choices=FAULTS, required=True); child.add_argument('args', nargs=argparse.REMAINDER)
    for action in ('verify', 'child-fail', 'child-delay'):
        command = sub.add_parser(action); command.add_argument('--root', type=Path, required=True)
        if action.startswith('child-'): command.add_argument('folder', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(json.dumps({'prepared': str(prepare(args.source, args.destination))})); return 0
    root = read_root(args.root)
    if args.action == 'serve':
        if not 1024 <= args.port <= 65535: parser.error('Use an unprivileged local port.')
        import uvicorn
        app, service = scenario_app(root, f'http://127.0.0.1:{args.port}', args.fault)
        print(json.dumps({'test_only': True, 'fault': args.fault, 'token_file': str(service.token_file)}), flush=True)
        try: uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False, access_log=False)
        finally: service.close()
    elif args.action == 'history':
        print(json.dumps(history(root,args.port,args.count)))
    elif args.action == 'worker':
        configure_worker(root, args.fault)
        from keystone.workspace.worker import main as worker_main
        return worker_main(args.args[1:] if args.args[:1] == ['--'] else args.args)
    elif args.action.startswith('child-'):
        if os.environ.get('KEYSTONE_SUPERVISED') != '1' or not inherited_fds(): return 2
        if args.folder.absolute().parent != root / 'control/jobs': return 2
        if args.action == 'child-delay': time.sleep(5)
        return 2
    else:
        receipt = verify(root)
        print(json.dumps({k: v for k, v in receipt.items() if k != 'jobs'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
