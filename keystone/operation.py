"""Supervised CLI operations: admission, durable identity, deadlines and safe receipts.

Trusted local OS user only. Agent artifacts remain authoritative financial evidence.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from keystone.maintenance import ROOT, gate, inherited_fds

ENTRYPOINTS = {
    'agent1': ['run.py'], 'agent2': ['monitor.py'],
    'agent3-events': ['-m', 'agent3.run_live'],
    'agent3-news': ['-m', 'agent3.run_news'],
    'agent3-bundles': ['-m', 'agent3.bundles'],
    'agent4-close': ['-m', 'agent4.close'],
    'agent4-report': ['-m', 'agent4.report'],
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_record(path, data):
    """Atomic, flushed local control record; never include prompts or credentials."""
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    with open(temp, 'w', encoding='utf-8') as stream:
        os.chmod(temp, 0o600)
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    sync_directory(path.parent)


def outcome(agent, code):
    if code == 0:
        return 'completed', 'Review agent evidence; process success is not financial approval.'
    if agent == 'agent1' and code == 3 or agent.startswith('agent3') and code == 3:
        return 'review_required', 'Inspect held agent evidence; do not publish as approved.'
    if agent == 'agent1' and code == 4:
        return 'incomplete', 'Inspect saved evidence before an explicit new operation.'
    if agent == 'agent4-close' and code == 3:
        return 'committed_delivery_failed', 'Recover the saved close by its run ID; do not repeat the close.'
    if agent == 'agent2' and code == 3:
        return 'review_required', 'Inspect saved cycle and triage audit; cycle may already be committed.'
    if agent.startswith('agent3') and code == 4:
        return 'unavailable', 'Inspect the attempt and bundle before retrying or recovering its index.'
    return 'failed_inspect_state', 'Inspect authoritative state before retrying; failure does not prove no commit.'


def execute(agent, arguments, operation_id, *, directory=None, allow_paid=False, allow_live_data=False,
            timeout=600, max_requests=12, max_output_tokens=48000):
    if agent not in ENTRYPOINTS or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', operation_id):
        raise ValueError('Invalid operation identity or agent.')
    if not 1 <= timeout <= 600 or not 1 <= max_requests <= 12 or not 1 <= max_output_tokens <= 48000:
        raise ValueError('Limits must be positive and within the selected pilot ceiling.')
    # Scheduler mode is outside supervised one-operation acceptance.
    if agent == 'agent2' and any(a in {'--loop', '--cron', '--reset'} for a in arguments):
        raise ValueError('Unattended scheduling and reset are outside controlled operation.')
    def option(name):
        value = None
        for index, token in enumerate(arguments):
            if token == name:
                value = arguments[index+1] if index+1 < len(arguments) else None
            elif token.startswith(name+'='):
                value = token.split('=',1)[1]
        return value
    if agent == 'agent3-news' and option('--scorer') in {'finbert','divergence'}:
        raise ValueError('Optional model scoring is outside the frozen pilot.')
    live_data = (agent == 'agent3-events' or
                 agent == 'agent3-news' and not option('--fixture') or
                 agent == 'agent1' and any(a == '--live' or a.startswith('--live=') for a in arguments) or
                 agent == 'agent2' and ('yfinance' in arguments or '--data-source=yfinance' in arguments))
    if live_data and not allow_live_data:
        raise ValueError('Live data requires explicit admission and separately reviewed source rights.')
    base = Path(directory) if directory else ROOT / 'state' / 'operations'
    fingerprint = hashlib.sha256(json.dumps([agent, arguments, allow_paid, allow_live_data, timeout, max_requests,
                                           max_output_tokens], separators=(',', ':')).encode()).hexdigest()
    with gate():
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        if base.is_symlink() or base.stat().st_mode & 0o077:
            raise ValueError('Operation directory must be private and not a symlink.')
        location = base / operation_id
        # A used ID is never executed twice, even after failure or process death.
        location.mkdir(mode=0o700, exist_ok=False)
        # Persist the ID directory and its parent before admitting side effects.
        sync_directory(base)
        sync_directory(base.parent)
        receipt = location / 'operation.json'
        record = dict(schema_version=1, operation_id=operation_id, agent=agent,
                      request_sha256=fingerprint, status='admitted', created_at=now(),
                      paid_calls_enabled=allow_paid, live_data_enabled=allow_live_data, timeout_seconds=timeout,
                      max_requests=max_requests, max_output_tokens=max_output_tokens,
                      financial_approval=False, supervisor_pid=os.getpid())
        defaults = {
            'agent1': {'--output':'output'},
            'agent2': {'--db':'state/monitor.duckdb'},
            'agent3-events': {'--db':'state/catalyst.duckdb','--output-dir':'output/agent3-runs'},
            'agent3-news': {'--db':'state/catalyst.duckdb','--output-dir':'output/agent3-news'},
        }.get(agent, {})
        record['evidence_locations'] = {}
        for key in ('--db','--output','--output-dir','--rebuild'):
            value = option(key) or defaults.get(key)
            if value:
                path = Path(value).expanduser()
                record['evidence_locations'][key[2:]] = str(path if path.is_absolute() else ROOT/path)
        write_record(receipt, record)
        budget = location / 'usage.json'
        write_record(budget, dict(schema_version=1, enabled=allow_paid, max_requests=max_requests,
                                 max_output_tokens=max_output_tokens, requests_reserved=0,
                                 output_tokens_reserved=0, input_bytes_limit=100000,
                                 deadline_epoch=time.time()+timeout, calls=[]))
        env = dict(os.environ, KEYSTONE_SUPERVISED='1', KEYSTONE_USAGE_PATH=str(budget.resolve()),
                   AGENT_MCP_PARENT_GUARD='1', MPLBACKEND='Agg', AGENT_DATA_SOURCE='fixture', AGENT_SENTIMENT_SCORER='lm')
        process = None
        started = time.monotonic()
        prior_term = signal.getsignal(signal.SIGTERM)
        def interrupted(*_):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        try:
            process = subprocess.Popen([sys.executable, *ENTRYPOINTS[agent], *arguments],
                                       cwd=ROOT, env=env, pass_fds=inherited_fds(),
                                       start_new_session=True, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            record.update(status='running', worker_pid=process.pid)
            write_record(receipt, record)
            code = process.wait(timeout=timeout)
            status, action = outcome(agent, code)
            record.update(status=status, exit_code=code, next_action=action)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            record.update(status='outcome_unknown', termination='deadline' if isinstance(exc, subprocess.TimeoutExpired) else 'cancelled',
                          next_action='Inspect agent records for a commit and recover saved delivery; never retry blindly.')
            code = 124 if isinstance(exc, subprocess.TimeoutExpired) else 130
        except Exception as exc:
            record.update(status='outcome_unknown', error_type=type(exc).__name__,
                          next_action='Inspect agent state and operation receipt before retrying.')
            code = 2
        finally:
            # Include inherited child workers in cleanup, even if the immediate
            # process has already exited. No separate session for Agent 3 workers.
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            signal.signal(signal.SIGTERM, prior_term)
        usage = json.loads(budget.read_text())
        record['model_control'] = dict(requests_reserved=usage['requests_reserved'],
                                       output_tokens_reserved=usage['output_tokens_reserved'],
                                       unknown_usage_calls=sum(c['status'] != 'reported' for c in usage['calls']),
                                       last_refusal=usage.get('last_refusal'), cost_status='unpriced')
        record.update(finished_at=now(), duration_seconds=round(time.monotonic()-started, 3))
        write_record(receipt, record)
        return code, receipt, record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('agent', choices=ENTRYPOINTS)
    parser.add_argument('--operation-id', required=True, help='unique ID; reused IDs are refused, never rerun')
    parser.add_argument('--allow-paid-model', action='store_true')
    parser.add_argument('--allow-live-data', action='store_true')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--max-requests', type=int, default=12)
    parser.add_argument('--max-output-tokens', type=int, default=48000)
    # Separate control options from the agent's own options explicitly.
    raw = list(sys.argv[1:] if argv is None else argv)
    split = raw.index('--') if '--' in raw else len(raw)
    args = parser.parse_args(raw[:split])
    arguments = raw[split+1:]
    try:
        code, path, record = execute(args.agent, arguments, args.operation_id,
                                    allow_paid=args.allow_paid_model, allow_live_data=args.allow_live_data, timeout=args.timeout,
                                    max_requests=args.max_requests, max_output_tokens=args.max_output_tokens)
        print(json.dumps({'operation_id':args.operation_id, 'status':record['status'],
                          'receipt':str(path), 'next_action':record['next_action']}))
        return code
    except (Exception, KeyboardInterrupt) as exc:
        print(json.dumps({'status':'refused_or_control_failure', 'error_type':type(exc).__name__,
                          'next_action':'Check operation ID, admission lock and receipt; do not assume no agent state was committed.'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
