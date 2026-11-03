"""Local research result to native reader. Mapping only; no financial arithmetic."""
from .common import text_cell,metric_cell


def build(b):
    source=b.source;b.currency='EUR'
    b.view['identity'].update(ticker=source['identity']['listing']['ticker'],period_end=source['identity']['period_end'])
    b.view['summary'].update(text=f"Company analysis calculated from supplied local evidence for {b.run.entity}. Financial review is required.",template_id='local-research-summary-v1')
    b.view['sources'][0].update(label='Calculated from supplied local evidence',observed_at=None,
        date_reason='Each metric retains its own statement/quote date. Source authenticity has not been independently established.')
    indices={m['id']:i for i,m in enumerate(source['metrics'])}
    for index,m in enumerate(source['metrics']):
        b.metric(m['id'],m['label'],f'/metrics/{index}/value',m['unit'],period=m['period_end'] or b.run.period,visibility=m['visibility'])
        rendered=b.view['metrics'][-1]
        rendered.update(availability=m['availability'],reason_codes=m['reason_codes'],as_of=m['as_of'])
    charts=[]
    for i,s in enumerate(source['series']):
        points=[b.point(s['id']+'-'+str(j),p['date'],p['date'],f'/series/{i}/points/{j}/value') for j,p in enumerate(s['points'])]
        charts.append(b.chart(s['id'],s['label'],'Supplied annual observations. Missing values remain gaps.',s['kind'],s['unit'],
            [dict(id=s['id']+'-series',label=s['label'],points=points)],x_kind='date',x_label='Financial period end'))
    val=source['analysis_plan']['valuation'];assumptions=[];scenario_chart=[]
    if val:
        for key,label,unit in [('discount_rate','Discount rate assumption','fraction'),('high_growth','Initial growth assumption','fraction'),
                    ('terminal_growth','Terminal growth assumption','fraction'),('horizon_years','Projection horizon','count'),('tax_rate','Explicit tax-rate override','fraction')]:
            mid='assumption-'+key.replace('_','-')
            b.metric(mid,label,'/analysis_plan/valuation/'+key,unit,period='Selected model assumption',visibility='supporting')
            assumptions.append(dict(id=mid,cells=[text_cell('parameter',label),metric_cell('value',mid)],evidence_refs=[b.evidence('/analysis_plan/valuation/'+key)]))
        for key in ('bear','base','bull'):
            mid='weight-'+key;b.metric(mid,key.title()+' scenario weight','/analysis_plan/valuation/weights/'+key,'fraction',period='Assigned weight; not probability',visibility='supporting')
            assumptions.append(dict(id=mid,cells=[text_cell('parameter',key.title()+' scenario weight'),metric_cell('value',mid)],evidence_refs=[b.evidence('/analysis_plan/valuation/weights/'+key)]))
        pts=[b.point('scenario-'+k,k,k.title(),f"/metrics/{indices[k+'-per-share']}/value") for k in ('bear','base','bull')]
        scenario_chart=[b.chart('conditional-scenarios','Conditional equity values per share','Assigned scenarios, not broker targets or forecast probabilities.',
            'scenario_range','currency_per_share',[dict(id='scenario-values',label='Conditional equity value per share',points=pts)],visibility='diagnostic')]
    table=b.table('assumptions','Selected valuation assumptions',[('parameter','Parameter'),('value','Selected value')],assumptions) if assumptions else None
    names={'summary':'At a glance','performance':'Financial performance','valuation':'Conditional valuation','peers':'Peer comparison',
           'market':'Market price history','consensus':'External analyst estimates','external-research':'Broker research','evidence':'Evidence and method'}
    bridge_rows=[]
    for key in ('bear-ev','base-ev','bull-ev','total-debt','cash-and-equivalents','bear-equity','base-equity','bull-equity'):
        if key in indices:
            bridge_rows.append(dict(id='bridge-'+key,cells=[text_cell('measure',source['metrics'][indices[key]]['label']),metric_cell('value',key)],evidence_refs=[b.evidence(f'/metrics/{indices[key]}/value')]))
    bridge=b.table('equity-bridge','Enterprise to equity bridge',[('measure','Measure'),('value','Retained amount')],bridge_rows)
    for s in source['sections']:
        ident=s['id'];ids=s['metric_ids']
        b.section(ident,names[ident], ' / '.join(s['reason_codes']).replace('_',' ') if s['reason_codes'] else
            'Calculated from the exact selected local input. Review source dates, scope and assumptions.',metrics=ids,
            findings=[b.observation(m,diagnostic=ident=='valuation') for m in ids] if ident=='summary' else [],
            charts=charts if ident=='performance' else scenario_chart if ident=='valuation' else [],
            tables=([table,bridge] if table else [bridge]) if ident=='valuation' else [],availability=s['availability'],reasons=s['reason_codes'])
    for i,check in enumerate(source['checks']):
        if check['status']=='pass':continue
        b.review('data_basis' if check['reason_code'] in {'synthetic_evidence','operator_attested_origin','source_dates_unknown','stale_statements'} else 'valuation_assumptions',
            check['reason_code'].replace('_',' ').capitalize(),check['detail'],'Inspect the linked calculation and original input before relying on this section.',
            [f'artifact:{b.primary_id}#/checks/{i}'],[b.evidence(f'/checks/{i}')],section_refs=check['section_ids'])
    for key in ('market_consensus','external_research'):
        b.view['analyst_content'][key]=b.analyst_area('unavailable',['unsupported_input_group'])
    b.view['glossary']=[dict(term='Conditional model-value gap',definition='Model value divided by the dated supplied quote, minus one. It is not an expected return.'),
        dict(term='Scenario weights',definition='Explicit analyst assumptions; they are not measured probabilities.'),
        dict(term='Local inputs',definition='Supplied structured observations. No provider retrieval or language-model inference was performed.')]
