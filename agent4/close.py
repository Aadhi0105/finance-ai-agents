"""Bounded offline close: approved budget + actuals delta -> frozen evidence.

Database commit is authoritative. Delivery is an atomic, retryable export of saved
bytes, never a recalculation against newer actuals. No ERP/approval service implied.
"""
from __future__ import annotations

import argparse
import calendar
from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from agent4.contracts import cents
from agent4.hierarchy import rollup
from agent4.output import board_pack
from agent4.reforecast import reforecast
from agent4.state import VarianceStore, canonical, digest, identifier, iso_period

SCHEMA_VERSION = 1


def _fields(value, allowed, required=None):
    if not isinstance(value, dict) or set(value) - set(allowed) or not set(required or allowed) <= set(value):
        raise ValueError(f'expected fields: {", ".join(sorted(allowed))}')


def _safe_run_id(value):
    if not isinstance(value, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', value) is None:
        raise ValueError('run_id must be 1–100 letters, digits, underscores or hyphens')
    return value


def _periods(year, frequency):
    step = {'monthly': 1, 'quarterly': 3, 'annual': 12}.get(frequency)
    if step is None:
        raise ValueError('frequency must be monthly, quarterly or annual')
    return [date(year, month, calendar.monthrange(year, month)[1]).isoformat() for month in range(step, 13, step)]


def _amount(value):
    cents(value)
    return ('-' if value < 0 else '') + f'{abs(value)//100}.{abs(value)%100:02d}'


def _topology(template):
    """Require stable IDs; financial inputs and histories come only from state."""
    ids, leaves, names = set(), set(), set()
    def visit(node, root=False, depth=0):
        if depth > 50:
            raise ValueError('tree too deep')
        _fields(node, {'name','node_id','sign','root_measure','children','leaf'}, {'name','node_id'})
        ident = identifier(node['node_id'], 'node_id')
        label = identifier(node['name'], 'name')
        if ident in ids or label in names:
            raise ValueError('duplicate node ID or name')
        ids.add(ident); names.add(label)
        if not root and node.get('sign') not in ('add','subtract'):
            raise ValueError('non-root nodes require a sign')
        if ('children' in node) == ('leaf' in node):
            raise ValueError('node requires leaf or children')
        if 'leaf' in node:
            _fields(node['leaf'], {'type'})
            if node['leaf']['type'] not in ('revenue','variable_cost','fixed_cost'):
                raise ValueError('invalid leaf type')
            leaves.add(ident)
        else:
            if not isinstance(node['children'], list) or not node['children']:
                raise ValueError('children must be nonempty')
            for child in node['children']:
                visit(child, depth=depth+1)
    visit(template, root=True)
    return leaves


def _totals(template, values, period):
    out = {}
    def visit(node):
        if 'leaf' in node:
            value = values[(node['node_id'], period)]
        else:
            value = sum((1 if c['sign']=='add' else -1)*visit(c) for c in node['children'])
        out[node['node_id']] = cents(value, 'node total')
        return value
    visit(template)
    return out


def _code_identity():
    root = Path(__file__).resolve().parent.parent
    paths = sorted((root/'agent4').glob('*.py')) + [root/'tools/statistical_checks.py', root/'mcp_server/client.py']
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def _freshness(store, request):
    latest = store.con.execute('SELECT run_id,close_period FROM a4_heads WHERE entity=?', [request['entity']]).fetchone()
    supersedes = request.get('supersedes')
    if latest is None:
        if supersedes is not None:
            raise ValueError('supersedes requires a previously committed close')
        store.con.execute('INSERT INTO a4_heads VALUES (?,?,?)', [request['entity'],request['run_id'],request['close_period']])
        return
    if request['close_period'] < latest[1]:
        raise ValueError('stale close: historical corrections require a new current close snapshot')
    if request['close_period'] == latest[1]:
        if supersedes != latest[0]:
            raise ValueError('close already committed: replay its run_id or explicitly supersede the latest run')
    elif supersedes is not None:
        raise ValueError('supersedes is only for a correction of the latest close period')
    # This write also arbitrates concurrent closes for an existing entity.
    store.con.execute('UPDATE a4_heads SET run_id=?,close_period=? WHERE entity=?',
                      [request['run_id'],request['close_period'],request['entity']])


def execute_close(store, request):
    """Record attempts separately so interrupted work can be distinguished from a commit."""
    from uuid import uuid4
    if not isinstance(request, dict):
        raise ValueError('close request must be an object')
    run_id = _safe_run_id(request.get('run_id'))
    request_digest = digest(request)
    attempt_id = uuid4().hex
    store.attempt_event(attempt_id, run_id, request_digest, 'started')
    try:
        result = _execute_close(store, request)
    except BaseException as exc:
        store.attempt_event(attempt_id, run_id, request_digest, 'failed', str(exc))
        raise
    store.attempt_event(attempt_id, run_id, request_digest, result['status'])
    return result


def _execute_close(store, request):
    """Commit sources, forecasts and full bundle together, or roll back everything.

    The same run_id + identical request replays before any freshness/recalculation.
    Failures before commit leave no accounting state; delivery is separate.
    """
    _fields(request, {'run_id','entity','close_period','frequency','budget','actuals','tree','supersedes','data_kind'},
            {'run_id','entity','close_period','frequency','budget','actuals','tree'})
    run_id = _safe_run_id(request['run_id'])
    request_digest = digest(request)
    existing = store.get_run(run_id)
    if existing:
        if existing['request_digest'] != request_digest:
            raise ValueError('run_id conflict: changed inputs require a new run_id')
        return {**existing, 'status':'replayed'}
    if request.get('data_kind', 'unverified') not in ('synthetic', 'unverified'):
        raise ValueError('data_kind must be synthetic or unverified')
    entity = identifier(request['entity'], 'entity')
    close = iso_period(request['close_period'])
    annual = _periods(date.fromisoformat(close).year, request['frequency'])
    if close not in annual:
        raise ValueError('close must be a calendar reporting-period end')
    leaves = _topology(request['tree'])
    for kind in ('budget', 'actuals'):
        fields = {'version','rows','source'} | ({'approved'} if kind=='budget' else set())
        _fields(request[kind], fields)
        identifier(request[kind]['source'], kind+' source')
    if request['budget']['approved'] is not True:
        raise ValueError('an explicitly approved budget basis is required')
    budget_version = request['budget']['version']
    actuals_version = request['actuals']['version']
    with store.transaction():
        _freshness(store, request)
        for kind in ('budget','actuals'):
            data = request[kind]
            meta = {'entity':entity,'currency':'EUR','frequency':request['frequency'],'source':data['source']}
            if kind == 'budget':
                meta['approved'] = True
                store.set_budget(data['version'], data['rows'], metadata=meta)
            else:
                store.append_actuals(data['version'], data['rows'], metadata=meta)
        entity_versions = [v for v in store.versions('actuals') if v['metadata'].get('entity') == entity]
        if entity_versions[-1]['version'] != actuals_version:
            raise ValueError('stale actuals basis: use the latest entity delta for a new close')
        budget_rows = store.get_budget(budget_version)
        actuals_rows = store.actuals_snapshot(actuals_version)
        # Reject changed cadence/currency even for older deltas in the same entity.
        for version in {r['source_version'] for r in actuals_rows}:
            meta = store.version_info('actuals', version)['metadata']
            if meta.get('currency') != 'EUR' or meta.get('frequency') != request['frequency']:
                raise ValueError('actuals history has incompatible currency or frequency')
        for rows in (budget_rows, actuals_rows):
            for row in rows:
                period = row['period']
                if row['line'] not in leaves or period not in _periods(date.fromisoformat(period).year, request['frequency']):
                    raise ValueError('source panel contains an unknown line or misaligned period')
        if any(row['period'] > close for row in actuals_rows):
            raise ValueError('actuals contain future observations beyond the close')
        budget = {(r['line'],r['period']):r['amount_cents'] for r in budget_rows}
        actuals = {(r['line'],r['period']):r['amount_cents'] for r in actuals_rows}
        elapsed = annual.index(close)+1
        if any((line,p) not in budget for line in leaves for p in annual):
            raise ValueError('budget is incomplete for the full reporting year')
        if any((line,p) not in actuals for line in leaves for p in annual[:elapsed]):
            raise ValueError('actuals are incomplete for closed YTD periods')
        candidate_history = sorted({p for _,p in actuals if p < close})
        history_periods = [p for p in candidate_history if all((line,p) in actuals and (line,p) in budget for line in leaves)]
        held_history = sorted(set(candidate_history)-set(history_periods))
        bt = {p:_totals(request['tree'],budget,p) for p in sorted(set(annual+history_periods))}
        at = {p:_totals(request['tree'],actuals,p) for p in sorted(set(history_periods+annual[:elapsed]))}
        tree = deepcopy(request['tree'])
        def bind(node):
            ident = node['node_id']
            node.update(budget_cents=bt[close][ident],actual_cents=at[close][ident],
                        observation_history=[{'period':p,'variance_cents':cents(at[p][ident]-bt[p][ident])} for p in history_periods],
                        history_frequency=request['frequency'])
            if 'leaf' in node:
                node['leaf'].update(name=node['name'], budget={'amount':_amount(bt[close][ident])}, actual={'amount':_amount(at[close][ident])})
            for child in node.get('children',[]):
                bind(child)
        bind(tree)
        tree['context'] = {'entity':entity,'currency':'EUR','monetary_unit':'major','close_date':close,
                           'source_version':f'{budget_version} / {actuals_version}'}
        result = rollup(tree)
        forecasts = {}
        def forecast(node):
            ident = node['node_id']
            ytd = sum(at[p][ident] for p in annual[:elapsed])
            phasing = [bt[p][ident] for p in annual]
            forecasts[ident] = reforecast(cents(ytd), cents(sum(phasing)), elapsed, len(annual),
                budget_phasing_cents=phasing,
                variance_history_cents=[at[p][ident]-bt[p][ident] for p in history_periods]+[node['total_variance_cents']],
                direction='higher_is_better' if node['sign_toward_profit']==1 else 'lower_is_better',
                name=ident, persistence=node['persistence']['persistence'], close_period=close)
            for child in node.get('children',[]):
                forecast(child)
        forecast(result)
        pack = board_pack(result, reforecast_by_line=forecasts)
        lineage = {'budget':store.version_info('budget',budget_version),
                   'actuals':store.version_info('actuals',actuals_version),
                   'actuals_semantics':'effective ordered deltas; later versions supersede matching line/period only',
                   'history_budget_basis':'selected approved budget, including any supplied prior-period budgets',
                   'completeness':'all leaf lines, full-year budget and closed YTD actuals verified',
                   'history_periods':history_periods,'excluded_incomplete_history_periods':held_history,
                   'forecast_basis':'YTD actuals and annual phasing derived from the frozen source panels; amount-only decomposition'}
        bundle = {'schema_version':SCHEMA_VERSION, 'run_id':run_id, 'request_digest':request_digest,
                  'request':deepcopy(request), 'lineage':lineage, 'code_identity':_code_identity(),
                  'sources':{'budget':budget_rows,'effective_actuals':actuals_rows},
                  'bound_tree':tree, 'report':pack}
        rf_rows = []
        for ident, rf in forecasts.items():
            rf_rows.append({'line':ident,'landing_cents':rf.get('projected_landing_cents'), 'prob_hit':rf.get('prob_hit_target'),
                'status':'held' if rf.get('projected_landing_cents') is None else 'computed',
                'probability_reason':rf.get('error') or rf.get('reason') or rf.get('confidence') or 'not available', 'result':rf})
        if rf_rows:
            store.record_reforecast(close, rf_rows, version=run_id,
                                    metadata={'run_id':run_id,'entity':entity,'budget_version':budget_version,
                                              'actuals_version':actuals_version,'request_digest':request_digest})
        store.commit_run(run_id, request_digest, entity, close, bundle)
    return {**store.get_run(run_id), 'status':'committed'}


def deliver_run(store, run_id, output_dir):
    """Export one complete JSON evidence/report bundle using atomic rename.

    Existing identical output is an idempotent success. A conflicting artifact is
    never overwritten. A per-run lock serializes concurrent exporters.
    """
    _safe_run_id(run_id)
    saved = store.get_run(run_id)
    if saved is None:
        raise ValueError('unknown run_id')
    target = Path(output_dir) / f'{run_id}.json'
    temp_path = None
    try:
        import fcntl
        target.parent.mkdir(parents=True, exist_ok=True)
        # Advisory lock is released by the OS even if the exporting process dies.
        with (target.parent / f'.{run_id}.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            payload = canonical(saved['bundle']) + '\n'
            if target.exists():
                if target.read_text(encoding='utf-8') != payload:
                    raise ValueError('existing output conflicts with saved run; choose a clean output directory')
            else:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix=f'.{run_id}.', suffix='.tmp', dir=target.parent, delete=False) as f:
                    temp_path = Path(f.name)
                    f.write(payload); f.flush(); os.fsync(f.fileno())
                os.replace(temp_path, target)
                temp_path = None
                fd = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        store.delivery_event(run_id, 'delivered', str(target.resolve()))
        return {'status':'delivered', 'run_id':run_id, 'path':str(target.resolve()), 'bundle_digest':saved['bundle_digest']}
    except Exception as exc:
        store.delivery_event(run_id, 'failed', str(exc))
        raise
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--input', help='Explicit close request JSON')
    action.add_argument('--recover', help='Export a previously committed run ID without recomputation')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--html', action='store_true', help='Also export a portable HTML report and close-history snapshot')
    args = parser.parse_args(argv)
    try:
        with VarianceStore(args.db) as store:
            if args.input:
                with open(args.input, encoding='utf-8') as f:
                    request = json.load(f)
                result = execute_close(store, request)
                run_id = request['run_id']
            else:
                run_id = args.recover
                result = {'status':'recovered'}
                if store.get_run(run_id) is None:
                    raise ValueError('unknown run_id')
            try:
                delivered = deliver_run(store, run_id, args.output_dir)
                if args.html:
                    from agent4.report import export_reports
                    delivered.update(export_reports(store, run_id, args.output_dir))
            except Exception as exc:
                print(canonical({'status':'committed_delivery_failed','run_id':run_id,'error':str(exc)}))
                return 3
            print(canonical({**delivered,'close_status':result['status']}))
            return 0
    except Exception as exc:
        print(canonical({'status':'failed','error':str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
