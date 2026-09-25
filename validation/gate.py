"""Fail-closed evidence gate for a complete Agent 1 equity-research run.

Confidence describes evidence quality, not investment probability. A quality
warning always requires review; findings alone never block publication.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
import statistics
from types import SimpleNamespace

from tools.financial_contract import finite, financial_error, price_error
from tools.analytical import compute_ratios, run_dcf, compute_derived

_REQUIRED = ('get_financials', 'get_prices', 'compute_ratios', 'run_dcf',
             'peer_outlier_check', 'get_consensus')
from agent.state import DEPENDENCIES as _DEPENDENCIES


def _nonfinite(obj):
    if isinstance(obj, dict):
        return any(_nonfinite(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_nonfinite(v) for v in obj)
    return isinstance(obj, (int, float)) and not isinstance(obj, bool) and not finite(obj)


def _same(actual, expected):
    """Compare an expected calculation schema without trusting claimed statuses."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_same(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual == expected
    if finite(expected):
        return finite(actual) and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10)
    return actual == expected


def _date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
    except ValueError:
        return None


def assess(analysis: dict, now: date | None = None, calls: list | None = None) -> dict:
    """Malformed evidence must produce a failed gate, never an approval/crash."""
    try:
        return _assess(analysis, now, calls)
    except (TypeError, ValueError, AttributeError, KeyError, ArithmeticError):
        return aggregate_checks([{'check': 'malformed_evidence', 'status': 'fail',
                                  'detail': 'evidence contains an invalid schema or arithmetic value'}])


def _assess(analysis: dict, now: date | None = None, calls: list | None = None) -> dict:
    """Pure validation; never fetches data. Optional call log verifies dependencies."""
    checks = []
    ref = now or datetime.now(timezone.utc).date()

    def add(name, status, detail):
        checks.append({'check': name, 'status': status, 'detail': detail})

    if not isinstance(analysis, dict):
        return aggregate_checks([{'check': 'analysis', 'status': 'fail', 'detail': 'analysis must be a mapping'}])
    for name in _REQUIRED:
        result = analysis.get(name)
        if not isinstance(result, dict) or not result or result.get('error'):
            add('required_' + name, 'fail', f'{name} missing, malformed, or failed')
    for name, result in analysis.items():
        if not isinstance(result, dict) or _nonfinite(result):
            add('finite_' + name, 'fail', f'{name} contains malformed/non-finite evidence')
        elif result.get('error'):
            # Unavailable consensus is represented by available=False, not an error.
            add('tool_error_' + name, 'fail', str(result['error']))

    def result(name):
        value = analysis.get(name)
        return value if isinstance(value, dict) else {}

    fin_result, prices = result('get_financials'), result('get_prices')
    fin = fin_result.get('financials')
    if not isinstance(fin, dict):
        fin = {}
    ticker = fin_result.get('ticker')
    for name in _REQUIRED + ('get_historical_trend', 'compute_derived'):
        if name in analysis and (not ticker or result(name).get('ticker') != ticker):
            add('ticker_' + name, 'fail', 'evidence must identify the same company as the financial statements')
    try:
        ferr = financial_error(fin)
        perr = price_error(prices, fin)
    except (TypeError, ValueError, AttributeError):
        ferr, perr = 'malformed financial contract', 'malformed price contract'
    add('financial_contract', 'fail' if ferr else 'pass', ferr or 'currency, units and annual periods declared')
    add('price_contract', 'fail' if perr else 'pass', perr or 'compatible quote currency, units and share basis')
    missing = [k for k in ('revenue', 'net_income') if not finite(fin.get(k))]
    missing += [k for k in ('market_cap', 'shares_outstanding', 'current_price')
                if not finite(prices.get(k)) or prices[k] <= 0]
    add('data_completeness', 'fail' if missing else 'pass', 'missing/invalid: ' + ', '.join(missing) if missing else 'core financial and quote inputs present')

    period = _date(fin.get('period'))
    if period is None or period > ref:
        add('filing_recency', 'fail', 'statement date missing, invalid, or in the future')
    elif (ref - period).days > 548:
        add('filing_recency', 'quality_warn', 'annual statement older than 18 months (548 days)')
    else:
        add('filing_recency', 'pass', 'annual statement within 18 months')
    # Live dates are assessed, never inferred from retrieval time. Fixtures are
    # explicitly illustrative and can never earn approval as live research.
    for name in ('get_financials', 'get_prices', 'get_consensus', 'get_historical_trend'):
        item = result(name)
        if not item:
            continue
        source = item.get('source')
        if source == 'fixture':
            add('source_' + name, 'quality_warn', 'illustrative fixture; not independently verified market evidence')
        elif source != 'yfinance':
            add('source_' + name, 'fail', 'missing or unsupported data provenance')
        else:
            retrieved = _date(item.get('retrieved_at'))
            if retrieved is None or retrieved > ref or (ref - retrieved).days > 7:
                add('retrieval_' + name, 'quality_warn', 'live evidence retrieval date missing, future, or older than seven days')
        if name == 'get_prices' or (name == 'get_consensus' and item.get('available')):
            observed = _date(item.get('as_of'))
            if observed is None or observed > ref or (ref - observed).days > 7:
                add('as_of_' + name, 'quality_warn', 'observation date unknown, future, or older than seven days; retrieval is not observation')
        for warning in item.get('warnings', []) if isinstance(item.get('warnings', []), list) else ['malformed warnings']:
            add('assumption_' + name, 'quality_warn', str(warning))

    # Recompute deterministic calculations against CURRENT inputs. This detects
    # stale/mutated output even when an append-only call log was not supplied.
    state = SimpleNamespace(ticker=ticker, results=analysis)
    dcf, ratios, peer = result('run_dcf'), result('compute_ratios'), result('peer_outlier_check')
    assumptions = dcf.get('assumptions') if isinstance(dcf.get('assumptions'), dict) else {}
    sources = assumptions.get('parameter_sources', {})
    if not isinstance(sources, dict):
        sources = {}
    defaults = [k for k, v in sources.items() if v == 'model_default']
    if defaults:
        add('model_defaults', 'quality_warn', 'model defaults require analyst review: ' + ', '.join(defaults))
    if any(sources.get(k) not in ('caller_supplied', 'model_default')
           for k in ('horizon_years', 'discount_rate', 'terminal_growth', 'high_growth', 'weights')):
        add('assumption_provenance', 'fail', 'DCF must declare the source of each forecast parameter')
    if not ferr and not perr and ticker:
        for name, function, parameters in (
            ('compute_ratios', compute_ratios, {}),
            ('run_dcf', run_dcf, {k: assumptions.get(k) for k in ('horizon_years', 'discount_rate', 'terminal_growth', 'high_growth', 'weights') if sources.get(k) == 'caller_supplied'}),
        ):
            if name == 'run_dcf':
                fcff = assumptions.get('fcff_inputs', {})
                if isinstance(fcff, dict) and fcff.get('tax_basis') == 'analyst-supplied tax rate':
                    parameters['tax_rate'] = fcff.get('tax_rate')
            expected = function({'ticker': ticker, **parameters}, state)
            add('reconcile_' + name, 'fail' if expected.get('error') or not _same(result(name), expected) else 'pass',
                'output must reconcile to current inputs and declared assumptions')
            if name == 'run_dcf':
                for warning in expected.get('warnings', []):
                    add('dcf_assumption', 'quality_warn', warning)
        if 'compute_derived' in analysis:
            expected = compute_derived({'ticker': ticker}, state)
            add('reconcile_compute_derived', 'pass' if not expected.get('error') and _same(result('compute_derived'), expected) else 'fail',
                'derived comparisons must reconcile to current evidence')

    if assumptions.get('net_debt_bridge_status') != 'complete':
        add('net_debt_bridge', 'fail', 'equity-research publication requires a complete debt/cash bridge')
    if not finite(dcf.get('scenario_weighted_per_share')) or not finite(dcf.get('implied_upside')):
        add('equity_valuation', 'fail', 'no usable per-share valuation and price comparison')
    if dcf.get('applicability') == 'distressed_equity':
        add('dcf_applicability', 'fail', 'distressed residual equity; this model cannot support a share-price target')
    if finite(assumptions.get('high_growth')) and assumptions['high_growth'] > .25:
        add('growth_assumption', 'quality_warn', 'initial growth exceeds 25%; analyst justification required')
    if finite(dcf.get('implied_upside')) and abs(dcf['implied_upside']) > .5:
        add('valuation_gap', 'info_finding', 'valuation differs from price by more than 50%; explain the finding')
    concentration = dcf.get('terminal_value_concentration', {})
    if isinstance(concentration, dict) and finite(concentration.get('base')) and concentration['base'] > .85:
        add('terminal_value_concentration', 'info_finding', 'terminal value exceeds 85% of base enterprise value')

    pes = peer.get('peer_pes')
    n = len(pes) if isinstance(pes, dict) else 0
    if n < 2 or peer.get('n_peers') != n or any(not finite(v) or v <= 0 for v in (pes.values() if isinstance(pes, dict) else [])):
        add('peer_evidence', 'fail', 'need at least two finite positive peer multiples and matching coverage count')
    elif n < 5:
        add('peer_sample_size', 'quality_warn', 'fewer than five usable peers; fragile screening statistics')
    evidence = peer.get('peer_evidence')
    if isinstance(pes, dict) and n >= 2 and all(finite(v) and v > 0 for v in pes.values()):
        peer_values = []
        evidence_ok = isinstance(evidence, dict)
        for symbol, shown_pe in pes.items():
            record = evidence.get(symbol, {}) if isinstance(evidence, dict) else {}
            pf, pp = record.get('financials'), record.get('prices')
            try:
                facts = pf['financials']
                valid = (pf.get('ticker') == symbol and pp.get('ticker') == symbol
                         and not financial_error(facts) and not price_error(pp, facts)
                         and finite(facts.get('net_income')) and facts['net_income'] > 0
                         and finite(pp.get('market_cap')))
                raw_pe = pp['market_cap'] / facts['net_income'] if valid else None
                valid = valid and finite(raw_pe) and _same(record.get('pe'), raw_pe) and _same(shown_pe, round(raw_pe, 2))
            except (KeyError, TypeError, ValueError, AttributeError, ZeroDivisionError):
                valid = False
            evidence_ok = evidence_ok and valid
            if valid:
                peer_values.append(raw_pe)
                for snapshot in (pf, pp):
                    if snapshot.get('source') not in ('fixture', 'yfinance'):
                        add('peer_source', 'fail', f'{symbol}: missing source provenance')
                    elif snapshot.get('source') == 'fixture':
                        add('peer_source', 'quality_warn', f'{symbol}: illustrative fixture')
                    else:
                        retrieved = _date(snapshot.get('retrieved_at'))
                        if retrieved is None or retrieved > ref or (ref - retrieved).days > 7:
                            add('peer_retrieval', 'quality_warn', f'{symbol}: retrieval date missing, future or stale')
                observed = _date(pp.get('as_of'))
                if observed is None or observed > ref or (ref - observed).days > 7:
                    add('peer_observation', 'quality_warn', f'{symbol}: quote observation date missing, future or stale')
                fiscal = _date(facts.get('period'))
                if fiscal is None or fiscal > ref or (ref - fiscal).days > 548:
                    add('peer_period', 'quality_warn', f'{symbol}: annual statement date missing, future or stale')
                elif facts['period'] != fin.get('period'):
                    add('peer_period', 'quality_warn', f'{symbol}: fiscal period differs from target')
        if not evidence_ok:
            add('peer_lineage', 'fail', 'peer multiples require matching source company, currency, period and raw inputs')
        else:
            median = statistics.median(peer_values)
            mad = statistics.median(abs(v - median) for v in peer_values)
            mean, sd = statistics.mean(peer_values), statistics.pstdev(peer_values)
            target = prices.get('market_cap', 0) / fin['net_income'] if finite(fin.get('net_income')) and fin['net_income'] > 0 and finite(prices.get('market_cap')) else None
            if target is None:
                add('peer_target', 'fail', 'positive target earnings and market cap required for P/E comparison')
            else:
                mz = .6745 * (target - median) / mad if mad else None
                z = (target - mean) / sd if sd else None
                verdict = abs(mz) > 3.5 if mz is not None else abs(z) > 2 if z is not None else None
                expected_peer = {'target_pe': round(target, 2), 'peer_median': round(median, 2),
                                 'peer_mad': round(mad, 2), 'peer_mean': round(mean, 2), 'peer_stdev': round(sd, 2),
                                 'modified_z': round(mz, 2) if mz is not None else None,
                                 'z_score': round(z, 2) if z is not None else None, 'is_outlier': verdict}
                add('reconcile_peers', 'pass' if _same(peer, expected_peer) else 'fail', 'peer statistics reconcile to retained source evidence')
    if peer.get('is_outlier') is None or peer.get('comparison_status') == 'insufficient_dispersion':
        add('peer_dispersion', 'quality_warn', 'peer outlier verdict is indeterminate')
    if peer.get('verdict_divergence'):
        add('peer_method_agreement', 'info_finding', 'robust and mean-based peer verdicts diverge')
    for warning in peer.get('warnings', []) if isinstance(peer.get('warnings', []), list) else ['malformed warnings']:
        add('peer_assumption', 'quality_warn', str(warning))

    from tools.data import _consensus_result, _summarise_trend
    consensus, trend = result('get_consensus'), result('get_historical_trend')
    try:
        usable_consensus = bool(consensus.get('available') is True and not consensus.get('error') and
                                _consensus_result(ticker, '', consensus.get('consensus', {}))['available'])
        history = _summarise_trend(ticker, '', trend.get('revenue_by_year', {}), {})
        usable_history = bool(trend.get('available') is True and not trend.get('error') and history['available']
                              and _same(trend.get('revenue_cagr'), history['revenue_cagr'])
                              and _same(trend.get('cagr_years'), history['cagr_years']))
    except (TypeError, ValueError, AttributeError):
        usable_consensus = usable_history = False
    if usable_consensus:
        estimates = consensus.get('consensus', {})
        if consensus.get('monetary_unit') != 'base':
            add('consensus_units', 'fail', 'consensus must declare base monetary units')
        for key, currency_key in (('price_target', 'quote_currency'), ('revenue_estimate_avg', 'reporting_currency'), ('eps_estimate_avg', 'reporting_currency')):
            if estimates.get(key) and consensus.get(currency_key) != fin.get('currency'):
                add('consensus_currency', 'fail', 'estimate currency missing or incompatible with the financial evidence')
        declared_coverage = consensus.get('coverage', {})
        for metric, estimates_by_period in estimates.items():
            if metric not in ('price_target', 'revenue_estimate_avg', 'eps_estimate_avg') or not estimates_by_period:
                continue
            counts = declared_coverage.get(metric) if isinstance(declared_coverage, dict) else None
            if metric == 'price_target':
                known = finite(counts) and counts > 0 and counts == int(counts)
            else:
                known = isinstance(counts, dict) and all(finite(counts.get(period)) and counts[period] > 0 and counts[period] == int(counts[period]) for period in estimates_by_period)
            if not known:
                add('consensus_coverage_unknown', 'quality_warn', f'{metric}: analyst coverage missing or invalid')
    coverage = consensus.get('coverage', {})
    if isinstance(coverage, dict):
        for metric, counts in coverage.items():
            estimates = consensus.get('consensus', {}).get(metric, {}) if isinstance(consensus.get('consensus'), dict) else {}
            invalid_coverage = (metric == 'price_target' and estimates and finite(counts) and counts <= 0)
            if isinstance(counts, dict) and isinstance(estimates, dict):
                invalid_coverage = any(period in estimates and finite(count) and count <= 0 for period, count in counts.items())
            if invalid_coverage:
                usable_consensus = False
                add('consensus_coverage', 'fail', 'published estimate has explicitly zero/negative analyst coverage')
    add('comparison_basis', 'pass' if usable_consensus or usable_history else 'fail',
        'usable analyst estimates' if usable_consensus else 'reconciled annual history' if usable_history else 'no usable consensus or comparable historical growth')

    if calls is not None:
        latest = {}
        for index, call in enumerate(calls):
            if isinstance(call, dict):
                latest[call.get('tool')] = (index, call)
        for name in _REQUIRED + ('get_historical_trend', 'compute_derived'):
            if name not in analysis:
                continue
            entry = latest.get(name)
            if not entry or entry[1].get('status') != 'success' or not _same(result(name), entry[1].get('output')):
                add('call_evidence_' + name, 'fail', 'latest result has no matching successful call record')
        for name, dependencies in _DEPENDENCIES.items():
            if name not in analysis:
                continue
            index = latest.get(name, (-1, {}))[0]
            if any(latest.get(dep, (-1, {}))[0] > index for dep in dependencies):
                add('stale_' + name, 'fail', 'upstream inputs were refreshed after this calculation; recompute before publication')
    return aggregate_checks(checks)


def aggregate_checks(checks: list[dict]) -> dict:
    """Warnings require review, independent of the descriptive quality score."""
    checks = list(checks)
    if not checks:
        checks.append({'check': 'empty_validation', 'status': 'fail', 'detail': 'no evidence assessed'})
    counts = {status: sum(c.get('status') == status for c in checks)
              for status in ('pass', 'info_finding', 'quality_warn', 'fail')}
    invalid = any(c.get('status') not in counts for c in checks)
    if invalid:
        checks.append({'check': 'invalid_check', 'status': 'fail', 'detail': 'unknown check status'})
        counts['fail'] += 1
    review = counts['fail'] > 0 or counts['quality_warn'] > 0
    return {'verdict': 'flag_for_review' if review else 'pass',
            'confidence': 'low' if counts['fail'] else 'medium' if review else 'high',
            'score': round(max(0., 1. - .15 * counts['quality_warn'] - counts['fail']), 2),
            **{'n_' + k: v for k, v in counts.items()}, 'checks': checks,
            'thresholds': {'quality_warn_weight': .15, 'note': 'any failure or quality warning requires review; findings do not affect score'},
            'assessed_by': 'validation.gate (deterministic evidence quality, not investment probability)'}
