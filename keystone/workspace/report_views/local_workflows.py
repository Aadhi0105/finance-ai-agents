"""Native presentation of new local workflow results; no calculation engines."""
from .common import text_cell,metric_cell


def build(b):
    s=b.source;w=b.run.workflow
    b.view['summary'].update(text={'monitoring':'Evaluate supplied history against your analyst policies. Read the latest observations and changes below.',
        'events':'See how the supplied historical events differed from their market-model benchmark. These observations do not predict the next event.',
        'news':'See which supplied articles mention this company, which text repeats, and which words contribute to the diagnostic tone.'}[w]+' Financial review is required.',
        template_id='local-workflow-summary-v1')
    b.view['sources'][0].update(label='New calculations from supplied local evidence',date_reason='Each value retains its supplied observation or publication date. Upload and calculation dates do not verify the source.')
    for i,m in enumerate(s['metrics']):
        b.metric(m['id'],m['label'],f'/metrics/{i}/value',m['unit'],period=m['period'],currency_code=m['currency'],visibility=m['visibility'])
        # This source family retains every exact number as decimal text. Its
        # strict result contract has already checked integer count syntax.
        if m['unit']=='count' and m['value'] is not None:
            b.view['metrics'][-1].update(value=m['value'],availability='available',reason_codes=[])
        if m['value'] is None:b.view['metrics'][-1].update(reason_codes=[m['reason']])
    main=[m['id'] for m in s['metrics'] if m['visibility']=='main']
    b.section('summary','At a glance','New calculations from this exact supplied input; held for review.',metrics=main)
    charts=[]
    for i,ch in enumerate(s['charts']):
        pts=[b.point(ch['id']+'-'+str(j),p['x'],p['label'],f'/charts/{i}/points/{j}/value') for j,p in enumerate(ch['points'])]
        charts.append(b.chart(ch['id'],ch['title'],'Retained numerical observations. Use the exact table or select a point for its label and value.',
            ch['type'],ch['unit'],[dict(id=ch['id']+'-series',label=ch['title'],points=pts)],x_kind=ch['x_kind'],x_label='Observation date' if ch['x_kind']=='date' else 'Historical event',
            currency_code=ch['currency'],visibility='main' if w=='monitoring' else 'diagnostic'))
    rows=[dict(id='observation-'+str(i),cells=[text_cell('observation',r['label']),text_cell('date',r['date']),metric_cell('value',r['metric_id']),
        *([metric_cell('threshold',r['related_metric_id'])] if w=='monitoring' else []),
        text_cell('status',r['status'].replace('_',' ').title()),text_cell('detail',r['detail'])],evidence_refs=[b.evidence('/rows/'+str(i))]) for i,r in enumerate(s['rows'])]
    table=b.table('observations','Supplied evidence and calculated outcomes',[('observation','Observation'),('date','Date'),('value','Observed / calculated value'),
        *([('threshold','Policy threshold')] if w=='monitoring' else []),('status','Outcome'),('detail','Meaning')],rows)
    b.section('observations',{'monitoring':'What changed in the supplied history?','events':'What happened around each event?','news':'Which stories were assessed?'}[w],
        'Policy outcomes' if w=='monitoring' else 'Historical diagnostics' if w=='events' else 'Document-level lexical diagnostics',
        metrics=[m['id'] for m in s['metrics'] if m['visibility']!='main'],charts=charts,tables=[table])
    if w=='news':
        exclusions=s['details']['exclusions']
        t=b.table('excluded-inputs','Excluded news evidence',[('record','Record'),('stage','Stage'),('reason','Reason')],
            [dict(id='excluded-'+str(i),cells=[text_cell('record',e.get('id') or e.get('evidence_id') or str(e.get('input_index'))),text_cell('stage',e['stage']),text_cell('reason',e['reason'].replace('_',' '))],evidence_refs=[b.evidence('/details/exclusions/'+str(i))]) for i,e in enumerate(exclusions)])
        b.section('coverage','Coverage and exclusions','A missing, stale or irrelevant document does not become neutral tone.',tables=[t])
    if w=='events':
        rejected=s['details']['study']['rejected_events']
        t=b.table('rejected-windows','Rejected event windows',[('record','Supplied window index'),('reason','Reason')],
            [dict(id='rejected-'+str(i),cells=[text_cell('record',e['index']),text_cell('reason',e['reason'])],evidence_refs=[b.evidence('/details/study/rejected_events/'+str(i))]) for i,e in enumerate(rejected)])
        b.section('coverage','Window coverage','All rejected event windows retain their reason. Accepted windows remain diagnostic.',tables=[t])
    b.section('method','Method and limits','The method and exact supplied parameters are retained with this report.')
    for i,note in enumerate(s['limitations']):
        b.review('statistical_eligibility','Method boundary '+str(i+1),note,'Inspect the supplied input and retained calculation before relying on this result.',
            [f'artifact:{b.primary_id}#/limitations/{i}'],[b.evidence('/limitations/'+str(i))],section_refs=['observations','method'])
    b.view['glossary']=[dict(term='Supplied local evidence',definition='Structured input selected by the analyst. No new provider retrieval or paid model inference was performed.'),
        dict(term='Diagnostic',definition='A descriptive calculation held for review, without a prediction or approval claim.')]
