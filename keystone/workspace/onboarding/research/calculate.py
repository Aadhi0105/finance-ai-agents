"""Fixed local research plan. Supplied observations only; no data acquisition."""
from datetime import date
from decimal import Decimal, localcontext
from types import SimpleNamespace

from tools.analytical import compute_ratios, run_dcf
from tools.financial_contract import annual_pair
from .. import contracts as c
from .contracts import semantic, plan, validate_shape, SECTIONS


def decimal(value):
    if value is None:return None
    out=format(Decimal(str(value)),'f')
    if not Decimal(out).is_finite():raise ValueError('Nonfinite calculation')
    return '0' if Decimal(out)==0 else out


def calculate(package,request,binding,job_id,producer,evaluated_on):
    plan(request)
    payload=package['payload'];periods=payload['periods'];current=periods[-1];obs=current['observations']
    value=lambda k: Decimal(obs[k]['value']) if obs[k]['value'] is not None else None
    ticker=payload['listing']['ticker'];day=date.fromisoformat(evaluated_on)
    p=lambda key,i=len(periods)-1:f'/periods/{i}/observations/{key}/value'
    q=lambda key:'/quote/observations/'+key+'/value'
    quote=payload['quote'];fresh=bool(quote and (day-date.fromisoformat(quote['as_of'])).days<=7)
    prices={k:float(o['value']) if o['value'] is not None else None for k,o in quote['observations'].items()} if fresh else {}
    quote_reason='stale_quote' if quote else 'missing_quote'
    financials={k:float(o['value']) if o['value'] is not None else None for k,o in obs.items()}
    financials.update(currency='EUR',monetary_unit='base',period_type='annual',period=current['period_end'],
        statement_periods={k:current['period_end'] for k in ('income','cashflow','balance')},capex_convention='outflow_magnitude',
        working_capital_convention='balance_change',ebit=financials['operating_income'],ebit_basis='operating income proxy (supplied local statements)',
        sector='Operating company',instrument_type='EQUITY')
    if len(periods)>1:
        financials.update(prior_period=periods[-2]['period_end'],revenue_prior=float(periods[-2]['observations']['revenue']['value']) if periods[-2]['observations']['revenue']['value'] is not None else None)
    state=SimpleNamespace(ticker=ticker,results={'get_financials':dict(ticker=ticker,financials=financials)})
    if fresh:state.results['get_prices']=dict(ticker=ticker,currency='EUR',monetary_unit='base',**prices)
    ratios=compute_ratios({'ticker':ticker},state)
    if ratios.get('error'):raise ValueError('Ratio calculation failed')
    metrics=[];derivations=[];series=[]
    def add(ident,label,num,unit,pointers,method='sourced_annual',rounding='source_decimal',period=current['period_end'],asof=None,
            reason=None,visibility='main',parameters=(),availability=None):
        present=num is not None and reason is None
        status='available' if present else availability or ('withheld' if reason in {'stale_quote','bridge_incomplete','unsupported_equity_claims','distressed_equity'} else 'unavailable')
        did='derive-'+ident
        metrics.append(dict(id=ident,label=label,value=decimal(num) if present else None,unit=unit,currency='EUR' if unit in {'currency','currency_per_share'} else None,
            period_end=period,as_of=asof,visibility=visibility,availability=status,reason_codes=[] if present else [reason or 'missing_observation'],derivation_id=did if present else None))
        if present:
            derivations.append(dict(id=did,method=method,input_pointers=pointers,parameter_pointers=list(parameters),metric_ids=[ident],rounding=rounding))
        return ident
    perf=[]
    for index,item in enumerate(periods):
        year=item['period_end'][:4];rv=item['observations']['revenue']['value'];ni=item['observations']['net_income']['value']
        rid=add('revenue-'+year,'Annual revenue '+year,rv,'currency',[p('revenue',index)],period=item['period_end'])
        margin=round(float(ni)/float(rv),4) if rv is not None and Decimal(rv)>0 and ni is not None else None
        mid=add('net-margin-'+year,'Annual net margin '+year,margin,'fraction',[p('net_income',index),p('revenue',index)],'net_margin','engine_ratio_4dp',period=item['period_end'],reason=None if margin is not None else 'nonpositive_revenue' if rv is not None and Decimal(rv)<=0 else 'missing_observation')
        perf.extend([rid,mid])
    for key,label in [('operating_income','Operating income'),('net_income','Attributable ordinary net income'),('total_debt','Period-end debt including leases'),('cash_and_equivalents','Period-end unrestricted cash')]:
        perf.append(add(key.replace('_','-'),label,obs[key]['value'],'currency',[p(key)]))
    for key,label,inputs in [('gross_margin','Gross margin',['gross_profit','revenue']),('operating_margin','Operating margin',['operating_income','revenue']),
                             ('revenue_growth_yoy','Revenue growth',['revenue'])]:
        num=ratios['ratios'][key]
        ident='revenue-yoy' if key=='revenue_growth_yoy' else key.replace('_','-')
        pointers=[p(k) for k in inputs]
        if key=='revenue_growth_yoy' and len(periods)>1:pointers.append(p('revenue',len(periods)-2))
        reason=None if num is not None else 'history_gap' if key=='revenue_growth_yoy' else 'nonpositive_revenue' if value('revenue')<=0 else 'missing_observation'
        perf.append(add(ident,label,num,'fraction',pointers,'revenue_yoy' if key=='revenue_growth_yoy' else key,'engine_ratio_4dp',reason=reason))
    suffix=[]
    for item in reversed(periods):
        rev=item['observations']['revenue']['value']
        if rev is None or Decimal(rev)<=0 or suffix and not annual_pair(suffix[-1]['period_end'],item['period_end']):break
        suffix.append(item)
    cagr=None
    if len(suffix)>=3:
        with localcontext() as context:
            context.prec=40
            cagr=(Decimal(suffix[0]['observations']['revenue']['value'])/Decimal(suffix[-1]['observations']['revenue']['value']))**(Decimal(1)/(len(suffix)-1))-1
        cagr=round(float(cagr),16)
    perf.append(add('revenue-cagr','Revenue CAGR '+(' / '.join([suffix[-1]['period_end'],suffix[0]['period_end']]) if suffix else ''),cagr,'fraction',
        [p('revenue',i) for i in range(len(periods)-len(suffix),len(periods))],'revenue_cagr','engine_float_decimal',reason=None if cagr is not None else 'insufficient_history'))
    claims=['noncontrolling_interests','preferred_equity','other_equity_claims']
    bridge_reason='bridge_incomplete' if any(value(k) is None for k in ['total_debt','cash_and_equivalents']+claims) else 'unsupported_equity_claims' if any(value(k)!=0 for k in claims) else None
    for ident,label,key,inputs,method in [('annual-pe','Dated quote / annual earnings','pe',[q('market_cap'),p('net_income')],'annual_pe'),
                 ('ev-operating-income','Dated EV / annual operating income','ev_ebit',[q('market_cap'),p('total_debt'),p('cash_and_equivalents'),p('operating_income')]+[p(k) for k in claims],'ev_operating_income')]:
        reason=None;status=None
        if not fresh:reason=quote_reason
        elif ident=='ev-operating-income' and bridge_reason:reason=bridge_reason
        elif value('net_income' if ident=='annual-pe' else 'operating_income') is not None and value('net_income' if ident=='annual-pe' else 'operating_income')<=0:
            reason='nonpositive_earnings' if ident=='annual-pe' else 'nonpositive_operating_income';status='not_applicable'
        num=ratios['ratios'].get(key) if not reason else None
        perf.append(add(ident,label,num,'multiple',inputs,method,'engine_ratio_4dp',reason=reason,availability=status,asof=quote['as_of'] if quote else None,visibility='supporting'))
    val=request['analysis_plan']['valuation'];val_ids=[];v_reason=None;v_status='available'
    dcf=None
    fcff_fields=['operating_income','depreciation_amortization','capex','change_in_working_capital']
    if not val:v_reason='excluded_by_plan';v_status='not_applicable'
    elif bridge_reason:v_reason=bridge_reason;v_status='withheld'
    elif any(value(k) is None for k in fcff_fields):v_reason='missing_fcff_input';v_status='withheld'
    else:
        tax=Decimal(val['tax_rate']) if val['tax_basis']=='explicit_rate' else value('tax_provision')/value('pretax_income') if value('pretax_income') is not None and value('pretax_income')>0 and value('tax_provision') is not None else None
        if tax is None or not 0<=tax<=1:v_reason='tax_basis_unavailable';v_status='withheld'
        elif value('operating_income')*(1-tax)+value('depreciation_amortization')-value('capex')-value('change_in_working_capital')<=0:
            v_reason='nonpositive_fcff';v_status='not_applicable'
        else:
            args={k:float(val[k]) for k in ('discount_rate','terminal_growth','high_growth')}
            args.update(ticker=ticker,horizon_years=val['horizon_years'],weights={k:float(x) for k,x in val['weights'].items()},tax_rate=float(tax))
            dcf=run_dcf(args,state)
            if dcf.get('error'):raise ValueError('DCF calculation failed')
    vp=[p(k) for k in fcff_fields+['total_debt','cash_and_equivalents']+claims]
    if val and val['tax_basis']=='effective_rate':vp += [p('tax_provision'),p('pretax_income')]
    params=['/analysis_plan/valuation']
    val_ids.append(add('base-fcff','Base FCFF',dcf['assumptions']['fcf_base'] if dcf else None,'currency',vp,'fcff','engine_float_decimal',reason=v_reason,availability=v_status if v_reason else None,visibility='diagnostic',parameters=params))
    for scenario in ('bear','base','bull'):
        for field,label,key,unit,rounding in [('ev','Enterprise value','enterprise_value','currency','engine_amount_0dp'),('equity','Equity value','equity_value','currency','engine_amount_0dp'),
                ('per-share','Equity value per share','value_per_share','currency_per_share','engine_per_share_2dp'),('terminal-concentration','Terminal-value concentration','terminal_value_concentration','fraction','engine_fraction_4dp')]:
            num=(dcf.get(key) or {}).get(scenario) if dcf else None;reason=v_reason
            if dcf and field=='per-share' and num is None:reason='distressed_equity' if dcf['applicability']=='distressed_equity' else 'missing_shares' if fresh else quote_reason
            val_ids.append(add(scenario+'-'+field,label+' · '+scenario,num,unit,vp+([q('shares_outstanding')] if field=='per-share' and num is not None else []),
                'dcf_scenario',rounding,reason=reason,visibility='diagnostic',parameters=params,availability=v_status if v_reason else None,asof=quote['as_of'] if quote and field=='per-share' else None))
    for ident,label,key,unit,method in [('weighted-per-share','Scenario-weighted equity value per share','scenario_weighted_per_share','currency_per_share','dcf_weighted'),
                    ('model-value-gap','Conditional model-value gap','implied_upside','fraction','model_value_gap')]:
        num=dcf.get(key) if dcf else None;reason=v_reason
        if dcf and num is None:reason='distressed_equity' if dcf['applicability']=='distressed_equity' else quote_reason if not fresh else 'missing_shares' if not prices.get('shares_outstanding') else 'missing_observation'
        val_ids.append(add(ident,label,num,unit,vp+([q('shares_outstanding')]+([q('current_price')] if ident=='model-value-gap' else []) if num is not None else []),
            method,'engine_per_share_2dp' if unit=='currency_per_share' else 'engine_fraction_4dp',reason=reason,availability=v_status if v_reason else None,visibility='diagnostic',parameters=params,asof=quote['as_of'] if quote else None))
    by_id={m['id']:m for m in metrics}
    for ident,label,unit,field in [('revenue-history','Annual revenue','currency','revenue'),('net-margin-history','Annual net margin','fraction','net-margin')]:
        points=[]
        for item in periods:
            metric=by_id[field+'-'+item['period_end'][:4]]
            points.append(dict(date=item['period_end'],value=metric['value'],metric_id=metric['id'] if metric['value'] is not None else None,reason_codes=metric['reason_codes']))
        series.append(dict(id=ident,label=label,kind='bar' if unit=='currency' else 'line',unit=unit,currency='EUR' if unit=='currency' else None,points=points))
    sections=[dict(id='summary',requested=True,availability='available',reason_codes=[],metric_ids=['revenue-'+current['period_end'][:4],'operating-margin','revenue-yoy']),
              dict(id='performance',requested=True,availability='available',reason_codes=[],metric_ids=perf),
              dict(id='valuation',requested=val is not None,availability=v_status,reason_codes=[v_reason] if v_reason else [],metric_ids=val_ids)]
    sections += [dict(id=k,requested=False,availability='unavailable',reason_codes=['unsupported_input_group'],metric_ids=[]) for k in ('peers','market','consensus','external-research')]
    sections.append(dict(id='evidence',requested=True,availability='available',reason_codes=[],metric_ids=[]))
    checks=[dict(id='source-basis',status='review',reason_code='synthetic_evidence' if binding['classification']=='synthetic' else 'operator_attested_origin',
                 section_ids=list(SECTIONS),detail='Supplied local observations require financial review. Matching files do not establish source authenticity.')]
    for reason in sorted({r for m in metrics for r in m['reason_codes']}):
        checks.append(dict(id='check-'+reason,status='hold',reason_code=reason,section_ids=[s['id'] for s in sections if any(reason in by_id[i]['reason_codes'] for i in s['metric_ids'])],detail=reason.replace('_',' ').capitalize()+'. Inspect the exact supplied observations and selected scope.'))
    if any(s['published_at'] is None or s['retrieved_at'] is None for s in package['sources']):
        checks.append(dict(id='source-dates',status='review',reason_code='source_dates_unknown',section_ids=['evidence'],detail='Source publication/retrieval instants are unknown. Processing time is not an observation date.'))
    if (day-date.fromisoformat(current['period_end'])).days>548:
        checks.append(dict(id='old-statements',status='review',reason_code='stale_statements',section_ids=['summary','performance','valuation'],detail='Annual statements are older than 548 days. These are dated historical observations.'))
    lineage={k:binding[k] for k in ('workspace_id','dataset_id','version_id','contract_sha256','payload_sha256','receipt_sha256','entity_sha256','policy_sha256')}
    lineage.update(job_id=job_id,operation_id='web-'+job_id[4:],request_sha256=c.fingerprint(request),analysis_plan_sha256=c.fingerprint(request['analysis_plan']),
        source_reference_sha256=c.fingerprint(request['source']),assumption_review_sha256=c.fingerprint(request['assumption_review']) if request['assumption_review'] else None)
    result=dict(schema_version=1,kind='keystone.local-research-result',source_schema='agent1.local-analysis/1',result_id='result-'+job_id[4:],
        identity=dict(entity_id=payload['entity_id'],listing=payload['listing'],currency='EUR',monetary_unit='base',period_start=current['period_start'],period_end=current['period_end']),
        execution=dict(mode='local_inputs',status='completed',profile='calculate-local-research',profile_version=1,evaluated_on=evaluated_on,
            financial_approval=False,live_data_enabled=False,paid_models_enabled=False,provider_requests=0,model_calls=0,output_tokens=0),
        provenance=dict(classification=binding['classification'],source_integrity='matched',source_authenticity='not_independently_verified',producer={**producer, 'validator_version':'financial-kit/1.0.0','recipe':'agent1-local-report/1.0.0'}),
        lineage=lineage,analysis_plan=request['analysis_plan'],evidence_gate='review_required',sections=sections,metrics=metrics,series=series,derivations=derivations,checks=checks)
    validate_shape('result',result)
    if len(c.canonical(result))>2_000_000:raise ValueError('Result capacity')
    return result
