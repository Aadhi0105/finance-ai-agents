"""Opt-in bounded provider checks; no LLM calls, credentials, or report approval.

Run from the repository: python -m scripts.check_agent1_live --ticker AAPL --output PATH
Each adapter runs in a subprocess with a timeout. Store normalized evidence and
explicit failures, not provider stderr (which can contain request details).
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

OPERATIONS = ('get_financials', 'get_prices', 'get_consensus', 'get_historical_trend', 'get_price_history')


def probe(ticker, operation, timeout):
    try:
        result = subprocess.run([sys.executable, '-m', 'scripts.check_agent1_live',
            '--ticker', ticker, '--worker', operation], capture_output=True, text=True,
            timeout=timeout, cwd=Path(__file__).resolve().parents[1])
        if result.returncode:
            return {'status':'unavailable', 'error_type':'worker_failure', 'exit_code':result.returncode}
        payload = json.loads(result.stdout)
        json.dumps(payload, allow_nan=False)
        return payload
    except subprocess.TimeoutExpired:
        return {'status':'unavailable','error_type':'timeout'}
    except (ValueError, TypeError):
        return {'status':'unavailable','error_type':'invalid_worker_output'}


def worker(ticker, operation):
    from tools import data
    from tools.financial_contract import financial_error, finite
    import contextlib
    import io
    os.environ['AGENT_DATA_SOURCE'] = 'yfinance'
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            fn = getattr(data, operation)
            evidence = fn(ticker, period='1mo') if operation == 'get_price_history' else fn({'ticker':ticker})
            if operation == 'get_price_history' and not evidence.get('error'):
                from tools.price_history import prepare_history
                evidence = prepare_history(evidence)
        json.dumps(evidence, allow_nan=False)
        issues = []
        if evidence.get('error'):
            issues.append('provider returned an error')
        elif operation == 'get_financials':
            error = financial_error(evidence.get('financials') or {})
            if error:
                issues.append(error)
        elif operation == 'get_prices':
            for field in ('current_price', 'market_cap', 'shares_outstanding'):
                value = evidence.get(field)
                if not finite(value) or value <= 0:
                    issues.append(field + ' missing or invalid')
            if evidence.get('as_of') is None:
                issues.append('quote observation time unavailable')
        elif operation in ('get_consensus','get_historical_trend') and not evidence.get('available'):
            issues.append('usable comparison evidence unavailable')
        elif operation == 'get_price_history':
            from composer import _valid_history
            _valid_history(evidence.get('history', []))
            issues.extend(evidence.get('warnings', []))
        return {'status':'review' if issues else 'observed', 'issues':issues, 'evidence':evidence}
    except Exception as exc:
        return {'status':'unavailable','error_type':type(exc).__name__}


def main(argv=None):
    import re
    from tools.registry import TICKER_PATTERN
    from composer import save_record, _git_provenance
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticker', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--worker', choices=OPERATIONS, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not re.fullmatch(TICKER_PATTERN, args.ticker) or not 1 <= args.timeout <= 120:
        parser.error('valid ticker and timeout of 1–120 seconds required')
    if args.worker:
        print(json.dumps(worker(args.ticker.upper(), args.worker), allow_nan=False))
        return 0
    if args.output is None:
        parser.error('--output is required')
    record = {'kind':'agent1_provider_probe', 'ticker':args.ticker.upper(),
              'checked_at':datetime.now(timezone.utc).isoformat(), **_git_provenance(),
              'scope':'provider observations only; not financial approval or model verification',
              'operations':{}}
    save_record(args.output, record)
    for operation in OPERATIONS:
        record['operations'][operation] = probe(record['ticker'], operation, args.timeout)
        save_record(args.output, record)
        print(operation + ': ' + record['operations'][operation]['status'], flush=True)
    return 1 if any(r['status']=='unavailable' for r in record['operations'].values()) else 0


if __name__ == '__main__':
    sys.exit(main())
