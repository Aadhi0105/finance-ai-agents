"""Exact amounts and retained Python bridge data; forecast scope stays separate."""
from .common import metric_cell, text_cell
from .values import get, token


def build(b):
    source = b.source
    tree = source['report']['full_hierarchy']
    b.view['identity']['period_end'] = get(source, '/request/close_period')
    result = []
    for key, label in [('budget_cents', 'Close budget'), ('actual_cents', 'Close actual'), ('total_variance_cents', 'Actual less budget')]:
        ident = 'close-' + key.replace('_', '-')
        result.append(b.metric(ident, label, '/report/full_hierarchy/' + key, 'currency', transform='minor_to_major'))
    entry = b.series['derivations']['bridge']
    points = [b.point('step-' + str(i), str(i), row['label'], f'/derivations/bridge/data/{i}/value', derived=True,
                      start=row['start'], end=row['end'], assessment=row['assessment'])
              for i, row in enumerate(entry['data'])]
    bridge = b.chart('close-bridge', 'Budget to actual', 'Exact saved-account bridge; favourability follows the saved profit-impact convention.',
        'waterfall', 'currency', [dict(id='bridge-series', label='Saved close bridge', points=points)], x_label='Anchor / account')
    b.section('close-results', 'Monthly financial close', 'Accounting reconciliation establishes agreement within supplied panels.',
              metrics=result, findings=[b.observation(m) for m in result], charts=[bridge])
    account_rows = []

    def walk(node, pointer):
        i = len(account_rows)
        cells = [text_cell('account', node['name'])]
        for field, label in [('budget_cents', 'Budget'), ('actual_cents', 'Actual'), ('total_variance_cents', 'Variance')]:
            ident = b.metric('account-' + str(i) + '-' + field.replace('_', '-'), label + ' · ' + node['name'],
                             pointer + '/' + field, 'currency', transform='minor_to_major', visibility='supporting')
            cells.append(metric_cell(field, ident))
        cells.extend([text_cell('favourability', 'Favourable' if node.get('favourable') is True else
                               'Adverse' if node.get('favourable') is False else 'Unavailable'),
                      text_cell('review', node.get('quadrant'))])
        account_rows.append(dict(id='account-row-' + str(i), cells=cells, evidence_refs=[b.evidence(pointer, 'Saved account evidence')]))
        for j, child in enumerate(node.get('children', [])):
            walk(child, pointer + '/children/' + str(j))
    walk(tree, '/report/full_hierarchy')
    table = b.table('accounts', 'Saved account evidence', [('account', 'Account'), ('budget_cents', 'Budget'),
        ('actual_cents', 'Actual'), ('total_variance_cents', 'Variance'), ('favourability', 'Assessment'), ('review', 'Saved review class')], account_rows)
    b.section('accounts', 'Account evidence', 'Retain source amounts and diagnostic restrictions without inventing business causes.', tables=[table])
    root_forecast = '/report/reforecasts/' + token(tree['node_id'])
    forecast = get(source, root_forecast, {}) or {}
    held = str(forecast.get('publication_status', '')).startswith('held') or bool(forecast.get('error'))
    forecast_metrics = []
    for key, label, unit, transform in [('projected_landing_cents', 'Provisional year-end landing', 'currency', 'minor_to_major'),
                                       ('target_cents', 'Year-end target', 'currency', 'minor_to_major'),
                                       ('prob_hit_target', 'Uncalibrated model probability', 'fraction', 'identity')]:
        forecast_metrics.append(b.metric('forecast-' + key.replace('_', '-'), label, root_forecast + '/' + key,
            unit, transform=transform, period='Year-end forecast from close ' + str(get(source, '/request/close_period')),
            visibility='diagnostic', restriction='forecast_held' if held else None))
    for i, label in enumerate(['Model interval lower bound', 'Model interval upper bound']):
        forecast_metrics.append(b.metric('forecast-band-' + str(i), label, root_forecast + '/band_cents/' + str(i),
            'currency', transform='minor_to_major', period='Year-end model interval', visibility='diagnostic',
            restriction='forecast_held' if held else None))
    b.section('forecast', 'Forecast evidence', 'Forecast period, assumptions and calibration limits are separate from the close.', metrics=forecast_metrics)
    b.review('statistical_eligibility', 'Forecast and source limitations',
        'A provisional landing or uncalibrated probability is not a guarantee. Source authenticity and business causes are not established by accounting checks.',
        'Inspect the original forecast interval, persistence evidence, assumptions and source versions.',
        [f'artifact:{b.primary_id}#/report/reforecasts', f'artifact:{b.primary_id}#/lineage'],
        [b.evidence('/report/reforecasts'), b.evidence('/lineage')], section_refs=['close-results', 'accounts', 'forecast'])
