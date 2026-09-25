"""Metric-specific numeric evidence, rendered by Python rather than copied by LLM.

The model places [[claim:metric_id]] on its OWN LINE. Each resolves to a complete
labelled sentence from a whitelisted current result. Free-text numeric claims
are rejected; numeric equality elsewhere in the run is never sufficient proof.
This validates numerical evidence, not the truth of qualitative interpretation.
"""
from __future__ import annotations

import re
from tools.financial_contract import finite

_MARKER = re.compile(r'\[\[claim:([a-z][a-z0-9_]*)\]\]')
_NUMBER = re.compile(r'[+−-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)', re.UNICODE)
_NUMBER_WORD = re.compile(r'\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|'
                          r'thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|'
                          r'thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|'
                          r'billion|trillion|half|quarter|double|triple|twice)\b', re.I)

# ID, tool, path, label, unit. No arbitrary nested numbers, call durations or
# unrelated company values can enter this catalogue.
_SPECS = [
    ('revenue', 'get_financials', 'financials.revenue', 'annual revenue', 'money'),
    ('net_income', 'get_financials', 'financials.net_income', 'annual net income', 'money'),
    ('ebit', 'get_financials', 'financials.ebit', 'annual EBIT', 'money'),
    ('current_price', 'get_prices', 'current_price', 'current share price', 'money_per_share'),
    ('market_cap', 'get_prices', 'market_cap', 'market capitalization', 'money'),
    ('shares', 'get_prices', 'shares_outstanding', 'shares outstanding', 'shares'),
    ('gross_margin', 'compute_ratios', 'ratios.gross_margin', 'gross margin', 'percent'),
    ('operating_margin', 'compute_ratios', 'ratios.operating_margin', 'operating margin', 'percent'),
    ('net_margin', 'compute_ratios', 'ratios.net_margin', 'net margin', 'percent'),
    ('revenue_growth', 'compute_ratios', 'ratios.revenue_growth_yoy', 'annual revenue growth', 'percent'),
    ('pe', 'compute_ratios', 'ratios.pe', 'annual P/E', 'multiple'),
    ('ev_ebit', 'compute_ratios', 'ratios.ev_ebit', 'EV/EBIT', 'multiple'),
    ('dcf_value', 'run_dcf', 'scenario_weighted_per_share', 'scenario-weighted equity value per share', 'money_per_share'),
    ('dcf_gap', 'run_dcf', 'implied_upside', 'signed valuation gap versus share price', 'percent'),
    ('fcff', 'run_dcf', 'assumptions.fcf_base', 'FCFF base', 'money'),
    ('net_debt', 'run_dcf', 'assumptions.net_debt', 'net debt', 'money'),
    ('discount_rate', 'run_dcf', 'assumptions.discount_rate', 'assumed discount rate', 'percent'),
    ('initial_growth', 'run_dcf', 'assumptions.high_growth', 'assumed initial FCFF growth', 'percent'),
    ('terminal_growth', 'run_dcf', 'assumptions.terminal_growth', 'assumed terminal growth', 'percent'),
    ('horizon', 'run_dcf', 'assumptions.horizon_years', 'assumed forecast horizon', 'years'),
    ('tax_rate', 'run_dcf', 'assumptions.fcff_inputs.tax_rate', 'assumed tax rate', 'percent'),
    ('historical_growth', 'get_historical_trend', 'revenue_cagr', 'historical annual revenue CAGR', 'percent'),
    ('peer_median', 'peer_outlier_check', 'peer_median', 'peer median annual P/E', 'multiple'),
    ('peer_count', 'peer_outlier_check', 'n_peers', 'usable peer count', 'count'),
    ('consensus_growth', 'compute_derived', 'metrics.consensus_implied_revenue_growth.value', 'consensus-implied next-year revenue growth', 'percent'),
    ('growth_vs_history', 'compute_derived', 'metrics.growth_vs_history.percentage_points', 'consensus growth minus historical CAGR', 'percentage_points'),
]
for _scenario in ('bear', 'base', 'bull'):
    _SPECS += [
        (f'{_scenario}_value', 'run_dcf', f'value_per_share.{_scenario}', f'{_scenario} equity value per share', 'money_per_share'),
        (f'{_scenario}_ev', 'run_dcf', f'enterprise_value.{_scenario}', f'{_scenario} enterprise value', 'money'),
    ]
for _period, _suffix in (('0y', 'current_year'), ('+1y', 'next_year')):
    _SPECS += [(f'consensus_revenue_{_suffix}', 'get_consensus', f'consensus.revenue_estimate_avg.{_period}',
                f'consensus revenue for provider period {_period}', 'money')]
_SPECS += [('consensus_target', 'get_consensus', 'consensus.price_target.mean', 'mean analyst price target', 'money_per_share')]


def _get(obj, path):
    for part in path.split('.'):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def build_evidence_catalog(results: dict) -> dict:
    """Named current-result evidence only; each item retains its exact source path."""
    fin = _get(results, 'get_financials.financials') or {}
    ticker = _get(results, 'get_financials.ticker')
    catalog = {}
    if not isinstance(fin, dict) or not isinstance(ticker, str) or not ticker:
        return catalog
    for identity, tool, path, label, unit in _SPECS:
        payload = results.get(tool)
        if not isinstance(payload, dict) or payload.get('error') or payload.get('ticker') != ticker:
            continue
        if tool in ('get_consensus', 'get_historical_trend') and payload.get('available') is not True:
            continue
        value = _get(payload, path)
        if not finite(value):
            continue
        currency = payload.get('currency') or fin.get('currency')
        if tool == 'get_consensus':
            currency = payload.get('quote_currency' if unit == 'money_per_share' else 'reporting_currency')
        if unit.startswith('money') and not currency:
            continue
        period = payload.get('period') or fin.get('period')
        if tool == 'get_prices':
            period = payload.get('as_of') or 'observation date unknown'
        elif tool == 'get_consensus':
            period = payload.get('as_of') or 'estimate publication date unknown'
        elif tool == 'get_historical_trend':
            years = payload.get('cagr_years', [])
            period = '–'.join((years[0], years[-1])) if years else 'historical interval unknown'
        elif tool == 'compute_derived':
            period = 'current evidence comparison; see source inputs'
        elif tool == 'peer_outlier_check':
            period = 'mixed peer fiscal periods; see peer evidence'
        if not period:
            continue
        if unit == 'percent':
            displayed = f'{value * 100:+.2f}%'
        elif unit == 'percentage_points':
            displayed = f'{value:+.2f} percentage points'
        elif unit == 'multiple':
            displayed = f'{value:.2f}x'
        elif unit.startswith('money'):
            displayed = f'{currency} {value:,.2f}' + (' per share' if unit == 'money_per_share' else '')
        else:
            displayed = f'{value:,.0f} {unit}'
        sentence = f'{ticker} — {label}: {displayed} (period: {period}; source: {tool}/{path}).'
        catalog[identity] = {'id': identity, 'ticker': ticker, 'metric': label, 'value': value,
                             'unit': unit, 'currency': currency if unit.startswith('money') else None,
                             'period': period, 'tool': tool, 'path': path, 'rendered': sentence}
    return catalog


def ground_note(note: str, results: dict) -> dict:
    """Render isolated claim markers and reject all unbound numerical content.

    Original text is retained for audit; a failure is for review, never approval.
    Only current results are accepted. Historical call comparisons require a
    future explicit versioned-evidence interface, not a pooled registry.
    """
    catalog = build_evidence_catalog(results)
    unmatched, evidence, rendered = [], [], []
    ticker = _get(results, 'get_financials.ticker')
    for line in (note or '').splitlines():
        marker = _MARKER.fullmatch(line.strip())
        if marker:
            item = catalog.get(marker.group(1))
            if item:
                evidence.append(item)
                rendered.append(item['rendered'])
            else:
                unmatched.append({'figure': line, 'reason': 'unknown or unavailable current metric'})
                rendered.append(line)
            continue
        # Exact subject ticker is an identifier, not a financial quantity (e.g. 7203.T).
        text = re.sub(r'(?<!\w)' + re.escape(ticker) + r'(?!\w)', '', line) if ticker else line
        if '[[claim:' in text:
            unmatched.append({'figure': line, 'reason': 'claim markers must occupy a standalone line; labels cannot be supplied by the model'})
        for match in list(_NUMBER.finditer(text)) + list(_NUMBER_WORD.finditer(text)):
            unmatched.append({'figure': match.group(), 'reason': 'free-text numeric content has no metric-specific evidence reference'})
        rendered.append(line)
    if not evidence:
        unmatched.append({'figure': '', 'reason': 'no supported numerical evidence cited'})
    return {'passed': not unmatched, 'figures_checked': len(evidence) + len(unmatched),
            'claims_checked': len(evidence), 'unmatched': unmatched, 'evidence': evidence,
            'rendered_note': '\n'.join(rendered), 'original_note': note,
            'note': 'numerical claims rendered from named current evidence; qualitative interpretation is not mechanically verified',
            'checked_by': 'note_grounding (metric, ticker, period, unit and exact source path)'}
