"""Event presentation 1.1: retained scope, case metadata and readable restrictions.

No study is rerun. The original 1.0 mapping remains unchanged for saved views.
"""
from decimal import Decimal

from .common import metric_cell, text_cell
from .values import decimal_text, get

ROOT = '/record/result'
STUDY = ROOT + '/study'
SECTIONS = ['historical-findings', 'event-context', 'event-sample', 'event-review']
TOPICS = {
    'sample': ('Sample and independence', 'The retained sample does not establish independent evidence. Repeated issuers or overlapping windows can share influences.', 'Review the required sample, issuer dependence, overlaps and rejected cases.'),
    'timing': ('Event dates and timing', 'The saved record does not establish all release times, source provenance or measurement-window dates needed for a dated event interpretation.', 'Review issuer release evidence, exchange sessions and the actual measurement dates.'),
    'comparison': ('Comparison basis', 'Peer comparability, benchmark return definitions or price-calendar quality still require review.', 'Check economic comparability, return bases, benchmark evidence and missing observations.'),
    'design': ('Study design and review evidence', 'The retained study design or review record does not resolve the original research requirements.', 'Inspect sampling decisions, predeclared tests, adjustments and the saved review evidence.'),
    'control': ('Control comparison', 'The control study has an unresolved or adverse check. It cannot establish that the event result is reliable or causal.', 'Review the control sample, its inference and any overlap with real events.'),
    'inference': ('Statistical inference', 'The saved statistical test is unavailable, invalid or subject to an additional restriction.', 'Inspect all original statistical checks; a finite mean or larger sample does not itself resolve them.'),
    'assembly': ('Excluded or unresolved evidence', 'Some requested evidence was excluded, rejected or could not be assembled.', 'Review every exclusion and its original reason before assessing coverage.'),
}


def _topic(code):
    if code in {'thin_data', 'fewer_than_10_independent_events', 'repeated_issuer_dependence', 'overlapping_cross_issuer_windows'}:
        return 'sample'
    if code in {'missing_window_dates', 'unverified_event_dates', 'missing_or_inconsistent_release_provenance'}:
        return 'timing'
    if code in {'comparability', 'unverified_benchmark_basis', 'price_calendar_quality_flags'}:
        return 'comparison'
    if code in {'multiple_testing', 'adjusted_significance', 'validation_only', 'unreviewed_sampling_assumptions', 'missing_review_evidence'}:
        return 'design'
    if code in {'placebo', 'control_overlaps_real_event'}:
        return 'control'
    if code in {'assembly', 'rejected_input_records'}:
        return 'assembly'
    return 'inference'


def _table(b, section, ident, title, columns, rows):
    b.table(ident, title, columns, rows)
    next(s for s in b.view['sections'] if s['id'] == section)['table_refs'].append(ident)


def _text_row(b, ident, label, pointer, value=None):
    return dict(id=ident, cells=[text_cell('field', label), text_cell('value', get(b.source, pointer, 'Not retained') if value is None else value)],
                evidence_refs=[b.maybe_evidence(pointer, label)])


def extend(b):
    for ident, title, purpose in [
        ('event-context', 'Study basis', 'Retained method and scope; no new study or source acquisition.'),
        ('event-sample', 'Sample and exclusions', 'Inspect the actual retained cases, requested peers and exclusions.'),
        ('event-review', 'Statistical review', 'Readable topics retain every original finding and its source reference.'),
    ]:
        b.section(ident, title, purpose)
    cases = get(b.source, STUDY + '/per_event', []) or []
    if not isinstance(cases, list) or any(not isinstance(c, dict) for c in cases):
        raise ValueError('Invalid saved event cases')
    _basis(b)
    _sample(b, cases)
    _reviews(b)
    _diagnostics(b, cases)
    # Dates here remain explicitly recorded metadata, never verified session positions.
    chart = next(c for c in b.view['charts'] if c['id'] == 'event-cases')
    if chart['availability'] == 'available':
        chart['series'][0]['points'] = [
            b.point('case-' + str(i), str(i), str(c.get('ticker', 'Unknown issuer')), STUDY + '/per_event/' + str(i) + '/car') if 'car' in c else
            dict(id='case-' + str(i), x=str(i), label=str(c.get('ticker', 'Unknown issuer')), y=None,
                 evidence_refs=[b.evidence(STUDY + '/per_event/' + str(i), 'Saved case without CAR')], reason_codes=['case_car_not_retained'])
            for i, c in enumerate(cases)]
    for series in chart['series']:
        for point in series['points']:
            index = int(point['x'])
            case = cases[index]
            point['x'] = str(case.get('ticker', 'Unknown issuer')) + ' #' + str(index + 1)
            point['label'] = 'Recorded event: ' + str(case.get('event_date', 'date not retained')) + ' · timing requires review'
    chart['x_axis']['label'] = 'Retained issuer / case'
    b.view['glossary'] += [
        dict(term='Equal-event weighting', definition='Each accepted historical case has the same weight in the saved mean. Multiple cases from one issuer are not automatically independent.'),
        dict(term='Statistical inference', definition='A conclusion about a broader process requires eligible assumptions and a valid test. A descriptive mean alone does not provide it.'),
        dict(term='Control study', definition='A comparison using separate control observations. An unresolved control check weakens interpretation; it does not establish causality.'),
    ]


def _basis(b):
    category = get(b.source, ROOT + '/event_class')
    labels = {'earnings': 'Earnings announcements'}
    fields = [('category', 'Event category', ROOT + '/event_class', labels.get(category, category or 'Not retained')),
              ('event-type', 'Saved study label', ROOT + '/event_type', None),
              ('method', 'Saved method', STUDY + '/method', None),
              ('weighting', 'Saved weighting', STUDY + '/weighting', None),
              ('comparability', 'Peer comparability status', ROOT + '/comparability_status', None),
              ('inference', 'Recorded inference status', STUDY + '/inference_status', None),
              ('publication', 'Recorded publication state', ROOT + '/scenario/publication_state', None),
              ('power', 'Sample-size limitation', STUDY + '/power_note', None)]
    _table(b, 'event-context', 'event-basis', 'Saved study basis', [('field', 'Basis'), ('value', 'Saved description')],
           [_text_row(b, *field) for field in fields])


def _sample(b, cases):
    rows = []
    for i, case in enumerate(cases):
        pointer = STUDY + '/per_event/' + str(i)
        dates = case.get('window_dates')
        window = ', '.join(map(str, dates)) if isinstance(dates, list) and dates else 'Dates not retained'
        rows.append(dict(id='case-metadata-' + str(i), cells=[
            text_cell('case', str(case.get('ticker', 'Unknown issuer')) + ' #' + str(i + 1)),
            text_cell('issuer', case.get('issuer_id') or case.get('ticker') or 'Not retained'),
            text_cell('event-date', case.get('event_date') or 'Not retained'),
            text_cell('timing', 'Recorded as reviewed; source review still applies' if case.get('date_status') == 'reviewed' else 'Unverified or not retained'),
            text_cell('window', window), text_cell('benchmark', case.get('benchmark') or 'Not retained'),
            text_cell('benchmark-review', case.get('benchmark_status') or 'Not retained')],
            evidence_refs=[b.evidence(pointer, 'Saved case metadata')]))
    _table(b, 'event-sample', 'event-case-metadata', 'Retained case dates and basis',
        [('case', 'Historical case'), ('issuer', 'Issuer identity'), ('event-date', 'Recorded event date'),
         ('timing', 'Timing review'), ('window', 'Measurement dates'), ('benchmark', 'Benchmark'), ('benchmark-review', 'Benchmark review')], rows)
    peers = []
    for key, role in [('pinned_peers', 'Requested / pinned peer'), ('contributing_peers', 'Recorded contributor'), ('excluded_peers', 'Recorded exclusion')]:
        values = get(b.source, ROOT + '/' + key, []) or []
        if not isinstance(values, list):
            raise ValueError('Invalid saved peer list')
        for i, value in enumerate(values):
            pointer = ROOT + '/' + key + '/' + str(i)
            name = value.get('ticker', 'Not retained') if isinstance(value, dict) else value
            peers.append(dict(id=key + '-' + str(i), cells=[text_cell('company', name), text_cell('role', role)],
                              evidence_refs=[b.evidence(pointer, role)]))
    _table(b, 'event-sample', 'event-peer-selection', 'Recorded peer selection', [('company', 'Company'), ('role', 'Saved role')], peers)
    excluded = []
    for key, pointer in [('rejected', STUDY + '/rejected_events'), ('assembly', ROOT + '/per_peer_report')]:
        values = get(b.source, pointer, []) or []
        for i, value in enumerate(values):
            if not isinstance(value, dict):
                raise ValueError('Invalid saved exclusion')
            if key == 'assembly' and not any(value.get(k) for k in ('excluded', 'error', 'rejected_events')):
                continue
            excluded.append(dict(id=key + '-' + str(i), cells=[text_cell('record', value.get('ticker', 'Input record ' + str(value.get('index', i)))),
                text_cell('stage', 'Rejected study input' if key == 'rejected' else 'Assembly review'),
                text_cell('reason', value.get('reason') or value.get('error') or 'Inspect the saved rejected-event details')],
                evidence_refs=[b.evidence(pointer + '/' + str(i), 'Original exclusion')]))
    _table(b, 'event-sample', 'event-exclusions', 'Rejected or unresolved records',
           [('record', 'Record'), ('stage', 'Scope'), ('reason', 'Saved reason')], excluded)


def _reviews(b):
    checks = get(b.source, ROOT + '/gate/checks', []) or []
    reasons = get(b.source, STUDY + '/inference_reasons', []) or []
    # Replace the 1.0 generic group only in this version; keep policy/scope notes.
    b.view['review_items'] = [r for r in b.view['review_items']
        if not any(ref.startswith('artifact:' + b.primary_id + '#' + ROOT + '/gate/checks/') for ref in r['source_check_refs'])]
    groups, rows = {}, []
    for i, check in enumerate(checks):
        code, status = str(check.get('check', 'unknown')), check.get('status')
        topic = _topic(code)
        pointer = ROOT + '/gate/checks/' + str(i)
        rows.append(dict(id='gate-' + str(i), cells=[text_cell('topic', TOPICS[topic][0]),
            text_cell('status', {'pass': 'Passed saved check', 'fail': 'Requires review', 'warn': 'Review note'}.get(status, 'Unknown; review required')),
            text_cell('code', code), text_cell('detail', check.get('detail') or 'No detail retained')],
            evidence_refs=[b.evidence(pointer, 'Original study check')]))
        if status != 'pass': groups.setdefault(topic, []).append(pointer)
    for i, reason in enumerate(reasons):
        groups.setdefault(_topic(str(reason)), []).append(STUDY + '/inference_reasons/' + str(i))
    for topic, pointers in groups.items():
        title, explanation, action = TOPICS[topic]
        b.review('statistical_eligibility', title, explanation, action,
            [f'artifact:{b.primary_id}#{p}' for p in pointers], [b.evidence(p, title) for p in pointers],
            section_refs=SECTIONS, impact='publication_block')
    _table(b, 'event-review', 'event-gates', 'Original study checks',
           [('topic', 'Review topic'), ('status', 'Saved check result'), ('code', 'Original identifier'), ('detail', 'Original detail')], rows)


def _diagnostics(b, cases):
    metrics = {m['id']: m for m in b.view['metrics']}
    identifiers = {str(c.get('issuer_id') or c.get('ticker') or '') for c in cases}
    valid_counts = True
    for ident, key, actual in [('event-count', 'n_events', len(cases)), ('issuer-count', 'n_issuers', len(identifiers))]:
        raw = get(b.source, STUDY + '/' + key)
        if type(raw) is not int or raw != actual or raw < 0:
            metrics[ident].update(value=None, availability='withheld', reason_codes=['saved_sample_inconsistent'])
            valid_counts = False
    consistent = valid_counts and bool(cases) and all(decimal_text(c.get('car')) is not None for c in cases)
    if not consistent:
        metrics['mean-car'].update(value=None, availability='withheld', reason_codes=['saved_sample_inconsistent'])
        b.review('statistical_eligibility', 'Saved sample consistency',
            'The retained case count or numerical case evidence does not support the saved aggregate.',
            'Resolve the original sample record; no aggregate is recalculated here.',
            [f'artifact:{b.primary_id}#{STUDY}'], [b.evidence(STUDY, 'Saved study')], section_refs=SECTIONS, impact='publication_block')
    p = decimal_text(get(b.source, STUDY + '/p_value'))
    checks = get(b.source, ROOT + '/gate/checks', []) or []
    inference_passed = any(c.get('check') == 'inference' and c.get('status') == 'pass' for c in checks)
    if (not consistent or get(b.source, STUDY + '/inference_status') != 'available'
            or len(cases) < 10 or len(identifiers) != len(cases) or not inference_passed
            or get(b.source, STUDY + '/rejected_events', [])
            or type(get(b.source, STUDY + '/caar_significant')) is not bool
            or get(b.source, STUDY + '/inference_reasons', []) or p is None or not 0 <= Decimal(p) <= 1):
        metrics['p-value'].update(value=None, availability='withheld', reason_codes=['inference_unavailable_or_invalid'])
    metrics['mean-car']['label'] = 'Historical mean abnormal return (CAR)'
    metrics['mean-car']['visibility'] = 'diagnostic'
    metrics['p-value']['visibility'] = 'diagnostic'
    # Refresh the one affected fixed-template observation; never publish a stale mean.
    b.view['findings'] = [f for f in b.view['findings'] if any(k in f['content']['metric_refs'] for k in ('event-count', 'issuer-count'))]
    b.observation('mean-car', diagnostic=True)
    b.observation('p-value', diagnostic=True)
    historical = next(s for s in b.view['sections'] if s['id'] == 'historical-findings')
    historical['finding_refs'] = [f['id'] for f in b.view['findings']]
    base = ROOT + '/scenario'
    family = 'diagnostic_distribution' if isinstance(get(b.source, base + '/diagnostic_distribution'), dict) else 'distribution'
    spread_consistent = consistent and get(b.source, base + '/n_events') == len(cases)
    rows = []
    for key, label in [('median_car', 'Median retained case'), ('p10', '10th percentile of retained cases'),
                       ('p25', '25th percentile of retained cases'), ('p75', '75th percentile of retained cases'), ('p90', '90th percentile of retained cases')]:
        ident = b.metric('event-' + key.replace('_', '-'), label, base + '/' + family + '/' + key, 'fraction',
                         visibility='diagnostic', restriction=None if spread_consistent else 'saved_spread_sample_inconsistent')
        historical['metric_refs'].append(ident)
        rows.append(dict(id=key, cells=[text_cell('measure', label), metric_cell('value', ident)],
                         evidence_refs=[b.maybe_evidence(base + '/' + family + '/' + key, label)]))
    _table(b, 'historical-findings', 'event-spread', 'Saved descriptive sample spread', [('measure', 'Sample description'), ('value', 'Diagnostic value')], rows)
    counts = [metrics[k] for k in ('event-count', 'issuer-count')]
    if all(m['availability'] == 'available' for m in counts):
        text = f"The saved synthetic study records {counts[0]['value']} historical cases from {counts[1]['value']} issuers. "
        if metrics['mean-car']['availability'] == 'available':
            text += f"Its mean accumulated abnormal return is {Decimal(metrics['mean-car']['value']) * 100:,.2f}%, a description of the retained sample. "
        else: text += 'The aggregate mean is withheld. '
        text += 'This does not predict the next event or establish that an announcement caused the observed move.'
        b.view['summary'].update(text=text, template_id='event-study-summary-v1',
            metric_refs=['event-count', 'issuer-count', 'mean-car'],
            evidence_refs=list(dict.fromkeys(ref for m in [*counts, metrics['mean-car']] for ref in m['evidence_refs'])))
