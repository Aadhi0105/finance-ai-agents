"""Native data acceptance: actual saved engines, source bindings and read boundary."""
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import socket

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
import pytest

from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog, Manifest, ManifestV2
from keystone.workspace.prepare import prepare_workspace
from keystone.workspace.report_views.errors import NativeViewError
from keystone.workspace.report_views.projection import build_view
from keystone.workspace.report_views.publish import project_workspace
from keystone.workspace.report_views.series import prepare_series
from keystone.workspace.report_views.validation import SCHEMA, validate_view
from keystone.workspace.report_views.values import canonical, minor_to_major, resolve

ROOT = Path(__file__).resolve().parents[1]


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@pytest.fixture(scope='module')
def legacy(tmp_path_factory):
    return prepare_workspace(tmp_path_factory.mktemp('native-source') / 'legacy')


@pytest.fixture(scope='module')
def native(legacy, tmp_path_factory):
    before = hashes(legacy)
    with pytest.MonkeyPatch.context() as patch:
        def forbidden(*args, **kwargs):
            raise AssertionError('Projection attempted network acquisition')
        patch.setattr(socket.socket, 'connect', forbidden)
        result = project_workspace(legacy, tmp_path_factory.mktemp('native-view') / 'saved')
    assert hashes(legacy) == before
    return result


def client(root):
    return TestClient(create_app(root), base_url='http://127.0.0.1')


def metric(view, ident):
    return next(m for m in view['metrics'] if m['id'] == ident)


def chart(view, ident):
    return next(c for c in view['charts'] if c['id'] == ident)


def case(native, workflow, edit=lambda x: None):
    catalog = Catalog(native)
    run = next(r for r in catalog.load().runs if r.workflow == workflow)
    by_id = {a.id: a for a in run.artifacts}
    primary = by_id[run.native_view.source_artifact_ids[0]]
    source = json.loads(catalog.read(run.id, primary))
    edit(source)
    primary = primary.model_copy(update={'sha256': hashlib.sha256(canonical(source)).hexdigest()})
    retained = prepare_series(run, source, primary)
    series = by_id[run.native_view.source_artifact_ids[1]].model_copy(update={
        'sha256': hashlib.sha256(canonical(retained)).hexdigest()})
    view = build_view(run, source, retained, [primary, series])
    validate_view(view, run, source, retained, [primary, series])
    return view, source, retained, run, [primary, series]


def rewrite_artifact(root, run_id, artifact_id, edit):
    manifest = json.loads((root / 'catalog.json').read_text())
    run = next(r for r in manifest['runs'] if r['id'] == run_id)
    artifact = next(a for a in run['artifacts'] if a['id'] == artifact_id)
    path = root / 'runs' / run_id / artifact['name']
    value = json.loads(path.read_text())
    edit(value)
    data = canonical(value) + b'\n'
    path.write_bytes(data)
    artifact.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
    (root / 'catalog.json').write_bytes(canonical(manifest))


def test_schema_copy_and_design_examples_remain_valid():
    documented = json.loads((ROOT / 'docs/webapp/native-reports/report-view.schema.json').read_text())
    assert SCHEMA == documented
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    for path in (ROOT / 'docs/webapp/native-reports/examples').glob('*.json'):
        validator.validate(json.loads(path.read_text()))


def test_legacy_compatibility_and_explicit_registration(legacy, native):
    old = client(legacy)
    assert isinstance(Catalog(legacy).load(), Manifest)
    assert old.get('/api/runs').status_code == 200
    response = old.get('/api/runs/research-example/report-view')
    assert response.status_code == 409 and response.json()['error']['code'] == 'native_view_unavailable'
    assert old.get('/api/runs/research-example/files/report_REVIEW.html').status_code == 200
    upgraded = Catalog(native).load()
    assert isinstance(upgraded, ManifestV2) and upgraded.schema_version == 2
    for run in upgraded.runs:
        assert run.native_view and len(run.native_view.source_artifact_ids) == 2
        assert next(a for a in run.artifacts if a.id == run.report_id).kind == 'report'


def test_native_preparation_publishes_only_after_all_views(tmp_path, monkeypatch):
    from keystone.workspace.report_views import publish
    original = publish.register_views
    def unpublished(destination, manifest):
        assert not (destination / 'catalog.json').exists()
        return original(destination, manifest)
    monkeypatch.setattr(publish, 'register_views', unpublished)
    result = prepare_workspace(tmp_path / 'direct-native', native=True)
    assert Catalog(result).load().schema_version == 2


def test_all_five_views_are_typed_source_bound_and_held(native):
    c = client(native)
    for run in Catalog(native).load().runs:
        view = c.get(f'/api/runs/{run.id}/report-view').json()
        Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(view)
        assert view['workflow'] == run.workflow and view['identity']['source_run_id'] == run.source_run_id
        assert view['state']['evidence_gate'] == 'held_for_review'
        assert view['state']['financial_approval'] is False
        assert view['state']['integrity'] == 'matched'
        sources = {a['id']: json.loads((native / 'runs' / run.id / a['name']).read_text()) for a in view['artifacts']}
        for entry in view['evidence']:
            resolve(sources[entry['artifact_id']], entry['pointer'])
        assert all(m['value'] is None if m['availability'] != 'available' else isinstance(m['value'], str) for m in view['metrics'])


def test_no_delivery_writes_or_financial_calculation_even_on_cold_cache(native, monkeypatch):
    import composer
    from keystone.workspace.report_views import delivery, series
    from agent4 import output
    def forbidden(*args, **kwargs):
        raise AssertionError('Read attempted execution or acquisition')
    monkeypatch.setattr(series, 'prepare_series', forbidden)
    for name in ('_sma', '_rolling_vol', '_drawdown', '_align_on_dates'):
        monkeypatch.setattr(composer, name, forbidden)
    monkeypatch.setattr(output, 'waterfall_rows', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    delivery._VALIDATED.clear()
    before = hashes(native)
    c = client(native)
    for run in Catalog(native).load().runs:
        url = f'/api/runs/{run.id}/report-view'
        response = c.get(url)
        head = c.head(url)
        assert response.status_code == head.status_code == 200 and not head.content
        assert head.headers['content-length'] == str(len(response.content))
        for artifact in run.artifacts:
            r = c.get(f'/api/runs/{run.id}/files/{artifact.name}')
            assert r.status_code == 200
            assert hashlib.sha256(r.content).hexdigest() == artifact.sha256
        assert response.headers['cache-control'] == 'no-store'
    assert hashes(native) == before


@pytest.mark.parametrize('damage', ['value', 'prose', 'pointer', 'metric-ref', 'gate', 'series-binding', 'view-version', 'adapter-version', 'source-version', 'oversized'])
def test_updated_hash_does_not_bypass_semantic_validation(native, tmp_path, damage):
    root = tmp_path / 'altered'
    shutil.copytree(native, root)
    c = client(root)
    assert c.get('/api/runs/research-example/report-view').status_code == 200  # Warm success marker.
    def edit(view):
        if damage == 'value': metric(view, 'revenue')['value'] = '999'
        if damage == 'prose': view['summary']['text'] = 'PRIVATE_UNSUPPORTED_RECOMMENDATION'
        if damage == 'pointer': view['evidence'][0]['pointer'] = '/missing'
        if damage == 'metric-ref': view['summary']['metric_refs'] = ['missing']
        if damage == 'gate': view['state']['evidence_gate'] = 'passed_evidence_checks'
        if damage == 'view-version': view['schema_version'] = 2
        if damage == 'oversized': view['summary']['text'] = 'x' * (8 * 1024 * 1024)
    if damage == 'series-binding':
        rewrite_artifact(root, 'research-example', 'native-series', lambda x: x.update(source_sha256='0' * 64))
    elif damage == 'source-version':
        rewrite_artifact(root, 'research-example', 'file-1', lambda x: x.update(schema_version=999))
    elif damage == 'adapter-version':
        path = root / 'catalog.json'
        manifest = json.loads(path.read_text())
        manifest['runs'][0]['native_view']['adapter_version'] = '99.0.0'
        path.write_bytes(canonical(manifest))
    else:
        rewrite_artifact(root, 'research-example', 'native-view', edit)
    for url in ['/api/runs/research-example/report-view', '/api/runs/research-example/files/native-report.json', '/api/runs/research-example/files/report_REVIEW.html']:
        response = c.get(url)
        assert response.status_code == (409 if damage in {'view-version', 'adapter-version', 'source-version'} else 503)
        assert response.json()['error']['code'] in {'unsupported_report_schema', 'saved_evidence_invalid'}
        assert str(root) not in response.text and 'PRIVATE_UNSUPPORTED' not in response.text


@pytest.mark.parametrize('target', ['catalog.json', 'runs/research-example/native-report.json', 'runs/research-example/native-series.json', 'runs/research-example/model.json'])
def test_native_symlinks_and_tamper_are_refused(native, tmp_path, target):
    root = tmp_path / 'linked'
    shutil.copytree(native, root)
    path = root / target
    outside = tmp_path / 'outside.json'
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    response = client(root).get('/api/runs/research-example/report-view')
    assert response.status_code == 503 and response.json()['error']['code'] == 'saved_evidence_invalid'


def test_native_error_envelopes_and_access_boundary(native):
    c = client(native)
    response = c.get('/api/runs/missing/report-view')
    assert response.status_code == 404 and response.json()['error']['code'] == 'saved_run_not_found'
    for headers in [{'host': 'external.example'}, {'origin': 'null'}, {'sec-fetch-site': 'cross-site'}]:
        r = c.get('/api/runs/research-example/report-view', headers=headers)
        assert r.status_code == 403 and r.json()['error']['code'] == 'local_access_required'
    r = c.post('/api/runs/research-example/report-view')
    assert r.status_code == 405 and r.json()['error']['code'] == 'read_only_workspace'


def test_reprojection_copies_only_registered_originals(native, tmp_path):
    before = hashes(native)
    result = project_workspace(native, tmp_path / 'reprojected')
    manifest = Catalog(result).load()
    assert len(manifest.runs) == 5
    assert not (result / '_private').exists()
    for run in manifest.runs:
        assert len([a for a in run.artifacts if a.id == 'native-view']) == 1
        for artifact in run.artifacts:
            assert (result / 'runs' / run.id / artifact.name).read_bytes() == (native / 'runs' / run.id / artifact.name).read_bytes()
    assert hashes(native) == before
    with pytest.raises(FileExistsError):
        project_workspace(native, result)
    with pytest.raises(ValueError):
        project_workspace(native, native / 'nested-copy')


def test_projection_failure_never_publishes_partial_catalogue(legacy, tmp_path, monkeypatch):
    from keystone.workspace.report_views import publish
    before = hashes(legacy)
    original = publish.prepare_series
    def fail_second(run, *args):
        if run.workflow == 'monitoring':
            raise NativeViewError()
        return original(run, *args)
    monkeypatch.setattr(publish, 'prepare_series', fail_second)
    destination = tmp_path / 'partial'
    with pytest.raises(NativeViewError):
        project_workspace(legacy, destination)
    assert not (destination / 'catalog.json').exists() and hashes(legacy) == before
    assert client(destination).get('/api/runs').status_code == 503


def test_research_derived_series_match_existing_definitions(native):
    from composer import _align_on_dates, _drawdown, _rolling_vol, _sma
    view, source, retained, _, _ = case(native, 'research')
    history = source['chart_data']['price_history']['history']
    close = [r['close'] for r in history]
    for key, values in [('ma50', _sma(close, 50)), ('ma200', _sma(close, 200)),
                        ('volatility30', _rolling_vol(close, 30)), ('drawdown', _drawdown(close))]:
        saved = retained['derivations'][key]['data']
        assert [r['date'] for r in saved] == [r['date'] for r in history]
        assert [None if r['value'] is None else float(r['value']) for r in saved] == values
    assert all(p['y'] is None for p in chart(view, 'prices')['series'][1]['points'][:49])
    dates, stock, index = _align_on_dates(history, source['chart_data']['index_history']['history'])
    for key, raw in [('rebased_stock', stock), ('rebased_index', index)]:
        assert [r['date'] for r in retained['derivations'][key]['data']] == dates
        assert [float(r['value']) for r in retained['derivations'][key]['data']] == [100 * v / raw[0] for v in raw]


def test_research_consensus_is_separate_and_currency_bound(native):
    def populate(source):
        source['analysis']['get_consensus'].update(available=True, quote_currency='EUR', reporting_currency='EUR',
            consensus={'price_target': {'mean': 650}, 'revenue_estimate_avg': {'+1y': 40000000000}})
    view, *_ = case(native, 'research', populate)
    consensus = view['analyst_content']['market_consensus']
    assert consensus['availability'] == 'available'
    assert metric(view, 'consensus-price-target-mean')['value'] == '650'
    assert metric(view, 'weighted-valuation')['id'] not in consensus['metric_refs']
    assert metric(view, 'historical-growth')['id'] not in consensus['metric_refs']
    assert view['analyst_content']['external_research']['availability'] == 'unavailable'
    def incompatible(source):
        populate(source)
        source['analysis']['get_consensus']['quote_currency'] = 'USD'
        source['analysis']['get_consensus']['reporting_currency'] = None
    view, *_ = case(native, 'research', incompatible)
    assert metric(view, 'consensus-price-target-mean')['value'] is None
    assert metric(view, 'consensus-revenue-estimate-avg-next-1y')['value'] is None


def test_research_invalid_history_valuation_and_peer_cases_preserve_restrictions(native):
    def invalid(source):
        source['chart_data']['price_history']['history'][2]['close'] = -1
        source['analysis']['run_dcf']['value_basis'] = 'enterprise_value'
        source['analysis']['peer_outlier_check']['peer_pes']['ASM.AS'] = -1
    view, *_ = case(native, 'research', invalid)
    assert chart(view, 'prices')['availability'] == 'withheld'
    assert chart(view, 'prices')['series'] == []
    assert metric(view, 'weighted-valuation')['value'] is None
    assert chart(view, 'valuation-scenarios')['series'] == []
    assert chart(view, 'peer-multiples')['availability'] == 'withheld'


def test_grouping_preserves_every_original_failed_or_warned_check(native):
    for workflow, pointer in [('research', '/validation/checks'), ('events', '/record/result/gate/checks')]:
        view, source, _, _, artifacts = case(native, workflow)
        checks = resolve(source, pointer)
        expected = {f'artifact:{artifacts[0].id}#{pointer}/{i}' for i, c in enumerate(checks) if c.get('status') != 'pass'}
        actual = {ref for item in view['review_items'] for ref in item['source_check_refs']}
        assert expected <= actual


def test_monitoring_retained_history_and_original_effective_separation(native):
    def correction(source):
        item = source['run']['rows'][0]['item_id']
        next(r for r in source['current'] if r['item_id'] == item).update(value=9.25, _pending_review=True, revision_id='saved-revision')
    view, source, *_ = case(native, 'monitoring', correction)
    index = next(i for i, r in enumerate(source['current']) if r['item_id'] == source['run']['rows'][0]['item_id'])
    assert metric(view, 'effective-value-' + str(index))['value'] == '9.25'
    assert metric(view, 'cycle-value-0')['value'] == str(source['run']['rows'][0]['value'])
    table = next(t for t in view['tables'] if t['id'] == 'effective-observations')
    assert 'correction review pending' in table['rows'][index]['cells'][-1]['text']
    assert len(view['charts'][0]['series'][0]['points']) == 9
    view, *_ = case(native, 'monitoring', lambda s: s['run'].update(triage_history={}))
    assert view['charts'][0]['availability'] == 'unavailable'
    def unknown(source):
        source['run']['rows'][0]['metric'] = 'unrecognised'
    view, *_ = case(native, 'monitoring', unknown)
    assert metric(view, 'cycle-value-0')['availability'] == 'withheld'


def test_events_and_news_never_invent_predictions_or_neutral_published_tone(native):
    events, *_ = case(native, 'events')
    assert metric(events, 'event-count')['value'] == '8'
    assert metric(events, 'p-value')['value'] is None
    assert metric(events, 'mean-car')['visibility'] == 'diagnostic'
    assert chart(events, 'event-path')['availability'] == 'withheld'
    news, *_ = case(native, 'news')
    assert metric(news, 'published-tone-0')['value'] is None
    assert metric(news, 'diagnostic-tone-0')['value'] in {'0', '0.0'}
    assert 'neutral' not in metric(news, 'published-tone-0')['label'].lower()


def test_close_bridge_uses_exact_major_units_and_forecast_missing_is_null(native):
    view, *_ = case(native, 'close')
    points = chart(view, 'close-bridge')['series'][0]['points']
    assert [Decimal(p['y']) for p in points] == list(map(Decimal, ['60', '10', '-5', '65']))
    assert [(p['start'], p['end']) for p in points] == [('0', '60'), ('60', '70'), ('70', '65'), ('0', '65')]
    assert [p['assessment'] for p in points] == ['anchor', 'favourable', 'adverse', 'anchor']
    assert metric(view, 'forecast-projected-landing-cents')['value'] == '780'
    assert metric(view, 'forecast-prob-hit-target')['value'] is None
    assert metric(view, 'forecast-band-0')['value'] is None


def test_reference_and_payload_bounds_are_enforced_before_delivery(native):
    view, source, series, run, artifacts = case(native, 'events')
    huge = copy.deepcopy(view)
    huge['charts'] = huge['charts'] * 21
    with pytest.raises(NativeViewError):
        validate_view(huge, run, source, series, artifacts)
    huge = copy.deepcopy(view)
    huge['summary']['text'] = 'x' * (8 * 1024 * 1024)
    with pytest.raises(NativeViewError):
        validate_view(huge, run, source, series, artifacts)


def test_exact_minor_conversion_does_not_round_large_integers():
    assert minor_to_major(12345678901234567890123456789012) == '123456789012345678901234567890.12'
    assert minor_to_major(-1) == '-0.01'
    assert minor_to_major(0) == '0'
    assert minor_to_major(True) is None


@pytest.mark.parametrize('damage', ['missing-registration', 'same-source-twice', 'wrong-kind', 'boolean-version', 'nonfinite-exponent'])
def test_registration_and_strict_json_fail_closed(native, tmp_path, damage):
    root = tmp_path / 'invalid'
    shutil.copytree(native, root)
    path = root / 'catalog.json'
    value = json.loads(path.read_text())
    run = value['runs'][0]
    if damage == 'missing-registration': run['native_view'] = None
    if damage == 'same-source-twice': run['native_view']['source_artifact_ids'] = ['file-1', 'file-1']
    if damage == 'wrong-kind': next(a for a in run['artifacts'] if a['id'] == 'native-view')['kind'] = 'evidence'
    if damage == 'boolean-version': value['schema_version'] = True
    path.write_bytes(canonical(value))
    if damage == 'nonfinite-exponent':
        path.write_text(path.read_text().replace('"schema_version":2', '"schema_version":1e999'))
    response = client(root).get('/api/runs/research-example/report-view')
    assert response.status_code == 503 and response.json()['error']['code'] == 'saved_evidence_invalid'


def test_expanded_research_bridge_retains_exact_source_values_and_signed_net_debt(native):
    view, source, *_ = case(native, 'research')
    assert metric(view, 'dcf-net-debt')['value'] == '-7500000000'
    assert metric(view, 'dcf-net-debt')['currency'] == 'EUR'
    for scenario in ('bear', 'base', 'bull'):
        enterprise = Decimal(metric(view, 'dcf-enterprise-' + scenario)['value'])
        equity = Decimal(metric(view, 'dcf-equity-' + scenario)['value'])
        assert enterprise - Decimal('-7500000000') == equity
        assert Decimal(metric(view, 'dcf-per-share-' + scenario)['value']) == Decimal(str(source['analysis']['run_dcf']['value_per_share'][scenario]))
        assert metric(view, 'dcf-weight-' + scenario)['visibility'] == 'diagnostic'
    assert metric(view, 'fcff-base')['value'] != metric(view, 'free-cash-flow')['value']


@pytest.mark.parametrize('damage', ['missing-bridge', 'currency', 'enterprise-only'])
def test_expanded_research_never_bypasses_an_ineligible_equity_bridge(native, damage):
    def edit(source):
        dcf = source['analysis']['run_dcf']
        if damage == 'missing-bridge': dcf['assumptions']['net_debt_bridge_status'] = 'missing'
        if damage == 'currency': dcf['currency'] = 'USD'
        if damage == 'enterprise-only': dcf['value_basis'] = 'enterprise_value'
    view, *_ = case(native, 'research', edit)
    assert metric(view, 'weighted-valuation')['value'] is None
    assert metric(view, 'dcf-per-share-base')['value'] is None
    assert chart(view, 'valuation-scenarios')['series'] == []
    assert view['state']['financial_approval'] is False


def test_expanded_peer_evidence_retains_dates_and_exclusions(native):
    def edit(source):
        source['analysis']['peer_outlier_check']['excluded_peers']['BAD'] = 'No admissible earnings'
        source['analysis']['peer_outlier_check']['peer_evidence']['ASM.AS']['prices']['currency'] = 'GBP'
    view, *_ = case(native, 'research', edit)
    table = next(t for t in view['tables'] if t['id'] == 'peer-evidence')
    rows = {r['cells'][0]['text']: r for r in table['rows']}
    assert rows['LRCX']['cells'][3]['text'] == '2025-06-30'
    assert rows['LRCX']['cells'][5]['text'] == 'USD'
    assert rows['ASM.AS']['cells'][5]['text'] == 'GBP'
    assert rows['BAD']['cells'][1]['text'] == 'Excluded'
    assert rows['BAD']['cells'][-1]['text'] == 'No admissible earnings'
    excluded = rows['BAD']['cells'][2]['metric_id']
    assert metric(view, excluded)['value'] is None


@pytest.mark.parametrize('count', [12, 12.0, 0, -1, 1.5, True])
def test_expanded_consensus_coverage_never_creates_a_usable_zero_analyst_estimate(native, count):
    def edit(source):
        source['analysis']['get_consensus'].update(available=True, quote_currency='EUR', reporting_currency='EUR',
            consensus={'price_target': {'mean': 650}}, coverage={'price_target': count})
    view, *_ = case(native, 'research', edit)
    target = metric(view, 'consensus-price-target-mean')
    if count in (12, 12.0) and type(count) is not bool:
        assert target['value'] == '650'
        assert metric(view, 'consensus-coverage-0')['value'] == '12'
        assert view['analyst_content']['market_consensus']['availability'] == 'available'
    else:
        assert target['value'] is None
        assert view['analyst_content']['market_consensus']['availability'] == 'unavailable'


def test_research_1_0_delivery_stays_compatible_and_reprojection_is_explicit(native, tmp_path):
    from keystone.workspace.catalog import RunV2
    root = tmp_path / 'legacy-native'
    shutil.copytree(native, root)
    catalog = Catalog(root)
    run = next(r for r in catalog.load().runs if r.workflow == 'research')
    primary = next(a for a in run.artifacts if a.id == run.native_view.source_artifact_ids[0])
    source = json.loads(catalog.read(run.id, primary))
    old_run = run.model_copy(update={'native_view': run.native_view.model_copy(update={'adapter_version': '1.0.0'})})
    retained = prepare_series(old_run, source, primary)
    rewrite_artifact(root, run.id, 'native-series', lambda value: (value.clear(), value.update(retained)))
    path = root / 'catalog.json'
    manifest = json.loads(path.read_text())
    manifest['runs'][0]['native_view']['adapter_version'] = '1.0.0'
    path.write_bytes(canonical(manifest))
    old_run = RunV2.model_validate(manifest['runs'][0])
    by_id = {a.id: a for a in old_run.artifacts}
    view = build_view(old_run, source, retained, [primary, by_id['native-series']])
    rewrite_artifact(root, run.id, 'native-view', lambda value: (value.clear(), value.update(view)))
    response = client(root).get('/api/runs/research-example/report-view')
    assert response.status_code == 200
    assert not any(t['id'] == 'equity-bridge' for t in response.json()['tables'])
    before = hashes(root)
    new = project_workspace(root, tmp_path / 'upgraded')
    upgraded = Catalog(new).load().runs[0]
    assert upgraded.native_view.adapter_version == '1.1.0'
    assert client(new).get('/api/runs/research-example/report-view').status_code == 200
    assert hashes(root) == before
