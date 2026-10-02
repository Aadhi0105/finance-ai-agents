"""Bounded Track B worker. Saves the exact scored evidence used for rendering."""
import sys
from agent3.execution import Attempt, read_record, EXIT_CODES
from agent3.news_live import fetch_entity_news
from agent3.news_funnel import run_funnel
from agent3.sentiment import get_scorer
from agent3.news_contracts import asof


def execute(attempt):
    request = attempt.record['request']
    try:
        attempt.checkpoint('scorer_setup', {})
        scorer = get_scorer(request['scorer'])
        if request['data_mode'] == 'fixture':
            attempt.checkpoint('fixture_input', {})
            payload = read_record(request['fixture'])
            items = payload['items']
        else:
            attempt.checkpoint('news_fetch', {})
            fetched = fetch_entity_news(request['ticker'])
            attempt.checkpoint('news_fetched', {'fetched': fetched})
            items = fetched['items']
        cutoff = request.get('as_of') or asof().isoformat()
        attempt.checkpoint('news_scoring', {'input_items': items, 'as_of': cutoff})
        result = run_funnel(items, {request['ticker']}, scorer,
                            aliases={request['ticker']: request['aliases']}, as_of=cutoff,
                            max_age_days=request['max_age_days'], data_mode=request['data_mode'])
        attempt.checkpoint('news_result', {'result': result})
        if result['scored_items'] and all('error_type' in i['score_evidence'] for i in result['scored_items']):
            attempt.finish('unavailable', 'all_scorers_unavailable_or_invalid')
        else:
            attempt.finish(result['status'])
    except Exception as exc:
        attempt.finish('unavailable', 'news_stage_unavailable', type(exc).__name__)
    return EXIT_CODES[attempt.record['status']]


if __name__ == '__main__':
    path = sys.argv[1]
    raise SystemExit(execute(Attempt(path, read_record(path))))
