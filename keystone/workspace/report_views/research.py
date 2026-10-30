"""Agent 1 saved evidence to native report data; no free-form draft publication."""
from decimal import Decimal

from .common import metric_cell, text_cell
from .values import currency, get, history_ok, token


def build(b):
    source = b.source
    financial = get(source, '/analysis/get_financials/financials', {}) or {}
    period = financial.get('period') or b.run.period
    b.currency = currency(financial.get('currency'))
    b.view['identity']['period_end'] = financial.get('period')
    performance = []
    for key, label in [('revenue', 'Annual revenue'), ('operating_income', 'Operating income'),
                       ('net_income', 'Net income'), ('free_cash_flow', 'Reported free cash flow')]:
        performance.append(b.metric(key.replace('_', '-'), label,
            '/analysis/get_financials/financials/' + key, 'currency', period=period))
    for key, label in [('operating_margin', 'Operating margin'), ('net_margin', 'Net margin'),
                       ('revenue_growth_yoy', 'Revenue growth versus prior year')]:
        performance.append(b.metric(key.replace('_', '-'), label,
            '/analysis/compute_ratios/ratios/' + key, 'fraction', period=period))
    years = get(source, '/analysis/get_historical_trend/cagr_years', []) or []
    growth_period = f'{years[0]}–{years[-1]}' if len(years) >= 2 else 'Historical period unavailable'
    performance.append(b.metric('historical-growth', 'Historical revenue CAGR',
        '/analysis/get_historical_trend/revenue_cagr', 'fraction', period=growth_period))
    history_charts = []
    for key, title, unit in [('revenue_by_year', 'Annual revenue history', 'currency'),
                              ('net_margin_by_year', 'Annual net margin history', 'fraction')]:
        mapping = get(source, '/analysis/get_historical_trend/' + key, {}) or {}
        points = [b.point('year-' + str(i), year, year,
                         '/analysis/get_historical_trend/' + key + '/' + token(year))
                  for i, year in enumerate(sorted(mapping))]
        ident = key.replace('_', '-')
        history_charts.append(b.chart(ident, title, 'Saved annual observations; no analyst forecast is added.',
            'bar' if unit == 'currency' else 'line', unit,
            [dict(id=ident + '-series', label=title, points=points)], x_label='Financial year'))
    b.section('performance', 'Business performance', 'Read the saved annual evidence and its historical context.',
              metrics=performance, findings=[b.observation(m) for m in performance], charts=history_charts)

    dcf = get(source, '/analysis/run_dcf', {}) or {}
    eligible = dcf.get('applicability') == 'positive_fcff_model' and dcf.get('value_basis') == 'equity_value'
    restriction = None if eligible else 'equity_valuation_ineligible_or_unavailable'
    valuation = [b.metric('weighted-valuation', 'Scenario-weighted equity value per share',
                         '/analysis/run_dcf/scenario_weighted_per_share', 'currency_per_share',
                         period=period, visibility='diagnostic', restriction=restriction)]
    scenarios = get(source, '/analysis/run_dcf/value_per_share', {}) or {}
    points = [b.point('scenario-' + key, key, key.title(), '/analysis/run_dcf/value_per_share/' + key)
              for key in ('bear', 'base', 'bull') if key in scenarios]
    scenario_chart = b.chart('valuation-scenarios', 'Saved valuation scenarios',
        'Conditional per-share values. Scenario weights are assumptions, not measured probabilities.',
        'scenario_range', 'currency_per_share',
        [dict(id='valuation-series', label='Equity value per share', points=points)],
        x_label='Scenario', visibility='diagnostic', restriction=restriction)
    assumption_rows = []
    for key, label, unit in [('discount_rate', 'Discount rate assumption', 'fraction'),
                             ('high_growth', 'Initial growth assumption', 'fraction'),
                             ('terminal_growth', 'Terminal growth assumption', 'fraction'),
                             ('horizon_years', 'Projection horizon', 'count')]:
        ident = b.metric('assumption-' + key.replace('_', '-'), label,
                         '/analysis/run_dcf/assumptions/' + key, unit, period='Saved model assumption', visibility='supporting')
        valuation.append(ident)
        assumption_rows.append(dict(id='row-' + key, cells=[text_cell('assumption', label),
            metric_cell('value', ident), text_cell('basis', get(source, '/analysis/run_dcf/assumptions/parameter_sources/' + key))],
            evidence_refs=[b.maybe_evidence('/analysis/run_dcf/assumptions/' + key)]))
    assumptions = b.table('valuation-assumptions', 'Valuation assumptions',
        [('assumption', 'Parameter'), ('value', 'Saved value'), ('basis', 'Parameter source')], assumption_rows)
    b.section('valuation', 'Valuation and assumptions', 'Inspect the value basis, model assumptions and restrictions.',
              metrics=valuation, charts=[scenario_chart], tables=[assumptions])

    peers = get(source, '/analysis/peer_outlier_check/peer_pes', {}) or {}
    peer_points = [b.point('peer-' + str(i), name, name, '/analysis/peer_outlier_check/peer_pes/' + token(name))
                   for i, name in enumerate(peers)]
    if get(source, '/analysis/peer_outlier_check/target_pe') is not None:
        peer_points.append(b.point('target-peer', str(get(source, '/meta/ticker')), 'Target company',
                                   '/analysis/peer_outlier_check/target_pe'))
    bad_multiple = any(p['y'] is None or Decimal(p['y']) <= 0 for p in peer_points)
    peer_chart = b.chart('peer-multiples', 'Saved peer multiples',
        'Screening diagnostics; inspect peer exclusions, periods and economic comparability.',
        'dot_plot', 'multiple', [dict(id='peer-series', label='Saved P/E', points=peer_points)],
        visibility='diagnostic', x_label='Company', restriction='ineligible_peer_multiple' if bad_multiple else None)
    b.section('peers', 'Peer comparison', 'Compare retained screening measures, not an economic-comparability approval.',
              charts=[peer_chart])

    market = _market(b)
    b.section('market', 'Saved market context', 'Inspect the retained observations and Python-prepared chart series.', charts=market)
    consensus = _consensus(b)
    b.section('consensus', 'Market consensus', 'External estimates are distinct from Keystone valuation and historical growth.',
        metrics=consensus, availability=b.view['analyst_content']['market_consensus']['availability'],
        reasons=b.view['analyst_content']['market_consensus']['reason_codes'])
    b.view['analyst_content']['external_research'] = b.analyst_area('unavailable', ['broker_reports_not_collected'])
    b.section('external-research', 'External research', 'Named-broker reports and ratings were not collected.',
              availability='unavailable', reasons=['broker_reports_not_collected'])

    def category(code):
        if code.startswith(('peer', 'reconcile_peers')):
            return 'peer_comparability'
        if code.startswith(('model_defaults', 'growth_assumption', 'dcf', 'fcff', 'reconcile_run_dcf')):
            return 'valuation_assumptions'
        if code.startswith(('as_of', 'filing_recency', 'history_')):
            return 'observation_dates'
        if code.startswith(('note', 'qualitative', 'narrative')):
            return 'narrative_support'
        return 'delivery' if code.startswith('artifact_') else 'data_basis'

    sections = {'peer_comparability': ['peers'], 'valuation_assumptions': ['valuation'],
                'observation_dates': ['market', 'consensus'], 'narrative_support': ['performance', 'valuation']}
    b.checks('/validation/checks', category, lambda c: sections.get(c, ['performance', 'valuation', 'peers', 'market', 'consensus']))
    b.view['glossary'] = [dict(term='Operating margin', definition='Operating income divided by revenue for the stated period.'),
        dict(term='Scenario-weighted valuation', definition='A conditional model result using assigned weights, not an external target or measured outcome probability.')]


def _market(b):
    source = b.source
    quote_ccy = currency(get(source, '/analysis/get_prices/currency'))
    history = get(source, '/chart_data/price_history/history')
    clean = history_ok(history) and not get(source, '/chart_data/price_history/excluded_observations', [])
    price_series = []
    if clean:
        price_series.append(dict(id='close-series', label='Saved close', points=[
            b.point('close-' + str(i), row['date'], row['date'], f'/chart_data/price_history/history/{i}/close')
            for i, row in enumerate(history)]))
    for key, label in [('ma50', '50-observation moving average'), ('ma200', '200-observation moving average')]:
        entry = b.series['derivations'][key]
        if entry['data']:
            price_series.append(_derived_series(b, key, label))
    result = [b.chart('prices', 'Price and moving averages', 'Saved close prices; null warmup windows remain gaps.',
        'line', 'currency', price_series, x_kind='date', x_label='Observation date', currency_code=quote_ccy,
        restriction=None if clean else 'history_missing_invalid_or_excluded')]
    rebase = [(_derived_series(b, key, label)) for key, label in
              [('rebased_stock', 'Company (rebased)'), ('rebased_index', 'Benchmark (rebased)')]
              if b.series['derivations'][key]['availability'] == 'available']
    result.append(b.chart('benchmark', 'Price versus benchmark', 'Common dates rebased to 100 at the first shared observation.',
        'line', 'index', rebase, x_kind='date', x_label='Common observation date'))
    for key, title in [('volatility30', '30-observation annualised volatility'), ('drawdown', 'Drawdown from prior peak')]:
        entry = b.series['derivations'][key]
        series = [_derived_series(b, key, title)] if entry['data'] else []
        result.append(b.chart(key, title, 'Retained Python series using the original chart definition.',
            'line', 'fraction', series, x_kind='date', x_label='Observation date'))
    return result


def _derived_series(b, key, label):
    return dict(id=key + '-series', label=label, points=[
        b.point(key + '-' + str(i), row['date'], row['date'], f'/derivations/{key}/data/{i}/value', derived=True)
        for i, row in enumerate(b.series['derivations'][key]['data'])])


def _consensus(b):
    source = b.source
    record = get(source, '/analysis/get_consensus', {}) or {}
    estimates = record.get('consensus') or {}
    items = []
    if record.get('available') is True:
        for family, unit in [('price_target', 'currency_per_share'), ('revenue_estimate_avg', 'currency'),
                             ('eps_estimate_avg', 'currency_per_share')]:
            ccy = record.get('quote_currency' if family == 'price_target' else 'reporting_currency')
            for period in (estimates.get(family) or {}):
                if period not in ({'low', 'high', 'mean', 'median'} if family == 'price_target' else {'0q', '+1q', '0y', '+1y'}):
                    continue
                restriction = None if currency(ccy) is not None and ccy == b.currency else 'estimate_currency_incompatible'
                ident = 'consensus-' + family.replace('_', '-') + '-' + period.replace('+', 'next-')
                items.append(b.metric(ident, family.replace('_', ' ').title() + ' · ' + period,
                    '/analysis/get_consensus/consensus/' + family + '/' + token(period), unit,
                    currency_code=ccy, period='Provider estimate period: ' + period if family != 'price_target' else 'Estimate horizon not established',
                    visibility='supporting', restriction=restriction))
    if not items:
        items.append(b.metric('consensus-target', 'External mean analyst target',
            '/analysis/get_consensus/consensus/price_target/mean', 'currency_per_share',
            currency_code=record.get('quote_currency'), period='Estimate horizon unavailable'))
    available = any(m['availability'] == 'available' and m['id'] in items for m in b.view['metrics'])
    evidence = [b.maybe_evidence('/analysis/get_consensus', 'Saved external-estimate availability')]
    b.view['analyst_content']['market_consensus'] = b.analyst_area(
        'available' if available else 'unavailable', [] if available else ['no_usable_analyst_estimates'], items, evidence)
    # analyst_area uses a default for an omitted reason list; available estimates have no missing reason.
    if available:
        b.view['analyst_content']['market_consensus']['reason_codes'] = []
    return items
