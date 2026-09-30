"""Run bounded historical earnings analysis, preserving review and failure evidence."""
import argparse
import os
from pathlib import Path
import sys

from agent3.execution import Attempt, ROOT, read_record, run_bounded
from agent3.orchestrator import render_brief
from agent3.peers import _pin
from agent.models import AnthropicModel
from agent3.study_plan import validate_plan
from tools.event_contracts import ticker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ticker', nargs='?')
    parser.add_argument('event_type', nargs='?')
    parser.add_argument('--peers', nargs='*', default=None)
    parser.add_argument('--live-propose', action='store_true', help='request an audited live model proposal (default without --peers)')
    parser.add_argument('--study-plan', help='sourced human review plan JSON')
    parser.add_argument('--retry-from', help='saved run.json; reuse request and accepted peers, fetch fresh provider data')
    parser.add_argument('--db', help='outcome database (default: repository state/catalyst.duckdb)')
    parser.add_argument('--output-dir', default=str(ROOT / 'output' / 'agent3-runs'))
    parser.add_argument('--timeout', type=int, default=300, help='whole worker deadline in seconds, 30–3600 (default 300)')
    args = parser.parse_args(argv)
    # Predictable .env location; exported environment always takes precedence.
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
    attempt = None
    try:
        if not 30 <= args.timeout <= 3600:
            raise ValueError('timeout must be between 30 and 3600 seconds')
        retry_peer_set = None
        if args.retry_from:
            if any((args.ticker, args.event_type, args.peers is not None, args.live_propose, args.study_plan)):
                raise ValueError('retry cannot change ticker, event type, peers or study plan; start a new run instead')
            old = read_record(args.retry_from)
            if not isinstance(old, dict) or type(old.get('schema_version')) is not int or old['schema_version'] != 1:
                raise ValueError('unsupported retry record')
            if not isinstance(old.get('request'), dict):
                raise ValueError('retry record requires a request object')
            request = dict(old['request'])
            retry_peer_set = old.get('pinned_peer_set') or old.get('retry_peer_set')
            if retry_peer_set:
                if not isinstance(retry_peer_set, dict):
                    raise ValueError('retry peer set must be an object')
                if retry_peer_set.get('ticker') != request['ticker']:
                    raise ValueError('retry peer target differs from request')
                pinned = _pin(request['ticker'], retry_peer_set, 'retry')
                request.update(peers=pinned['peers'], live_propose=False)
            if args.db:
                request['db'] = str(Path(args.db).resolve())
        else:
            if not args.ticker or not args.event_type:
                raise ValueError('ticker and event_type are required without --retry-from')
            if args.peers is not None and args.live_propose:
                raise ValueError('--peers and --live-propose are mutually exclusive')
            live_env = os.environ.get('AGENT3_LIVE_PROPOSE')
            if live_env not in (None, '0', '1'):
                raise ValueError('AGENT3_LIVE_PROPOSE must be 0 or 1')
            request = {'ticker': ticker(args.ticker), 'event_type': args.event_type,
                       'peers': args.peers, 'live_propose': args.peers is None and (args.live_propose or live_env != '0'),
                       'study_plan': read_record(args.study_plan) if args.study_plan else None,
                       'db': str(Path(args.db).resolve()) if args.db else str(ROOT / 'state' / 'catalyst.duckdb'),
                       'transport': os.environ.get('AGENT_STATS_VIA_MCP', '0'), 'model': AnthropicModel().model}
        request.setdefault('model', AnthropicModel().model)
        attempt = Attempt.create(args.output_dir, request,
                                 str(Path(args.retry_from).resolve()) if args.retry_from else None)
        if retry_peer_set:
            attempt.checkpoint('configuration', {'retry_peer_set': retry_peer_set, 'pinned_peer_set': retry_peer_set})
        # Validate imported retry data just as strictly as fresh CLI configuration.
        request['ticker'] = ticker(request['ticker'])
        if not isinstance(request['event_type'], str) or not request['event_type'].strip() or len(request['event_type']) > 200:
            raise ValueError('event_type must be nonempty text of at most 200 characters')
        if not isinstance(request['model'], str) or not request['model'].strip():
            raise ValueError('model ID must be nonempty text')
        if request['transport'] not in ('0', '1') or type(request['live_propose']) is not bool:
            raise ValueError('invalid transport or proposal mode')
        if not isinstance(request['db'], str) or not request['db']:
            raise ValueError('database path must be nonempty text')
        if request['peers'] is not None:
            pinned = _pin(request['ticker'], {'peers': request['peers']}, 'override')
            request['peers'] = pinned['peers']
            validate_plan(request['study_plan'], [request['ticker']] + request['peers'], request['event_type'])
        if request['peers'] is None and not request['live_propose']:
            raise ValueError('explicit peers or live proposal required; fixture fallback is disabled')
        attempt.save()
        code = run_bounded(attempt, args.timeout)
        record = attempt.record
        if record['status'] in ('held', 'completed'):
            print(render_brief(record['result']))
        else:
            print(f"{record['status'].upper()}: {record.get('reason', 'unavailable')} (stage: {record['stage']})")
            for report in record.get('per_peer_report', []):
                print(f"  {report.get('ticker')}: {report.get('reason', report.get('error', 'excluded'))}")
        print(f'Run record: {attempt.path}')
        if record['status'] in ('failed', 'unavailable'):
            print('Retry with --retry-from <run.json>; accepted peers are reused, market data is fetched again.')
        return code
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if attempt is not None:
            try:
                attempt.finish('refused', 'invalid_configuration', type(exc).__name__)
                print(f'Run record: {attempt.path}')
            except OSError:
                pass
        print('REFUSED: invalid configuration or unreadable input/output. Check arguments, JSON schema and file permissions.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
