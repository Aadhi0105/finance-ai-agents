"""Verify retained populated live-news retrieval, accounting, holds and replay.

python -m scripts.check_agent3_news_acceptance BUNDLE --output NEW_JSON --html NEW_HTML
No provider or scorer is invoked. This is execution acceptance, not tone accuracy.
"""
import argparse
from agent3 import bundles
from agent3.news_live import shape_items
from agent3.news_contracts import canonical_url


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify(bundle):
    record = bundle['record']
    fetched, result = record['fetched'], record['result']
    require(record['request']['data_mode'] == 'live', 'requires live evidence')
    require(fetched['source'] == 'yfinance.Search', 'unsupported retrieval source')
    require(fetched['transport']['status'] == 'populated' and fetched['transport']['http_status'] == 200,
            'requires populated successful retrieval')
    raw = fetched['raw_items']
    require(bool(raw) and fetched['raw_count'] == len(raw), 'raw count mismatch')
    shaped = shape_items(fetched['ticker'], raw, retrieved_at=fetched['retrieved_at'])
    for item in shaped:
        item.update(retrieval_query=fetched['query'],
                    text_scope='headline_and_provider_summary' if item.get('body') else 'headline_only')
    require(shaped == fetched['items'] == record['input_items'], 'retained provider shaping mismatch')
    require(fetched['shaped_count'] == len(shaped), 'shaped count mismatch')
    f = result['funnel']; excluded = result['exclusions']
    require(f['raw'] == len(raw), 'funnel input mismatch')
    require(f['ingested'] + sum(e['stage'] == 'ingest' for e in excluded) == len(raw), 'ingestion accounting mismatch')
    require(f['after_relevance'] + sum(e['stage'] == 'relevance' for e in excluded) == f['ingested'], 'relevance accounting mismatch')
    scored = result['scored_items']
    require(bool(scored) and len(scored) == f['after_dedup'], 'no scored relevant evidence')
    require(sum(i['cluster_size'] for i in scored) == f['after_relevance'], 'cluster accounting mismatch')
    for item in scored:
        require(bool(item['relevance']['matches']), 'missing headline relevance evidence')
        require(canonical_url(item['url']) == item['url'], 'invalid source link')
        evidence = item['score_evidence']
        require('error_type' not in evidence, 'scorer failed')
        if evidence['scorer'] == 'lm':
            pos, neg = len(evidence['matched_positive']), len(evidence['matched_negative'])
            require((pos,neg,pos+neg) == (evidence['pos_hits'],evidence['neg_hits'],evidence['tone_words']), 'lexical count mismatch')
            require(evidence['score'] == ((pos-neg)/(pos+neg) if pos+neg else None), 'lexical arithmetic mismatch')
        if item.get('text_scope') == 'headline_only':
            require('headline_only_evidence' in item['review_reasons'], 'headline-only evidence not held')
    require(record['status'] == result['status'] == 'held', 'expected conservative live LM hold')
    require(all(s['level'] is None for s in result['signals']), 'held level published')
    replay = bundles.replay(bundle)
    require(replay['verification'] == 'matched', 'offline replay mismatch')
    html = bundles.export_html(bundle, replay)
    require('HELD_FOR_REVIEW' in html and 'Retained news evidence' in html, 'held evidence export missing')
    return {'status':'passed', 'scope':'populated retrieval/accounting/replay; not sentiment accuracy or complete news coverage',
            'attempt_id':record['run_id'], 'bundle_sha256':bundle['bundle_sha256'],
            'ticker':fetched['ticker'], 'query':fetched['query'], 'funnel':f,
            'exclusions': {stage:sum(e['stage']==stage for e in excluded) for stage in ('ingest','relevance')},
            'missing_lexical_scores':sum(i['sentiment'] is None for i in scored),
            'replay':'matched', 'held_export':'passed'}, html


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle'); p.add_argument('--output'); p.add_argument('--html')
    args=p.parse_args()
    result,html=verify(bundles.read_bundle(args.bundle))
    if args.output: bundles.write_once(args.output,result)
    if args.html: bundles.write_text_once(args.html,html)
    import json
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
