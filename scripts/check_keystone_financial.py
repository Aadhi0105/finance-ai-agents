"""Frozen Batch 4 offline financial acceptance. No production approval is inferred."""
from copy import deepcopy
from contextlib import closing
from datetime import date
from decimal import Decimal, localcontext
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'fixtures/production_v1/batch4-plan.json'
FROZEN_SHA='5360ea173751f61212d6bc6180dc522f60f76df6eca8c6500a10a46714a06f29'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def require(value, message):
    if not value:raise AssertionError(message)
def close(actual,expected,tolerance):
    require(actual is not None and abs(Decimal(str(actual))-Decimal(str(expected)))<=Decimal(str(tolerance)),
            f'numerical mismatch: {actual} vs {expected}')


def state(fin,prices,ticker='TST'):
    from agent.state import RunState
    s=RunState(ticker)
    contract=dict(currency='EUR',monetary_unit='base',period_type='annual',period='2025-12-31',
                  prior_period='2024-12-31',working_capital_convention='balance_change',capex_convention='outflow_magnitude',
                  statement_periods={'income':'2025-12-31','balance_sheet':'2025-12-31','cash_flow':'2025-12-31'})
    s.results={'get_financials':{'ticker':ticker,'financials':{**contract,**fin}},
               'get_prices':{'ticker':ticker,'currency':'EUR','monetary_unit':'base',**prices}}
    return s


def discounted_oracle(fcff,case):
    # Decimal cumulative growth products and discounted cash-flow sums, independent
    # of the application's float DCF helpers and returned assumptions.
    with localcontext() as ctx:
        ctx.prec=40
        n=case['horizon_years']; r=Decimal(str(case['discount_rate'])); terminal=Decimal(str(case['terminal_growth']))
        answers={}
        for name,delta in [('bear','-0.04'),('base','0'),('bull','0.04')]:
            high=Decimal(str(case['high_growth']))+Decimal(delta)
            growth=[high if n==1 else high+(terminal-high)*Decimal(i)/Decimal(n-1) for i in range(n)]
            cash=[];acc=Decimal(str(fcff))
            for g in growth:acc*=1+g;cash.append(acc)
            pv=sum(amount/(1+r)**(i+1) for i,amount in enumerate(cash))
            answers[name]=pv+cash[-1]*(1+terminal)/(r-terminal)/(1+r)**n
        return answers


def agent1(plan):
    from tools.analytical import run_dcf,compute_ratios
    from tools.issuer_reconciliation import apply_reviewed_profile
    from validation.qualitative_claims import control_note
    reference=read(ROOT/'references/issuer/ASML.AS-2025-12-31.json')
    retained=read(ROOT/'references/issuer/ASML.AS-provider-2026-09-26.json')
    normalized=deepcopy(retained['financials']);f=normalized['financials']
    f['provider_ebit']=f['ebit'];f['ebit']=f['operating_income']
    normalized=apply_reviewed_profile(normalized)
    require(normalized['issuer_reconciliation']['status']=='matched','ASML retained reconciliation')
    lines=reference['expected_provider_fields'];D=lambda x:Decimal(str(x))
    wc=sum(reference['cash_flow_components'].values())-reference['cash_flow_components']['current_tax_assets_and_liabilities']
    expected=D(lines['operating_income'])*(1-D(lines['tax_provision'])/D(lines['pretax_income']))+D(lines['depreciation_amortization'])-D(lines['capex'])+D(wc)
    s=state({},retained['prices'],'ASML.AS');s.results['get_financials']=normalized
    result=run_dcf({'ticker':'ASML.AS'},s)
    close(result['assumptions']['fcf_base'],expected,plan['thresholds']['fcff_base_currency'])
    require(reference['operating_cash_flow']-reference['pp_and_e_purchases']-reference['intangible_purchases']==lines['free_cash_flow'],'ASML cash flow identity')
    require(reference['current_borrowings']+reference['noncurrent_debt']==lines['total_debt'],'ASML debt identity')
    ratios=compute_ratios({'ticker':'ASML.AS'},s)['ratios']
    for key,numerator in [('gross_margin','gross_profit'),('operating_margin','operating_income'),('net_margin','net_income')]:
        close(ratios[key],D(lines[numerator])/D(lines['revenue']),plan['thresholds']['rounded_ratio'])
    base={'ebit':1000,'depreciation_amortization':200,'capex':100,'tax_provision':250,'pretax_income':1000,
          'change_in_working_capital':0,'total_debt':300,'cash_and_equivalents':100}
    prices={'shares_outstanding':10,'current_price':500}
    cases=[]
    for case in plan['dcf_cases']:
        actual=run_dcf({'ticker':'TST',**{k:v for k,v in case.items() if k!='id'}},state(base,prices))
        expected_ev=discounted_oracle(850,case)
        for scenario,ev in expected_ev.items():
            close(actual['enterprise_value'][scenario],ev,plan['thresholds']['rounded_ev_currency'])
            close(actual['equity_value'][scenario],ev-200,plan['thresholds']['rounded_ev_currency'])
            close(actual['value_per_share'][scenario],(ev-200)/10,plan['thresholds']['rounded_per_share_currency'])
        weighted=sum((expected_ev[k]-200)*Decimal(w) for k,w in [('bear','.25'),('base','.5'),('bull','.25')])/10
        close(actual['scenario_weighted_per_share'],weighted,plan['thresholds']['rounded_per_share_currency'])
        cases.append({'id':case['id'],'scenarios':3,'status':'passed'})
    for patch in ({'ebit':-5000},{'sector':'Financial Services'},{'capex':None}):
        require(run_dcf({'ticker':'TST'},state({**base,**patch},prices)).get('error'),'DCF boundary must refuse')
    incomplete=run_dcf({'ticker':'TST'},state({**base,'total_debt':None},prices))
    require(incomplete['value_basis']=='enterprise_value_only' and incomplete['scenario_weighted_per_share'] is None,'incomplete equity bridge')
    require(run_dcf({'ticker':'TST'},state(base,{**prices,'currency':'USD'})).get('error'),'currency mismatch')
    claim='The company is guaranteed to outperform. [Issuer](https://example.invalid)'
    controlled=control_note(claim+'\n[[claim:revenue]]',{'get_financials':normalized})
    require(claim in controlled['withheld_lines'] and claim not in controlled['published_note'],'unsupported claim leaked')
    return {'status':'passed','retained_issuer':'ASML.AS FY2025','independent_fcff':str(expected),
            'dcf_cases':cases,'negative_cases':len(plan['agent1_boundaries']),
            'limitations':['Retained reference, not fresh PDF verification.','No current price/share or forecast certification.']}


def agent2(plan,out):
    from monitoring.live_data import load_profile,observation
    from scheduler.cycle import _run_cycle
    from state.store import StateStore
    from monitoring.recovery import decide
    ref=read(ROOT/'references/monitoring/SRAIL.SW-2025-12-31.json')
    items=load_profile(ROOT/'watchlists/stadler-annual.json')['items'];today=date(2026,10,10)
    snap=dict(ticker='SRAIL.SW',source='yfinance',period='2025-12-31',period_type='annual',currency='CHF',monetary_unit='base',values=deepcopy(ref['expected_fields']))
    expected=[Decimal(4236715)/Decimal(4428274),Decimal(160571)/Decimal(42378),Decimal(275453)/Decimal(278451)]
    actual=[]
    for item,value in zip(items,expected):
        obs=observation(item,snap,today);close(obs['value'],value,plan['thresholds']['unrounded_ratio']);actual.append(obs['value'])
    patches=[({'error':'provider_timeout'},'provider_timeout'),({'period':'2020-12-31'},'stale_reporting_period'),
             ({'period':'2027-12-31'},'future_period'),({'currency':'EUR'},'currency_or_unit_mismatch'),
             ({'monetary_unit':'millions'},'currency_or_unit_mismatch'),({'period_type':'quarterly'},'annual_period_required'),
             ({'period':'2026-06-30'},'issuer_reference_required'),({'values':{**snap['values'],'current_assets':snap['values']['current_assets']+100000}},'issuer_reconciliation_mismatch')]
    for patch,reason in patches:
        obs=observation(items[0],{**snap,**patch},today)
        require(obs['value'] is None and obs['reason']==reason,reason)
    db=str(out/'monitor.duckdb')
    def cycle(value):return _run_cycle(db,live_inputs=[{'item':item,'observation':observation(item,value,today)} for item in items],observed_on=today)
    first=cycle(snap);second=cycle(snap)
    require(len(first['rows'])==3 and not first['surfaced'],'baseline contract')
    require(first['rows'][0]['breached'] is True,'baseline liquidity breach hidden')
    require(second['status']=='no_new_observations','duplicate refreshed history')
    outage=cycle({**snap,'error':'provider_timeout'})
    require(outage['status']=='review_required' and not outage['rows'],'outage must hold')
    with closing(StateStore(db)) as store:require(len(store.full_state())==3,'outage discarded prior state')
    # Deliberate synthetic, sub-resolution correction; not an asserted issuer revision.
    changed=deepcopy(snap);changed['values']['current_assets']+=500
    cycle(changed)
    with closing(StateStore(db)) as store:review=store.reviews()[0]
    decide(db,review['review_id'],'approve','synthetic acceptance harness','Controlled within-resolution correction, not an issuer claim')
    corrected=(Decimal(4236715000)+500)/Decimal(4428274000)
    with closing(StateStore(db)) as store:
        close(next(r for r in store.full_state() if r['item_id']==items[0]['item_id'])['value'],corrected,1e-12)
        require(store.get_run(1)==first,'approval rewrote original cycle')
    rejected=deepcopy(changed);rejected['values']['current_assets']+=250
    cycle(rejected)
    with closing(StateStore(db)) as store:review=store.reviews()[0]
    decide(db,review['review_id'],'reject','synthetic acceptance harness','Controlled rejected correction')
    with closing(StateStore(db)) as store:
        close(next(r for r in store.full_state() if r['item_id']==items[0]['item_id'])['value'],corrected,1e-12)
    replay=_run_cycle(db,asof_cycle=1,live_inputs=[],observed_on=today)
    require(replay=={**first,'replayed':True},'original cycle replay mismatch')
    return {'status':'passed','ratios':actual,'scenarios':plan['agent2_scenarios'],
            'scope':'offline constructed adapter inputs from retained issuer reference; synthetic correction workflow; no live fetch or human approval'}


def news(plan):
    from agent3.news_funnel import ingest,relevance_filter,dedup_cluster,run_funnel
    from agent3.sentiment import LoughranMcDonaldScorer
    p=plan['news'];asof=plan['as_of'];errors=[]
    def item(identity,headline,**patch):
        return dict(id=identity,headline=headline,body='',url='https://example.invalid/'+identity,source='synthetic',language='en',
                    published_at='2026-10-09T12:00:00Z',retrieved_at=asof,entities=[],**patch)
    counts={'tp':0,'fp':0,'fn':0,'tn':0}
    for case in p['relevance']:
        raw=item(case['id'],case['headline']);raw.update(body=case['body'],entities=case['provider_entities'])
        rows=relevance_filter(ingest([raw],as_of=asof),list(p['aliases']),aliases=p['aliases'])
        found=set(rows[0]['entities'] if rows else []);expected=set(case['expected_entities'])
        if found!=expected:errors.append({'id':case['id'],'expected':sorted(expected),'actual':sorted(found)})
        for tk in p['aliases']:
            counts['tp' if tk in found and tk in expected else 'fp' if tk in found else 'fn' if tk in expected else 'tn']+=1
    for case in p['freshness']:
        raw=item(case['id'],'ASML reports results');raw['published_at']=case['published_at'];excluded=[]
        rows=ingest([raw],as_of=asof,exclusions=excluded)
        found='accepted' if rows else excluded[0]['reason']
        if found!=case['expected']:errors.append({'id':case['id'],'expected':case['expected'],'actual':found})
    for case in p['dedup']:
        a=item(case['id']+'a',case['a']);b=item(case['id']+'b',case['b'])
        a['published_at']=case.get('first_at',a['published_at']);b['published_at']=case.get('second_at',b['published_at'])
        rows=relevance_filter(ingest([a,b],as_of=asof),list(p['aliases']),aliases=p['aliases'])
        actual=len(dedup_cluster(rows))
        if actual!=case['clusters']:errors.append({'id':case['id'],'expected':case['clusters'],'actual':actual})
    funnel=run_funnel([item('tone','ASML reports strong profit growth')],list(p['aliases']),LoughranMcDonaldScorer(),aliases=p['aliases'],as_of=asof)
    require(funnel['status']=='held' and all(s['level'] is None for s in funnel['signals']),'synthetic tone was published')
    return {'status':'failed' if errors else 'passed','relevance_cases':len(p['relevance']),'freshness_cases':len(p['freshness']),
            'dedup_cases':len(p['dedup']),'entity_label_confusion_counts':counts,'mismatches':errors,
            'human_reviewed':False,'production_quality_accepted':False}


def run(output):
    require(sha(PLAN)==FROZEN_SHA,'Evaluation plan changed; version and freeze before running')
    plan=read(PLAN);out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    for path,expected in plan['source_hashes'].items():require(sha(ROOT/path)==expected,'Source changed: '+path)
    result={'schema_version':1,'plan_sha256':FROZEN_SHA,'candidate_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'worktree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
            'runner_sha256':sha(__file__),'started_at':datetime.now(timezone.utc).isoformat(),'sections':{},'blocked':plan['blocked'],'production_release_approved':False}
    def section(name,fn):
        try:result['sections'][name]=fn()
        except Exception as exc:result['sections'][name]={'status':'failed','error_type':type(exc).__name__,'detail':str(exc)}
        (out/'acceptance.json').write_text(json.dumps(result,indent=2,default=str,allow_nan=False)+'\n')
    section('agent1',lambda:agent1(plan));section('agent2',lambda:agent2(plan,out));section('news',lambda:news(plan))
    def events():
        from agent3.bundles import read_bundle
        from scripts.check_agent3_closure import verify
        reports=[]
        for entry in plan['retained_event_bundles']:
            p=ROOT/entry['path']
            if not p.exists():return {'status':'blocked','reason':'Retained bundle unavailable; no automatic refetch.'}
            require(sha(p)==entry['sha256'],'Retained event bundle changed')
            reports.append(verify(read_bundle(p)))
        return {'status':'passed','reports':reports,'fresh_issuer_verification':False}
    section('events',events)
    def fpna():
        from scripts.check_agent4_closure import run_acceptance
        value=run_acceptance(out/'agent4')
        require(value['committed_closes']==plan['agent4_expected_closes'],'Unexpected close count')
        return {'status':'passed','synthetic_result':value,'company_acceptance':'blocked: authorised data unavailable'}
    section('agent4',fpna)
    result['finished_at']=datetime.now(timezone.utc).isoformat()
    result['status']='failed' if any(v['status']=='failed' for v in result['sections'].values()) else 'offline_checks_passed_with_release_holds'
    require(sha(PLAN)==FROZEN_SHA,'Plan changed during evaluation')
    (out/'acceptance.json').write_text(json.dumps(result,indent=2,default=str,allow_nan=False)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);args=p.parse_args()
    os.environ.update(AGENT_DATA_SOURCE='fixture',AGENT_STATS_VIA_MCP='0',AGENT_SENTIMENT_SCORER='lm',LM_DICTIONARY_CSV='')
    from keystone.maintenance import gate
    with gate():
        result=run(args.output)
    print(json.dumps(result,indent=2,default=str));raise SystemExit(1 if result['status']=='failed' else 0)
