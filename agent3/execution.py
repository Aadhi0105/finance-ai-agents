"""Attempt checkpoints, bounded workers and terminal immutable bundle publication."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4

from agent3.orchestrator import analyze_event_type, publication_allowed
from agent3.peers import PeerProposalError

ROOT = Path(__file__).resolve().parents[1]
EXIT_CODES = {'completed': 0, 'refused': 2, 'held': 3, 'unavailable': 4, 'failed': 5}


def now():
    return datetime.now(timezone.utc).isoformat()


def _redact(value, secrets=None):
    # Neither raw provider/SDK stderr nor exception messages are persisted.
    # Also redact configured credentials from any model/user text saved in a record.
    if secrets is None:
        secrets = [secret for key, secret in os.environ.items()
                   if any(word in key.upper() for word in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD')) and len(secret) >= 8]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, '[REDACTED]')
        return value
    if isinstance(value, dict):
        return {k: _redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, secrets) for v in value]
    return value


def read_record(path, *, max_bytes=100_000_000):
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError('record exceeds size limit')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


class Attempt:
    def __init__(self, path, record):
        self.path, self.record = Path(path), record

    @classmethod
    def create(cls, directory, request, retry_of=None):
        run_id = uuid4().hex
        path = Path(directory).resolve() / run_id / 'run.json'
        path.parent.mkdir(parents=True, exist_ok=False)
        from agent3.bundles import provenance
        attempt = cls(path, {'schema_version': 1, 'run_id': run_id, 'created_at': now(),
                             'request': request, 'retry_of': retry_of, 'status': 'running',
                             'stage': 'configuration', 'stage_history': [], 'provenance': provenance()})
        attempt.save()
        return attempt

    def save(self):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(_redact(self.record), indent=2, allow_nan=False))
        tmp.replace(self.path)

    def checkpoint(self, stage, data):
        self.record.update(data)
        self.record['stage'] = stage
        self.record['stage_history'].append({'stage': stage, 'at': now()})
        self.save()

    def finish(self, status, reason=None, error_type=None):
        self.record.update(status=status, finished_at=now())
        if reason:
            self.record['reason'] = reason
        if error_type:
            self.record['error_type'] = error_type
        if 'result' in self.record:
            hold_terminal_result(self.record['result'], status)
        self.save()


def hold_terminal_result(result, status):
    """Share the terminal failure boundary between execution and offline replay."""
    if status not in ('unavailable', 'failed', 'refused'):
        return
    result['status'] = status
    if 'signals' in result:
        result['publication_state'] = 'HELD_FOR_REVIEW'
        for item in result['signals']:
            if item.get('level') is not None:
                item['diagnostic_level'] = item['level']
            item.update(level=None, flag_review=True, publication_state='HELD_FOR_REVIEW')
    scenario = result.get('scenario')
    if isinstance(scenario, dict):
        distribution = scenario.pop('distribution', None)
        if distribution is not None:
            scenario['diagnostic_distribution'] = distribution
        scenario.update(distribution=None, publication_state='HELD_FOR_REVIEW')


def execute(attempt):
    """Worker body; one model request, one provider pass, no automatic retries."""
    request = attempt.record['request']
    try:
        os.environ['AGENT_STATS_VIA_MCP'] = request['transport']
        os.environ['AGENT_MCP_PARENT_GUARD'] = '1'
        if request.get('model'):
            os.environ['AGENT_MODEL'] = request['model']
        result = analyze_event_type(request['event_type'], source='yfinance',
                                    ticker=request['ticker'], peers=request['peers'],
                                    live_propose=request['live_propose'], study_plan=request['study_plan'],
                                    checkpoint=attempt.checkpoint,
                                    peer_decision=attempt.record.get('retry_peer_set'))
        if attempt.record.get('retry_peer_set'):
            # Retain original proposal identity, not just the override created by this attempt.
            result['pinned_peer_set'] = attempt.record['retry_peer_set']
        status = result.get('status', 'held')
        if status not in EXIT_CODES:
            raise ValueError('unknown terminal status')
        if status == 'completed' and not publication_allowed(result):
            status = result['status'] = 'held'
            scenario = result.get('scenario') or {}
            scenario['diagnostic_distribution'] = scenario.pop('distribution', None)
            scenario.update(distribution=None, publication_state='HELD_FOR_REVIEW')
            result.setdefault('gate', {}).update(verdict='HOLD_FOR_REVIEW')
        attempt.checkpoint('result', {'result': result})
        if status in ('held', 'completed'):
            attempt.checkpoint('persistence', {})
            from agent3.catalyst_state import CatalystStore
            store = CatalystStore(request['db'])
            try:
                store.record_outcome(attempt.record['run_id'], result['study'], result['gate'], result.get('pinned_peers'))
            finally:
                store.close()
        attempt.finish(status, result.get('reason'))
    except PeerProposalError as exc:
        attempt.record['peer_proposal_audit'] = exc.audit
        attempt.finish('unavailable' if exc.code in ('missing_credentials', 'model_unavailable') else 'refused', exc.code)
    except (ValueError, KeyError, TypeError) as exc:
        configuration = attempt.record['stage'] in ('configuration', 'peer_selection', 'assembly')
        attempt.finish('refused' if configuration else 'failed',
                       'invalid_configuration_or_input' if configuration else 'invalid_stage_result', type(exc).__name__)
    except Exception as exc:
        attempt.finish('failed', 'execution_failed', type(exc).__name__)
    return EXIT_CODES[attempt.record['status']]


def run_bounded(attempt, timeout, *, worker_module='agent3.execution'):
    """Kill the worker group; the guarded MCP server detects parent loss separately."""
    process = None
    try:
        process = subprocess.Popen([sys.executable, '-m', worker_module, str(attempt.path)],
                                   cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        process.wait(timeout=timeout)
        attempt.record = read_record(attempt.path)
        if attempt.record.get('status') not in EXIT_CODES or process.returncode != EXIT_CODES.get(attempt.record.get('status')):
            attempt.finish('failed', 'worker_exit_without_valid_outcome')
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        attempt.record = read_record(attempt.path)
        attempt.finish('unavailable', 'run_deadline_exceeded' if isinstance(exc, subprocess.TimeoutExpired) else 'interrupted')
    except Exception as exc:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        attempt.finish('failed', 'worker_launch_or_record_failure', type(exc).__name__)
    from agent3.bundles import seal
    path = seal(attempt)
    db = attempt.record['request'].get('db')
    if db:
        from agent3.bundles import write_once
        receipt = {'bundle': str(path), 'indexed': False}
        try:
            from agent3.catalyst_state import CatalystStore
            store = CatalystStore(db)
            try:
                store.index_bundle(path)
            finally:
                store.close()
            receipt['indexed'] = True
        except Exception as exc:
            # Bundle is authoritative and already sealed. Indexing can be recovered
            # explicitly without modifying a completed analytical attempt.
            receipt['error_type'] = type(exc).__name__
        try:
            write_once(path.with_name('index-receipt.json'), receipt)
        except (OSError, ValueError):
            print('Bundle saved; index receipt could not be written. Inspect or reconcile the database index.')
        if not receipt['indexed']:
            print('Bundle saved; database index pending. Reconcile with agent3.bundles --index-db.')
    return EXIT_CODES[attempt.record['status']]


if __name__ == '__main__':
    from keystone.maintenance import gate
    with gate():
        path = Path(sys.argv[1])
        raise SystemExit(execute(Attempt(path, read_record(path))))
