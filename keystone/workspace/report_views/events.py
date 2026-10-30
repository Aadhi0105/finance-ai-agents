"""Historical diagnostic observations never become a forward forecast."""
from .values import get


def build(b):
    b.view['identity']['ticker'] = get(b.source, '/record/request/ticker')
    fields = [('event-count', 'Historical event cases', 'n_events', 'count'),
              ('issuer-count', 'Distinct issuers', 'n_issuers', 'count'),
              ('mean-car', 'Diagnostic mean accumulated abnormal return', 'caar', 'fraction'),
              ('p-value', 'Statistical inference p-value', 'p_value', 'p_value')]
    metrics = []
    for ident, label, key, unit in fields:
        restriction = 'inference_unavailable' if key == 'p_value' and get(b.source, '/record/result/study/inference_status') != 'available' else None
        metrics.append(b.metric(ident, label, '/record/result/study/' + key, unit,
                                visibility='diagnostic' if key in {'caar', 'p_value'} else 'main', restriction=restriction))
    cases = get(b.source, '/record/result/study/per_event', []) or []
    points = [b.point('case-' + str(i), str(i), str(row.get('ticker', 'Unspecified issuer')),
                      f'/record/result/study/per_event/{i}/car')
              for i, row in enumerate(cases) if 'car' in row]
    case_chart = b.chart('event-cases', 'Historical per-event diagnostics',
        'Saved CAR observations, not next-event predictions. Publication restrictions remain in force.',
        'bar', 'fraction', [dict(id='car-series', label='Diagnostic CAR', points=points)],
        visibility='diagnostic', x_label='Retained historical case')
    path_chart = b.chart('event-path', 'Event-window path',
        'A verified date/session path requires a separately supported alignment projection.',
        'line', 'fraction', visibility='diagnostic', x_kind='relative_session',
        x_label='Confirmed event-relative session', restriction='verified_event_path_not_projected')
    b.section('historical-findings', 'Past event reactions',
        'Inspect the retained sample and its diagnostic observations; no forward-return scenario is introduced.',
        metrics=metrics, findings=[b.observation(m, diagnostic=m in {'mean-car', 'p-value'}) for m in metrics],
        charts=[case_chart, path_chart])
    b.checks('/record/result/gate/checks', lambda _: 'statistical_eligibility', lambda _: ['historical-findings'])
    b.review('statistical_eligibility', 'Historical scope and review requirements',
        'Historical descriptions do not establish a future-return forecast. A minimum sample count alone does not resolve timing, dependence, comparability or control checks.',
        'Inspect every original gate and scenario restriction.',
        [f'artifact:{b.primary_id}#/record'], [b.evidence('/record')], section_refs=['historical-findings'])
    b.view['glossary'] = [dict(term='Abnormal return', definition='Stock return minus the return estimated by the saved market model.'),
        dict(term='CAR', definition='Sum of abnormal returns over the supplied historical event window; not a prediction.')]
