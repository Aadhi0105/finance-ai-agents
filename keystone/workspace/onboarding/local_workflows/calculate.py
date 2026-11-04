"""Source-free calculations with fixed methods; every result remains under review."""
from datetime import date
from decimal import Decimal
import re
from statistics import mean

from .. import contracts as c
from .contracts import semantic, METHODS


def calculate(package,entity,record):
    p=semantic(package,entity);w=package['workflow']
    result=dict(schema_version=1,kind='keystone.local-workflow-result',workflow=w,result_id='result-'+record.job_id[4:],
        method=METHODS[w],classification=record.source.classification,source=record.source.model_dump(),request_sha256=record.request_sha256,
        job_id=record.job_id,producer_sha256=record.producer_sha256,execution_status='held',financial_approval=False,
        metrics=[],charts=[],rows=[],details={},limitations=[],period=package['dataset']['title'])
    def metric(id_,label,value,unit='count',period=None,currency=None,reason='supplied_value_unavailable',visibility='main'):
        result['metrics'].append(dict(id=id_,label=label,value=format(Decimal(str(value)),'f') if value is not None else None,
            unit=unit,currency=currency,period=period or result['period'],reason=reason if value is None else None,visibility=visibility))
        return id_
    def chart(id_,title,points,unit,x_kind='category',currency=None,type_='bar'):
        result['charts'].append(dict(id=id_,title=title,unit=unit,currency=currency,x_kind=x_kind,type=type_,points=points))
    if w=='monitoring':
        from scheduler.cycle import calculate_observation, _surfaces
        from state.classify import classify
        result['period']=p['as_of'];assessed=breaches=missing=exceptions=0;details=[]
        for index,item in enumerate(p['items']):
            cov=dict(item_id=item['id'],entity=entity['name'],metric=item['metric'],covenant_type='analyst_policy',
                threshold=float(item['threshold']),direction=item['direction'])
            history=[];last=None;rows=[]
            for cycle,o in enumerate(item['observations'],1):
                if o['value'] is None:continue
                day=date.fromisoformat(o['date']);v=float(o['value'])
                prior={**last,'margin':float(last['margin'])} if last else None
                row=calculate_observation(cov,v,day,cycle,prior,history,last is None)
                # Preserve the supplied decimal policy boundary. Statistical
                # diagnostics use floats; they do not decide an exact breach.
                exact=Decimal(o['value']);threshold=Decimal(item['threshold'])
                margin=exact-threshold if item['direction']=='below' else threshold-exact
                row.update(breached=margin>0,margin=str(margin),status=classify(
                    prior,margin>0,float(margin),last is None))
                history.append(dict(value=v,data_ts=day,cycle=cycle));last=row
                rows.append({**row,'data_ts':day.isoformat()})
            latest=item['observations'][-1];valid=latest['value'] is not None
            assessed+=valid;missing+=not valid
            breaches+=int(valid and last['breached']);exceptions+=int(valid and last['status']!='BASELINE' and _surfaces(last))
            prefix='item-'+str(index)
            metric(prefix+'-value',item['metric'],latest['value'],item['unit'],latest['date'],item['currency'],visibility='supporting')
            metric(prefix+'-threshold',item['metric']+' · policy threshold',item['threshold'],item['unit'],latest['date'],item['currency'],visibility='supporting')
            status=last['status'] if valid else 'MISSING_OBSERVATION'
            result['rows'].append(dict(label=item['metric'],date=latest['date'],status=status,metric_id=prefix+'-value',related_metric_id=prefix+'-threshold',detail='Policy requires value to stay '+item['direction']+' threshold'))
            chart(prefix+'-history',item['metric']+' · supplied history',
                [dict(x=o['date'],label=o['date'],value=o['value']) for o in item['observations']],item['unit'],'date',item['currency'],'line')
            details.append(dict(id=item['id'],rows=rows,latest_status=status))
        metric('assessed','Latest observations assessed',assessed);metric('breaches','Active policy breaches in assessed observations',breaches)
        metric('exceptions','Newly surfaced changes or diagnostics',exceptions);metric('missing','Missing latest observations',missing)
        result['details']=dict(items=details)
        result['limitations']=['Thresholds are supplied analyst policies, not contractual covenant conclusions.',
            'Each request evaluates its supplied history independently. Earlier web jobs are not a monitoring predecessor or an approved correction.',
            'The first usable observation establishes a baseline; it does not generate a new-breach alert.',
            'Observation dates are shown as supplied. No claim of current compliance or calibrated breach probabilities is made.']
    elif w=='events':
        from agent3.orchestrator import analyze_assembled
        from tools.event_study import run_event_study
        def normalized(e):
            return {**{k:v for k,v in e.items() if k not in {'source_id','benchmark'}},
                'date_status':'unverified','benchmark_status':'unverified','design_status':'unverified'}
        es=dict(source='supplied_local',events=[normalized(e) for e in p['events']],placebo_events=[normalized(e) for e in p['controls']],
            contributing_peers=sorted({e['ticker'] for e in p['events']}),comparability_status='unverified')
        analysis=analyze_assembled(p['event_type'],es,calculator=run_event_study);study=analysis['study']
        result['period']='Supplied historical windows'
        metric('events','Usable historical events',study['n_events']);metric('issuers','Distinct issuers',study['n_issuers'])
        metric('requested-events','Supplied event windows',len(p['events']));metric('rejected-events','Rejected event windows',len(study['rejected_events']))
        metric('mean-car','Historical mean abnormal return',study['caar'],'fraction',visibility='diagnostic')
        metric('p-value','Eligible statistical inference',None,'p_value',reason='independence_and_source_reviews_required')
        points=[]
        for index,e in enumerate(study['per_event']):
            mid='event-'+str(index);label=e['ticker']+' · '+e['event_date']
            metric(mid,label+' · cumulative abnormal return',e['car'],'fraction',e['anchor_date'],visibility='diagnostic')
            points.append(dict(x=str(index),label=label,value=format(Decimal(str(e['car'])),'f')))
            result['rows'].append(dict(label=label,date=e['anchor_date'],status='HISTORICAL_DIAGNOSTIC',metric_id=mid,related_metric_id=None,detail='Supplied dates and benchmark require review'))
        chart('event-cars','Historical reactions by event',points,'fraction',type_='dot_plot')
        result['details']=analysis
        result['limitations']=['Historical market-model diagnostics are not a return forecast or a causal claim.',
            'Supplied dates, benchmark mapping, sampling, controls and peer comparability have not been independently reviewed.',
            'Statistical inference and forward scenarios remain held, regardless of the sample count.']
    else:
        from agent3.news_funnel import ingest,relevance_filter,dedup_cluster,score_items,aggregate
        sources={s['source_id']:s for s in package['sources']};excluded=[]
        raw=[{**a,'source':sources[a['source_id']]['provider_or_owner'],'entities':[]} for a in p['articles']]
        ingested=ingest(raw,as_of=p['as_of'],max_age_days=p['max_age_days'],exclusions=excluded)
        relevant=relevance_filter(ingested,{p['ticker']},aliases={p['ticker']:p['aliases']},exclusions=excluded)
        clusters=dedup_cluster(relevant);words=p['word_list']
        class SuppliedWords:
            name='supplied-word-list/1'
            def score(self,item):
                tokens=re.findall(r'[a-z]+',(item['headline']+' '+item['body']).lower())
                pos=sum(t in words['positive'] for t in tokens);neg=sum(t in words['negative'] for t in tokens)
                return dict(scorer=self.name,score=(pos-neg)/len(tokens) if tokens and pos+neg else None,confidence=None,
                    positive_count=pos,negative_count=neg,token_count=len(tokens),word_list_sha256=c.fingerprint(words),
                    flag_review=True,review_reasons=['lexical_tone_not_contextual_sentiment']+([] if pos+neg else ['no_matching_tone_words']))
        scored=score_items(clusters,SuppliedWords());signals=aggregate(scored)
        result['period']=p['as_of'][:10]
        for key,label,n in [('articles','Supplied articles',len(raw)),('relevant','Relevant articles',len(relevant)),
            ('clusters','Distinct text clusters',len(clusters)),('scored','Clusters with word-list evidence',sum(i['sentiment'] is not None for i in scored)),('excluded','Excluded records',len(excluded))]:metric(key,label,n)
        points=[]
        for index,s in enumerate(signals):
            mid='day-'+str(index);metric(mid,'Document word tone · '+s['day'],s['diagnostic_level'],'score',s['day'],reason='no_matching_tone_words',visibility='diagnostic')
            points.append(dict(x=s['day'],label=s['day'],value=format(Decimal(str(s['diagnostic_level'])),'f') if s['diagnostic_level'] is not None else None))
        chart('daily-tone','Document word tone by publication day',points,'score','date',type_='dot_plot')
        for i,item in enumerate(scored):
            mid='story-'+str(i);metric(mid,'Word tone · document '+str(i+1),item['sentiment'],'score',item['day'],reason='no_matching_tone_words',visibility='diagnostic')
            result['rows'].append(dict(label=item['headline'],date=item['day'],status='LEXICAL_DIAGNOSTIC' if item['sentiment'] is not None else 'NO_TONE_EVIDENCE',metric_id=mid,related_metric_id=None,
                detail=str(item['cluster_size'])+' article record(s) in this text cluster · '+item['text_scope']))
        result['details']=dict(scored_items=scored,signals=signals,exclusions=excluded,ingested_items=ingested,
            funnel=dict(raw=len(raw),ingested=len(ingested),relevant=len(relevant),clusters=len(clusters)),word_list=words)
        result['limitations']=['Score = (positive token count − negative token count) / all English word tokens, using the exact supplied word list.',
            'This simple method does not understand negation, context or entity-specific sentiment. A missing match is unavailable, not neutral.',
            'Headline aliases establish relevance; provider tags alone do not. Identical text can cluster; independent stories are not established.',
            'No FinBERT, Loughran–McDonald dictionary, model download or return forecast is implied. All tone is diagnostic and requires review.']
    if len(c.canonical(result))>2_000_000:raise ValueError('Calculated result exceeds bounds')
    return result
