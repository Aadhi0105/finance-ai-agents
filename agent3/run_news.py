"""Current-news document tone with explicit review controls and saved evidence."""
import argparse
import os
from pathlib import Path
import sys
from agent3.execution import Attempt, ROOT, run_bounded
from agent3.news_funnel import render_news
from agent3.news_contracts import asof
from tools.event_contracts import ticker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ticker')
    parser.add_argument('--alias', action='append', default=[], help='explicit issuer headline alias, repeatable')
    parser.add_argument('--news-query', help='explicit provider search query (default: ticker); does not establish relevance')
    parser.add_argument('--scorer', choices=['lm','finbert','divergence','stub'])
    parser.add_argument('--demo', action='store_true', help='allow stub only with an explicit fixture')
    parser.add_argument('--fixture', help='offline JSON with items list')
    parser.add_argument('--as-of', help='timezone-aware cutoff; required for historical fixtures')
    parser.add_argument('--max-age-days', type=int, default=7)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--db', default=str(ROOT/'state'/'catalyst.duckdb'), help='bundle index database')
    parser.add_argument('--output-dir', default=str(ROOT/'output'/'agent3-news'))
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env', override=False)
    try:
        tk = ticker(args.ticker)
        name = args.scorer or os.environ.get('AGENT_SENTIMENT_SCORER', 'lm')
        if name not in ('lm', 'finbert', 'divergence', 'stub'):
            raise ValueError('unsupported scorer')
        if name == 'stub' and not (args.demo and args.fixture):
            raise ValueError('stub requires --demo and --fixture')
        if args.demo and name != 'stub':
            raise ValueError('--demo is reserved for fixture stub scores')
        if not 30 <= args.timeout <= 3600 or not 1 <= args.max_age_days <= 30:
            raise ValueError('invalid timeout or freshness window')
        if any(len(a.strip()) < 3 or len(a) > 200 for a in args.alias) or len(args.alias) > 20:
            raise ValueError('aliases must be 3–200 characters, at most 20')
        if args.news_query is not None and (args.fixture or not 1 <= len(args.news_query.strip()) <= 200):
            raise ValueError('news query requires live mode and 1–200 characters')
        if args.as_of:
            asof(args.as_of)
        if args.fixture and not args.as_of:
            raise ValueError('fixture mode requires --as-of')
        request = {'db': str(Path(args.db).resolve()), 'ticker': tk, 'aliases': args.alias, 'scorer': name,
                   'data_mode': 'fixture' if args.fixture else 'live', 'news_query': args.news_query,
                   'fixture': str(Path(args.fixture).resolve()) if args.fixture else None,
                   'as_of': args.as_of, 'max_age_days': args.max_age_days}
        attempt = Attempt.create(args.output_dir, request)
        code = run_bounded(attempt, args.timeout, worker_module='agent3.news_execution')
        result = attempt.record.get('result')
        if result:
            print(render_news(result))
        else:
            print(f"{attempt.record['status'].upper()}: {attempt.record.get('reason')} at {attempt.record['stage']}")
        print(f'Run record: {attempt.path}')
        print(f'Immutable bundle: {attempt.path.with_name("bundle.json")}')
        return code
    except (OSError, ValueError) as exc:
        print(f'REFUSED: news configuration/input ({type(exc).__name__}); check scorer, aliases, dates and paths.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
