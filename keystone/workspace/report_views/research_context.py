"""Agent 1 adapter 1.1: map retained detail without recalculating the analysis.

The 1.0 adapter remains byte-compatible. New presentation revisions add saved
bridge amounts, peer metadata and estimate coverage using the existing schema.
"""
from .common import metric_cell, text_cell
from .values import currency, decimal_text, get, token


def extend(b):
    _valuation(b)
    _peers(b)
    _market(b)
    _consensus(b)
    b.view['glossary'] += [
        dict(term='FCFF', definition='Unlevered model cash flow before financing. It is distinct from the separately reported free-cash-flow measure.'),
        dict(term='Enterprise to equity', definition='The saved model subtracts net debt from enterprise value. Negative net debt represents net cash.'),
        dict(term='P/E screening', definition='A retained price-to-earnings multiple is a comparison input. Fiscal periods and economic comparability still require review.'),
    ]


def _section(b, ident):
    return next(s for s in b.view['sections'] if s['id'] == ident)


def _metric(b, section, *args, **kwargs):
    ident = b.metric(*args, **kwargs)
    _section(b, section)['metric_refs'].append(ident)
    return ident


def _table(b, section, *args):
    ident = b.table(*args)
    _section(b, section)['table_refs'].append(ident)
    return ident


def _text_rows(b, fields):
    return [dict(id='context-' + str(i), cells=[text_cell('field', label),
        text_cell('value', get(b.source, pointer, 'Not retained'))],
        evidence_refs=[b.maybe_evidence(pointer, label)]) for i, (label, pointer) in enumerate(fields)]


def _valuation(b):
    root = '/analysis/run_dcf'
    dcf = get(b.source, root, {}) or {}
    ccy = currency(dcf.get('currency'))
    eligible = (dcf.get('applicability') == 'positive_fcff_model' and dcf.get('value_basis') == 'equity_value'
                and get(dcf, '/assumptions/net_debt_bridge_status') == 'complete')
    restriction = None if eligible else 'equity_valuation_ineligible_or_unavailable'
    # All representations keep an incompatible/missing equity bridge withheld.
    if not eligible or ccy is None or ccy != b.currency:
        for metric in b.view['metrics']:
            if metric['id'] == 'weighted-valuation':
                metric.update(value=None, availability='withheld', reason_codes=['equity_bridge_or_currency_unavailable'])
        for chart in b.view['charts']:
            if chart['id'] == 'valuation-scenarios':
                chart.update(series=[], availability='withheld', reason_codes=['equity_bridge_or_currency_unavailable'])
        restriction = 'equity_bridge_or_currency_unavailable'
    net = _metric(b, 'valuation', 'dcf-net-debt', 'Saved net debt (debt less cash)', root + '/assumptions/net_debt',
                  'currency', visibility='diagnostic', restriction=restriction, currency_code=ccy)
    _metric(b, 'valuation', 'fcff-base', 'Unlevered model cash flow (FCFF)', root + '/assumptions/fcf_base',
            'currency', visibility='diagnostic', restriction=restriction, currency_code=ccy)
    rows = []
    for scenario in ('bear', 'base', 'bull'):
        cells = [text_cell('scenario', scenario.title())]
        refs = []
        for column, label, pointer, unit in [
            ('enterprise', 'Enterprise value', '/enterprise_value/', 'currency'),
            ('equity', 'Equity value', '/equity_value/', 'currency'),
            ('per-share', 'Equity value per share', '/value_per_share/', 'currency_per_share'),
            ('weight', 'Assigned scenario weight', '/assumptions/weights/', 'fraction'),
            ('growth', 'Scenario initial growth assumption', '/assumptions/scenario_high_growth/', 'fraction'),
        ]:
            ident = _metric(b, 'valuation', 'dcf-' + column + '-' + scenario, label + ' · ' + scenario.title(),
                root + pointer + scenario, unit, visibility='diagnostic', restriction=restriction,
                currency_code=ccy, period='Saved model scenario; financial input period ' + b.run.period)
            cells.append(metric_cell(column, ident))
            refs.append(b.maybe_evidence(root + pointer + scenario))
        cells.insert(2, metric_cell('net-debt', net))
        rows.append(dict(id='bridge-' + scenario, cells=cells, evidence_refs=refs))
    _table(b, 'valuation', 'equity-bridge', 'Saved enterprise-to-equity bridge',
        [('scenario', 'Scenario'), ('enterprise', 'Enterprise value'), ('net-debt', 'Net debt'),
         ('equity', 'Equity value'), ('per-share', 'Per share'), ('weight', 'Assigned weight'), ('growth', 'Initial growth')], rows)
    fields = [('Model', root + '/assumptions/model'), ('Value basis', root + '/value_basis'),
              ('Applicability', root + '/applicability'), ('Cash-flow definition', root + '/assumptions/fcf_source'),
              ('Discount-rate basis', root + '/assumptions/discount_rate_basis'),
              ('Scenario-weight basis', root + '/assumptions/weight_basis'),
              ('Bridge status', root + '/assumptions/net_debt_bridge_status')]
    _table(b, 'valuation', 'model-basis', 'Saved model basis', [('field', 'Basis'), ('value', 'Saved description')], _text_rows(b, fields))


def _peers(b):
    root = '/analysis/peer_outlier_check'
    peers = get(b.source, root + '/peer_pes', {}) or {}
    excluded = get(b.source, root + '/excluded_peers', {}) or {}
    rows = []
    entries = [(str(get(b.source, '/meta/ticker')), 'Target company', root + '/target_pe', '/analysis/get_financials/financials', '/analysis/get_prices')]
    entries += [(name, 'Excluded' if name in excluded else 'Included in saved screening', root + '/peer_pes/' + token(name),
                 root + '/peer_evidence/' + token(name), root + '/peer_evidence/' + token(name)) for name in dict.fromkeys([*peers, *excluded])]
    bad = any(decimal_text(v) is None or float(v) <= 0 for v in peers.values())
    target = get(b.source, root + '/target_pe')
    bad = bad or target is not None and (decimal_text(target) is None or float(target) <= 0)
    for i, (name, status, pointer, metadata, quotes) in enumerate(entries):
        restriction = 'peer_excluded' if name in excluded else 'ineligible_peer_multiple' if bad else None
        ident = _metric(b, 'peers', 'peer-pe-' + str(i), 'Saved P/E · ' + name, pointer, 'multiple',
            visibility='diagnostic', restriction=restriction, period=str(get(b.source, metadata + '/period') or 'Financial period not retained'))
        period = get(b.source, metadata + '/period')
        price_date = get(b.source, quotes + ('/as_of' if i == 0 else '/price_as_of'))
        quote_ccy = get(b.source, quotes + ('/currency' if i == 0 else '/prices/currency'))
        evidence = list(dict.fromkeys([b.maybe_evidence(pointer), b.maybe_evidence(metadata)]))
        reason = excluded.get(name, get(b.source, metadata + '/reason'))
        rows.append(dict(id='peer-record-' + str(i), cells=[text_cell('company', name), text_cell('selection', status),
            metric_cell('pe', ident), text_cell('period', period or 'Not retained'),
            text_cell('quote-date', price_date or 'Not retained'), text_cell('currency', quote_ccy or 'Unknown'),
            text_cell('note', reason or 'Review economic comparability and period alignment')], evidence_refs=evidence))
    _table(b, 'peers', 'peer-evidence', 'Included and excluded peer evidence',
        [('company', 'Company'), ('selection', 'Saved role'), ('pe', 'P/E'), ('period', 'Financial period'),
         ('quote-date', 'Quote observation'), ('currency', 'Quote currency'), ('note', 'Restriction / review')], rows)


def _market(b):
    root = '/analysis/get_prices'
    as_of = get(b.source, root + '/as_of')
    _metric(b, 'market', 'saved-quote', 'Saved quote', root + '/current_price', 'currency',
            period='Quote observation: ' + str(as_of or 'date not retained'), currency_code=get(b.source, root + '/currency'))
    fields = [('Quote observation', root + '/as_of'), ('Quote source', root + '/source'),
              ('History end date', '/chart_data/price_history/effective_end_date'),
              ('Benchmark', '/chart_data/index_history/index_ticker'),
              ('History policy', '/chart_data/price_history/history_policy')]
    _table(b, 'market', 'market-basis', 'Saved market-data basis', [('field', 'Basis'), ('value', 'Saved value')], _text_rows(b, fields))


def _consensus(b):
    area = b.view['analyst_content']['market_consensus']
    rows = []
    # Iterate a snapshot because coverage metrics are added to the same collection.
    estimates = [m for m in b.view['metrics'] if m['id'] in area['metric_refs']]
    for i, metric in enumerate(estimates):
        evidence = next(e for e in b.view['evidence'] if e['id'] == metric['evidence_refs'][0])
        parts = evidence['pointer'].split('/')
        family, period = (parts[-2], parts[-1]) if '/consensus/' in evidence['pointer'] else ('price_target', 'mean')
        pointer = '/analysis/get_consensus/coverage/' + token(family) + ('' if family == 'price_target' else '/' + token(period))
        ident = _metric(b, 'consensus', 'consensus-coverage-' + str(i), 'Saved analyst count · ' + metric['label'],
                       pointer, 'count', visibility='supporting', period=metric['period_label'])
        raw = get(b.source, pointer)
        # Provider exports may encode an integral count as a JSON float. Preserve
        # its exact integer meaning; fractional, negative and boolean values stay unavailable.
        if type(raw) is float and decimal_text(raw) is not None and raw >= 0 and raw.is_integer():
            next(m for m in b.view['metrics'] if m['id'] == ident).update(value=str(int(raw)), availability='available', reason_codes=[])
        if raw is not None and (type(raw) not in (int, float) or decimal_text(raw) is None
                                or raw <= 0 or type(raw) is float and not raw.is_integer()):
            metric.update(value=None, availability='withheld', reason_codes=['analyst_coverage_invalid'])
        rows.append(dict(id='estimate-' + str(i), cells=[text_cell('estimate', metric['label']),
            metric_cell('value', metric['id']), text_cell('period', metric['period_label']), metric_cell('coverage', ident)],
            evidence_refs=list(dict.fromkeys(metric['evidence_refs'] + [b.maybe_evidence(pointer)]))))
    _table(b, 'consensus', 'consensus-evidence', 'Saved external estimate coverage',
        [('estimate', 'External estimate'), ('value', 'Saved value'), ('period', 'Provider period / horizon'), ('coverage', 'Analyst count')], rows)
    if not any(m['availability'] == 'available' for m in estimates):
        area.update(availability='unavailable', reason_codes=['no_usable_analyst_estimates'])
        _section(b, 'consensus').update(availability='unavailable', reason_codes=['no_usable_analyst_estimates'])
