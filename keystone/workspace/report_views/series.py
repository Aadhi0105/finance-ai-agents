"""Operator-only series preparation using the existing chart definitions.

HTTP delivery imports neither this module nor the financial/chart helpers.
The retained series are an explicit, hashed source artifact for a native view.
"""
from .sources import adapter_for, check_source
from .values import decimal_text, get, history_ok, minor_to_major


def prepare_series(run, source, source_artifact):
    check_source(run, source)
    adapter_id, version, _ = adapter_for(run)
    result = {'schema_version': 1, 'kind': 'keystone.report-series',
              'adapter_id': adapter_id, 'adapter_version': version,
              'source_artifact_id': source_artifact.id,
              'source_sha256': source_artifact.sha256, 'derivations': {}}
    if run.workflow == 'research':
        _research(source, result['derivations'])
    elif run.workflow == 'close':
        _close(source, result['derivations'])
    return result


def _research(source, out):
    # Lazy import: no chart library, provider or model needs to run on delivery.
    from composer import _align_on_dates, _drawdown, _rolling_vol, _sma
    history = get(source, '/chart_data/price_history/history')
    index = get(source, '/chart_data/index_history/history')
    clean = history_ok(history) and not get(source, '/chart_data/price_history/excluded_observations', [])
    definitions = {'ma50': ('composer._sma', {'window': 50}),
                   'ma200': ('composer._sma', {'window': 200}),
                   'volatility30': ('composer._rolling_vol', {'window': 30, 'annualisation_days': 252}),
                   'drawdown': ('composer._drawdown', {})}
    for key, (method, parameters) in definitions.items():
        entry = dict(method=method, parameters=parameters,
                     source_pointers=['/chart_data/price_history/history'],
                     availability='available' if clean else 'withheld',
                     reason_codes=[] if clean else ['history_missing_invalid_or_excluded'], data=[])
        if clean:
            closes = [r['close'] for r in history]
            values = (_sma(closes, parameters['window']) if key.startswith('ma') else
                      _rolling_vol(closes, 30) if key == 'volatility30' else _drawdown(closes))
            entry['data'] = [{'date': row['date'], 'value': decimal_text(value)}
                             for row, value in zip(history, values)]
            if not any(r['value'] is not None for r in entry['data']):
                entry.update(availability='unavailable', reason_codes=['warmup_window_unfilled'])
        out[key] = entry
    index_clean = (clean and history_ok(index)
                   and not get(source, '/chart_data/index_history/excluded_observations', []))
    dates, stock, market = _align_on_dates(history, index) if index_clean else ([], [], [])
    for key, values in [('rebased_stock', stock), ('rebased_index', market)]:
        out[key] = dict(method='common-date rebasing: 100 * close / first common close',
                        parameters={'base': 100},
                        source_pointers=['/chart_data/price_history/history', '/chart_data/index_history/history'],
                        availability='available' if dates else 'unavailable',
                        reason_codes=[] if dates else ['compatible_history_unavailable'],
                        data=[{'date': day, 'value': decimal_text(100 * value / values[0])}
                              for day, value in zip(dates, values)])


def _close(source, out):
    from agent4.output import waterfall_rows
    tree = source['report']['full_hierarchy']
    rows = waterfall_rows(tree)
    out['bridge'] = dict(method='agent4.output.waterfall_rows; exact integer cents / 100',
                         parameters={'minor_units_per_major': 100},
                         source_pointers=['/report/full_hierarchy'], availability='available',
                         reason_codes=[], data=[{
                             'label': row['label'], 'value': minor_to_major(row['value_cents']),
                             'start': minor_to_major(row['start_cents']),
                             'end': minor_to_major(row['end_cents']),
                             'assessment': ('anchor' if row['kind'] == 'anchor' else
                                            'favourable' if row['favourable'] else 'adverse')
                         } for row in rows])
