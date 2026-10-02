"""Auditable current-news tone. No output enters Track A or predicts returns."""
from __future__ import annotations
from collections import defaultdict
from datetime import timedelta
import re
import json
import math
import statistics

from agent3.news_contracts import asof, timestamp, canonical_url, digest
from agent3.sentiment import get_scorer, validate_score
from tools.event_contracts import ticker, finite


def ingest(raw_items, *, as_of=None, max_age_days=7, exclusions=None):
    cutoff = asof(as_of)
    if type(max_age_days) is not int or not 1 <= max_age_days <= 30:
        raise ValueError('max_age_days must be an integer in [1,30]')
    if not isinstance(raw_items, list) or len(raw_items) > 1000:
        raise ValueError('news must be a list of at most 1000 records')
    excluded = exclusions if exclusions is not None else []
    out = []
    for index, raw in enumerate(raw_items):
        reason = None
        try:
            if not isinstance(raw, dict):
                raise ValueError('invalid_record')
            if raw.get('source_error'):
                raise ValueError(raw['source_error'])
            published = timestamp(raw.get('published_at'))
            retrieved = timestamp(raw['retrieved_at']) if raw.get('retrieved_at') else None
            if published > cutoff:
                raise ValueError('future_publication')
            if cutoff-published > timedelta(days=max_age_days):
                raise ValueError('stale_publication')
            if retrieved and (retrieved > cutoff or published > retrieved):
                raise ValueError('inconsistent_retrieval_time')
            headline, body = raw.get('headline'), raw.get('body', '')
            if not isinstance(headline, str) or not headline.strip() or not isinstance(body, str):
                raise ValueError('missing_or_invalid_text')
            if len(headline)+len(body) > 100000:
                raise ValueError('oversized_text')
            entities = raw.get('entities', [])
            if not isinstance(entities, list):
                raise ValueError('invalid_entity_tags')
            entities = sorted({ticker(e) for e in entities})
            flags = []
            if raw.get('language') not in ('en', 'en-US', 'en-GB'):
                flags.append('unsupported_or_unknown_language')
            url = canonical_url(raw.get('url'))
            if not url:
                flags.append('missing_article_url')
            if not retrieved:
                flags.append('missing_retrieval_timestamp')
            item = {**raw, 'published_at': published.isoformat(), 'day': published.date().isoformat(),
                    'retrieved_at': retrieved.isoformat() if retrieved else None,
                    'headline': headline.strip(), 'body': body.strip(), 'entities': entities,
                    'url': url, 'source': str(raw.get('source') or 'unknown'), 'review_reasons': flags}
            item['evidence_id'] = digest({'id': raw.get('id'), 'url': url, 'published_at': item['published_at'],
                                          'headline': item['headline'], 'body': item['body'], 'source': item['source']})
            out.append(item)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) and str(exc) in {
                'future_publication','stale_publication','inconsistent_retrieval_time','invalid_record',
                'missing_or_invalid_text','oversized_text','invalid_entity_tags','unsupported_provider_shape'} else 'invalid_timestamp_or_record'
        if reason:
            excluded.append({'input_index': index, 'id': raw.get('id') if isinstance(raw, dict) else None,
                             'stage': 'ingest', 'reason': reason})
    return sorted(out, key=lambda x: (x['published_at'], x['evidence_id']))


def _aliases(universe, aliases):
    if universe is None:
        raise ValueError('explicit news universe is required')
    result = {}
    for entity in universe:
        tk = ticker(entity)
        names = (aliases or {}).get(tk, [])
        if not isinstance(names, list) or len(names) > 20:
            raise ValueError('aliases must be bounded lists')
        if any(not isinstance(a, str) or len(a.strip()) < 3 or len(a) > 200 for a in names):
            raise ValueError('aliases must be strings of 3–200 characters')
        # Full exchange ticker or cashtag is explicit; bare short ticker may be a common word.
        result[tk] = list(dict.fromkeys([tk] if '.' in tk else [])) + names
    return result


def relevance_filter(items, universe=None, *, aliases=None, exclusions=None):
    names = _aliases(universe, aliases)
    out = []
    for item in items:
        text = item['headline']
        matches = {}
        for tk, candidates in names.items():
            hits = [a for a in candidates if re.search(r'(?<!\w)' + re.escape(a) + r'(?!\w)', text, re.I)]
            if re.search(r'\$' + re.escape(tk) + r'(?![\w.])', text, re.I):
                hits.append('$'+tk)
            if hits:
                matches[tk] = hits
        if not matches:
            if exclusions is not None:
                exclusions.append({'evidence_id': item['evidence_id'], 'stage': 'relevance',
                                   'reason': 'no_headline_entity_evidence'})
            continue
        flags = list(item.get('review_reasons', []))
        if len(matches) > 1 or len(item.get('entities', [])) > 1:
            flags.append('multi_entity_document_tone')
        out.append({**item, 'provider_entities': item.get('entities', []), 'entities': sorted(matches),
                    'relevance': {'method': 'headline_alias_or_cashtag', 'matches': matches,
                                  'scope': 'document-level tone associated with a headline mention; not entity-specific'},
                    'review_reasons': sorted(set(flags))})
    return out


def _tokens(text):
    return re.findall(r"\w+(?:['’]\w+)*|[$€£¥%]|[+-](?=\d)", text.casefold())


def dedup_cluster(items):
    """Conservative text identity, within 24 hours, across UTC midnight.

    Case/whitespace and punctuation changes can cluster; words (including negation),
    numbers and bodies must match. Corrections retain separate evidence.
    """
    ordered = sorted(items, key=lambda x: (x['published_at'], x['evidence_id']))
    reps = []
    identities = defaultdict(set)
    for item in ordered:
        signature = digest([_tokens(item['headline']), _tokens(item['body']), sorted(item['entities'])])
        for identity in (item.get('url'), (item.get('source'), item.get('id')) if item.get('id') else None):
            if identity:
                identities[str(identity)].add(signature)
    for item in ordered:
        signature = digest([_tokens(item['headline']), _tokens(item['body']), sorted(item['entities'])])
        flags = list(item.get('review_reasons', []))
        ids = [item.get('url'), (item.get('source'), item.get('id')) if item.get('id') else None]
        if any(len(identities[str(k)]) > 1 for k in ids if k):
            flags.append('article_identity_has_changed_text')
        item = {**item, 'review_reasons': sorted(set(flags))}
        rep = next((r for r in reps if r['_signature'] == signature and
                    timestamp(item['published_at'])-timestamp(r['published_at']) <= timedelta(hours=24)), None)
        if rep is None:
            rep = {**item, '_signature': signature, 'members': [], 'cluster_size': 0, 'sources': []}
            reps.append(rep)
        rep['members'].append(item)
        rep['cluster_size'] += 1
        rep['sources'] = sorted(set(rep['sources'] + [item['source']]))
        rep['review_reasons'] = sorted(set(rep['review_reasons'] + item['review_reasons']))
    for rep in reps:
        rep.pop('_signature')
        rep['cluster_id'] = digest(sorted({m['evidence_id'] for m in rep['members']}))
    return reps


def score_items(items, scorer=None):
    scorer = scorer if scorer is not None else get_scorer()
    out = []
    for item in items:
        flags = list(item.get('review_reasons', []))
        try:
            score = scorer.score(item)
            json.dumps(score, allow_nan=False)
            if not isinstance(score, dict) or not isinstance(score.get('scorer'), str):
                raise ValueError('invalid scorer record')
            if score.get('score') is None:
                validate_score({**score, 'score': 0.0})
            # None represents no evidence, never synthetic neutrality.
            if isinstance(score, dict) and score.get('score') is None:
                flags.extend(score.get('review_reasons', []))
                flags.append('sentiment_unavailable')
            else:
                validate_score(score)
            if score.get('flag_review'):
                flags.extend(score.get('review_reasons', []) or [score.get('reason') or 'scorer_requires_review'])
            record = {**item, 'sentiment': score.get('score'), 'sentiment_confidence': None,
                      'scorer': score['scorer'], 'score_evidence': score}
            for key in ('divergence', 'primary_score', 'secondary_score', 'reason'):
                if key in score:
                    record[key] = score[key]
        except Exception as exc:
            flags.append('scorer_failure')
            record = {**item, 'sentiment': None, 'sentiment_confidence': None,
                      'scorer': getattr(scorer, 'name', type(scorer).__name__),
                      'score_evidence': {'error_type': type(exc).__name__, 'reason': 'scorer_unavailable_or_invalid'}}
        record.update(review_reasons=sorted(set(flags)), flag_review=bool(flags))
        out.append(record)
    return out


def aggregate(items):
    buckets = defaultdict(list)
    for item in items:
        for entity in sorted(set(item['entities'])):
            buckets[(entity, item['day'])].append(item)
    signals = []
    for (entity, day), group in sorted(buckets.items()):
        scores = [g['sentiment'] for g in group if g['sentiment'] is not None]
        reasons = sorted({r for g in group for r in g['review_reasons']})
        held = bool(reasons) or not scores
        mean = statistics.mean(scores) if scores else None
        signals.append({'entity': entity, 'day': day, 'day_timezone': 'UTC',
                        'level': None if held else mean, 'diagnostic_level': mean if held else None,
                        'dispersion': statistics.pstdev(scores) if scores else None,
                        'count': len(group), 'scored_count': len(scores), 'confidence': None,
                        'confidence_note': 'No calibrated reliability estimate',
                        'count_note': 'Heuristic text clusters, not demonstrated independent stories',
                        'tone_scope': 'document-level; not entity-specific sentiment',
                        'total_coverage': sum(g['cluster_size'] for g in group),
                        'unique_sources': sorted({s for g in group for s in g['sources']}),
                        'cluster_ids': [g['cluster_id'] for g in group],
                        'scorers': sorted({g['scorer'] for g in group}),
                        'flag_review': held, 'review_reasons': reasons,
                        'publication_state': 'HELD_FOR_REVIEW' if held else 'DESCRIPTIVE',
                        'computed_by': 'news_funnel.aggregate (python)'})
    return signals


def run_funnel(raw_items, universe=None, scorer=None, *, aliases=None, as_of=None, max_age_days=7, data_mode='fixture'):
    cutoff = asof(as_of).isoformat()
    excluded = []
    ingested = ingest(raw_items, as_of=cutoff, max_age_days=max_age_days, exclusions=excluded)
    relevant = relevance_filter(ingested, universe, aliases=aliases, exclusions=excluded)
    clustered = dedup_cluster(relevant)
    scored = score_items(clustered, scorer)
    return finalize_news(scored, ingested, excluded, cutoff=cutoff, aliases=aliases,
                         max_age_days=max_age_days, data_mode=data_mode,
                         counts={'raw': len(raw_items), 'after_relevance': len(relevant), 'after_dedup': len(clustered)})


def finalize_news(scored, ingested, excluded, *, cutoff, aliases, max_age_days, data_mode, counts):
    """Shared publication boundary for execution and replay of retained scores."""
    signals = aggregate(scored)
    reasons = sorted({r for s in signals for r in s['review_reasons']})
    if excluded:
        reasons.append('excluded_input_evidence')
    if not signals:
        reasons.append('no_relevant_usable_news')
    if data_mode not in ('fixture', 'live'):
        raise ValueError('unknown news data mode')
    if data_mode == 'fixture':
        reasons.append('illustrative_fixture')
    held = bool(reasons)
    if held:
        for signal in signals:
            if signal['level'] is not None:
                signal['diagnostic_level'], signal['level'] = signal['level'], None
            signal.update(publication_state='HELD_FOR_REVIEW', flag_review=True,
                          review_reasons=sorted(set(signal['review_reasons'] + reasons)))
    return {'schema_version': 1, 'status': 'held' if held else 'completed',
            'publication_state': 'HELD_FOR_REVIEW' if held else 'DESCRIPTIVE',
            'review_reasons': sorted(set(reasons)), 'data_mode': data_mode,
            'as_of': cutoff, 'max_age_days': max_age_days, 'aliases': aliases or {},
            'signals': signals, 'scored_items': scored, 'exclusions': excluded,
            'ingested_items': ingested,
            'funnel': {'raw': counts['raw'], 'ingested': len(ingested), 'after_relevance': counts['after_relevance'],
                       'after_dedup': counts['after_dedup'], 'entity_days': len(signals)},
            'scope_note': 'Current retrieved news only; not a historical point-in-time archive or return forecast'}


def _publishable_signal(result, signal):
    """Do not expose a saved level based only on a stale publication label."""
    try:
        if result.get('status') != 'completed' or result.get('data_mode') != 'live' or result.get('publication_state') != 'DESCRIPTIVE' or result.get('review_reasons') or result.get('exclusions'):
            return False
        if signal.get('publication_state') != 'DESCRIPTIVE' or signal.get('flag_review') is not False or signal.get('review_reasons'):
            return False
        if not finite(signal.get('level')) or not -1 <= signal['level'] <= 1:
            return False
        ids = signal['cluster_ids']
        if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
            return False
        stories = [i for i in result['scored_items'] if i['cluster_id'] in ids]
        if len(stories) != len(ids) or type(signal['count']) is not int or signal['count'] != len(stories):
            return False
        scores = []
        for story in stories:
            if story.get('flag_review') or story.get('review_reasons') or signal['entity'] not in story['entities'] or signal['day'] != story['day']:
                return False
            evidence = validate_score(story['score_evidence'])
            if evidence.get('flag_review') or evidence.get('review_reasons') or evidence['scorer'] == 'stub':
                return False
            if story['sentiment'] != evidence['score']:
                return False
            scores.append(evidence['score'])
        return math.isclose(statistics.mean(scores), signal['level'], rel_tol=1e-12, abs_tol=1e-12)
    except (ValueError, KeyError, TypeError):
        return False


def render_news(result):
    signals = result.get('signals', [])
    allowed = bool(signals) and all(_publishable_signal(result, s) for s in signals)
    state = 'DESCRIPTIVE' if allowed else 'HELD_FOR_REVIEW'
    lines = [f'NEWS TONE — {state}', result.get('scope_note', ''),
             f"Review: {result.get('review_reasons', [])}"]
    for s in signals:
        value = s.get('level') if allowed else None
        lines.append(f"  {s['entity']} {s['day']} UTC: document tone={value if value is not None else 'HELD'}; clusters={s['count']}; scorers={s['scorers']}")
    lines.append(f"Excluded records: {len(result.get('exclusions', []))}; scored evidence: {len(result.get('scored_items', []))}")
    return '\n'.join(lines)
