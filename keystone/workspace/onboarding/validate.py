"""Bounded offline source validation in an owned subprocess; no financial state writes."""
import argparse
from datetime import date
import math
from pathlib import Path
from types import SimpleNamespace

from ..catalog import ArtifactV2, read_confined, read_json
from ..job_files import write_new
from ..worker import offline_environment
from . import contracts as c

VERSION='1.0.0'
TERMINAL={'completed','held','refused','unavailable','failed'}


def fields(value,allowed,required):
    if not isinstance(value,dict) or set(value)-set(allowed) or not set(required)<=set(value):
        raise c.InputError()


def iso_day(value):
    if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value: raise c.InputError()
    return value


def number(value):
    if value is not None and (type(value) not in (int,float) or not math.isfinite(value)): raise c.InputError()


def source_description(workflow,source,entity,classification,folder):
    """Recognise producer families before their consumed fields reach a renderer."""
    reasons=[];eligible=True
    if workflow=='research':
        fields(source,{'schema_version','meta','execution','artifacts','validation','note','note_template','analysis','call_history','chart_data'},
               {'schema_version','meta','execution','analysis','chart_data','note','call_history'})
        meta=source['meta'];execution=source['execution']
        if (type(source['schema_version']) is not int or source['schema_version']!=2
                or not isinstance(meta,dict) or not isinstance(execution,dict) or not isinstance(source['analysis'],dict)
                or not isinstance(source['chart_data'],dict) or not isinstance(source['call_history'],list)
                or not isinstance(source['note'],str) or source.get('note_template') is not None and not isinstance(source['note_template'],str)
                or entity['kind']!='company' or meta.get('ticker')!=entity['ticker']
                or (meta.get('mode'),meta.get('data_source')) not in {('offline','fixture'),('live','yfinance')}
                or meta.get('mode')=='live' and classification=='synthetic'):
            raise c.InputError()
        if (set(source['analysis'])-{'get_financials','get_prices','compute_ratios','run_dcf','peer_outlier_check','get_consensus','get_historical_trend','compute_derived'}
                or any(not isinstance(v,dict) for v in source['analysis'].values())): raise c.InputError()
        from validation.publication import assess_record
        result,_=assess_record(source)
        if result['verdict']!='pass': reasons.append('research_evidence_requires_review')
        period=meta.get('statement_period') or 'Period not retained'
        if meta.get('statement_period'): iso_day(period)
        upstream=meta.get('run_id');status=execution.get('status')
        status=status if status in TERMINAL else 'held'
        if status!='completed': reasons.append('original_execution_not_completed')
    elif workflow=='monitoring':
        required={'run','current','reviews','decisions','data_mode','cycles','attempts','unreadable_audits','exported_at'}
        fields(source,required,required)
        if (source['data_mode'] not in {'bundled_fixtures','yfinance'}
                or source['data_mode']=='yfinance' and classification=='synthetic'
                or any(not isinstance(source[k],list) for k in ('current','reviews','decisions','cycles','attempts'))
                or type(source['unreadable_audits']) is not int or source['unreadable_audits']<0): raise c.InputError()
        c.instant(source['exported_at'])
        cycles=source['cycles']
        if any(type(x) is not int or x<1 for x in cycles) or cycles!=sorted(set(cycles)): raise c.InputError()
        run=source['run']
        if run is None:
            return dict(upstream_id='empty',period='No saved cycle',execution_status='unavailable',eligible=False,
                        reasons=['no_selected_monitoring_cycle'])
        if not isinstance(run,dict) or type(run.get('cycle')) is not int or run['cycle'] not in cycles: raise c.InputError()
        rows=run.get('rows')
        if not isinstance(rows,list): raise c.InputError()
        if run.get('data_ts'):iso_day(run['data_ts'])
        names=set()
        for row in [*rows,*source['current']]:
            if not isinstance(row,dict) or not isinstance(row.get('entity'),str) or not row['entity']: raise c.InputError()
            names.add(row['entity'])
            for key in ('value','threshold','breach_prob'): number(row.get(key))
            if row.get('data_ts'): iso_day(row['data_ts'])
            if row.get('direction') not in {'above','below'}: raise c.InputError()
            for key in ('breached','anomaly_significant','drifting'):
                if row.get(key) is not None and type(row[key]) is not bool: raise c.InputError()
        allowed={entity['name']} if entity['kind']=='company' else set(entity['members'])
        if not names<=allowed: raise c.InputError()
        for key in ('reviews','decisions'):
            if any(not isinstance(r,dict) for r in source[key]): raise c.InputError()
            ids=[r.get('review_id') for r in source[key]]
            if None in ids or len(ids)!=len(set(ids)): raise c.InputError()
        upstream=str(run['cycle']);period=str(run.get('data_ts') or 'Date not retained')+' · cycle '+upstream;status='completed'
    elif workflow in {'events','news'}:
        allowed={'schema_version','kind','attempt_id','content_fingerprint','inputs','record','provenance','replay_scope','bundle_sha256'}
        fields(source,allowed,allowed)
        from agent3.bundles import read_bundle,replay
        bundle=read_bundle(folder/'payload.json')
        inputs=bundle['inputs'];request=inputs.get('request');record=bundle['record']
        if not isinstance(request,dict): raise c.InputError()
        if workflow=='events':
            if 'input_items' in inputs or 'saved_scores' in inputs or not isinstance(request.get('event_type'),str): raise c.InputError()
            assembled=inputs.get('assembled_inputs')
            if assembled is not None:
                if not isinstance(assembled,dict) or assembled.get('source') not in {'fixture','live'}: raise c.InputError()
                if assembled['source']=='live' and classification=='synthetic': raise c.InputError()
                from tools.event_contracts import validate_event,MAX_EVENTS
                events=assembled.get('events',[]);controls=assembled.get('placebo_events',[])
                if not isinstance(events,list) or not isinstance(controls,list) or len(events)>MAX_EVENTS or len(controls)>MAX_EVENTS: raise c.InputError()
                for e in [*events,*controls]: validate_event(e)
                tickers={e['ticker'] for e in events}
                if entity['kind']!='group' or not tickers<=set(entity['members']): raise c.InputError()
            period='Retained historical event windows'
        else:
            if 'assembled_inputs' in inputs or request.get('ticker')!=entity['ticker'] or entity['kind']!='company': raise c.InputError()
            if request.get('data_mode') not in {'fixture','live'} or request['data_mode']=='live' and classification=='synthetic': raise c.InputError()
            cutoff=inputs.get('as_of') or request.get('as_of')
            if cutoff: c.instant(cutoff)
            period=(cutoff[:10] if cutoff else 'Cutoff not retained')+' · saved cutoff'
        rebuilt=replay(bundle)
        if rebuilt['verification']=='mismatch': raise c.InputError()
        if rebuilt['verification']!='matched': eligible=False;reasons.append('incomplete_replay_inputs')
        upstream=bundle['attempt_id'];status=record['status']
    else:
        allowed={'schema_version','run_id','request','request_digest','bound_tree','sources','lineage','report','code_identity'}
        fields(source,allowed,allowed)
        from agent4.report import validate_bundle
        from agent4.state import digest
        validate_bundle({'bundle':source,'bundle_digest':digest(source)})
        request=source['request']
        if (type(source['schema_version']) is not int or request.get('entity')!=entity['name'] or entity['kind']!='company'
                or request.get('data_kind') not in {'synthetic','unverified'}
                or request.get('data_kind')=='unverified' and classification=='synthetic'): raise c.InputError()
        from agent4.close import _topology,_periods
        from agent4.contracts import cents
        leaves=_topology(request['tree']);close=iso_day(request['close_period'])
        if request['budget'].get('approved') is not True:raise c.InputError()
        for kind in ('budget','actuals'):
            seen=set()
            for row in request[kind]['rows']:
                fields(row,{'line','period','amount_cents'},{'line','period','amount_cents'})
                key=(row['line'],iso_day(row['period']))
                cents(row['amount_cents'])
                if key in seen or key[0] not in leaves or key[1] not in _periods(date.fromisoformat(key[1]).year,request['frequency']):raise c.InputError()
                if kind=='actuals' and key[1]>close:raise c.InputError()
                seen.add(key)
        for row in source['sources']['effective_actuals']:
            if iso_day(row['period'])>close or row['line'] not in leaves:raise c.InputError()
        upstream=source['run_id'];period=iso_day(request['close_period']);status='completed'
    if not isinstance(upstream,str) or not 1<=len(upstream)<=200: raise c.InputError()
    return dict(upstream_id=upstream,period=period,execution_status=status,eligible=eligible,reasons=reasons)


def candidate_run(workflow,description,entity,classification):
    return SimpleNamespace(id='candidate',workflow=workflow,agent={'research':'agent1','monitoring':'agent2','events':'agent3','news':'agent3','close':'agent4'}[workflow],
        title='Imported saved evidence',entity=entity['name'],period=description['period'],source_run_id=description['upstream_id'],
        execution_status=description['execution_status'],review_status='review_required',prepared_at='2000-01-01T00:00:00Z',native_view=None,
        input_origin=SimpleNamespace(classification=classification,contract_sha256='0'*64))


def validate(folder):
    folder=Path(folder)
    descriptor=c.Preflight.model_validate(read_json(read_confined(folder,'preflight.json',65536))).model_dump()
    context=read_json(read_confined(folder,'context.json',65536))
    package=read_confined(folder,'package.json')
    if len(package)!=descriptor['package_bytes'] or c.sha(package)!=descriptor['package_sha256']: raise c.InputError()
    value=c.envelope(c.bounded_json(package))
    if {k:v for k,v in value.items() if k!='payload'}!=descriptor['metadata']: raise c.InputError()
    payload=c.canonical(value['payload'])
    if c.sha(payload)!=descriptor['payload_sha256']: raise c.InputError()
    write_new(folder/'payload.json',payload)
    if value['payload_format'] in c.LOCAL_FORMATS.values():
        from .local_workflows.contracts import validate_import
        validate_import(value,context,folder)
        return
    if value['payload_format'] == c.FRESH_RESEARCH:
        from .research.receipt import validate_import
        validate_import(value,context,folder)
        return
    fresh = value['payload_format'] == c.FRESH_CLOSE
    if fresh:
        description = validate_close_request(value, context, folder)
    else:
        description=source_description(value['workflow'],value['payload'],context['entity'],context['policy']['classification'],folder)
    declared=value['dataset']['upstream_id']
    allowed={description['upstream_id']}
    if value['workflow']=='research':allowed.add(value['payload']['meta']['ticker']+'_'+description['upstream_id'])
    if declared is not None and declared not in allowed:raise c.InputError()
    if value['workflow'] in {'research','close'}:
        from ..report_views.values import get
        currency=get(value['payload'],'/meta/currency') if value['workflow']=='research' else 'EUR'
        for source in value['sources']:
            if source['currency'] is not None and currency is not None and source['currency']!=currency:raise c.InputError()
    if value['workflow']=='research' and value['dataset']['listing']:
        from ..report_views.values import get
        quote=value['dataset']['listing']['quote_currency'];saved=get(value['payload'],'/analysis/get_prices/currency')
        if quote is not None and (saved is None or quote!=saved):raise c.InputError()
    # Validate the consumed native shape without publishing a bootstrap report.
    if description['eligible'] and not fresh:
        from ..report_views.series import prepare_series
        from ..report_views.projection import build_view
        from ..report_views.validation import validate_view
        run=candidate_run(value['workflow'],description,context['entity'],context['policy']['classification'])
        primary=ArtifactV2(id='source',name='payload.json',label='Imported source',kind='evidence',bytes=len(payload),sha256=c.sha(payload))
        series=prepare_series(run,value['payload'],primary)
        encoded=c.canonical(series)
        secondary=ArtifactV2(id='native-series',name='native-series.json',label='Retained native series',kind='evidence',bytes=len(encoded),sha256=c.sha(encoded))
        view=build_view(run,value['payload'],series,[primary,secondary])
        validate_view(view,run,value['payload'],series,[primary,secondary])
    receipt=dict(schema_version=2 if fresh else 1,validator_version=VERSION,producer=c.code_identity(),payload_sha256=c.sha(payload),**description)
    if fresh: receipt['accounting_source'] = context['accounting_source']
    write_new(folder/'validation.json',c.canonical(c.validation_receipt(receipt).model_dump()))


def validate_close_request(value, context, folder):
    from agent4.close import prepare_close_sources
    from .close_state import open_state, summary
    entity = context['entity']; request = value['payload']
    if (entity['kind'] != 'company' or request.get('entity') != entity['name']
            or request.get('data_kind') not in {'synthetic','unverified'}
            or request['data_kind'] == 'unverified' and context['policy']['classification'] == 'synthetic'
            or {s['role'] for s in value['sources']} != {'budget','actuals'}
            or any(s['currency'] != 'EUR' or s['units'] != 'integer cents' for s in value['sources'])):
        raise c.InputError()
    pin = c.AccountingSource.model_validate(context['accounting_source']).model_dump()
    if pin['entity_id'] != entity['id']: raise c.InputError()
    for declaration in value['sources']:
        for row in request[declaration['role']]['rows']:
            if (declaration['period_start'] and row['period'] < declaration['period_start']
                    or declaration['period_end'] and row['period'] > declaration['period_end']):
                raise c.InputError()
    path = folder / 'predecessor.duckdb'
    dummy = SimpleNamespace(descriptor={'id':pin['workspace_id']})
    with open_state(path if path.exists() else ':memory:', write=True) as store:
        if summary(dummy, entity['id'], store) != pin: raise c.InputError()
        store.con.execute('BEGIN TRANSACTION'); store._in_transaction = True
        try: prepare_close_sources(store, request)
        finally:
            store.con.execute('ROLLBACK'); store._in_transaction = False
    return dict(upstream_id=request['run_id'], period=request['close_period'], execution_status='completed',
                eligible=True, reasons=['fresh_close_requires_financial_review'])


def main():
    parser=argparse.ArgumentParser(allow_abbrev=False);parser.add_argument('folder',type=Path)
    args=parser.parse_args()
    from ..saved_job import deny_network
    import socket
    import signal
    # This bound survives loss of the supervising HTTP process, which may no
    # longer be present to enforce subprocess.run's timeout or release leases.
    signal.signal(signal.SIGALRM,signal.SIG_DFL)
    signal.alarm(c.VALIDATION_SECONDS)
    socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=deny_network
    try: validate(args.folder);return 0
    except Exception: return 2
    finally:signal.alarm(0)


if __name__=='__main__':
    raise SystemExit(main())
