"""Offline raw-price oracle for retained issuer-date validation bundles.

python -m scripts.check_agent3_closure BUNDLE [--mcp] [--output FILE]
No provider calls; --mcp additionally exercises the real statistics subprocess.
This verifies calculations and expected holds, not research eligibility.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from agent3 import bundles
from tools.event_study import run_event_study


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def verify(bundle, *, mcp=False):
    record = bundle['record']
    es = record['assembled_inputs']
    plan = es['study_plan']
    require(plan.get('validation_only') is True, 'requires a validation-only source plan')
    require(record['status'] == 'held', 'validation must remain held')
    study = record['result']['study']
    expected = [(tk, e['release_timestamp']) for tk, c in plan['companies'].items()
                for e in c['reviewed_events']]
    actual = [(e['ticker'], e['release_timestamp']) for e in es['events']]
    require(bool(expected) and sorted(actual) == sorted(expected), 'missing or unexpected issuer events')
    require(not es.get('excluded_peers'), 'excluded issuer')
    checks = []
    for kind, events, results in [('event', es['events'], study['per_event']),
                                 ('control', es['placebo_events'], study['placebo']['per_event'])]:
        require(len(events) == len(results), 'rejected or missing calculations')
        for event, result in zip(events, results):
            tk = event['ticker']
            snapshot = record['provider_snapshots'][tk]
            stock, market = dict(snapshot['stock_prices']), dict(snapshot['benchmark_prices'])
            dates = sorted(stock.keys() & market.keys())
            i = dates.index(event['anchor_date'])
            require(i >= 281 and i + 1 < len(dates), 'insufficient raw-price window')
            require(event['est_dates'] == dates[i-280:i-30], 'estimation date mismatch')
            require(event['window_dates'] == dates[i-1:i+2], 'event window mismatch')
            arrays = {}
            for prefix, indices in [('est', range(i-280, i-30)), ('evt', range(i-1, i+2))]:
                for name, prices in [('stock', stock), ('market', market)]:
                    key = prefix + '_' + name
                    arrays[key] = np.array([prices[dates[j]] / prices[dates[j-1]] - 1 for j in indices])
                    require(np.allclose(arrays[key], event[key], rtol=1e-12, atol=1e-14), key + ' mismatch')
            alpha, beta = np.linalg.lstsq(np.column_stack([np.ones(250), arrays['est_market']]),
                                         arrays['est_stock'], rcond=None)[0]
            car = float((arrays['evt_stock'] - alpha - beta * arrays['evt_market']).sum())
            require(np.allclose([alpha, beta, car], [result['alpha'], result['beta'], result['car']],
                                rtol=1e-10, atol=1e-12), 'independent OLS mismatch')
            if kind == 'event':
                source = next(e for e in plan['companies'][tk]['reviewed_events']
                              if e['release_timestamp'] == event['release_timestamp'])
                require(event['anchor_date'] == source['expected_anchor_date'], 'issuer anchor mismatch')
                require(event['session'] == source['session'], 'issuer session mismatch')
                require(event['date_status'] == 'source_checked', 'automatic check mislabeled as human review')
            checks.append({'kind': kind, 'ticker': tk, 'anchor_date': event['anchor_date'],
                           'session': event['session'], 'car': car, 'raw_price_oracle': 'passed'})
    replay = bundles.replay(bundle)
    require(replay['verification'] == 'matched', 'offline replay mismatch')
    require(replay['result']['scenario']['distribution'] is None, 'held distribution published')
    html = bundles.export_html(bundle, replay)
    require('Historical quantiles:' not in html, 'held export publishes quantiles')
    parity = 'not_run'
    if mcp:
        from mcp_server.client import run_event_study as remote
        local = run_event_study(es['events'], es['event_type'], es['placebo_events'])
        require(remote(es['events'], es['event_type'], es['placebo_events']) == local, 'MCP parity mismatch')
        require(local == study, 'saved calculation mismatch')
        parity = 'passed'
    return {'attempt_id': record['run_id'], 'bundle_sha256': bundle['bundle_sha256'],
            'status': 'passed', 'scope': 'calculation/date validation; no publication approval',
            'events': checks, 'offline_replay': 'matched', 'held_export': 'passed', 'mcp_parity': parity}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle')
    parser.add_argument('--mcp', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args()
    result = verify(bundles.read_bundle(args.bundle), mcp=args.mcp)
    if args.output:
        bundles.write_once(Path(args.output), result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
