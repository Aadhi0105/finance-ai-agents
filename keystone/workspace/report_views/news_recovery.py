"""News 1.2: an early failed attempt is not a successful empty news feed."""
from . import news_context
from .common import text_cell
from .values import get


def extend(b):
    if isinstance(get(b.source, '/record/result'), dict):
        news_context.extend(b)
        return
    if get(b.source, '/record/status') not in {'failed', 'unavailable', 'refused'}:
        raise ValueError('An analytical result is required for this news state')
    pointer = '/record'
    evidence = b.evidence(pointer, 'Original incomplete news attempt')
    b.section('news-context', 'Saved attempt basis', 'Execution stopped before an analytical news result was retained.')
    fields = [('coverage-state', 'Coverage state', 'retrieval_failed'),
              ('cutoff', 'Requested cutoff (not an observation)', get(b.source, pointer + '/request/as_of') or 'Not retained'),
              ('max-age', 'Requested maximum publication age', get(b.source, pointer + '/request/max_age_days', 'Not retained')),
              ('input-basis', 'Input basis', 'Saved synthetic attempt; coverage not established'),
              ('terminal-reason', 'Saved terminal reason', get(b.source, pointer + '/reason') or 'Not retained')]
    b.table('news-basis', 'Saved incomplete news attempt', [('field', 'Basis'), ('value', 'Saved description')],
        [dict(id=ident, cells=[text_cell('field', label), text_cell('value', value)], evidence_refs=[evidence]) for ident, label, value in fields])
    b.view['sections'][-1]['table_refs'].append('news-basis')
    ident = b.chart('news-coverage', 'Saved news coverage', 'No analytical processing counts were retained.',
                    'bar', 'count', restriction='news_attempt_incomplete')
    next(s for s in b.view['sections'] if s['id'] == 'coverage')['chart_refs'].append(ident)
    b.review('delivery', 'News attempt stopped without a result',
        'The saved attempt stopped before retaining an analytical news result. Coverage and document tone cannot be established; this is not a valid empty feed.',
        'Inspect the original terminal status and reason. A new controlled attempt would be separate work.',
        [f'artifact:{b.primary_id}#/record'], [evidence], section_refs=['coverage', 'retained-news', 'tone', 'news-context'], impact='publication_block')
    b.view['summary'].update(text='The saved synthetic news attempt stopped without an analytical result. Coverage is unavailable and published tone is withheld. No conclusion about the presence or absence of company news is supported.',
        template_id='news-retrieval-summary-v1', evidence_refs=[evidence])
