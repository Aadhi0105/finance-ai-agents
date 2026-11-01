"""Monitoring presentation 1.1: source-linked scopes and correction evidence.

No detection, probability model or correction is run. The 1.0 recipe is retained.
Counts below count saved Boolean flags, never classification-name substrings.
"""
from .common import metric_cell, text_cell
from .monitoring import MULTIPLES
from .values import get


REASONS = {
    'duplicate_observation': 'Duplicate observation; retained state unchanged',
    'correction_requires_review': 'Changed observation awaiting correction review',
    'definition_change_requires_review': 'Changed policy or metric definition awaiting review',
    'pending_review': 'Item held pending an existing review',
    'rejected_candidate': 'Previously rejected candidate; retained state unchanged',
}


def _table(b, section, ident, title, columns, rows):
    b.table(ident, title, columns, rows)
    next(s for s in b.view['sections'] if s['id'] == section)['table_refs'].append(ident)


def _text_row(b, ident, label, pointer):
    return dict(id=ident, cells=[text_cell('field', label), text_cell('value', get(b.source, pointer, 'Not retained'))],
                evidence_refs=[b.maybe_evidence(pointer, label)])


def _breaches(b, ident, label, pointer, *, exclude_retired=False):
    rows = get(b.source, pointer)
    valid = isinstance(rows, list) and all(isinstance(r, dict) and type(r.get('breached')) is bool for r in rows)
    b.metric(ident, label, pointer, 'count', transform='approved_python_derivation',
             restriction=None if valid else 'saved_breach_flags_incomplete')
    metric = b.view['metrics'][-1]
    if valid:
        metric.update(value=str(sum(r['breached'] is True and not (exclude_retired and r.get('retired_to')) for r in rows)), availability='available', reason_codes=[])
    evidence = next(e for e in b.view['evidence'] if e['id'] == metric['evidence_refs'][0])
    evidence['method'] = 'Count records whose saved breached flag is true' + (' excluding rows with a saved retired_to replacement' if exclude_retired else '') + '; missing/non-Boolean flags withhold the count. No new threshold assessment.'
    return ident


def _number(b, ident, label, pointer, definition):
    return b.metric(ident, label, pointer, 'multiple' if definition.get('metric') in MULTIPLES else 'unknown',
                    visibility='supporting', period='Observation: ' + str(definition.get('data_ts', 'not retained')),
                    restriction=None if definition.get('metric') in MULTIPLES else 'metric_unit_unknown')


def _candidate_rows(b, records, pointer, prefix):
    rows = []
    for i, record in enumerate(records):
        candidate = record.get('candidate') or {}
        if not isinstance(candidate, dict):
            raise ValueError('Invalid saved monitoring candidate')
        p = f'{pointer}/{i}'
        value = _number(b, f'{prefix}-value-{i}', 'Proposed input · ' + str(record.get('item_id')), p + '/candidate/value', candidate)
        threshold = _number(b, f'{prefix}-threshold-{i}', 'Proposed policy threshold', p + '/candidate/threshold', candidate)
        previous = record.get('previous') or candidate
        previous_value = _number(b, f'{prefix}-previous-{i}', 'Previously retained input',
            p + ('/previous/value' if isinstance(record.get('previous'), dict) and 'value' in record['previous'] else '/previous_value'), previous)
        rows.append(dict(id=f'{prefix}-{i}', cells=[
            text_cell('item', record.get('item_id')), text_cell('entity', record.get('entity', candidate.get('entity'))),
            text_cell('reason', REASONS.get(record.get('reason'), record.get('reason', 'Not retained'))),
            text_cell('metric', candidate.get('metric')), text_cell('date', candidate.get('data_ts')),
            metric_cell('previous', previous_value), metric_cell('candidate', value),
            text_cell('direction', {'above': 'At or above', 'below': 'At or below'}.get(candidate.get('direction'), 'Unknown')),
            metric_cell('threshold', threshold)], evidence_refs=[b.evidence(p, 'Saved candidate and retained-input context')]))
    return rows


CANDIDATE_COLUMNS = [('item', 'Item ID'), ('entity', 'Entity'), ('reason', 'Saved reason'), ('metric', 'Proposed metric'),
    ('date', 'Candidate observation date'), ('previous', 'Previously retained value'), ('candidate', 'Candidate value'),
    ('direction', 'Candidate policy direction'), ('threshold', 'Candidate policy threshold')]


def extend(b):
    for ident, title, purpose in [
        ('monitor-context', 'Cycle and export basis', 'Selected-cycle metadata and export time have different meanings.'),
        ('monitor-coverage', 'Skipped inputs', 'Skipped inputs do not reassess compliance or remove retained breaches.'),
        ('monitor-corrections', 'Correction evidence', 'Read-only proposals, decisions and separately saved before/after observations.'),
        ('monitor-triage', 'Saved triage attempts', 'Saved process metadata; model commentary does not establish an approved action.'),
    ]:
        b.section(ident, title, purpose)
    selected = get(b.source, '/run/rows', [])
    current = get(b.source, '/current', [])
    if not isinstance(selected, list) or not isinstance(current, list):
        raise ValueError('Invalid monitoring observations')
    counts = [_breaches(b, 'cycle-breaches', 'Recorded breaches in the selected cycle', '/run/rows'),
              _breaches(b, 'effective-breaches', 'Recorded breaches in non-retired export items', '/current', exclude_retired=True)]
    for metric in b.view['metrics']:
        if metric['id'] in {'effective-items', 'effective-breaches', 'reviews-count', 'decisions-count'}:
            metric['period_label'] = 'Snapshot export: ' + b.source['exported_at']
    # The 1.0 recipe created this observation before export-scope metadata existed.
    b.view['findings'] = [f for f in b.view['findings'] if f['id'] != 'finding-effective-items']
    b.observation('effective-items')
    next(s for s in b.view['sections'] if s['id'] == 'original-cycle')['metric_refs'].append(counts[0])
    next(s for s in b.view['sections'] if s['id'] == 'effective-state')['metric_refs'] += ['effective-items', counts[1]]
    for key, pointer in [('cycle', '/run/rows'), ('effective', '/current')]:
        table = next(t for t in b.view['tables'] if t['id'] == key + '-observations')
        table['columns'].insert(0, dict(id='item', label='Item ID'))
        table['columns'].insert(-1, dict(id='breach', label='Saved breach flag'))
        table['columns'].insert(-1, dict(id='signals', label='Saved early-warning signals'))
        if key == 'cycle':
            table['columns'].insert(-1, dict(id='attention', label='Selected-cycle attention'))
        for row, original in zip(table['rows'], get(b.source, pointer)):
            row['cells'].insert(0, text_cell('item', original.get('item_id')))
            flag = original.get('breached')
            row['cells'].insert(-1, text_cell('breach', 'Recorded breach' if flag is True else 'No recorded breach' if flag is False else 'Flag unavailable'))
            signals = [label for field, label in [('anomaly_significant', 'Unusual observation'), ('drifting', 'Drift diagnostic'),
                       ('breach_tail', 'Threshold-path diagnostic')] if original.get(field) is True]
            row['cells'].insert(-1, text_cell('signals', ' · '.join(signals) or 'No flags recorded'))
            if key == 'cycle':
                surfaced = get(b.source, '/run/surfaced', [])
                row['cells'].insert(-1, text_cell('attention', 'Surfaced for attention' if any(r.get('item_id') == original.get('item_id') for r in surfaced) else 'Not surfaced'))
                row['evidence_refs'].append(b.maybe_evidence('/run/surfaced', 'Saved selected-cycle surfaced items'))
            if original.get('retired_to'):
                row['cells'][-1]['text'] += ' · retired series; replacement item: ' + str(original['retired_to'])
    fields = [('cycle', 'Selected cycle', '/run/cycle'), ('date', 'Cycle observation date', '/run/data_ts'),
        ('status', 'Saved cycle status', '/run/status'), ('baseline', 'Baseline / alert suppression', '/run/baseline'),
        ('gap', 'Missed scheduler cycles', '/run/gap'), ('replay', 'Saved replay flag', '/run/replayed'),
        ('export', 'Snapshot exported at (not an observation date)', '/exported_at'),
        ('audit', 'Unreadable triage audits', '/unreadable_audits')]
    _table(b, 'monitor-context', 'monitor-basis', 'Cycle and export basis', [('field', 'Field'), ('value', 'Saved value')],
           [_text_row(b, 'basis-' + ident, label, p) for ident, label, p in fields])
    skipped = get(b.source, '/run/skipped', []) or []
    _table(b, 'monitor-coverage', 'skipped-inputs', 'Skipped inputs in the selected cycle', CANDIDATE_COLUMNS,
           _candidate_rows(b, skipped, '/run/skipped', 'skipped'))
    _table(b, 'monitor-corrections', 'pending-corrections', 'Pending correction proposals — not applied', CANDIDATE_COLUMNS,
           _candidate_rows(b, b.source['reviews'], '/reviews', 'pending'))
    decision_rows, before_after = [], []
    for i, decision in enumerate(b.source['decisions']):
        p = f'/decisions/{i}'
        decision_rows.append(dict(id=f'decision-{i}', cells=[text_cell(k, decision.get(k)) for k in
            ['review_id', 'item_id', 'action', 'decided_at', 'reviewer', 'reason', 'effect', 'replacement_id']],
            evidence_refs=[b.evidence(p, 'Saved correction decision; local attribution only')]))
        for side in ['before', 'after']:
            records = decision.get(side, [])
            if not isinstance(records, list):
                raise ValueError('Invalid correction history')
            for j, row in enumerate(records):
                rp = f'{p}/{side}/{j}'
                value = _number(b, f'decision-{i}-{side}-value-{j}', 'Saved decision observation', rp + '/value', row)
                threshold = _number(b, f'decision-{i}-{side}-threshold-{j}', 'Saved decision policy', rp + '/threshold', row)
                before_after.append(dict(id=f'decision-{i}-{side}-{j}', cells=[
                    text_cell('review', decision.get('review_id')), text_cell('side', side), text_cell('item', row.get('item_id')),
                    text_cell('date', row.get('data_ts')), text_cell('metric', row.get('metric')), metric_cell('value', value),
                    text_cell('direction', {'above': 'At or above', 'below': 'At or below'}.get(row.get('direction'), 'Unknown')),
                    metric_cell('threshold', threshold), text_cell('state', row.get('status'))], evidence_refs=[b.evidence(rp)]))
    _table(b, 'monitor-corrections', 'correction-decisions', 'Saved correction decisions — local attribution only',
        [(k, label) for k, label in [('review_id', 'Review ID'), ('item_id', 'Item ID'), ('action', 'Decision'),
         ('decided_at', 'Decision time'), ('reviewer', 'Local reviewer name'), ('reason', 'Saved reason'),
         ('effect', 'Saved effect'), ('replacement_id', 'Replacement series')]], decision_rows)
    _table(b, 'monitor-corrections', 'decision-observations', 'Separately retained decision histories — before and after',
        [('review', 'Review ID'), ('side', 'Decision scope'), ('item', 'Item ID'), ('date', 'Observation date'),
         ('metric', 'Metric'), ('value', 'Value'), ('direction', 'Policy direction'), ('threshold', 'Policy threshold'), ('state', 'Saved classification')], before_after)
    attempts = b.source['attempts']
    _table(b, 'monitor-triage', 'triage-attempts', 'Saved triage attempts — process evidence',
        [('attempt', 'Attempt'), ('status', 'Saved status'), ('publication', 'Saved publication state'), ('mode', 'Saved model mode')],
        [dict(id=f'attempt-{i}', cells=[text_cell('attempt', a.get('attempt_id', get(a, '/execution/run_id', f'Saved attempt {i + 1}'))),
              text_cell('status', get(a, '/execution/status', a.get('status', a.get('publication_status')))),
              text_cell('publication', a.get('publication')), text_cell('mode', a.get('model_mode'))],
              evidence_refs=[b.evidence(f'/attempts/{i}', 'Saved triage process record')]) for i, a in enumerate(attempts)])
    scope = ('This is a baseline cycle; alerting was suppressed. Recorded breach flags remain separate from surfaced alerts.'
        if get(b.source, '/run/baseline') is True else
        'No new observations were retained in this cycle. Compliance was not reassessed; prior effective state remains visible.'
        if not selected else
        'Read the selected cycle separately from effective state at export. A surfaced item can be an early warning without a recorded breach.')
    b.view['summary'] = dict(text=scope + ' Thresholds are saved analyst policies, not verified contractual covenants. Financial review is required.',
        template_id='monitoring-summary-v1', metric_refs=['cycle-items', 'surfaced-items', 'cycle-breaches', 'effective-items', 'effective-breaches'],
        evidence_refs=[b.evidence('/run'), b.evidence('/current')], review_refs=[])
    b.review('data_basis', 'Observation coverage and correction boundaries',
        'A skipped or quiet cycle does not clear earlier breaches. Effective state can contain older observations. Pending proposals are not applied; saved decisions identify any restatement or replacement series.',
        'Inspect dates, skipped inputs, original histories and correction records. Local reviewer names are not authenticated signatures.',
        [f'artifact:{b.primary_id}#/reviews', f'artifact:{b.primary_id}#/decisions'],
        [b.evidence('/reviews'), b.evidence('/decisions')], section_refs=['original-cycle', 'effective-state', 'history', 'monitor-context', 'monitor-coverage', 'monitor-corrections'])
    b.review('statistical_eligibility', 'Early-warning diagnostics require interpretation',
        'Anomaly, drift and threshold-path flags are saved diagnostics. They do not establish calibrated breach probabilities, legal compliance or a recommended financial action.',
        'Review the original diagnostic definitions, observation intervals, sample size and assumptions before acting.',
        [f'artifact:{b.primary_id}#/run'], [b.evidence('/run')], section_refs=['original-cycle', 'history', 'monitor-triage'])
    if get(b.source, '/unreadable_audits', 0):
        b.review('delivery', 'Triage audit coverage is incomplete', 'The snapshot records unreadable triage audits. An empty attempt list cannot establish that no attempt occurred.',
            'Inspect the retained audit files outside this reader.', [f'artifact:{b.primary_id}#/unreadable_audits'],
            [b.evidence('/unreadable_audits')], section_refs=['monitor-triage'])
    b.view['glossary'] += [dict(term=term, definition=definition) for term, definition in [
        ('Recorded breach', 'The saved breached Boolean flag, including widening, improving or stable breaches. The browser does not perform a fresh threshold assessment.'),
        ('Surfaced item', 'An item selected by saved detection for attention. It may be a breach or an early-warning diagnostic.'),
        ('Policy direction', 'At or above means value ≥ threshold is allowed; at or below means value ≤ threshold is allowed. These are analyst policies.'),
        ('Observation date and export time', 'Observation dates identify saved measurements. Export time identifies when this snapshot was assembled. Scheduler cycles are not reporting periods.'),
        ('Retained history', 'Only original-cycle histories actually saved in the snapshot are plotted. Cycle IDs, effective-state rows and decision histories are not joined into a new time series.'),
        ('Correction evidence', 'Pending candidates remain unapplied. Approved restatements preserve original-cycle records. Definition changes use a new series; rejection retains history. Names record local attribution only.'),
    ]]
