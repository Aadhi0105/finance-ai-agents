"""Closed local research contracts and semantic validation; no financial execution."""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import json

from jsonschema import Draft202012Validator, FormatChecker

FORMAT = 'agent1.financial-kit/1'
PROFILE = 'calculate-local-research'
MAX_PACKAGE = 1_000_000
SCHEMAS = {name: json.loads(Path(__file__).with_name(name+'.schema.json').read_text())
           for name in ('package','request','result','receipt')}
VALIDATORS = {name: Draft202012Validator(s,format_checker=FormatChecker()) for name,s in SCHEMAS.items()}
for schema in SCHEMAS.values(): Draft202012Validator.check_schema(schema)
SECTIONS = ('summary','performance','valuation','peers','market','consensus','external-research','evidence')


def today(): return datetime.now(timezone.utc).date()


def validate_shape(name,value):
    try:VALIDATORS[name].validate(value)
    except Exception as error:raise ValueError('Unsupported local research shape') from error
    if type(value['schema_version']) is not int: raise ValueError('Integer version required')
    return value


def envelope(value):
    # Preflight metadata deliberately contains no financial payload.
    schema={**SCHEMAS['package'],'properties':{**SCHEMAS['package']['properties'],'payload':{'type':'object'}}}
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(value)
    if type(value['schema_version']) is not int: raise ValueError('Integer version required')
    if len({s['source_id'] for s in value['sources']})!=len(value['sources']):raise ValueError('Duplicate sources')
    return value


def scope(metadata):
    return dict(listing=metadata['dataset']['listing'],company_type='nonfinancial_operating',instrument_type='ordinary_equity',
                financial_scope='consolidated',currency='EUR',monetary_unit='base',period_type='annual')


def producer():
    from .. import contracts as c
    from keystone.maintenance import ROOT
    old=c.code_identity()
    locks=[ROOT/'requirements-macos-arm64-py311.lock']
    lock=next(p for p in locks if p.is_file())
    schemas={p.name:c.sha(p.read_bytes()) for p in Path(__file__).parent.glob('*.schema.json')}
    return dict(code_commit=old['code_commit'],code_worktree_dirty=old['code_worktree_dirty'],python=old['python'],
                dependency_lock_sha256=c.sha(lock.read_bytes()),source_tree_sha256=c.fingerprint({'sources':old['source_sha256'],'schemas':schemas}))


def semantic(package,entity,asof=None):
    validate_shape('package',package)
    day=asof or today();payload=package['payload'];listing=package['dataset']['listing']
    if (entity['kind']!='company' or not entity['ticker'] or entity['id']!=payload['entity_id']
            or package['dataset']['entity_id']!=entity['id'] or listing!=payload['listing'] or entity['ticker']!=listing['ticker']):
        raise ValueError('Company/listing disagreement')
    sources={s['source_id']:s for s in package['sources']};used=set()
    if len(sources)!=len(package['sources']):raise ValueError('Duplicate source')
    for source in sources.values():
        if source['period_start']>source['period_end']:raise ValueError('Source period')
        times=[datetime.fromisoformat(source[k].replace('Z','+00:00')) if source[k] else None for k in ('published_at','retrieved_at')]
        if any(t and t>datetime.now(timezone.utc) for t in times) or all(times) and times[0]>times[1]:raise ValueError('Source times')
    def observation(obs,start,end,role,key):
        if obs['value'] is None:return None
        value=Decimal(obs['value']);source=sources[obs['source_id']];used.add(source['source_id'])
        if source['role']!=role or not source['period_start']<=start<=end<=source['period_end']:raise ValueError('Source coverage')
        if key in {'revenue','depreciation_amortization','capex','total_debt','cash_and_equivalents','noncontrolling_interests','preferred_equity','other_equity_claims'} and value<0:
            raise ValueError('Negative magnitude')
        if role=='quote_snapshot' and value<=0:raise ValueError('Nonpositive quote')
        if key=='shares_outstanding' and (value!=value.to_integral_value() or value>10**12):raise ValueError('Share count')
        return value
    previous=None;years=set()
    for period in payload['periods']:
        start,end=(date.fromisoformat(period[k]) for k in ('period_start','period_end'))
        if not 350<=(end-start).days+1<=380 or end>day or previous and start<=previous or end.year in years:raise ValueError('Annual periods')
        previous=end;years.add(end.year)
        values=[observation(obs,start.isoformat(),end.isoformat(),'annual_statements',key) for key,obs in period['observations'].items()]
        if all(x is None for x in values):raise ValueError('Empty period')
    current=payload['periods'][-1]['observations']
    if current['revenue']['value'] is None or all(current[k]['value'] is None for k in ('operating_income','net_income')):raise ValueError('Summary minimum')
    quote=payload['quote']
    if quote:
        if quote['listing']!=listing or date.fromisoformat(quote['as_of'])>day:raise ValueError('Quote basis')
        values={key:observation(o,quote['as_of'],quote['as_of'],'quote_snapshot',key) for key,o in quote['observations'].items()}
        if all(x is None for x in values.values()):raise ValueError('Empty quote')
        cap,price,shares=(values[k] for k in ('market_cap','current_price','shares_outstanding'))
        if all(x is not None for x in (cap,price,shares)) and abs(cap-price*shares)>Decimal('.05')*max(abs(cap),abs(price*shares)):
            raise ValueError('Quote reconciliation')
    if used!=set(sources):raise ValueError('Unused source')
    return payload


def plan(request):
    from ..contracts import fingerprint
    validate_shape('request',request)
    valuation=request['analysis_plan']['valuation']
    if valuation:
        if type(valuation['horizon_years']) is not int:raise ValueError('Integer horizon')
        r,g,h=(Decimal(valuation[k]) for k in ('discount_rate','terminal_growth','high_growth'))
        weights=[Decimal(x) for x in valuation['weights'].values()]
        if not (0<r<=1 and -1<g<r and Decimal('-.96')<h<=1) or any(not 0<=x<=1 for x in weights) or sum(weights)!=1:raise ValueError('DCF parameters')
        if valuation['tax_rate'] is not None and not 0<=Decimal(valuation['tax_rate'])<=1:raise ValueError('Tax rate')
        review=request['assumption_review']
        if review['source_reference_sha256']!=fingerprint(request['source']) or review['analysis_plan_sha256']!=fingerprint(request['analysis_plan']):raise ValueError('Review changed')
    return request


def readiness(payload,asof=None):
    day=asof or today();current=payload['periods'][-1];obs=current['observations'];reasons=[]
    if (day-date.fromisoformat(current['period_end'])).days>548:reasons.append('stale_statements')
    missing=any(obs[k]['value'] is None for k in ('operating_income','depreciation_amortization','capex','change_in_working_capital','total_debt','cash_and_equivalents','noncontrolling_interests','preferred_equity','other_equity_claims'))
    sections=[dict(id=k,status='minimum_satisfied' if k=='summary' else 'inputs_present' if k in {'performance','evidence'} else
                   'inputs_missing' if k=='valuation' and missing else 'requires_plan' if k=='valuation' else 'unsupported',
                   reason_codes=['missing_fcff_input'] if k=='valuation' and missing else ['unsupported_input_group'] if k in {'peers','market','consensus','external-research'} else []) for k in SECTIONS]
    quote=payload['quote']
    if quote and (day-date.fromisoformat(quote['as_of'])).days>7:reasons.append('stale_quote')
    return dict(evaluated_on=day.isoformat(),reason_codes=reasons,sections=sections)
