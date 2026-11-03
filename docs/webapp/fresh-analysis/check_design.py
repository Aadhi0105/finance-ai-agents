"""Check 4A.2 design examples only; never a production input/result validator.

No engine/provider imports, file writes, workspace access or remote schema refs.
The runtime acceptance matrix remains pending even when every check here passes.
"""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text())


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def pointer(value, path):
    for token in path.split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def replace(value, path, new):
    result = deepcopy(value)
    parent, key = path.rsplit('/', 1)
    target = pointer(result, parent)
    target[int(key) if isinstance(target, list) else key] = new
    return result


def verify_sample(package, request, result):
    """Reconcile these expected examples, not arbitrary financial semantics."""
    payload = package['payload']
    assert payload['entity_id'] == package['dataset']['entity_id'] == result['identity']['entity_id']
    assert package['dataset']['listing'] == payload['listing'] == payload['quote']['listing'] == result['identity']['listing']
    sources = {s['source_id']: s for s in package['sources']}
    assert len(sources) == len(package['sources'])
    used = set()
    dates = []
    for period in payload['periods']:
        dates.append(period['period_end'])
        for observation in period['observations'].values():
            if observation['value'] is not None:
                source = sources[observation['source_id']]
                assert source['period_start'] <= period['period_start'] <= period['period_end'] <= source['period_end']
                assert observation['locator'] and observation['missing_reason'] is None
                used.add(source['source_id'])
    assert dates == sorted(set(dates))
    for observation in payload['quote']['observations'].values():
        if observation['value'] is not None:
            source = sources[observation['source_id']]
            assert source['period_start'] <= payload['quote']['as_of'] <= source['period_end']
            used.add(source['source_id'])
    assert used == set(sources)
    plan_hash = digest(request['analysis_plan'])
    source_hash = digest(request['source'])
    assert request['assumption_review']['analysis_plan_sha256'] == plan_hash
    assert request['assumption_review']['source_reference_sha256'] == source_hash
    lineage = result['lineage']
    assert lineage['analysis_plan_sha256'] == plan_hash
    assert lineage['source_reference_sha256'] == source_hash
    assert lineage['request_sha256'] == digest(request)
    assert lineage['payload_sha256'] == digest(payload)
    assert lineage['assumption_review_sha256'] == digest(request['assumption_review'])
    assert lineage['contract_sha256'] == request['source']['contract_sha256']
    assert lineage['version_id'] == request['source']['version_id']
    assert lineage['dataset_id'] == request['source']['dataset_id']
    assert result['analysis_plan'] == request['analysis_plan']
    assert result['result_id'][7:] == lineage['job_id'][4:] == lineage['operation_id'][4:]
    metrics = {m['id']: m for m in result['metrics']}
    derivations = {d['id']: d for d in result['derivations']}
    assert len(metrics) == len(result['metrics'])
    assert len(derivations) == len(result['derivations'])
    section_ids = {s['id'] for s in result['sections']}
    assert section_ids == {'summary', 'performance', 'valuation', 'peers', 'market', 'consensus', 'external-research', 'evidence'}
    assert len(result['sections']) == len(section_ids)
    for section in result['sections']:
        assert set(section['metric_ids']) <= metrics.keys()
    for check in result['checks']:
        assert set(check['section_ids']) <= section_ids
    for metric in metrics.values():
        if metric['availability'] == 'available':
            derivation = derivations[metric['derivation_id']]
            assert metric['id'] in derivation['metric_ids']
        else:
            assert metric['value'] is None and metric['derivation_id'] is None and metric['reason_codes']
        assert (metric['currency'] == 'EUR') == (metric['unit'] in {'currency', 'currency_per_share'})
    for derivation in derivations.values():
        assert set(derivation['metric_ids']) <= metrics.keys()
        for path in derivation['input_pointers']:
            assert pointer(payload, path) is not None
        for path in derivation['parameter_pointers']:
            assert pointer(result, path) is not None
    for series in result['series']:
        assert [p['date'] for p in series['points']] == dates
        for point in series['points']:
            metric = metrics[point['metric_id']]
            assert point['value'] == metric['value'] and point['date'] == metric['period_end']
            assert (series['unit'], series['currency']) == (metric['unit'], metric['currency'])
    return metrics


def oracle(package, request, metrics):
    """Independent Decimal equations, without calling the shared engine."""
    with localcontext() as context:
        context.prec = 50
        obs = package['payload']['periods'][-1]['observations']
        value = lambda key: Decimal(obs[key]['value'])
        dcf = request['analysis_plan']['valuation']
        fcff = value('operating_income') * (1 - Decimal(dcf['tax_rate']))
        fcff += value('depreciation_amortization') - value('capex') - value('change_in_working_capital')
        assert fcff == Decimal('80000000') == Decimal(metrics['base-fcff']['value'])
        shares = Decimal(package['payload']['quote']['observations']['shares_outstanding']['value'])
        price = Decimal(package['payload']['quote']['observations']['current_price']['value'])
        r, g = Decimal(dcf['discount_rate']), Decimal(dcf['terminal_growth'])
        weighted = Decimal(0)
        for scenario in ('bear', 'base', 'bull'):
            h = Decimal(dcf['high_growth']) + Decimal(dcf['scenario_deltas'][scenario])
            first_cash = fcff * (1 + h)
            pv_first = first_cash / (1 + r)
            pv_terminal = first_cash * (1 + g) / (r - g) / (1 + r)
            ev = pv_first + pv_terminal
            equity = ev - value('total_debt') + value('cash_and_equivalents')
            ps = equity / shares
            for key, expected in [('ev', ev), ('equity', equity), ('per-share', ps)]:
                assert Decimal(metrics[scenario + '-' + key]['value']) == expected
            concentration = (pv_terminal / ev).quantize(Decimal('.0001'), rounding=ROUND_HALF_EVEN)
            assert Decimal(metrics[scenario + '-terminal-concentration']['value']) == concentration
            weighted += ps * Decimal(dcf['weights'][scenario])
        assert weighted == 100 == Decimal(metrics['weighted-per-share']['value'])
        assert weighted / price - 1 == Decimal('.25') == Decimal(metrics['model-value-gap']['value'])
        revenue = value('revenue')
        assert value('operating_income') / revenue == Decimal(metrics['operating-margin']['value'])
        prior = Decimal(package['payload']['periods'][-2]['observations']['revenue']['value'])
        assert (revenue / prior - 1).quantize(Decimal('.0001')) == Decimal(metrics['revenue-yoy']['value'])
        cagr = (revenue / Decimal(package['payload']['periods'][0]['observations']['revenue']['value'])).sqrt() - 1
        assert abs(cagr - Decimal(metrics['revenue-cagr']['value'])) < Decimal('1e-18')
        cap = Decimal(package['payload']['quote']['observations']['market_cap']['value'])
        assert (cap / value('net_income')).quantize(Decimal('.0001')) == Decimal(metrics['annual-pe']['value'])
        assert (cap + value('total_debt') - value('cash_and_equivalents')) / value('operating_income') == Decimal(metrics['ev-operating-income']['value'])


def main():
    schemas = {name: read(name + '.schema.json') for name in ('financial-kit', 'analysis-request', 'local-result', 'validation-receipt')}
    validators = {}
    for name, schema in schemas.items():
        Draft202012Validator.check_schema(schema)
        validators[name] = Draft202012Validator(schema, format_checker=FormatChecker())
    for key in ('analysis_plan', 'valuation', 'rate'):
        assert schemas['analysis-request']['$defs'][key] == schemas['local-result']['$defs'][key]
    examples = {p.name: json.loads(p.read_text()) for p in sorted((ROOT / 'examples').glob('*.json'))}
    assert len(examples) == 7
    for name, example in examples.items():
        kind = 'financial-kit' if name.endswith('kit.json') else 'local-result' if name.startswith('expected-') else 'analysis-request'
        validators[kind].validate(example)
    kit = examples['complete-kit.json']
    req = examples['valuation-request.json']
    result = examples['expected-valuation-result.json']
    metrics = verify_sample(kit, req, result)
    oracle(kit, req, metrics)
    partial = examples['missing-cash-kit.json']
    p_result = examples['expected-missing-cash-result.json']
    p_metrics = verify_sample(partial, examples['missing-cash-request.json'], p_result)
    assert partial['payload']['periods'][-1]['observations']['cash_and_equivalents']['value'] is None
    assert next(s for s in p_result['sections'] if s['id'] == 'valuation')['availability'] == 'withheld'
    for id_ in ('weighted-per-share', 'base-equity', 'base-ev', 'ev-operating-income'):
        assert p_metrics[id_]['value'] is None and p_metrics[id_]['reason_codes'] == ['bridge_incomplete']
    assert p_metrics['revenue-2025']['value'] == metrics['revenue-2025']['value']
    assert examples['summary-only-request.json']['analysis_plan']['valuation'] is None
    assert examples['summary-only-request.json']['assumption_review'] is None

    refused = 0
    cases = [
        ('financial-kit', kit, '/schema_version', 1),
        ('financial-kit', kit, '/payload/schema_version', 2),
        ('financial-kit', kit, '/payload/company_type', 'bank'),
        ('financial-kit', kit, '/payload/instrument_type', 'adr'),
        ('financial-kit', kit, '/payload/currency', 'CHF'),
        ('financial-kit', kit, '/payload/monetary_unit', 'millions'),
        ('financial-kit', kit, '/payload/period_type', 'quarterly'),
        ('financial-kit', kit, '/payload/periods', []),
        ('financial-kit', kit, '/payload/periods', [kit['payload']['periods'][0]] * 11),
        ('financial-kit', kit, '/payload/periods/2/period_end', '2025-02-30'),
        ('financial-kit', kit, '/payload/periods/2/capex_convention', 'cashflow_signed'),
        ('financial-kit', kit, '/payload/periods/2/observations/revenue/value', 1000),
        ('financial-kit', kit, '/payload/periods/2/observations/revenue/value', True),
        ('financial-kit', kit, '/payload/periods/2/observations/revenue/value', '1e9'),
        ('financial-kit', kit, '/payload/periods/2/observations/revenue/value', 'NaN'),
        ('financial-kit', kit, '/payload/periods/2/observations/revenue/value', '-0.000'),
        ('financial-kit', kit, '/payload/periods/2/observations/revenue/value', '01'),
        ('financial-kit', kit, '/payload/periods/2/observations/revenue/value', '1.1234567'),
        ('financial-kit', kit, '/payload/periods/2/observations/revenue/source_id', None),
        ('financial-kit', kit, '/payload/periods/2/observations/revenue/missing_reason', 'not_provided'),
        ('financial-kit', kit, '/payload/periods/0/observations/capex/missing_reason', None),
        ('financial-kit', kit, '/sources/0/category', None),
        ('analysis-request', req, '/schema_version', 2),
        ('analysis-request', req, '/assumption_review', None),
        ('analysis-request', req, '/assumption_review/acknowledged', False),
        ('analysis-request', req, '/analysis_plan/valuation/horizon_years', True),
        ('analysis-request', req, '/analysis_plan/valuation/horizon_years', 31),
        ('analysis-request', req, '/analysis_plan/valuation/scenario_deltas/bull', '0.05'),
        ('analysis-request', req, '/analysis_plan/valuation/tax_rate', None),
        ('analysis-request', req, '/timeout_seconds', 121),
        ('local-result', result, '/execution/mode', 'offline'),
        ('local-result', result, '/execution/financial_approval', True),
        ('local-result', result, '/execution/provider_requests', 1),
        ('local-result', result, '/execution/model_calls', 1),
        ('local-result', result, '/evidence_gate', 'approved'),
        ('local-result', result, '/metrics/0/value', None),
        ('local-result', result, '/metrics/0/value', 'Infinity'),
        ('local-result', result, '/metrics/0/availability', 'withheld'),
        ('local-result', p_result, '/metrics/15/value', '0'),
    ]
    # Select an actually held metric rather than relying on collection ordering.
    held_index = next(i for i, m in enumerate(p_result['metrics']) if m['availability'] == 'withheld')
    cases[-1] = ('local-result', p_result, f'/metrics/{held_index}/value', '0')
    for kind, original, path, bad in cases:
        assert not validators[kind].is_valid(replace(original, path, bad)), (kind, path, bad)
        refused += 1
    for kind, original, path, field in [
        ('financial-kit', kit, '', 'approved'),
        ('financial-kit', kit, '/payload', 'peers'),
        ('financial-kit', kit, '/payload', 'price_history'),
        ('analysis-request', req, '', 'command'),
        ('analysis-request', req, '/analysis_plan', 'provider'),
        ('local-result', result, '', 'analyst_recommendation'),
    ]:
        altered = deepcopy(original)
        pointer(altered, path)[field] = True
        assert not validators[kind].is_valid(altered)
        refused += 1
    # Show the boundary honestly: these need the future semantic validator.
    semantic_only = [
        ('financial-kit', replace(kit, '/payload/periods/2/observations/capex/value', '-1')),
        ('financial-kit', replace(kit, '/payload/periods/2/period_start', '2025-11-01')),
        ('analysis-request', replace(req, '/analysis_plan/valuation/discount_rate', '0.01')),
        ('analysis-request', replace(req, '/analysis_plan/valuation/weights/bear', '0.4')),
    ]
    for kind, value in semantic_only:
        assert validators[kind].is_valid(value)
    print(json.dumps(dict(design_schemas=4, fictional_examples=7, malformed_structural_cases_refused=refused,
        sample_lineage_and_references='matched', independent_decimal_benchmark='matched', missing_cash='held_without_zero',
        schema_only_counterexamples=len(semantic_only), runtime_acceptance='39 rows pending implementation',
        financial_processing_enabled=False), indent=2))


if __name__ == '__main__':
    main()
