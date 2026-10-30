"""Keep original-cycle observations separate from export-time effective state."""
from datetime import date

from .common import metric_cell, text_cell
from .values import decimal_text, get, token

MULTIPLES = {'interest_coverage', 'operating_interest_coverage', 'net_debt_to_ebitda',
             'net_debt_to_operating_ebitda_proxy', 'current_ratio'}


def build(b):
    metrics = [b.metric('effective-items', 'Effective-state items at export', '/current', 'count', transform='count'),
               b.metric('cycle-items', 'Selected-cycle observations', '/run/rows', 'count', transform='count'),
               b.metric('surfaced-items', 'Selected-cycle surfaced items', '/run/surfaced', 'count', transform='count')]
    tables = []
    for key, pointer, title in [('cycle', '/run/rows', 'Original selected-cycle observations'),
                               ('effective', '/current', 'Effective state at export')]:
        rows = []
        for i, row in enumerate(get(b.source, pointer, []) or []):
            unit = 'multiple' if row.get('metric') in MULTIPLES else 'unknown'
            restriction = 'metric_unit_unknown' if unit == 'unknown' else None
            ids = {}
            for field, label in [('value', 'Saved value'), ('threshold', 'Saved policy threshold')]:
                ident = key + '-' + field + '-' + str(i)
                ids[field] = b.metric(ident, label + ' · ' + str(row.get('item_id')),
                    f'{pointer}/{i}/{field}', unit, period='Observation: ' + str(row.get('data_ts')),
                    visibility='supporting', restriction=restriction)
                metrics.append(ident)
            direction = {'above': 'At or above', 'below': 'At or below'}.get(row.get('direction'), 'Direction unknown')
            state = str(row.get('status', 'Unavailable'))
            if row.get('_pending_review'):
                state += ' · correction review pending; retained observation'
            if row.get('revision_id'):
                state += ' · saved correction attribution; not an authenticated signature'
            rows.append(dict(id=key + '-row-' + str(i), cells=[
                text_cell('entity', row.get('entity')), text_cell('metric', row.get('metric')),
                text_cell('observed', row.get('data_ts')), metric_cell('value', ids['value']),
                text_cell('direction', direction), metric_cell('threshold', ids['threshold']),
                text_cell('state', state)], evidence_refs=[b.evidence(f'{pointer}/{i}', 'Saved monitoring observation')]))
        tables.append(b.table(key + '-observations', title,
            [('entity', 'Entity'), ('metric', 'Saved metric'), ('observed', 'Observation date'),
             ('value', 'Value'), ('direction', 'Policy direction'), ('threshold', 'Threshold'), ('state', 'Saved classification')], rows))
    b.section('original-cycle', 'Original selected cycle', 'Saved cycle observations and surfaced items; no fresh compliance assessment.',
        metrics=metrics[:3], tables=[tables[0]], findings=[b.observation(m) for m in metrics[:3]])
    b.section('effective-state', 'Effective state at export', 'This snapshot may differ from the original cycle after later observations or corrections.', tables=[tables[1]])
    charts = []
    for i, (item, history) in enumerate((get(b.source, '/run/triage_history', {}) or {}).items()):
        original = next((r for r in get(b.source, '/run/rows', []) if r.get('item_id') == item), {})
        unit = 'multiple' if original.get('metric') in MULTIPLES else 'unknown'
        valid, previous = isinstance(history, list), None
        for row in history if isinstance(history, list) else []:
            try:
                current = date.fromisoformat(row['data_ts'])
                if decimal_text(row.get('value')) is None or (previous and current <= previous):
                    valid = False
                previous = current
            except (KeyError, TypeError, ValueError):
                valid = False
        points = [b.point('observation-' + str(j), row['data_ts'], row['data_ts'],
                         '/run/triage_history/' + token(item) + f'/{j}/value')
                  for j, row in enumerate(history)] if valid else []
        charts.append(b.chart('history-' + str(i), 'Selected-cycle history · ' + item,
            'Actual observations retained for the original cycle; not current effective-state history.',
            'line', unit, [dict(id='observations-' + str(i), label=item, points=points)], x_kind='date',
            x_label='Saved observation date', restriction='history_or_units_unavailable' if not valid or unit == 'unknown' else None))
    if not charts:
        charts.append(b.chart('history-unavailable', 'Observation history', 'A cycle count does not establish a numerical history.',
                              'line', 'multiple'))
    b.section('history', 'Retained observation history', 'Only actually saved histories are available.', charts=charts)
    for field, title in [('reviews', 'Pending correction reviews'), ('decisions', 'Saved correction decisions')]:
        ident = b.metric(field + '-count', title, '/' + field, 'count', transform='count')
        b.section(field, title, 'Read-only evidence; original cycles remain unchanged and local attribution is not authenticated approval.', metrics=[ident])
    b.review('data_basis', 'Observation and policy scope',
        'Thresholds are saved synthetic analyst policies. Current effective state and original-cycle state answer different questions.',
        'Inspect observation dates, skipped inputs and any correction evidence separately.',
        [f'artifact:{b.primary_id}#/run', f'artifact:{b.primary_id}#/current'],
        [b.evidence('/run'), b.evidence('/current')], section_refs=['original-cycle', 'effective-state', 'history'])
