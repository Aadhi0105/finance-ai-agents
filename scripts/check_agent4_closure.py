"""Independently reconciled synthetic close lifecycle. Offline local/MCP acceptance.

Expected accounting and selected projection answers live in control-ledger.json.
The verifier uses direct sums/subtraction and Fraction, never the production
roll-up, projection, persistence or formatting functions as an expected-value oracle.
"""
from copy import deepcopy
from fractions import Fraction
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from agent4.close import execute_close, deliver_run
from agent4.report import export_reports, validate_bundle
from agent4.state import VarianceStore

FIXTURE=Path(__file__).resolve().parents[1]/'fixtures/agent4/closure/control-ledger.json'


def require(condition, message):
    if not condition:raise AssertionError(message)


def money(value):
    return ('-' if value<0 else '')+'€'+f'{abs(value)//100:,}.{abs(value)%100:02d}'


def row(line,period,amount):
    return dict(line=line,period=period,amount_cents=amount)


def budget(case,revised=False):
    rows=[row(line,p,amount) for p in case['history_periods'] for line,amount in [('sales',100000),('cost',60000)]]
    sales=case['revised_budget_sales' if revised else 'budget_sales']
    rows += [row(line,p,amount) for i,p in enumerate(case['periods']) for line,amount in [('sales',sales[i]),('cost',case['budget_cost'][i])]]
    return dict(version='plan-revised' if revised else 'plan-original',approved=True,source='controlled synthetic approved plan',rows=rows)


def request(case,index,revised=False):
    p=case['periods'][index]
    rows=[row('sales',p,case['actual_sales'][index]),row('cost',p,case['actual_cost'][index])]
    if index==0:
        rows=[row(line,period,case['history_sales' if line=='sales' else 'history_cost'][i]) for i,period in enumerate(case['history_periods']) for line in ('sales','cost')]+rows
    return dict(run_id=f'close-{index+1:02d}',entity='Controlled Synthetic Manufacturing',data_kind='synthetic',
        close_period=p,frequency='monthly',budget=budget(case,revised),
        actuals=dict(version=f'actual-{index+1:02d}',source='controlled synthetic closed ledger',rows=rows),
        tree=dict(name='Operating profit',node_id='profit',root_measure='profit',children=[
            dict(name='Sales',node_id='sales',sign='add',leaf=dict(type='revenue')),
            dict(name='Operating costs',node_id='cost',sign='subtract',leaf=dict(type='fixed_cost'))]))


def verify_answer_key(case):
    """Sanity-check the authored key independently of the application engine."""
    a=case['answer_key'];sales=case['actual_sales'];cost=case['actual_cost']
    profit=[s-c for s,c in zip(sales,cost)]
    require(profit==a['monthly_profit_original'],'answer-key monthly arithmetic')
    require([sum(profit[:i]) for i in range(1,8)]==a['ytd_profit_before_restatement'],'answer-key YTD arithmetic')
    correction=case['restatement']['amount_cents']-sales[1]
    require([sum(profit[:i])+correction for i in range(7,13)]==a['ytd_profit_after_restatement'],'answer-key restated YTD')
    require(sum(case['budget_sales'])-sum(case['budget_cost'])==a['original_annual_profit_budget'],'original budget key')
    revised=[s-c for s,c in zip(case['revised_budget_sales'],case['budget_cost'])]
    require(revised==a['monthly_budget_profit_revised'] and sum(revised)==a['revised_annual_profit_budget'],'revised budget key')
    require(sum(profit[:3])+9*40000==a['march_profit_landing'],'one-off normalized profit key')
    require(sum(sales[:3])+9*100000==a['march_sales_landing'],'one-off normalized sales key')
    for key,ytd,annual in [('july_profit_landing',340000,480000),('july_restated_profit_landing',345000,480000),('july_rebudget_profit_landing',345000,555000)]:
        require(round(Fraction(ytd*annual,280000))==a[key],key)
    require(sum(sales)+correction==a['year_end_sales'] and sum(cost)==a['year_end_cost'],'year-end line key')
    require(sum(profit)+correction==a['year_end_profit'],'year-end profit key')
    # Assumption schedule is authored independently: normalize isolated/noise
    # cases to remaining plan; use the phased ratio for ambiguous/persistent
    # cases; the closed year is actual. No classifier outputs are used here.
    original=[sum(profit[:m])+(12-m)*40000 if m<=5 else round(Fraction(sum(profit[:m])*480000,m*40000)) for m in range(1,8)]
    revised_landings=[395000+4*55000,round(Fraction(445000*555000,390000)),495000+2*55000,round(Fraction(545000*555000,500000)),595000]
    require(original==a['profit_landings_original'],'monthly original landing key')
    require(revised_landings==a['profit_landings_revised'],'monthly revised landing key')


def state_counts(store):
    return {kind:len(store.versions(kind)) for kind in ('budget','actuals','reforecast')} | {'runs':store.con.execute('SELECT count(*) FROM a4_runs').fetchone()[0]}


def expect_refusal(store,req,reason):
    before=state_counts(store)
    try:execute_close(store,req)
    except ValueError as exc:
        require(reason in str(exc),f'wrong rejection: {exc}')
    else:raise AssertionError('invalid close unexpectedly committed')
    require(state_counts(store)==before,'rejected close changed accounting versions')
    require(store.get_run(req['run_id']) is None,'rejected close has saved result')


def check_run(saved, expected, records):
    b=validate_bundle(saved);r=b['report'];t=r['full_hierarchy'];rf=r['reforecasts']['profit']
    for key,value in expected.items():
        observed={'actual':t['actual_cents'],'budget':t['budget_cents'],'ytd':rf['inputs']['ytd_cents'],
                  'annual_budget':rf['inputs']['full_year_budget_cents'],'landing':rf.get('projected_landing_cents'),
                  'persistence':t['persistence']['persistence']}[key]
        require(observed==value,f'{b["run_id"]} {key}: expected {value}, got {observed}')
    require(t['total_variance_cents']==expected['actual']-expected['budget'],'close variance control')
    require(len(t['history_snapshot']['prior_cents'])+1==len(rf['inputs']['variance_history_cents']),'current counted once')
    require(r['reconciliation']['passed'] and t['source_reconciliation']=='matched','publication controls')
    accounting=next(c['text'] for c in r['commentary'] if c['node_id']=='profit' and c['kind']=='accounting')
    require(money(t['actual_cents']) in accounting and money(t['budget_cents']) in accounting,'headline source amounts')
    for ident,f in r['reforecasts'].items():
        prob=f.get('prob_hit_target');band=f.get('band_cents')
        if prob is not None:require(0<=prob<=1,'probability outside range')
        if band is not None:require(band[0]<=f['projected_landing_cents']<=band[1],'landing outside range')
        if f.get('remaining_periods',1)>0:
            require(f.get('probability_kind')=='uncalibrated model estimate','probability caveat missing')
            require(any('not backtested' in x for x in f.get('assumptions',[])),'coverage caveat missing')
    records.append({'run_id':b['run_id'],'expected':expected,'actual_profit_cents':t['actual_cents'],
                    'variance_cents':t['total_variance_cents'],'ytd_profit_cents':rf['inputs']['ytd_cents'],
                    'profit_landing_cents':rf.get('projected_landing_cents'),'persistence':t['persistence']['persistence']})


def run_acceptance(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    case=json.loads(FIXTURE.read_text());verify_answer_key(case);a=case['answer_key'];records=[];snapshots={}
    db=output/'state.duckdb'
    with VarianceStore(db) as store:
        for i in range(7):
            req=request(case,i)
            if i==3:
                incomplete=deepcopy(req);incomplete['actuals']['rows'].pop()
                expect_refusal(store,incomplete,'incomplete')
            saved=execute_close(store,req);snapshots[req['run_id']]=saved['bundle_digest']
            expected=dict(actual=a['monthly_profit_original'][i],budget=40000,ytd=a['ytd_profit_before_restatement'][i],annual_budget=480000,landing=a['profit_landings_original'][i])
            if i in (2,5,6):expected['persistence']=a[{2:'march_persistence',5:'june_persistence',6:'july_persistence'}[i]]
            if i==2:expected['landing']=a['march_profit_landing']
            if i==6:expected['landing']=a['july_profit_landing']
            check_run(saved,expected,records)
            if i==2:
                require(saved['bundle']['report']['reforecasts']['sales']['projected_landing_cents']==a['march_sales_landing'],'March sales forecast')
                require('reversion is unconfirmed' in saved['bundle']['report']['full_hierarchy']['persistence']['reason'],'isolated spike overstated')
            before=state_counts(store)
            require(execute_close(store,req)['status']=='replayed','duplicate close did not replay')
            require(before==state_counts(store),'replay duplicated financial state')
        july=deepcopy(req)
        late=request(case,5);late['run_id']='late-june';late['actuals']['version']='late-june'
        expect_refusal(store,late,'stale close')
        correction=deepcopy(july);correction.update(run_id='july-restated',supersedes='close-07')
        correction['actuals']=dict(version='restatement-feb',source='controlled late February correction',rows=[case['restatement']])
        saved=execute_close(store,correction)
        snapshots[correction['run_id']]=saved['bundle_digest']
        check_run(saved,dict(actual=50000,budget=40000,ytd=345000,annual_budget=480000,landing=a['july_restated_profit_landing'],persistence='STRUCTURAL'),records)
        require(len(store.get_actuals('restatement-feb'))==38,'restatement dropped unaffected observations')
        require(store.get_actuals('actual-07')!=store.get_actuals('restatement-feb'),'restatement not effective')
        rebudget=deepcopy(correction);rebudget.update(run_id='july-rebudget',supersedes='july-restated');rebudget['budget']=budget(case,True)
        saved=execute_close(store,rebudget)
        snapshots[rebudget['run_id']]=saved['bundle_digest']
        check_run(saved,dict(actual=50000,budget=40000,ytd=345000,annual_budget=555000,landing=a['july_rebudget_profit_landing'],persistence='STRUCTURAL'),records)
        for i in range(7,12):
            saved=execute_close(store,request(case,i,True))
            snapshots[saved['bundle']['run_id']]=saved['bundle_digest']
            check_run(saved,dict(actual=50000,budget=55000,ytd=a['ytd_profit_after_restatement'][i-6],annual_budget=555000,landing=a['profit_landings_revised'][i-7]),records)
        rf=saved['bundle']['report']['reforecasts']['profit']
        require(rf['publication_status']=='deterministic' and rf['projected_landing_cents']==a['year_end_profit'],'closed-year landing')
        require(rf['band_cents']==[595000,595000] and rf['prob_hit_target']==a['year_end_hit_probability'],'closed-year outcome')
        require(rf['target_cents']==a['year_end_profit_target'],'closed-year target')
        require(saved['bundle']['report']['reforecasts']['sales']['projected_landing_cents']==a['year_end_sales'],'year-end sales')
        require(saved['bundle']['report']['reforecasts']['cost']['projected_landing_cents']==a['year_end_cost'],'year-end costs')
        for run_id,hash_value in snapshots.items():require(store.get_run(run_id)['bundle_digest']==hash_value,'historical report changed')
        blocked=output/'blocked';blocked.write_text('Deliberately unavailable output directory')
        for exporter in (deliver_run,export_reports):
            try:exporter(store,'close-12',blocked)
            except OSError:pass
            else:raise AssertionError('delivery failure not detected')
        require(store.get_run('close-12') is not None,'publication failure removed committed accounting')
        require([r['status'] for r in store.delivery_history('close-12')]==['failed','failed'],'missing failed delivery receipts')
        counts=state_counts(store)
    # Recovery happens on a fresh connection after close/rebudget/restatement.
    with VarianceStore(db) as store:
        delivered=deliver_run(store,'close-12',output/'recovered')
        export=export_reports(store,'close-12',output/'recovered')
        original_bytes=Path(delivered['path']).read_bytes()
        deliver_run(store,'close-12',output/'recovered')
        require(Path(delivered['path']).read_bytes()==original_bytes,'recovered JSON bytes changed')
        require(state_counts(store)==counts,'recovery changed financial state')
        folder=Path(export['html_path']).parent
        require((folder/'close-03.html').exists() and (folder/'july-restated.html').exists(),'history navigation incomplete')
        require('€5,950.00' in Path(export['html_path']).read_text(),'year-end HTML headline/forecast')
        require(json.loads((folder/'close-03.json').read_text())==store.get_run('close-03')['bundle'],'original evidence differs after recovery')
        # Compare meaningful frozen evidence across independent local/MCP runs;
        # timestamps and delivery paths deliberately differ and are excluded.
        parity={r['run_id']:{k:store.get_run(r['run_id'])['bundle'][k] for k in ('request','bound_tree','report','sources')} for r in records}
    # An explicitly missing prior-year period must hold inference, not be
    # silently filled or relabelled as a confident one-off.
    gap_req=request(case,0);gap_req.update(entity='Controlled History Gap',run_id='gap-close')
    gap_req['budget']['version']='gap-plan';gap_req['actuals']['version']='gap-actual'
    gap_req['actuals']['rows']=[r for r in gap_req['actuals']['rows'] if r['period']!='2025-07-31']
    with VarianceStore(output/'gap-state.duckdb') as store:
        gap=execute_close(store,gap_req)
        tree=gap['bundle']['report']['full_hierarchy'];rf=gap['bundle']['report']['reforecasts']['profit']
        require(tree['history_snapshot']['gaps'],'history gap not retained')
        require(tree['persistence']['persistence']=='UNKNOWN','gap produced confident persistence')
        require(rf['prob_hit_target'] is None and rf['band_cents'] is None,'gap published unsupported probability')
        export_reports(store,'gap-close',output/'gap-report')
        parity['gap-close']={k:gap['bundle'][k] for k in ('request','bound_tree','report','sources')}
    (output/'parity.json').write_text(json.dumps(parity,sort_keys=True,allow_nan=False)+'\n')
    summary={'status':'passed' ,'backend':'mcp' if os.getenv('AGENT_STATS_VIA_MCP')=='1' else 'local',
             'committed_closes':len(records),'auxiliary_history_gap':'passed','checks':['independent answer key','monthly closes','isolated spike','persistent pattern','missing input rollback/retry','late close rejection','partial restatement','formal re-budget','year-end exact outcome','duplicate replay','JSON/HTML failure and reopen recovery','historical immutability'],
             'state_counts':counts,'results':records,'html_path':export['html_path'],'database':str(db.resolve())}
    (output/'acceptance.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir');args=p.parse_args()
    if args.output_dir:out=Path(args.output_dir)
    else:
        root=Path('output/agent4-closure');root.mkdir(parents=True,exist_ok=True)
        parent=Path(tempfile.mkdtemp(prefix='acceptance-',dir=root));out=parent/'run'
    print(json.dumps(run_acceptance(out),indent=2))


if __name__=='__main__':main()
