"""Canonical, reference-bound commentary over a trusted frozen result registry.

The registry is an integrity snapshot, not a signature or proof of source truth.
Only deterministic templates are publishable; free numeric/causal rewrites fail.
"""
from copy import deepcopy
import hashlib
import json
from agent4.decomposition import euros
from agent4.hierarchy import validate_result, validate_analysis
from agent4.reforecast import reforecast


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _walk(tree):
    yield tree
    for child in tree.get('children', []):
        yield from _walk(child)


def build_registry(tree, reforecast_by_line=None, persistence_by_line=None):
    """Recheck calculations; bind optional results to exact node IDs and inputs."""
    validate_result(tree)
    validate_analysis(tree)
    nodes = list(_walk(tree))
    if len({n['node_id'] for n in nodes}) != len(nodes) or len({n['name'] for n in nodes}) != len(nodes):
        raise ValueError('ambiguous registry node identity')
    lookup = {n['name']: n for n in nodes}
    lookup.update({n['node_id']:n for n in nodes})
    forecasts = {}
    for key, result in (reforecast_by_line or {}).items():
        if key not in lookup:
            raise ValueError('forecast references an unknown node')
        node = lookup[key]
        if node['node_id'] in forecasts:
            raise ValueError('duplicate forecast aliases for one node')
        inputs = result.get('inputs')
        if not isinstance(inputs,dict) or inputs.get('name') not in (node['name'],node['node_id']):
            raise ValueError('forecast needs replayable inputs bound to this node')
        if _canonical(reforecast(**inputs)) != _canonical(result):
            raise ValueError('forecast differs from its computed input snapshot')
        context = tree.get('context', {})
        if context.get('close_date') and inputs.get('close_period') != context['close_date']:
            raise ValueError('forecast close does not match report close')
        # The P&L node may be a single close while the forecast is YTD. Do not
        # silently equate those values; retain the separate YTD input basis.
        result = deepcopy(result)
        result['input_basis'] = 'caller-supplied YTD scenario; not inferred from single-close actuals'
        forecasts[node['node_id']] = result
    for key, result in (persistence_by_line or {}).items():
        if key not in lookup or _canonical(result) != _canonical(lookup[key]['persistence']):
            raise ValueError('supplied persistence does not match the current node history')
    snapshot = {'schema_version':2, 'tree':deepcopy(tree), 'forecasts':forecasts}
    return {'registry_id':_digest(snapshot), 'snapshot':snapshot}


def _probability(result):
    value = result.get('prob_hit_target')
    if value is None:
        return 'unavailable'
    if result.get('remaining_periods') == 0:
        return f'{value:.0%}'
    if value < .001:
        return '<0.1%'
    if value > .999:
        return '>99.9%'
    return f'{value:.1%}'


def _claims(registry):
    root = registry['snapshot']['tree']
    output = []
    for node in _walk(root):
        ident = node['node_id']
        def emit(kind, tier, prose, fields):
            output.append({'claim_id':ident+'#'+kind, 'node_id':ident, 'kind':kind,
                'tier':tier, 'text':prose, 'registry_id':registry['registry_id'],
                'refs':[{'node_id':ident, 'field':field, 'registry_id':registry['registry_id']} for field in fields]})
        fav = 'favourable' if node['favourable'] else 'adverse'
        if node is root:
            fact = f"{node['name']} variance was {euros(node['total_variance_cents'])} ({fav}): actual {euros(node['actual_cents'])} vs budget {euros(node['budget_cents'])}."
        else:
            fact = f"{node['name']}: {euros(node['total_variance_cents'])} ({fav})."
        fields = ['budget_cents','actual_cents','total_variance_cents','favourable']
        if node.get('drivers'):
            fact += ' Drivers: '+', '.join(f"{d['driver']} {euros(d['cents'])}" for d in node['drivers'])+'.'
            fact += f" Rounding residual {euros(node['residual_cents'])}."
            fields += ['drivers','residual_cents']
        emit('accounting','computed_fact',fact,fields)
        emit('classification','observation',f"{node['name']}: {node['quadrant']} — {node['triage']}. {node['significance'].get('interpretation','Diagnostic unavailable')}",['quadrant','triage','significance'])
        p = node['persistence']
        score = f" Heuristic score {p['confidence']}; not a calibrated probability." if p.get('confidence') is not None else ''
        emit('persistence','observation',f"{node['name']}: persistence {p['persistence']}. {p['reason']}.{score} Business confirmation required.",['persistence','history_snapshot'])
        rf = registry['snapshot']['forecasts'].get(ident)
        if rf is not None and 'error' in rf:
            emit('forecast','observation',f"{node['name']}: forecast held for review. {rf['error']}. No landing, band or probability published.",['forecast'])
        elif rf is not None:
            landing = euros(rf['projected_landing_cents']) if rf.get('projected_landing_cents') is not None else 'unavailable'
            band = rf.get('band_cents')
            band_text = f"{euros(band[0])} to {euros(band[1])}" if band else 'unavailable'
            prose = (f"{node['name']}: reforecast landing {landing}; {rf.get('band_confidence', 'deterministic' if rf.get('remaining_periods') == 0 else 'unavailable')} range {band_text}; "
                     f"P(hit target) {_probability(rf)} ({rf['probability_kind']}). "
                     f"Target {euros(rf['target_cents'])}; direction {rf['direction']}; "
                     f"remaining periods {rf['inputs']['total_periods']-rf['inputs']['elapsed_periods']}. "
                     f"Method: {rf['method']}. {rf.get('reason',rf.get('confidence',''))}. "
                     f"{rf['input_basis']}. " + ' '.join(rf['assumptions']))
            if rf.get('persistence_effect'):
                prose += ' Adjustment: '+rf['persistence_effect']['adjustment']+'.'
            emit('forecast','observation',prose,['forecast'])
        if node.get('quadrant') in ('TOP_PRIORITY','EARLY_WARNING'):
            emit('business_cause','hypothesis',f"Business cause for {node['name']} requires confirmation — arithmetic alone does not establish causation.",['node_id'])
    return output


def compose(tree, persistence_by_line=None, reforecast_by_line=None, only_quadrants=None):
    registry = build_registry(tree,reforecast_by_line,persistence_by_line)
    return compose_registry(registry, only_quadrants)


def compose_registry(registry, only_quadrants=None):
    claims = _claims(registry)
    if only_quadrants is None:
        return claims
    root = registry['snapshot']['tree']
    ids = {n['node_id'] for n in _walk(root) if n.get('quadrant') in only_quadrants}
    ids.add(root['node_id'])
    return [c for c in claims if c['node_id'] in ids]


def reconcile(claims, registry, only_quadrants=None):
    """Exact canonical comparison: no claim-supplied values or regex fallbacks."""
    violations=[]
    try:
        if _digest(registry['snapshot']) != registry['registry_id']:
            raise ValueError('registry snapshot changed')
        expected={c['claim_id']:c for c in compose_registry(registry, only_quadrants)}
        seen=set()
        for i, claim in enumerate(claims):
            ident = claim.get('claim_id') if isinstance(claim,dict) else None
            if ident in seen or ident not in expected or _canonical(claim) != _canonical(expected[ident]):
                violations.append({'claim':i,'issue':'unknown, duplicate or noncanonical claim/reference'})
            seen.add(ident)
        if seen != set(expected):
            violations.append({'issue':'required canonical claims are missing'})
    except (ValueError, TypeError, KeyError, AttributeError):
        violations.append({'issue':'invalid claims or registry'})
    return {'passed':not violations,'n_claims':len(claims) if isinstance(claims,list) else 0,
            'violations':violations, 'note':'claims must match canonical text and typed references in the trusted registry'}
