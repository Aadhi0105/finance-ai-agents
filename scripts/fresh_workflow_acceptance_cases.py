"""Deterministic fictional volume cases, shared by 4D tests and local preview.

No credentials, permissions, network access or execution are provided here.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ('research', 'monitoring', 'events', 'news')


def package(workflow):
    path = (ROOT / 'docs/webapp/fresh-analysis/examples/complete-kit.json'
            if workflow == 'research' else ROOT / 'fixtures/local_workflows' / (workflow + '.json'))
    value = json.loads(path.read_text())
    p = value['payload']
    if workflow == 'research':
        latest = deepcopy(p['periods'][-1])
        p['periods'] = []
        for year in range(2016, 2026):
            period = deepcopy(latest)
            period.update(period_start=f'{year}-01-01', period_end=f'{year}-12-31')
            period['observations']['revenue']['value'] = str((year - 2015) * 100_000_000)
            p['periods'].append(period)
        value['sources'][0].update(period_start='2016-01-01', period_end='2025-12-31')
        # Refresh only this fictional quote date, never real observations.
        day = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        p['quote']['as_of'] = day
        value['sources'][1].update(period_start=day, period_end=day)
    elif workflow == 'monitoring':
        base = deepcopy(p['items'][0])
        days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(100)]
        p.update(as_of=days[-1], items=[])
        # One source covers all twenty policies on the same multiple basis.
        value['sources'] = [value['sources'][0]]
        value['sources'][0].update(period_start=days[0], period_end=days[-1])
        for i in range(20):
            item = deepcopy(base)
            item.update(id=f'policy-{i:02}', metric=f'Fictional policy {i + 1:02}', threshold='3')
            item['observations'] = [dict(date=day, value='2.5' if j < 50 else '3.5',
                                         source_id=value['sources'][0]['source_id']) for j, day in enumerate(days)]
            if i % 2:
                item['observations'][-1]['value'] = None
            p['items'].append(item)
    elif workflow == 'events':
        base = deepcopy(p['events'][0])
        p.update(events=[], controls=[])
        for i in range(20):
            for control in (False, True):
                event = deepcopy(base)
                event['ticker'] = f'N{i:03}'
                offset = timedelta(days=7 if control else 0)
                for key in ('event_date', 'anchor_date'):
                    event[key] = (date.fromisoformat(event[key]) - offset).isoformat()
                for key in ('est_dates', 'window_dates'):
                    event[key] = [(date.fromisoformat(day) - offset).isoformat() for day in event[key]]
                p['controls' if control else 'events'].append(event)
        days = [d for e in p['events'] + p['controls'] for d in e['est_dates'] + e['window_dates']]
        value['sources'][0].update(period_start=min(days), period_end=max(days))
    else:
        base = deepcopy(p['articles'][0])
        p['articles'] = []
        p['word_list']['positive'] = ['growth'] + ['positive' + letters(i) for i in range(99)]
        p['word_list']['negative'] = ['decline'] + ['negative' + letters(i) for i in range(99)]
        # Distinct filler tokens prevent accidental text clustering at max volume.
        for i in range(100):
            article = deepcopy(base)
            token = 'document' + letters(i)
            article.update(id=f'article-{i:03}', headline=f'Northstar Components growth bulletin {token}',
                           body=((token + ' ') * 600)[:5000], text_scope='supplied_text',
                           url=f'https://example.invalid/news/{i}')
            p['articles'].append(article)
    return value


def letters(number):
    return chr(97 + number // 26) + chr(97 + number % 26)


def entity(workflow):
    return dict(name=f'Northstar {workflow} volume case · fictional',
                kind='group' if workflow == 'events' else 'company',
                ticker=None if workflow == 'events' else 'NSTAR',
                members=[f'N{i:03}' for i in range(20)] if workflow == 'events' else [])
