"""Cross-process paid-call reservation for the supervised local CLI boundary."""
import json
import os
from pathlib import Path
import time
from filelock import FileLock
from keystone.operation import write_record


class BudgetRefused(RuntimeError):
    pass


def reserve(model, max_tokens, system, messages, tools):
    path = os.environ.get('KEYSTONE_USAGE_PATH')
    if os.environ.get('KEYSTONE_SUPERVISED') != '1':
        return None  # Legacy engineering APIs are explicitly outside this boundary.
    if not path:
        raise BudgetRefused('Missing supervised budget.')
    path = Path(path)
    with FileLock(str(path)+'.lock', timeout=0):
        data = json.loads(path.read_text())
        size = len(json.dumps([system, messages, tools], ensure_ascii=False).encode())
        reason = None
        if not data['enabled']:
            reason = 'paid_calls_disabled'
        elif time.time() >= data['deadline_epoch']:
            reason = 'deadline_exceeded'
        elif type(max_tokens) is not int or max_tokens <= 0:
            reason = 'invalid_output_limit'
        elif any(c['status'] != 'reported' for c in data['calls']):
            reason = 'prior_usage_unknown'
        elif data['requests_reserved'] >= data['max_requests']:
            reason = 'request_limit'
        elif data['output_tokens_reserved'] + max_tokens > data['max_output_tokens']:
            reason = 'output_reservation_limit'
        elif size > data['input_bytes_limit']:
            reason = 'input_size_limit'
        if reason:
            data['last_refusal'] = reason
            write_record(path, data)
            raise BudgetRefused('Paid call refused: ' + reason)
        index = len(data['calls'])
        data['calls'].append({'model':model, 'max_output_tokens':max_tokens,
                              'input_bytes':size, 'status':'usage_unknown', 'usage':None,
                              'cost_status':'unpriced'})
        data['requests_reserved'] += 1
        data['output_tokens_reserved'] += max_tokens
        write_record(path, data)  # Reserve before network; do not refund uncertain calls.
        return path, index


def report(reservation, usage):
    if reservation is None:
        return
    path, index = reservation
    with FileLock(str(path)+'.lock', timeout=0):
        data = json.loads(path.read_text())
        fields = ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')
        clean = {k:usage[k] for k in fields if k in usage and type(usage[k]) is int and usage[k]>=0}
        known = all(k in clean for k in ('input_tokens', 'output_tokens'))
        data['calls'][index].update(usage=clean, status='reported' if known else 'usage_unknown')
        write_record(path, data)
