"""Build and open a local Keystone workspace, without submitting new analysis."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'state/launcher'
SETTINGS = STATE / 'settings.json'


class LaunchError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def load_settings(path, workspace=None, port=None):
    try:
        value = json.loads(Path(path).read_text())
        if not isinstance(value, dict) or set(value) != {'schema_version', 'workspace', 'port', 'node', 'pnpm_js'} or type(value['schema_version']) is not int or value['schema_version'] != 1:
            raise ValueError()
        result = {key: value[key] for key in ('workspace', 'node', 'pnpm_js')}
        if workspace is not None: result['workspace'] = str(workspace)
        for key, raw in result.items():
            if not isinstance(raw, str) or not raw: raise ValueError()
            result[key] = (ROOT / Path(raw).expanduser()).resolve()
        result['port'] = value['port'] if port is None else port
        if type(result['port']) is not int or not 1024 <= result['port'] <= 65535: raise ValueError()
        descriptor = json.loads((result['workspace'] / 'workspace.json').read_text())
        if not isinstance(descriptor, dict) or descriptor.get('kind') != 'keystone.private-workspace' or not isinstance(descriptor.get('id'), str): raise ValueError()
        if not (result['workspace'] / 'reports/catalog.json').is_file(): raise ValueError()
        result['workspace_id'] = descriptor['id']
        if any(not result[k].is_file() for k in ('node', 'pnpm_js')): raise ValueError()
        if not (ROOT / '.venv/bin/python').is_file(): raise ValueError()
        return result
    except (OSError, ValueError, TypeError, KeyError):
        raise LaunchError('Check state/launcher/settings.json, the existing private workspace, .venv, and the configured Node/pnpm files. See docs/webapp/open-keystone.md.') from None


@contextmanager
def lease(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)  # Never unlink a lock another invocation may already have opened.


def revision():
    result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                            cwd=ROOT, capture_output=True, check=True)
    names = sorted(set(result.stdout.decode().split('\0')) - {''})
    digest = hashlib.sha256()
    for name in names:
        if Path(name).suffix not in {'.py', '.json', '.yaml', '.yml', '.lock', '.ts', '.tsx', '.css', '.html'}: continue
        path = ROOT / name
        if path.is_file():
            digest.update(name.encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def publish_build(source, destination):
    files = sorted(source.rglob('*'))
    if not (source / 'index.html').is_file() or any(p.is_symlink() for p in files):
        raise LaunchError('The website build did not produce the expected files.')
    # Publish hashed assets first and index last. Keep older assets for already
    # open tabs; a failed build never empties the website currently being served.
    for path in sorted((p for p in files if p.is_file()), key=lambda p: p == source / 'index.html'):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.launch-')
        try:
            with os.fdopen(fd, 'wb') as stream, path.open('rb') as incoming:
                shutil.copyfileobj(incoming, stream)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)


def build_website(config):
    environment = dict(os.environ)
    environment['PATH'] = str(config['node'].parent) + os.pathsep + str(ROOT / '.venv/bin') + os.pathsep + environment.get('PATH', os.defpath)
    command = [str(config['node']), str(config['pnpm_js'])]
    node = subprocess.run([str(config['node']), '--version'], capture_output=True, text=True, check=True).stdout.strip()
    manager = subprocess.run(command + ['--version'], cwd=ROOT / 'web', env=environment, capture_output=True, text=True, check=True).stdout.strip()
    expected = json.loads((ROOT / 'web/package.json').read_text())['packageManager'].split('@', 1)[1]
    if not node.startswith('v24.') or manager != expected:
        raise LaunchError('The website needs Node 24 and pnpm ' + expected + '; update the local launcher settings.')
    print('Building the website from your current local code…', flush=True)
    try:
        with lease(STATE / 'build.lock'), tempfile.TemporaryDirectory(dir=STATE, prefix='web-build-') as temporary:
            output = Path(temporary) / 'dist'
            subprocess.run(command + ['run', 'build', '--outDir', str(output), '--emptyOutDir'],
                           cwd=ROOT / 'web', env=environment, check=True)
            publish_build(output, ROOT / 'web/dist')
    except BlockingIOError:
        raise LaunchError('Another website build is running. Wait for it to finish and run Open Keystone again.') from None


def port_busy(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.5): return True
    except ConnectionRefusedError:
        return False


def probe(config):
    origin = 'http://127.0.0.1:' + str(config['port'])
    opener = build_opener(ProxyHandler({}), NoRedirect())
    def get(path, token=None):
        headers = {'Origin': origin}
        if token is not None: headers['Authorization'] = 'Bearer ' + token
        with opener.open(Request(origin + path, headers=headers), timeout=1) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000 or response.headers.get('Cache-Control') != 'no-store': return {}
            return json.loads(raw)
    try:
        capabilities = get('/api/execution')
        if capabilities.get('classification') != 'private' or capabilities.get('local_token_required') is not True: return False
        token = (config['workspace'] / 'control/access-token.key').read_text().strip()
        info = get('/api/workspace', token)
        return (info.get('workspace_id') == config['workspace_id'] and info.get('kind') == 'keystone.private-workspace-reports'
                and all(info.get(k) is True for k in ('input_admission_enabled', 'job_admission_enabled', 'job_worker_enabled', 'review_notes_enabled', 'review_corrections_enabled'))
                and all(info.get(k) is False for k in ('live_data_enabled', 'paid_models_enabled')))
    except (OSError, ValueError, HTTPError, URLError):
        return False


def wait_ready(config, child=None, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child is not None and child.poll() is not None:
            raise LaunchError('Keystone stopped before it was ready. Inspect the server message above; preserve workspace and lock files.')
        if probe(config): return
        time.sleep(.2)
    raise LaunchError('Keystone did not become ready within 30 seconds. Inspect the server output; preserve existing inputs and lock files.')


def announce(config, browser):
    url = 'http://127.0.0.1:' + str(config['port']) + '/'
    print('Keystone is ready: ' + url, flush=True)
    print('Connection file: ' + str(config['workspace'] / 'control/access-token.key'), flush=True)
    if browser:
        try: opened = webbrowser.open(url)
        except webbrowser.Error: opened = False
        if not opened: print('Open the address above in your browser.', flush=True)


def open_workspace(config, browser=True):
    key = hashlib.sha256((str(config['workspace']) + ':' + str(config['port'])).encode()).hexdigest()[:24]
    record = STATE / (key + '.json')
    lock = lease(STATE / (key + '.lock'))
    try:
        lock.__enter__()
    except BlockingIOError:
        try:
            saved = json.loads(record.read_text())
        except (OSError, ValueError):
            raise LaunchError('Another Open Keystone task is starting. Wait for its ready message.') from None
        if saved != {'workspace_id': config['workspace_id'], 'revision': revision()}:
            raise LaunchError('Local code has changed. Stop the existing Open Keystone task with Ctrl+C, then run it again to load the update.')
        build_website(config)
        if saved['revision'] != revision(): raise LaunchError('Local files changed during the build. Run Open Keystone again after saving your edits.')
        wait_ready(config)
        print('Reusing the matching running Open Keystone session.', flush=True)
        announce(config, browser)
        return 0
    child = None
    try:
        if port_busy(config['port']):
            raise LaunchError('Port ' + str(config['port']) + ' is already in use by a server outside this launcher. Stop its original terminal with Ctrl+C, then run Open Keystone again. No process or lock file was removed.')
        before = revision()
        build_website(config)
        if before != revision(): raise LaunchError('Local files changed during the build. Save your edits and run Open Keystone again.')
        command = [str(ROOT / '.venv/bin/python'), '-m', 'keystone.workspace', 'serve', '--workspace', str(config['workspace']),
                   '--port', str(config['port']), '--enable-imports', '--enable-job-admission', '--enable-worker', '--enable-review-notes', '--enable-review-corrections']
        child = subprocess.Popen(command, cwd=ROOT)
        record.write_text(json.dumps({'workspace_id': config['workspace_id'], 'revision': before}))
        wait_ready(config, child)
        announce(config, browser)
        print('Keep this terminal running. Ctrl+C stops this launcher’s server safely.', flush=True)
        return child.wait()
    finally:
        try:
            if child is not None and child.poll() is None:
                print('Waiting for Keystone to close safely…', flush=True)
                child.terminate()
                child.wait()
            if record.exists(): record.unlink()
        finally:
            lock.__exit__(None, None, None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, default=SETTINGS)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--port', type=int)
    parser.add_argument('--no-browser', action='store_true', help='Verify/start without opening the system browser')
    args = parser.parse_args(argv)
    previous = signal.getsignal(signal.SIGTERM)
    def stop(_signal, _frame): raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try:
        return open_workspace(load_settings(args.settings, args.workspace, args.port), not args.no_browser)
    except KeyboardInterrupt:
        print('Open Keystone stopped.', flush=True)
        return 0
    except (LaunchError, OSError, subprocess.SubprocessError) as error:
        # No HTTP headers, credential contents or environment dumps in diagnostics.
        print('Open Keystone: ' + (str(error) if isinstance(error, LaunchError) else 'Startup/build failed. Inspect the output above and the launcher setup guide.'), file=sys.stderr)
        return 2
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == '__main__':
    raise SystemExit(main())
