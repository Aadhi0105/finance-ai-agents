"""Closed, bounded local-input contracts. Validation performs no analysis or I/O."""
from datetime import date, datetime, timezone
from decimal import Decimal
import copy
import re
from typing import Literal

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import Field, model_validator

from ...catalog import ID, Record
from .. import contracts as c

FORMATS = {'monitoring':'agent2.observations/1', 'events':'agent3.event-windows/1', 'news':'agent3.news-text/1'}
PROFILES = {w:'calculate-local-'+w for w in FORMATS}
METHODS = {'monitoring':'supplied-history-thresholds/1', 'events':'supplied-market-model/1', 'news':'supplied-word-list/1'}
MAX_PACKAGE = 1_000_000
DECIMAL = r'^-?(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,8})?$'


class Observation(Record):
    date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    value: str | None = Field(pattern=DECIMAL, max_length=22)
    source_id: str = Field(pattern=ID)


class WatchItem(Record):
    id: str = Field(pattern=ID)
    metric: str = Field(min_length=1,max_length=120)
    unit: Literal['fraction','multiple','score','currency']
    currency: Literal['EUR'] | None
    threshold: str = Field(pattern=DECIMAL,max_length=22)
    direction: Literal['above','below']
    observations: list[Observation] = Field(min_length=1,max_length=100)


class Monitoring(Record):
    schema_version: Literal[1]
    kind: Literal['keystone.monitoring-observations']
    entity_id: str = Field(pattern=ID)
    as_of: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    threshold_basis: Literal['analyst_policy']
    items: list[WatchItem] = Field(min_length=1,max_length=20)


class Event(Record):
    ticker: str = Field(pattern=r'^[A-Z0-9][A-Z0-9.^=-]{0,31}$')
    event_date: str
    anchor_date: str
    est_dates: list[str] = Field(min_length=250,max_length=250)
    window_dates: list[str] = Field(min_length=3,max_length=3)
    est_stock: list[float] = Field(min_length=250,max_length=250)
    est_market: list[float] = Field(min_length=250,max_length=250)
    evt_stock: list[float] = Field(min_length=3,max_length=3)
    evt_market: list[float] = Field(min_length=3,max_length=3)
    source_id: str = Field(pattern=ID)
    benchmark: str = Field(min_length=1,max_length=120)


class Events(Record):
    schema_version: Literal[1]
    kind: Literal['keystone.event-windows']
    entity_id: str = Field(pattern=ID)
    event_type: str = Field(min_length=1,max_length=120)
    events: list[Event] = Field(min_length=1,max_length=20)
    controls: list[Event] = Field(max_length=20)


class Article(Record):
    id: str = Field(pattern=ID)
    headline: str = Field(min_length=1,max_length=1000)
    body: str = Field(max_length=5000)
    published_at: str = Field(max_length=80)
    retrieved_at: str = Field(max_length=80)
    url: str | None = Field(max_length=2048)
    source_id: str = Field(pattern=ID)
    language: Literal['en']
    text_scope: Literal['headline_only','supplied_text']


class WordList(Record):
    source_id: str = Field(pattern=ID)
    positive: list[str] = Field(min_length=1,max_length=100)
    negative: list[str] = Field(min_length=1,max_length=100)


class News(Record):
    schema_version: Literal[1]
    kind: Literal['keystone.news-text']
    entity_id: str = Field(pattern=ID)
    ticker: str = Field(pattern=r'^[A-Z0-9][A-Z0-9.^=-]{0,31}$')
    as_of: str = Field(max_length=80)
    max_age_days: int = Field(ge=1,le=30)
    aliases: list[str] = Field(min_length=1,max_length=20)
    word_list: WordList
    articles: list[Article] = Field(max_length=100)


MODELS = {'monitoring':Monitoring,'events':Events,'news':News}


def package_schema():
    schema=copy.deepcopy(c.SCHEMA)
    schema['$id']='urn:keystone:local-workflow-package:3'
    schema['title']='Supplied local-workflow package envelope'
    schema['properties']['schema_version']={'const':3}
    schema['properties']['workflow']={'enum':list(FORMATS)}
    schema['properties']['payload_format']={'enum':list(FORMATS.values())}
    schema['allOf']=[{'if':{'properties':{'workflow':{'const':w}}},'then':{'properties':{'payload_format':{'const':f}}}} for w,f in FORMATS.items()]
    return schema


def envelope(value):
    schema=package_schema()
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(value)
    if type(value['schema_version']) is not int or len({s['source_id'] for s in value['sources']})!=len(value['sources']):
        raise ValueError('Invalid envelope')
    if value['dataset']['upstream_id'] is not None:raise ValueError('New inputs have no saved-run identity')
    return value


def today():return datetime.now(timezone.utc).date()


def semantic(package,entity):
    envelope(package);w=package['workflow'];p=package['payload']
    MODELS[w].model_validate(p)
    if type(p['schema_version']) is not int:raise ValueError('Integer version required')
    if p['entity_id']!=entity['id'] or package['dataset']['entity_id']!=entity['id']:raise ValueError('Entity mismatch')
    sources={s['source_id']:s for s in package['sources']};used=set()
    def source(id_,role,days=(),units=None,currency=None):
        s=sources[id_];used.add(id_)
        if (s['role']!=role or s['units']!=units or s['currency']!=currency or not s['provider_or_owner']
                or not s['reference'] or not s['period_start'] or not s['period_end']):raise ValueError('Source basis missing')
        start,end=date.fromisoformat(s['period_start']),date.fromisoformat(s['period_end'])
        if start>end or end>today():raise ValueError('Source dates invalid')
        for day in days:
            if not start<=date.fromisoformat(day)<=end:raise ValueError('Observation outside source period')
        for k in ('published_at','retrieved_at'):
            if s[k] and c.instant(s[k])>datetime.now(timezone.utc):raise ValueError('Future source timestamp')
    if w=='monitoring':
        if entity['kind']!='company' or len({i['id'] for i in p['items']})!=len(p['items']):raise ValueError('Monitoring scope')
        cutoff=date.fromisoformat(p['as_of'])
        if cutoff>today():raise ValueError('Future cutoff')
        for item in p['items']:
            if not item['metric'].strip() or (item['unit']=='currency')!=(item['currency']=='EUR'):raise ValueError('Metric unit')
            ds=[o['date'] for o in item['observations']]
            if ds!=sorted(set(ds)) or date.fromisoformat(ds[-1])>cutoff:raise ValueError('Observation date order')
            for o in item['observations']:
                date.fromisoformat(o['date']);source(o['source_id'],'observations',[o['date']],item['unit'],item['currency'])
    elif w=='events':
        if entity['kind']!='group' or not p['event_type'].strip():raise ValueError('Event group required')
        from tools.event_contracts import validate_event
        identities=set()
        for e in p['events']+p['controls']:
            validate_event(e)
            if (e['ticker'] not in entity['members'] or date.fromisoformat(e['event_date'])>date.fromisoformat(e['anchor_date'])
                    or (date.fromisoformat(e['anchor_date'])-date.fromisoformat(e['event_date'])).days>4
                    or date.fromisoformat(e['window_dates'][-1])>today()):raise ValueError('Event scope/date')
            ident=(e['ticker'],e['anchor_date'])
            if ident in identities:raise ValueError('Duplicate event/control')
            identities.add(ident)
            source(e['source_id'],'event_windows',e['est_dates']+e['window_dates']+[e['event_date']],'simple returns')
    else:
        if entity['kind']!='company' or p['ticker']!=entity['ticker']:raise ValueError('News identity')
        cutoff=c.instant(p['as_of'])
        if cutoff>datetime.now(timezone.utc):raise ValueError('Future cutoff')
        if any(not 3<=len(a.strip())<=200 for a in p['aliases']) or len(set(p['aliases']))!=len(p['aliases']):raise ValueError('Aliases')
        words=p['word_list'];tokens=words['positive']+words['negative']
        if len(set(tokens))!=len(tokens) or any(not re.fullmatch(r'[a-z]{2,40}',t) for t in tokens):raise ValueError('Word list must be distinct lowercase English tokens')
        source(words['source_id'],'word_list',units='tokens')
        if len({a['id'] for a in p['articles']})!=len(p['articles']):raise ValueError('Duplicate article identity')
        from agent3.news_contracts import canonical_url
        if not p['articles']:
            for s in package['sources']:
                if s['role']=='news_text':source(s['source_id'],'news_text',units='text')
        for a in p['articles']:
            published,retrieved=c.instant(a['published_at']),c.instant(a['retrieved_at'])
            if not a['headline'].strip() or retrieved>cutoff or published>retrieved:raise ValueError('Article dates/text')
            if a['text_scope']=='headline_only' and a['body']:raise ValueError('Headline-only scope contains body')
            if a['url'] is not None and not canonical_url(a['url']):raise ValueError('Article URL')
            source(a['source_id'],'news_text',[published.date().isoformat()],'text')
    if used!=sources.keys():raise ValueError('Unused/missing source declaration')
    return p


class LocalValidation(c.ValidationReceipt):
    schema_version: Literal[4] = 4
    validator_version: Literal['local-workflows/1.0.0']
    analytical_execution: Literal['not_started']


def validate_import(package,context,folder):
    from ...job_files import write_new
    p=semantic(package,context['entity']);w=package['workflow']
    period=p['as_of'][:10] if w!='events' else 'Supplied historical event windows'
    receipt=LocalValidation(schema_version=4,validator_version='local-workflows/1.0.0',producer=c.code_identity(),
        payload_sha256=c.fingerprint(p),upstream_id='new-local-input',period=period,execution_status='held',eligible=True,
        reasons=['supplied_evidence_requires_review'],analytical_execution='not_started')
    write_new(folder/'validation.json',c.canonical(receipt.model_dump()))


def processing_plan(workflow):
    return dict(schema_version=1,method=METHODS[workflow],scope='supplied_evidence_only',financial_approval=False)


def producer():
    from ..research.contracts import producer as identity
    from keystone.maintenance import ROOT
    from pathlib import Path
    base=identity()
    sources={str(p.relative_to(ROOT)):c.sha(p.read_bytes()) for part in ('scheduler','state','monitoring') for p in sorted((ROOT/part).rglob('*.py'))}
    schemas={p.name:c.sha(p.read_bytes()) for p in Path(__file__).parent.glob('*.schema.json')}
    return {**base,'source_tree_sha256':c.fingerprint(dict(base=base['source_tree_sha256'],sources=sources,schemas=schemas))}


class CalculatedMetric(Record):
    id: str = Field(pattern=ID)
    label: str = Field(max_length=160)
    value: str | None = Field(pattern=r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$',max_length=80)
    unit: Literal['count','fraction','multiple','score','currency','p_value']
    currency: Literal['EUR'] | None
    period: str = Field(max_length=160)
    reason: str | None = Field(max_length=80)
    visibility: Literal['main','supporting','diagnostic']


class Point(Record):
    x: str = Field(max_length=120)
    label: str = Field(max_length=240)
    value: str | None = Field(max_length=80)


class Chart(Record):
    id: str = Field(pattern=ID)
    title: str = Field(max_length=160)
    unit: Literal['fraction','multiple','score','currency']
    currency: Literal['EUR'] | None
    x_kind: Literal['date','category']
    type: Literal['line','bar','dot_plot']
    points: list[Point] = Field(max_length=100)


class ResultRow(Record):
    label: str = Field(max_length=1000)
    date: str = Field(max_length=10)
    status: str = Field(max_length=80)
    metric_id: str = Field(pattern=ID)
    related_metric_id: str | None = Field(pattern=ID)
    detail: str = Field(max_length=1000)


class Result(Record):
    schema_version: Literal[1]
    kind: Literal['keystone.local-workflow-result']
    workflow: Literal['monitoring','events','news']
    result_id: str = Field(pattern=r'^result-[a-f0-9]{32}$')
    method: str
    classification: Literal['synthetic','provider','issuer','internal','mixed','unknown']
    source: dict
    request_sha256: str = Field(pattern=c.SHA)
    job_id: str = Field(pattern=r'^job-[a-f0-9]{32}$')
    producer_sha256: str = Field(pattern=c.SHA)
    execution_status: Literal['held']
    financial_approval: Literal[False]
    metrics: list[CalculatedMetric] = Field(max_length=200)
    charts: list[Chart] = Field(max_length=20)
    rows: list[ResultRow] = Field(max_length=100)
    details: dict
    limitations: list[str] = Field(max_length=10)
    period: str = Field(max_length=160)

    @model_validator(mode='after')
    def references(self):
        from ...job_contract import DatasetBinding
        binding=DatasetBinding.model_validate(self.source)
        ids={m.id for m in self.metrics}
        if (self.result_id!='result-'+self.job_id[4:] or self.method!=METHODS[self.workflow]
                or self.classification!=binding.classification or len(ids)!=len(self.metrics)
                or len({ch.id for ch in self.charts})!=len(self.charts)
                or any(row.metric_id not in ids or row.related_metric_id is not None and row.related_metric_id not in ids for row in self.rows)
                or self.financial_approval is not False):raise ValueError('Result binding')
        for m in self.metrics:
            if ((m.value is None)!=(m.reason is not None) or (m.unit=='currency')!=(m.currency=='EUR')
                    or m.unit=='count' and m.value is not None and not re.fullmatch(r'0|[1-9][0-9]*',m.value)):
                raise ValueError('Metric availability or basis')
        for chart in self.charts:
            if (chart.unit=='currency')!=(chart.currency=='EUR'):raise ValueError('Chart basis')
            for point in chart.points:
                if point.value is not None and not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',point.value):raise ValueError('Point value')
                if chart.x_kind=='date':date.fromisoformat(point.x)
        return self
