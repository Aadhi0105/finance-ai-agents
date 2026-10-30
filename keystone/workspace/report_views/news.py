"""Coverage, retained text and restricted tone have separate representations."""
from .common import text_cell
from .values import get


def build(b):
    b.view['identity']['ticker'] = get(b.source, '/record/request/ticker')
    coverage = []
    for key, label in [('raw', 'Input records'), ('after_relevance', 'Relevant records'), ('after_dedup', 'Retained headline clusters')]:
        coverage.append(b.metric('coverage-' + key.replace('_', '-'), label, '/record/result/funnel/' + key, 'count'))
    signals = get(b.source, '/record/result/signals', []) or []
    tone = []
    for i, row in enumerate(signals):
        published = b.metric('published-tone-' + str(i), 'Published tone · ' + str(row.get('entity')),
            f'/record/result/signals/{i}/level', 'score', period=str(row.get('day', b.run.period)),
            restriction='synthetic_published_tone_withheld')
        diagnostic = b.metric('diagnostic-tone-' + str(i), 'Saved diagnostic tone · ' + str(row.get('entity')),
            f'/record/result/signals/{i}/diagnostic_level', 'score', period=str(row.get('day', b.run.period)), visibility='diagnostic')
        tone.extend([published, diagnostic])
    if not signals:
        tone.append(b.metric('published-tone', 'Published tone', '/record/result/signals/0/level',
                              'score', restriction='published_tone_unavailable'))
    rows = []
    for i, item in enumerate(get(b.source, '/record/result/scored_items', []) or []):
        rows.append(dict(id='headline-' + str(i), cells=[
            text_cell('headline', item.get('headline')), text_cell('publisher', item.get('source')),
            text_cell('published', item.get('published_at')), text_cell('scope', item.get('text_scope', 'Retained headline/text only'))],
            evidence_refs=[b.evidence(f'/record/result/scored_items/{i}', 'Retained news evidence')]))
    headlines = b.table('retained-headlines', 'Retained news evidence',
        [('headline', 'Headline'), ('publisher', 'Source'), ('published', 'Published at (original timezone)'), ('scope', 'Text scope')], rows)
    b.section('coverage', 'News coverage', 'Coverage counts are distinct from independent stories or a market conclusion.',
              metrics=coverage, findings=[b.observation(m) for m in coverage])
    b.section('retained-news', 'Retained stories', 'Inspect the retained text, timestamps and source basis.', tables=[headlines])
    b.section('tone', 'Text-tone evidence', 'A withheld published level is not neutral, zero or a trading signal.', metrics=tone)
    evidence = b.maybe_evidence('/record/result', 'Original news publication and exclusion evidence')
    b.review('narrative_support', 'Tone and relevance limitations',
        'Published tone is withheld in this synthetic workspace. Diagnostic tone concerns retained document text, not a verified company-specific investment conclusion.',
        'Read scorer restrictions, relevance, duplicates, exclusions and the original publication state.',
        [f'artifact:{b.primary_id}#/record'], [evidence], section_refs=['coverage', 'retained-news', 'tone'])
    b.view['glossary'] = [dict(term='Headline cluster', definition='A heuristic text grouping, not proof of independent stories.'),
        dict(term='Diagnostic tone', definition='A descriptive score for supplied text; a null published level remains withheld.')]
