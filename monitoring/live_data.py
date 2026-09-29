"""Dated annual provider observations; analyst policies, never inferred loan covenants."""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from tools.financial_contract import currency_valid, finite

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    'current_assets': ('balance_sheet', 'Current Assets'),
    'current_liabilities': ('balance_sheet', 'Current Liabilities'),
    'total_debt': ('balance_sheet', 'Total Debt'),
    'cash': ('balance_sheet', 'Cash And Cash Equivalents'),
    'operating_income': ('financials', 'Operating Income'),
    'interest_expense': ('financials', 'Interest Expense'),
    'da': ('cashflow', 'Depreciation And Amortization'),
}
FORMULAS = {
    'current_ratio': ('current_assets', 'current_liabilities'),
    'operating_interest_coverage': ('operating_income', 'interest_expense'),
    'net_debt_to_operating_ebitda_proxy': ('total_debt', 'cash', 'operating_income', 'da'),
}


def load_profile(path):
    profile = json.loads(Path(path).read_text())
    if (not isinstance(profile, dict) or profile.get('schema_version') != 1
            or not isinstance(profile.get('items'), list) or not profile['items']):
        raise ValueError('watchlist requires schema_version=1 and nonempty items')
    ids = set()
    for item in profile['items']:
        if not isinstance(item, dict) or type(item.get('require_issuer_reconciliation')) is not bool:
            raise ValueError('each item must explicitly set require_issuer_reconciliation to true or false')
        for key in ('item_id', 'entity', 'ticker', 'metric', 'definition_version'):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError('missing profile field: ' + key)
        if item['item_id'] in ids:
            raise ValueError('duplicate watchlist item')
        ids.add(item['item_id'])
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9.^=-]{0,24}', item['ticker']):
            raise ValueError('invalid ticker')
        if item['metric'] not in FORMULAS:
            raise ValueError('unsupported metric')
        if item.get('threshold_basis') != 'analyst_policy':
            raise ValueError('only explicit analyst_policy thresholds supported; contractual covenants need a reviewed implementation')
        if not finite(item.get('threshold')) or item.get('direction') not in ('above', 'below'):
            raise ValueError('invalid threshold')
        if not currency_valid(item.get('currency')):
            raise ValueError('profile requires expected reporting currency')
        if type(item.get('max_age_days')) is not int or not 1 <= item['max_age_days'] <= 730:
            raise ValueError('max_age_days must be 1..730')
    return profile


def definition(item):
    # Include formula revision and all profile settings in the immutable series identity.
    return hashlib.sha256(json.dumps({'formula_revision': 1, **item}, sort_keys=True).encode()).hexdigest()


def fetch(ticker):
    """Bound network work in a separate process; never fall back to fixture data."""
    try:
        result = subprocess.run([sys.executable, '-m', 'monitoring.live_data', ticker],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        if result.returncode:
            return {'ticker': ticker, 'error': 'provider_failure'}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {'ticker': ticker, 'error': 'provider_timeout'}
    except (ValueError, OSError):
        return {'ticker': ticker, 'error': 'provider_unavailable'}


def provider_snapshot(ticker):
    import yfinance as yf
    from tools.data import _row, _date
    tk = yf.Ticker(ticker)
    frames = {name: getattr(tk, name) for name in ('financials', 'balance_sheet', 'cashflow')}
    # Latest annual income period, never mix it with another period's balance sheet.
    income = frames['financials']
    if income is None or income.empty:
        return {'ticker': ticker, 'error': 'annual_income_unavailable'}
    period = max(_date(column) for column in income.columns)
    info = tk.info or {}
    values = {key: _row(frames[frame], period, label) for key, (frame, label) in FIELDS.items()}
    return {'ticker': ticker, 'source': 'yfinance', 'period': period, 'period_type': 'annual',
            'currency': info.get('financialCurrency'), 'monetary_unit': 'base',
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'values': values,
            'field_labels': {key: {'statement': frame, 'row': label, 'period': period}
                             for key, (frame, label) in FIELDS.items()},
            'warnings': ['provider annual labels; publication date unavailable',
                         'generic accounting ratios; not contractual covenant calculations']}


def observation(item, snapshot, today):
    evidence = {'definition': deepcopy(item), 'definition_hash': definition(item),
                'provider': deepcopy(snapshot), 'data_mode': 'yfinance',
                'threshold_basis': 'analyst_policy'}
    def unavailable(reason):
        return {'value': None, 'reason': reason, 'evidence': evidence}
    if snapshot.get('error'):
        return unavailable(snapshot['error'])
    if snapshot.get('ticker') != item['ticker'] or snapshot.get('source') != 'yfinance':
        return unavailable('provider_identity_mismatch')
    if snapshot.get('currency') != item['currency'] or snapshot.get('monetary_unit') != 'base':
        return unavailable('currency_or_unit_mismatch')
    if snapshot.get('period_type') != 'annual':
        return unavailable('annual_period_required')
    try:
        period = date.fromisoformat(snapshot['period'])
    except (KeyError, ValueError, TypeError):
        return unavailable('invalid_period')
    if period > today:
        return unavailable('future_period')
    if (today - period).days > item['max_age_days']:
        return unavailable('stale_reporting_period')
    fields = snapshot.get('values', {})
    reference_path = ROOT / 'references' / 'monitoring' / f"{item['ticker']}-{period.isoformat()}.json"
    if reference_path.exists():
        reference = json.loads(reference_path.read_text())
        required_fields = FORMULAS[item['metric']]
        matched = (reference['currency'] == snapshot['currency'] and
                   all(finite(fields.get(key)) and
                       abs(fields[key] - reference['expected_fields'][key]) <= reference['absolute_tolerance']
                       for key in required_fields))
        evidence['issuer_reconciliation'] = {'status': 'matched' if matched else 'mismatch',
            'reference': reference, 'fields_checked': list(required_fields)}
        if not matched:
            return unavailable('issuer_reconciliation_mismatch')
    elif item.get('require_issuer_reconciliation'):
        return unavailable('issuer_reference_required')
    else:
        evidence['issuer_reconciliation'] = {'status': 'unreviewed'}
    required = FORMULAS[item['metric']]
    if any(not finite(fields.get(key)) for key in required):
        return unavailable('missing_or_invalid_input')
    if any(fields[key] < 0 for key in required if key != 'operating_income'):
        return unavailable('unsupported_negative_input')
    if item['metric'] == 'current_ratio':
        numerator, denominator = fields['current_assets'], fields['current_liabilities']
    elif item['metric'] == 'operating_interest_coverage':
        numerator, denominator = fields['operating_income'], fields['interest_expense']
    else:
        numerator = fields['total_debt'] - fields['cash']
        denominator = fields['operating_income'] + fields['da']
    if denominator <= 0:
        return unavailable('nonpositive_denominator')
    value = numerator / denominator
    if not finite(value):
        return unavailable('nonfinite_ratio')
    evidence.update(numerator=numerator, denominator=denominator,
                    inputs={key: fields[key] for key in required}, ratio=value)
    return {'value': value, 'data_ts': period, 'evidence': evidence}


def prepare(path, today=None):
    today = today or datetime.now(timezone.utc).date()
    profile = load_profile(path)
    snapshots = {ticker: fetch(ticker) for ticker in sorted({i['ticker'] for i in profile['items']})}
    return [{'item': item, 'observation': observation(item, snapshots[item['ticker']], today)}
            for item in profile['items']]


if __name__ == '__main__':
    try:
        print(json.dumps(provider_snapshot(sys.argv[1]), allow_nan=False))
    except Exception as exc:
        print(json.dumps({'ticker': sys.argv[1], 'error': 'provider_failure', 'error_type': type(exc).__name__}))
