"""News presentation 1.1: saved coverage, text scope and restricted diagnostics.

No acquisition, scoring, aggregation or publication decision is performed here.
The original 1.0 projection is retained for existing registrations.
"""
from decimal import Decimal

from .common import metric_cell, text_cell
from .values import decimal_text, get, token

ROOT = '/record/result'
SECTIONS = ['coverage', 'retained-news', 'tone', 'news-context', 'news-review']
SCORERS = {'stub', 'lm', 'finbert', 'finbert+lm'}
TOPICS = {
    'coverage': ('Coverage and excluded inputs', 'Coverage is bounded by the retained inputs and exclusions. An empty saved input, no relevant records and a failed retrieval have different meanings.'),
    'text': ('Text and language limits', 'Headline-only text, unspecified scope, unsupported language or truncation can limit interpretation. Full-article analysis is not implied.'),
    'relevance': ('Relevance and document identity', 'Headline matches associate text with a company. Multiple entities, changed text and heuristic clusters do not establish company-specific tone or independent stories.'),
    'scorer': ('Scorer and diagnostic limits', 'Saved scorer outputs are descriptive text diagnostics. Synthetic, lexical, ambiguous or conflicting scores do not establish calibrated reliability or a market outcome.'),
}


def _display(value, limit=900):
    text = str(value) if value is not None else 'Not retained'
    return text if len(text) <= limit else text[:limit] + '… [display excerpt; inspect original]'


def _list(source, pointer):
    rows = get(source, pointer, [])
    if not isinstance(rows, list):
        raise ValueError('Invalid saved news collection')
    return rows


def _table(b, section, ident, title, columns, rows):
    b.table(ident, title, columns, rows)
    next(s for s in b.view['sections'] if s['id'] == section)['table_refs'].append(ident)


def _topic(code):
    if code in {'excluded_input_evidence', 'no_relevant_usable_news', 'missing_retrieval_timestamp'}:
        return 'coverage'
    if code in {'headline_only_evidence', 'unsupported_or_unknown_language', 'input_truncated'}:
        return 'text'
    if code in {'multi_entity_document_tone', 'article_identity_has_changed_text', 'missing_article_url'}:
        return 'relevance'
    return 'scorer'


def _score(item):
    value = decimal_text(item.get('sentiment'))
    evidence = item.get('score_evidence') or {}
    if (not isinstance(evidence, dict) or item.get('scorer') not in SCORERS
            or value is None or not -1 <= Decimal(value) <= 1
            or decimal_text(evidence.get('score')) != value or evidence.get('scorer') != item.get('scorer')):
        return None
    return value


def extend(b):
    items = _list(b.source, ROOT + '/scored_items')
    signals = _list(b.source, ROOT + '/signals')
    ingested = _list(b.source, ROOT + '/ingested_items')
    excluded = _list(b.source, ROOT + '/exclusions')
    if any(not isinstance(i, dict) for i in [*items, *signals, *ingested, *excluded]):
        raise ValueError('Invalid saved news record')
    b.section('news-context', 'Saved coverage basis', 'Recorded cutoff, input basis and retrieval evidence.')
    b.section('news-review', 'News review evidence', 'Every original reason remains attached to the saved text.')
    consistent = _coverage(b, items, signals, ingested, excluded)
    _stories(b, items)
    _tone(b, items, signals, consistent)
    _reviews(b)
    b.view['glossary'] += [
        dict(term='Saved cutoff', definition='The recorded as-of instant used to screen publication times. Opening a saved report does not refresh that cutoff.'),
        dict(term='Document tone', definition='A description of retained text. It is not entity-specific sentiment, a return forecast or a recommendation.'),
        dict(term='Scorer output', definition='A saved model or lexical diagnostic. Class probabilities and confidence fields are not calibrated reliability or return probabilities.'),
    ]


def _coverage(b, items, signals, ingested, excluded):
    funnel = get(b.source, ROOT + '/funnel', {})
    keys = ['raw', 'ingested', 'after_relevance', 'after_dedup']
    counts = [funnel.get(k) for k in keys]
    consistent = (all(type(n) is int and n >= 0 for n in counts)
                  and counts == sorted(counts, reverse=True)
                  and counts[1] == len(ingested) and counts[3] == len(items)
                  and funnel.get('entity_days') == len(signals)
                  and all(type(i.get('cluster_size')) is int and i['cluster_size'] >= 1
                          and isinstance(i.get('members'), list) and len(i['members']) == i['cluster_size'] for i in items)
                  and counts[2] == sum(i['cluster_size'] for i in items))
    inputs = get(b.source, '/record/input_items')
    if isinstance(inputs, list) and counts[0] != len(inputs):
        consistent = False
    transport = get(b.source, '/record/fetched/transport', {}) or {}
    failed = (get(b.source, '/record/status') in {'failed', 'unavailable', 'refused'}
              or get(b.source, ROOT + '/status') in {'failed', 'unavailable', 'refused'}
              or get(b.source, '/record/provider_failure/status') == 'unavailable'
              or transport.get('status') == 'unavailable')
    state = ('retrieval_failed' if failed else 'coverage_unknown' if not consistent else
             'recorded_empty_response' if counts[0] == 0 and transport.get('status') == 'empty' and transport.get('http_status') == 200 else
             'empty_saved_input' if counts[0] == 0 else 'no_relevant_records' if counts[2] == 0 else 'retained_records')
    b.metric('coverage-ingested', 'Parsed input records', ROOT + '/funnel/ingested', 'count')
    coverage_ids = ['coverage-raw', 'coverage-ingested', 'coverage-after-relevance', 'coverage-after-dedup']
    coverage_section = next(s for s in b.view['sections'] if s['id'] == 'coverage')
    coverage_section['metric_refs'].append('coverage-ingested')
    points = [b.point('coverage-' + key, label, label, ROOT + '/funnel/' + key)
              for key, label in zip(keys, ['Input records', 'Parsed records', 'Relevant records', 'Retained clusters'])] if consistent and not failed else []
    chart = b.chart('news-coverage', 'Saved news coverage',
        'Counts at saved processing stages; clusters are not demonstrated independent stories.', 'bar', 'count',
        [dict(id='coverage-counts', label='Saved record count', points=points)], x_label='Saved processing stage',
        restriction='coverage_failed_or_inconsistent' if failed or not consistent else None)
    coverage_section['chart_refs'].append(chart)
    if not consistent or failed:
        for m in b.view['metrics']:
            if m['id'] in coverage_ids:
                m.update(value=None, availability='withheld', reason_codes=['coverage_failed_or_inconsistent'])
        b.view['findings'] = []
        coverage_section['finding_refs'] = []
        b.review('data_basis', 'Coverage cannot be established',
            'A failed retrieval or inconsistent saved counts cannot establish complete coverage or a valid empty feed.',
            'Inspect the saved processing record and source evidence; no counts are reconstructed here.',
            [f'artifact:{b.primary_id}#{ROOT}'], [b.evidence(ROOT)], section_refs=SECTIONS, impact='publication_block')
    fields = [('coverage-state', 'Saved coverage state', ROOT + '/funnel', state),
              ('cutoff', 'Saved cutoff', ROOT + '/as_of', None),
              ('max-age', 'Maximum publication age (days)', ROOT + '/max_age_days', None),
              ('input-basis', 'Input basis', ROOT + '/data_mode', 'Saved synthetic input; no live retrieval is established'),
              ('publication', 'Original publication state', ROOT + '/publication_state', None),
              ('scope', 'Original scope note', ROOT + '/scope_note', None)]
    rows = [dict(id=ident, cells=[text_cell('field', label), text_cell('value', _display(value if value is not None else get(b.source, pointer)))],
                 evidence_refs=[b.maybe_evidence(pointer, label)]) for ident, label, pointer, value in fields]
    _table(b, 'news-context', 'news-basis', 'Saved news basis', [('field', 'Basis'), ('value', 'Saved description')], rows)
    _table(b, 'coverage', 'news-exclusions', 'Excluded input evidence',
        [('record', 'Input reference'), ('stage', 'Stage'), ('reason', 'Saved reason')],
        [dict(id='exclusion-' + str(i), cells=[text_cell('record', _display(r.get('id') or r.get('evidence_id') or r.get('input_index'))),
            text_cell('stage', _display(r.get('stage'))), text_cell('reason', _display(r.get('reason')))],
            evidence_refs=[b.evidence(ROOT + '/exclusions/' + str(i), 'Original exclusion')]) for i, r in enumerate(excluded)])
    text = ('The saved synthetic news run retains ' + str(len(items)) + ' headline clusters. ' if consistent and not failed else
            'Coverage cannot be established from this saved news record. ')
    text += 'Published document tone is withheld. The retained text does not establish company-specific sentiment or a future return.'
    b.view['summary'].update(text=text, template_id='news-study-summary-v1',
        metric_refs=['coverage-after-dedup'], evidence_refs=[b.evidence(ROOT, 'Saved news coverage and publication evidence')])
    return consistent and not failed


def _stories(b, items):
    details, members, points, scorers = [], [], [], []
    headlines = next(t for t in b.view['tables'] if t['id'] == 'retained-headlines')
    for i, item in enumerate(items):
        pointer = ROOT + '/scored_items/' + str(i)
        # Display excerpts are explicit; the original full text stays in its sealed bundle.
        headlines['rows'][i]['cells'][0]['text'] = _display(item.get('headline'))
        headlines['rows'][i]['cells'][1]['text'] = _display(item.get('source'))
        scope = item.get('text_scope') or 'Retained headline and supplied text; original scope unspecified'
        headlines['rows'][i]['cells'][3]['text'] = _display(scope)
        fields = [('retrieved', item.get('retrieved_at')), ('language', item.get('language')), ('scope', scope),
                  ('relevance', (item.get('relevance') or {}).get('method')),
                  ('matches', (item.get('relevance') or {}).get('matches')),
                  ('cluster', item.get('cluster_id')), ('size', item.get('cluster_size')),
                  ('scorer', item.get('scorer')), ('url', item.get('url')),
                  ('excerpt', _display(item.get('body'), 700))]
        details.append(dict(id='story-' + str(i), cells=[text_cell(key, _display(value)) for key, value in fields],
                            evidence_refs=[b.evidence(pointer, 'Original retained story and scorer evidence')]))
        evidence = item.get('score_evidence') or {}
        scorers.append(dict(id='scorer-' + str(i), cells=[text_cell('story', 'Story ' + str(i + 1)),
            *[text_cell(key, _display(evidence.get(key))) for key in ('scorer', 'model', 'revision', 'token_count', 'token_limit', 'truncated', 'probability_note')]],
            evidence_refs=[b.maybe_evidence(pointer + '/score_evidence', 'Original scorer metadata')]))
        for j, member in enumerate(item.get('members', [])):
            if not isinstance(member, dict):
                raise ValueError('Invalid cluster member')
            members.append(dict(id='member-' + str(i) + '-' + str(j), cells=[text_cell('story', 'Story ' + str(i + 1)),
                text_cell('headline', _display(member.get('headline'))), text_cell('publisher', _display(member.get('source'))),
                text_cell('published', _display(member.get('published_at'))), text_cell('relevance', _display(member.get('relevance')))],
                evidence_refs=[b.evidence(pointer + '/members/' + str(j), 'Retained cluster member')]))
        point = (b.point('story-' + str(i), 'Story ' + str(i + 1), _display(item.get('headline'), 190), pointer + '/sentiment')
                 if 'sentiment' in item else dict(id='story-' + str(i), x='Story ' + str(i + 1), label=_display(item.get('headline'), 190),
                     y=None, evidence_refs=[b.evidence(pointer)], reason_codes=['story_score_unavailable']))
        if _score(item) is None:
            point.update(y=None, reason_codes=['story_score_unavailable_or_invalid'])
        points.append(point)
    _table(b, 'retained-news', 'news-story-details', 'Retained text and grouping basis',
        [('retrieved', 'Retrieved at'), ('language', 'Language'), ('scope', 'Text scope'), ('relevance', 'Relevance method'),
         ('matches', 'Recorded headline matches'), ('cluster', 'Cluster identity'), ('size', 'Recorded cluster size'),
         ('scorer', 'Scorer'), ('url', 'Recorded address (unverified)'), ('excerpt', 'Saved text excerpt')], details)
    _table(b, 'retained-news', 'news-cluster-members', 'Retained cluster members',
        [('story', 'Representative'), ('headline', 'Member headline'), ('publisher', 'Source'), ('published', 'Publication time'), ('relevance', 'Recorded relevance')], members)
    _table(b, 'tone', 'news-scorer-details', 'Saved scorer metadata',
        [('story', 'Representative'), ('scorer', 'Scorer'), ('model', 'Recorded model'), ('revision', 'Recorded revision'),
         ('token_count', 'Original tokens'), ('token_limit', 'Token limit'), ('truncated', 'Truncated'), ('probability_note', 'Probability limitation')], scorers)
    ident = b.chart('news-story-tone', 'Saved story tone diagnostics',
        'Diagnostic scores for retained document text on a -1 to +1 scale; not calibrated reliability, published company sentiment or return probabilities.',
        'bar', 'score', [dict(id='story-tone', label='Diagnostic text score', points=points)], visibility='diagnostic', x_label='Retained cluster representative')
    next(s for s in b.view['sections'] if s['id'] == 'tone')['chart_refs'].append(ident)


def _tone(b, items, signals, consistent):
    metrics = {m['id']: m for m in b.view['metrics']}
    rows = []
    for i, signal in enumerate(signals):
        ident = 'diagnostic-tone-' + str(i)
        value = decimal_text(signal.get('diagnostic_level'))
        ids = signal.get('cluster_ids')
        stories = [s for s in items if isinstance(ids, list) and s.get('cluster_id') in ids]
        valid = (consistent and isinstance(ids, list) and bool(ids) and len(set(ids)) == len(ids)
                 and signal.get('count') == len(ids) == len(stories)
                 and all(signal.get('entity') in s.get('entities', []) and signal.get('day') == s.get('day') for s in stories)
                 and signal.get('scored_count') == sum(_score(s) is not None for s in stories)
                 and any(_score(s) is not None for s in stories)
                 and value is not None and -1 <= Decimal(value) <= 1)
        if not valid:
            metrics[ident].update(value=None, availability='withheld', reason_codes=['diagnostic_evidence_unavailable_or_inconsistent'])
        pointer = ROOT + '/signals/' + str(i)
        rows.append(dict(id='signal-' + str(i), cells=[text_cell('entity', _display(signal.get('entity'))),
            text_cell('day', _display(signal.get('day')) + ' · ' + _display(signal.get('day_timezone'))),
            metric_cell('published', 'published-tone-' + str(i)), metric_cell('diagnostic', ident),
            text_cell('scorers', _display(signal.get('scorers'))), text_cell('scope', _display(signal.get('tone_scope')))],
            evidence_refs=[b.evidence(pointer, 'Original daily document-tone record')]))
    _table(b, 'tone', 'news-tone-records', 'Saved daily text-tone records',
        [('entity', 'Company association'), ('day', 'Saved date / timezone'), ('published', 'Published tone'),
         ('diagnostic', 'Diagnostic text average'), ('scorers', 'Scorers'), ('scope', 'Tone scope')], rows)


def _reviews(b):
    groups, rows = {}, []
    def collect(value, pointer):
        if isinstance(value, dict):
            for key, child in value.items():
                if key != 'review_reasons':
                    collect(child, pointer + '/' + token(key))
            reasons = value.get('review_reasons', [])
            if not isinstance(reasons, list):
                raise ValueError('Invalid saved news review reasons')
            for i, code in enumerate(reasons):
                ref = pointer + '/review_reasons/' + str(i)
                topic = _topic(str(code))
                groups.setdefault(topic, []).append(ref)
                rows.append(dict(id='reason-' + str(len(rows)), cells=[text_cell('topic', TOPICS[topic][0]), text_cell('code', _display(code))],
                                 evidence_refs=[b.evidence(ref, 'Original news review reason')]))
        elif isinstance(value, list):
            for i, child in enumerate(value):
                collect(child, pointer + '/' + str(i))
    collect(get(b.source, ROOT), ROOT)
    for topic, pointers in groups.items():
        title, explanation = TOPICS[topic]
        for offset in range(0, len(pointers), 100):
            batch = pointers[offset:offset + 100]
            b.review('narrative_support', title, explanation, 'Inspect the original text, scorer evidence and every linked saved restriction.',
                [f'artifact:{b.primary_id}#{p}' for p in batch], [b.evidence(p) for p in batch], section_refs=SECTIONS, impact='publication_block')
    _table(b, 'news-review', 'news-review-reasons', 'Original news review reasons', [('topic', 'Review topic'), ('code', 'Original identifier')], rows)
