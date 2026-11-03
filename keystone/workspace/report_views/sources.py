"""Closed adapter/version registry and bounded source identities."""
from .errors import NativeViewError
from .values import digest, get

ADAPTERS = {
    'research': ('agent1-native-report', '1.1.0', 'agent1.model/2'),
    'monitoring': ('agent2-native-report', '1.1.0', 'agent2.snapshot/unversioned'),
    'events': ('agent3-event-report', '1.1.0', 'agent3.run_bundle/1'),
    'news': ('agent3-news-report', '1.2.0', 'agent3.run_bundle/1'),
    'close': ('agent4-native-report', '1.1.0', 'agent4.close/1'),
}


def adapter_for(run):
    try:
        ident, latest, schema = ADAPTERS[run.workflow]
        private = getattr(run, 'input_origin', None) is not None
        if private:
            latest = '2.0.0'
        registration = getattr(run, 'native_view', None)
        version = registration.adapter_version if registration else latest
        supported = {'2.0.0'} if private else {'1.0.0', '1.1.0'}
        if run.workflow == 'news' and not private: supported.add('1.2.0')
        if version not in supported:
            raise NativeViewError('unsupported_report_schema')
        return ident, version, schema
    except KeyError as exc:
        raise NativeViewError('unsupported_report_schema') from exc


def check_source(run, source):
    """Recognise known shapes; a synthetic catalogue cannot relabel live inputs."""
    if not isinstance(source, dict):
        raise NativeViewError()
    workflow = run.workflow
    origin = getattr(run, 'input_origin', None)
    private = origin is not None
    if workflow == 'research':
        if type(source.get('schema_version')) is not int or source['schema_version'] != 2:
            raise NativeViewError('unsupported_report_schema')
        meta = source.get('meta', {})
        pair = (meta.get('mode'), meta.get('data_source')) if isinstance(meta, dict) else None
        if (pair not in ({('offline','fixture'), ('live','yfinance')} if private else {('offline','fixture')})
                or pair == ('live','yfinance') and origin.classification == 'synthetic'):
            raise NativeViewError('unsupported_report_schema')
        identities = {meta.get('run_id'), f"{meta.get('ticker')}_{meta.get('run_id')}"}
        execution = get(source, '/execution/status')
        if private and execution not in {'completed','held','refused','unavailable','failed'}:
            execution = 'held'
        if (run.source_run_id not in identities or not isinstance(source.get('analysis'), dict)
                or execution != run.execution_status):
            raise NativeViewError()
    elif workflow == 'monitoring':
        # This older export has no schema_version: recognise this exact family.
        required = {'run': dict, 'current': list, 'reviews': list, 'decisions': list,
                    'cycles': list, 'attempts': list, 'unreadable_audits': int,
                    'exported_at': str}
        if ('schema_version' in source or source.get('data_mode') not in ({'bundled_fixtures','yfinance'} if private else {'bundled_fixtures'})
                or source.get('data_mode') == 'yfinance' and origin.classification == 'synthetic'
                or any(type(source.get(k)) is not t for k, t in required.items())):
            raise NativeViewError('unsupported_report_schema')
        if (type(source['run'].get('cycle')) is not int
                or str(source['run']['cycle']) != run.source_run_id):
            raise NativeViewError()
    elif workflow in {'events', 'news'}:
        if (type(source.get('schema_version')) is not int or source['schema_version'] != 1
                or source.get('kind') != 'agent3.run_bundle'):
            raise NativeViewError('unsupported_report_schema')
        record, inputs = source.get('record'), source.get('inputs')
        if not isinstance(record, dict) or not isinstance(inputs, dict):
            raise NativeViewError()
        if (source.get('attempt_id') != run.source_run_id or record.get('run_id') != run.source_run_id
                or record.get('status') != run.execution_status
                or source.get('bundle_sha256') != digest({k: v for k, v in source.items() if k != 'bundle_sha256'})
                or source.get('content_fingerprint') != digest(inputs)
                or source.get('provenance') != record.get('provenance')):
            raise NativeViewError()
        request = record.get('request') or {}
        keys = ('assembled_inputs', 'n_event_types_tested', 'provider_snapshots', 'pinned_peer_set',
                'retry_peer_set', 'peer_proposal_audit', 'input_items', 'as_of', 'fetched')
        retained = {'request': {k: v for k, v in request.items() if k not in {'db', 'fixture'}},
                    **{k: record[k] for k in keys if k in record}}
        if 'input_items' in record and 'result' in record:
            retained['saved_scores'] = record['result'].get('scored_items', [])
        if retained != inputs:
            raise NativeViewError()
        mode = (get(source, '/inputs/assembled_inputs/source', request.get('source'))
                if workflow == 'events' else request.get('data_mode'))
        if mode not in ({'fixture','live'} if private else {'fixture'}) or mode == 'live' and origin.classification == 'synthetic':
            raise NativeViewError('unsupported_report_schema')
    elif workflow == 'close':
        if type(source.get('schema_version')) is not int or source['schema_version'] != 1:
            raise NativeViewError('unsupported_report_schema')
        request = source.get('request') or {}
        if (request.get('data_kind') not in ({'synthetic','unverified'} if private else {'synthetic'})
                or request.get('data_kind') == 'unverified' and origin.classification == 'synthetic'):
            raise NativeViewError('unsupported_report_schema')
        if get(source, '/report/full_hierarchy/context/currency') != 'EUR':
            raise NativeViewError('unsupported_report_schema')
        if (source.get('run_id') != run.source_run_id or request.get('run_id') != run.source_run_id
                or source.get('request_digest') != digest(request)
                or not isinstance(get(source, '/report/full_hierarchy'), dict)
                or not isinstance(source.get('lineage'), dict)):
            raise NativeViewError()
    else:
        raise NativeViewError('unsupported_report_schema')
