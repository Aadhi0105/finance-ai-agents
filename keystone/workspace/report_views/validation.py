"""Strict presentation bounds, references, retained-series and source bindings."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .errors import NativeViewError
from .projection import build_view
from .sources import adapter_for, check_source
from .values import canonical, decimal_text, get, history_ok, resolve

MAX_VIEW_BYTES = 8 * 1024 * 1024
SCHEMA_BYTES = Path(__file__).with_name('schema.json').read_bytes()
SCHEMA = json.loads(SCHEMA_BYTES)
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def validate_series(run, source, series, primary):
    if not isinstance(series, dict) or type(series.get('schema_version')) is not int:
        raise NativeViewError()
    adapter, version, _ = adapter_for(run)
    expected = dict(schema_version=1, kind='keystone.report-series', adapter_id=adapter,
                    adapter_version=version, source_artifact_id=primary.id,
                    source_sha256=primary.sha256, derivations=series.get('derivations'))
    if series != expected or not isinstance(series['derivations'], dict):
        raise NativeViewError()
    derivations = series['derivations']
    keys = {'ma50', 'ma200', 'volatility30', 'drawdown', 'rebased_stock', 'rebased_index'} if run.workflow == 'research' else {'bridge'} if run.workflow == 'close' else set()
    if set(derivations) != keys:
        raise NativeViewError()
    methods = {'ma50': ('composer._sma', {'window': 50}),
               'ma200': ('composer._sma', {'window': 200}),
               'volatility30': ('composer._rolling_vol', {'window': 30, 'annualisation_days': 252}),
               'drawdown': ('composer._drawdown', {}),
               'bridge': ('agent4.output.waterfall_rows; exact integer cents / 100', {'minor_units_per_major': 100})}
    for key, entry in derivations.items():
        if (not isinstance(entry, dict) or set(entry) != {'method', 'parameters', 'source_pointers', 'availability', 'reason_codes', 'data'}
                or entry['availability'] not in {'available', 'unavailable', 'withheld'}
                or not isinstance(entry['reason_codes'], list) or not isinstance(entry['data'], list)
                or len(entry['data']) > 2000):
            raise NativeViewError()
        if (any(not isinstance(r, str) or not r or len(r) > 80 for r in entry['reason_codes'])
                or len(entry['reason_codes']) > 30
                or (entry['availability'] == 'available') != (not entry['reason_codes'])
                or entry['availability'] == 'withheld' and entry['data']
                or entry['availability'] == 'available' and not any(isinstance(r, dict) and r.get('value') is not None for r in entry['data'])):
            raise NativeViewError()
        rebase = key.startswith('rebased_')
        method, params = (('common-date rebasing: 100 * close / first common close', {'base': 100})
                          if rebase else methods[key])
        pointers = (['/report/full_hierarchy'] if key == 'bridge' else
                    ['/chart_data/price_history/history', '/chart_data/index_history/history'] if rebase else
                    ['/chart_data/price_history/history'])
        if entry['method'] != method or entry['parameters'] != params or entry['source_pointers'] != pointers:
            raise NativeViewError()
        for pointer in pointers:
            # A missing history is a legitimate unavailable series, never fabricated data.
            if get(source, pointer) is None and entry['data']:
                raise NativeViewError()
        if key == 'bridge':
            for row in entry['data']:
                if (set(row) != {'label', 'value', 'start', 'end', 'assessment'} or not isinstance(row['label'], str)
                        or row['assessment'] not in {'anchor', 'favourable', 'adverse'}
                        or any(not isinstance(row[k], str) or decimal_text(row[k]) != row[k] for k in ('value', 'start', 'end'))):
                    raise NativeViewError()
        elif entry['data']:
            history = get(source, pointers[0])
            if not history_ok(history):
                raise NativeViewError()
            dates = [r['date'] for r in history]
            if rebase:
                index = get(source, pointers[1])
                if not history_ok(index):
                    raise NativeViewError()
                dates = sorted(set(dates) & {r['date'] for r in index})
            if len(entry['data']) != len(dates):
                raise NativeViewError()
            for row, day in zip(entry['data'], dates):
                if (set(row) != {'date', 'value'} or row['date'] != day
                        or row['value'] is not None and
                        (not isinstance(row['value'], str) or decimal_text(row['value']) != row['value'])):
                    raise NativeViewError()


def validate_view(view, run, source, series, artifacts):
    if not isinstance(view, dict) or type(view.get('schema_version')) is not int or view['schema_version'] != 1:
        raise NativeViewError('unsupported_report_schema')
    check_source(run, source)
    if len(canonical(view)) > MAX_VIEW_BYTES or next(VALIDATOR.iter_errors(view), None) is not None:
        raise NativeViewError()
    collections = ('artifacts', 'sources', 'evidence', 'metrics', 'findings', 'sections', 'charts', 'tables', 'review_items')
    ids = {}
    for name in collections:
        ids[name] = {row['id'] for row in view[name]}
        if len(ids[name]) != len(view[name]):
            raise NativeViewError()
    if (sum(len(s['points']) for c in view['charts'] for s in c['series']) > 20_000
            or sum(len(r['cells']) for t in view['tables'] for r in t['rows']) > 20_000):
        raise NativeViewError()
    refs = {'metric_refs': 'metrics', 'finding_refs': 'findings', 'chart_refs': 'charts',
            'table_refs': 'tables', 'review_refs': 'review_items', 'section_refs': 'sections', 'evidence_refs': 'evidence'}
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in refs and not set(item) <= ids[refs[key]]:
                    raise NativeViewError()
                if key == 'metric_id' and item not in ids['metrics']:
                    raise NativeViewError()
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(view)
    for table in view['tables']:
        columns = {c['id'] for c in table['columns']}
        if len(columns) != len(table['columns']) or len({r['id'] for r in table['rows']}) != len(table['rows']):
            raise NativeViewError()
        for row in table['rows']:
            if {c['column_id'] for c in row['cells']} != columns or len(row['cells']) != len(columns):
                raise NativeViewError()
    raw = {artifacts[0].id: source, artifacts[1].id: series}
    for entry in view['evidence']:
        if entry['artifact_id'] not in raw or entry['source_id'] not in ids['sources']:
            raise NativeViewError()
        resolve(raw[entry['artifact_id']], entry['pointer'])
    validate_series(run, source, series, artifacts[0])
    # Only mapping, exact unit conversion and fixed-template formatting happen here.
    # Financial/chart calculations were retained by the operator before publication.
    if view != build_view(run, source, series, artifacts):
        raise NativeViewError()
