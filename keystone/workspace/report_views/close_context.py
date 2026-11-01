"""Close presentation 1.1: exact accounting, dated evidence and conditional forecasts.

This projection maps retained results; it does not run a close or a forecast.
"""
from datetime import date
from decimal import Decimal
from .common import metric_cell, text_cell
from .values import get, minor_to_major, token

ROOT = '/report/full_hierarchy'


def _table(b, section, ident, title, columns, rows):
    b.table(ident, title, columns, rows)
    next(s for s in b.view['sections'] if s['id'] == section)['table_refs'].append(ident)


def _row(b, ident, label, pointer):
    value = get(b.source, pointer, 'Not retained')
    if type(value) is bool: value = 'Yes (saved assertion)' if value else 'No (saved assertion)'
    return dict(id=ident, cells=[text_cell('field', label), text_cell('value', value)],
                evidence_refs=[b.maybe_evidence(pointer, label)])


def _forecast_state(forecast):
    status = forecast.get('publication_status')
    held = bool(forecast.get('error')) or status not in {'point_only', 'model_estimate', 'deterministic'}
    if not held and status in {'model_estimate','deterministic'}:
        probability=forecast.get('prob_hit_target')
        if probability is not None and (type(probability) not in {int,float} or not Decimal(str(probability)).is_finite() or not 0<=Decimal(str(probability))<=1):
            raise ValueError('Invalid saved forecast probability')
        band=forecast.get('band_cents')
        if band is not None and (not isinstance(band,list) or len(band)!=2 or any(type(x) is not int for x in band) or band[0]>band[1]):
            raise ValueError('Invalid saved forecast interval')
    return held, status not in {'model_estimate', 'deterministic'}


def extend(b):
    for ident, title, purpose in [
        ('close-basis', 'Selected close and source versions', 'Source identity and internal checks are distinct from financial approval.'),
        ('close-diagnostics', 'Account review evidence', 'Saved materiality, significance and persistence; no invented business cause.'),
        ('close-history', 'Retained variance observations', 'Dated observations from the selected close, not an inventory of later closes.'),
        ('close-forecast-context', 'Forecast basis and restrictions', 'Year-end scenarios and model intervals are separate from monthly accounting.'),
        ('close-sources', 'Submitted and effective source panels', 'Original submitted actuals and effective actuals retain their own version basis.'),
    ]:
        b.section(ident, title, purpose)
    fields = [
        ('run', 'Selected saved run', '/run_id'), ('date', 'Close period', '/request/close_period'),
        ('frequency', 'Reporting frequency', '/request/frequency'), ('measure', 'Root measure', ROOT + '/root_measure'),
        ('name', 'Root account', ROOT + '/name'), ('currency', 'Currency', ROOT + '/context/currency'),
        ('budget-version', 'Budget version', '/lineage/budget/version'), ('actual-version', 'Submitted actuals version', '/lineage/actuals/version'),
        ('budget-source', 'Budget source label', '/lineage/budget/metadata/source'),
        ('actual-source', 'Actuals source label', '/lineage/actuals/metadata/source'),
        ('budget-assertion', 'Budget approval supplied by caller', '/request/budget/approved'),
        ('supersedes', 'Supersedes saved run (if retained)', '/request/supersedes'),
        ('accounting', 'Internal result reconciliation', '/report/reconciles'),
        ('source-check', 'Frozen panel reconciliation', '/report/source_reconciliation'),
        ('claim-check', 'Canonical claim check', '/report/reconciliation/passed'),
        ('coverage', 'Source completeness statement', '/lineage/completeness'),
        ('history-basis', 'Historical budget basis', '/lineage/history_budget_basis'),
        ('actual-semantics', 'Effective actuals semantics', '/lineage/actuals_semantics'),
    ]
    _table(b, 'close-basis', 'close-basis', 'Selected close and source basis', [('field','Field'),('value','Saved value')],
           [_row(b, ident, label, p) for ident, label, p in fields])
    accounts = next(t for t in b.view['tables'] if t['id'] == 'accounts')
    accounts['columns'].insert(0, dict(id='node',label='Account ID'))
    accounts['columns'] += [dict(id='parent',label='Parent account ID'), dict(id='material',label='Saved materiality'),
        dict(id='significant',label='Saved significance'),dict(id='impact',label='Saved profit impact')]
    diagnostics, history_rows, forecast_rows, forecast_details = [], [], [], []
    nodes = []
    def walk(node, pointer, parent='Root'):
        nodes.append((node,pointer,parent))
        for i, child in enumerate(node.get('children', [])): walk(child, f'{pointer}/children/{i}', node['node_id'])
    walk(get(b.source,ROOT),ROOT)
    for i, (node,p,parent) in enumerate(nodes):
        row = accounts['rows'][i]
        row['cells'].insert(0,text_cell('node',node['node_id']))
        material = get(node,'/materiality/material')
        significance = get(node,'/significance/significant')
        impact = b.metric(f'account-{i}-profit-impact', 'Saved profit impact · ' + node['name'], p+'/profit_impact_cents',
            'currency',transform='minor_to_major',visibility='supporting')
        row['cells'] += [text_cell('parent',parent),text_cell('material','Material' if material is True else 'Not material' if material is False else 'Unavailable'),
            text_cell('significant','Significant diagnostic' if significance is True else 'Not significant diagnostic' if significance is False else 'Not computable'),metric_cell('impact',impact)]
        diagnostics.append(dict(id=f'detail-{i}',cells=[text_cell(k,v) for k,v in [
            ('node',node['node_id']),('name',node['name']),('triage',node.get('triage')),
            ('significance',get(node,'/significance/reason',get(node,'/significance/interpretation','Not retained'))),
            ('persistence',get(node,'/persistence/persistence','Not retained')),('reason',get(node,'/persistence/reason','Not retained')),
            ('granularity',node.get('granularity_note','No additional granularity retained'))]], evidence_refs=[b.evidence(p,'Saved account diagnostics')]))
        for j, observation in enumerate(get(node,'/history_snapshot/prior_observations',[]) or []):
            op=f'{p}/history_snapshot/prior_observations/{j}'
            history_rows.append(dict(id=f'history-{i}-{j}',cells=[text_cell('node',node['node_id']),text_cell('date',observation.get('period')),
                text_cell('amount','EUR '+str(minor_to_major(observation.get('variance_cents'))))],
                evidence_refs=[b.evidence(op+'/variance_cents','Dated prior variance',transform='minor_to_major')]))
        fp='/report/reforecasts/'+token(node['node_id']); forecast=get(b.source,fp,{}) or {}
        held, point_only = _forecast_state(forecast)
        if i==0 and forecast.get('publication_status')=='deterministic':
            for metric in b.view['metrics']:
                if metric['id']=='forecast-prob-hit-target':metric['label']='Recorded target outcome (no remaining horizon)'
                if metric['id']=='forecast-projected-landing-cents':metric['label']='Closed-year actual amount'
                if metric['id'].startswith('forecast-band-'):metric['label']='Closed-year amount bound (no remaining horizon)'
        ids={}
        for field,label,unit,transform in [('projected_landing_cents','Provisional year-end landing','currency','minor_to_major'),
            ('target_cents','Year-end target','currency','minor_to_major'),('prob_hit_target','Uncalibrated model probability','fraction','identity')]:
            if field=='prob_hit_target' and forecast.get('publication_status')=='deterministic':label='Recorded target outcome (no remaining horizon)'
            if field=='projected_landing_cents' and forecast.get('publication_status')=='deterministic':label='Closed-year actual amount'
            ident = f'account-forecast-{i}-{field.replace("_","-")}'
            ids[field]=b.metric(ident,label+' · '+node['name'],fp+'/'+field,unit,transform=transform,visibility='diagnostic',period='Year-end scenario from close '+get(b.source,'/request/close_period'),
                restriction='forecast_held' if held else 'forecast_uncertainty_unavailable' if field=='prob_hit_target' and point_only else None)
        for band in range(2):
            ids['band-'+str(band)]=b.metric(f'account-forecast-{i}-band-{band}','Conditional interval bound · '+node['name'],fp+'/band_cents/'+str(band),'currency',transform='minor_to_major',visibility='diagnostic',period='Year-end conditional model interval',restriction='forecast_held' if held else 'forecast_uncertainty_unavailable' if point_only else None)
        forecast_rows.append(dict(id=f'forecast-{i}',cells=[text_cell('node',node['node_id']),text_cell('name',node['name']),
            text_cell('state',forecast.get('publication_status','Not retained')),metric_cell('landing',ids['projected_landing_cents']),metric_cell('target',ids['target_cents']),
            metric_cell('probability',ids['prob_hit_target']),metric_cell('low',ids['band-0']),metric_cell('high',ids['band-1']),text_cell('direction',forecast.get('direction','Not retained'))],evidence_refs=[b.evidence(fp,'Saved forecast and its assumptions')]))
        for field,label in [('method','Method'),('input_basis','Input basis'),('reason','Publication reason'),('confidence','Uncertainty basis'),
            ('band_confidence','Model interval level'),('probability_kind','Probability interpretation'),('remaining_periods','Remaining periods'),
            ('direction','Target direction'),('persistence','Saved persistence')]:
            forecast_details.append(dict(id=f'forecast-{i}-{field}',cells=[text_cell('node',node['node_id']),text_cell('field',label),text_cell('value',forecast.get(field,'Not retained'))],evidence_refs=[b.maybe_evidence(fp+'/'+field)]))
        for j, assumption in enumerate(forecast.get('assumptions',[]) or []):
            forecast_details.append(dict(id=f'assumption-{i}-{j}',cells=[text_cell('node',node['node_id']),text_cell('field','Saved assumption'),text_cell('value',assumption)],evidence_refs=[b.evidence(fp+f'/assumptions/{j}')]))
        for field,label in [('ytd_cents','Saved YTD actuals'),('target_cents','Saved year-end target')]:
            amount=minor_to_major(forecast.get(field))
            forecast_details.append(dict(id=f'forecast-{i}-{field}',cells=[text_cell('node',node['node_id']),text_cell('field',label),text_cell('value','Withheld' if held else 'Unavailable' if amount is None else 'EUR '+amount)],evidence_refs=[b.maybe_evidence(fp+'/'+field,transform='minor_to_major')]))
        if i==0:
            for metric in b.view['metrics']:
                if metric['id'].startswith('forecast-'):
                    uncertainty=metric['id'] in {'forecast-prob-hit-target','forecast-band-0','forecast-band-1'}
                    if held or uncertainty and point_only:
                        metric.update(value=None,availability='withheld',reason_codes=['forecast_held' if held else 'forecast_uncertainty_unavailable'])
    _table(b,'close-diagnostics','account-diagnostics','Saved account diagnostic limitations',
        [('node','Account ID'),('name','Account'),('triage','Saved triage'),('significance','Significance limitation'),('persistence','Persistence classification'),('reason','Persistence limitation'),('granularity','Attribution granularity')],diagnostics)
    _table(b,'close-history','account-prior-observations','Retained prior variances — account amounts',
        [('node','Account ID'),('date','Observation period'),('amount','Actual less budget (EUR)')],history_rows)
    _table(b,'close-forecast-context','account-forecasts','Saved account year-end evidence — diagnostic',
        [('node','Account ID'),('name','Account'),('state','Publication state'),('landing','Year-end amount'),('target','Target'),('probability','Saved probability / outcome'),('low','Interval lower bound'),('high','Interval upper bound'),('direction','Target direction')],forecast_rows)
    _table(b,'close-forecast-context','forecast-basis','Forecast basis and assumptions',
        [('node','Account ID'),('field','Field'),('value','Saved value')],forecast_details)
    _history(b)
    for ident,title,pointer in [('submitted-actuals','Original submitted actuals delta','/request/actuals/rows'),
        ('effective-actuals','Effective actuals used by the saved close','/sources/effective_actuals'),('budget-panel','Selected budget panel','/sources/budget')]:
        rows=[]
        for i, row in enumerate(get(b.source,pointer,[]) or []):
            p=pointer+'/'+str(i)
            rows.append(dict(id=ident+'-'+str(i),cells=[text_cell('line',row['line']),text_cell('date',row['period']),
                text_cell('amount','EUR '+str(minor_to_major(row['amount_cents']))),text_cell('minor',row['amount_cents']),
                text_cell('version',row.get('source_version',get(b.source,'/request/'+('budget' if ident=='budget-panel' else 'actuals')+'/version')))],
                evidence_refs=[b.evidence(p,'Saved source panel row'),b.evidence(p+'/amount_cents','Exact amount in cents / 100',transform='minor_to_major')]))
        _table(b,'close-sources',ident,title,[('line','Line ID'),('date','Period'),('amount','Amount (EUR)'),('minor','Canonical cents'),('version','Source version')],rows)
    exclusions=get(b.source,'/lineage/excluded_incomplete_history_periods',[]) or []
    _table(b,'close-sources','history-exclusions','Excluded incomplete historical periods',[('period','Saved excluded period / reason')],
        [dict(id='excluded-'+str(i),cells=[text_cell('period',item)],evidence_refs=[b.evidence('/lineage/excluded_incomplete_history_periods/'+str(i))]) for i,item in enumerate(exclusions)])
    b.view['summary']=dict(text='This saved close compares budget and actual amounts for one reporting period. The bridge explains the accounting movement; account review evidence and year-end evidence appear separately. Internal reconciliation does not authenticate a ledger or establish business causes.',
        template_id='close-summary-v1',metric_refs=['close-budget-cents','close-actual-cents','close-total-variance-cents'],evidence_refs=[b.evidence(ROOT)],review_refs=[])
    b.review('data_basis','Source versions and approval assertions','The budget approval flag is a saved caller assertion. Frozen panel reconciliation checks internal agreement; it does not authenticate the ledger or approve the financial conclusions.',
        'Inspect the submitted delta, effective versions, source completeness and any superseded close.',[f'artifact:{b.primary_id}#/lineage'],[b.evidence('/lineage')],section_refs=['close-basis','close-results','accounts','close-sources'])
    b.review('statistical_eligibility','Materiality and diagnostic availability','Material amounts can require review even when significance or persistence cannot be computed. A saved classification does not establish a business explanation or calibrated forecast.',
        'Review material accounts and unavailable diagnostics, then confirm causes with the business.',[f'artifact:{b.primary_id}#{ROOT}'],[b.evidence(ROOT)],section_refs=['close-diagnostics','close-history','accounts','forecast','close-forecast-context'])
    b.view['glossary'] += [dict(term=t,definition=d) for t,d in [
        ('Account variance and profit effect','Actual less budget is measured in the account’s own units. An increased cost can have a positive account variance and an adverse negative effect on profit. The bridge uses saved steps in the displayed root’s units.'),
        ('Internal reconciliation','Exact agreement within the supplied source panels and saved calculations. It is not ledger authentication or financial approval.'),
        ('Materiality and significance','Materiality is a size rule. Significance and persistence are separate saved diagnostics; unavailable results do not become insignificant or one-off.'),
        ('Year-end scenario','A conditional projection from saved YTD inputs, assumptions and remaining periods. A point-only result has no publishable uncertainty interval or probability. Model estimates are uncalibrated.'),
        ('Close history','This bundle retains dated prior variance observations and an optional supersedes identifier. It does not establish a complete inventory of later or related closes.'),
    ]]


def _history(b):
    history=get(b.source,ROOT+'/history_snapshot/prior_observations',[]) or []
    valid=isinstance(history,list); previous=None
    for row in history:
        try:
            stamp=date.fromisoformat(row['period'])
            if type(row.get('variance_cents')) is not int or previous and stamp<=previous: valid=False
            previous=stamp
        except (KeyError,TypeError,ValueError):valid=False
    close=get(b.source,'/request/close_period')
    valid=valid and get(b.source,ROOT+'/history_snapshot/current_period')==close and (not previous or previous<date.fromisoformat(close))
    points=[b.point('prior-'+str(i),row['period'],row['period'],ROOT+f'/history_snapshot/prior_observations/{i}/variance_cents',transform='minor_to_major') for i,row in enumerate(history)] if valid else []
    if valid:points.append(b.point('selected-close',close,close,ROOT+'/total_variance_cents',transform='minor_to_major'))
    chart=b.chart('close-variance-history','Root account variance history','Saved account amounts (actual less budget), including the selected close. This is not a forecast path or a close-run inventory.',
        'line','currency',[dict(id='root-variance',label='Saved root variance',points=points)],x_kind='date',x_label='Saved reporting period',
        restriction=None if valid else 'dated_history_unavailable')
    next(s for s in b.view['sections'] if s['id']=='close-history')['chart_refs'].append(chart)


def validate_bridge(source, rows):
    """Bind retained display amounts/endpoints to saved accounting, without engines."""
    from .errors import NativeViewError
    tree=get(source,ROOT);steps=[]
    if tree.get('kind')=='leaf':
        steps=[(d['driver'],d['cents']) for d in tree['drivers']]
        if tree['residual_cents']:steps.append(('Rounding residual',tree['residual_cents']))
    else:
        if tree.get('residual_cents',0):raise NativeViewError()
        steps=[(c['name'],c['total_variance_cents']*(1 if c['sign']=='add' else -1)) for c in tree['children']]
    running=tree['budget_cents']
    expected=[dict(label='Budget',value=minor_to_major(running),start='0',end=minor_to_major(running),assessment='anchor')]
    for label,value in steps:
        end=running+value
        expected.append(dict(label=label,value=minor_to_major(value),start=minor_to_major(running),end=minor_to_major(end),assessment='favourable' if value*tree['sign_toward_profit']>=0 else 'adverse'))
        running=end
    expected.append(dict(label='Actual',value=minor_to_major(running),start='0',end=minor_to_major(running),assessment='anchor'))
    if running!=tree['actual_cents'] or rows!=expected:raise NativeViewError()
