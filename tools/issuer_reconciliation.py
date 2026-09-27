"""Reviewed issuer profiles; never generalize one issuer/period to another."""
import json
import math
from pathlib import Path
from tools.financial_contract import finite

REFERENCE_DIR = Path(__file__).resolve().parents[1] / 'references' / 'issuer'


def apply_reviewed_profile(result):
    fin = result['financials']
    # Resolve from trusted local profiles, not a user-controlled file path.
    reference = None
    for path in REFERENCE_DIR.glob('*.json'):
        item = json.loads(path.read_text())
        if (item.get('ticker'), item.get('period'), item.get('currency')) == (
                result.get('ticker'), fin.get('period'), fin.get('currency')):
            reference = item
            break
    if reference is None:
        return result
    checks = []
    for key, expected in reference['expected_provider_fields'].items():
        actual = fin.get(key)
        checks.append({'field':key, 'issuer_value':expected, 'provider_value':actual,
                       'matched':finite(actual) and math.isclose(actual, expected, rel_tol=0, abs_tol=100000)})
    checks.append({'field':'valuation_ebit','issuer_value':reference['expected_provider_fields']['operating_income'],
                   'provider_value':fin.get('ebit'),
                   'matched':finite(fin.get('ebit')) and math.isclose(fin['ebit'],reference['expected_provider_fields']['operating_income'],rel_tol=0,abs_tol=100000)})
    raw = result['normalization']['working_capital']['raw']
    total = sum(reference['cash_flow_components'].values())
    checks.append({'field':'raw_working_capital_cash_contribution','issuer_value':total,
                   'provider_value':raw,'matched':finite(raw) and math.isclose(raw,total,rel_tol=0,abs_tol=100000)})
    matched = all(check['matched'] for check in checks)
    result['issuer_reconciliation'] = {'status':'matched' if matched else 'mismatch',
        'scope':'listed annual fields only; not current shares, market price, forecast or qualitative claims',
        'period':reference['period'],'source_url':reference['source_url'],
        'source_sha256':reference['source_sha256'],'pages':reference['statement_pages'],
        'checks':checks,'limitations':reference['limitations']}
    if not matched:
        result['error'] = 'provider data differs from reviewed issuer fields; reconciliation required'
        return result
    tax_contribution = reference['cash_flow_components']['current_tax_assets_and_liabilities']
    normalized = -(raw - tax_contribution)
    fin['change_in_working_capital'] = normalized
    fin['working_capital_basis'] = 'issuer-reconciled operating-assets/liabilities cash contribution excluding current tax; still a broad operating proxy'
    result['normalization']['working_capital'].update(
        operation='subtract issuer current-tax cash contribution, then negate',
        current_tax_cash_contribution=tax_contribution, normalized=normalized,
        issuer_source=reference['source_url'],issuer_page=reference['statement_pages']['cash_flow'])
    result.setdefault('warnings', []).extend(reference['limitations'])
    return result
