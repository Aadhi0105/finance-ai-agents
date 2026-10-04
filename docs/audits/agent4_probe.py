"""Audit reproducer, not a passing acceptance suite. Run from repository root.
Uses only synthetic inputs and temporary databases; output is ignored.
"""
import json, tempfile, math
from pathlib import Path
from copy import deepcopy
from agent4.decomposition import decompose_line, decompose_multiproduct, _c
from agent4.hierarchy import rollup
from agent4.materiality import classify_variance
from agent4.persistence import classify_persistence
from agent4.reforecast import reforecast
from agent4.commentary import build_registry, reconcile, compose
from agent4.output import board_pack, variance_waterfall_svg
from agent4.state import VarianceStore

Path('output/agent4-audit').mkdir(parents=True, exist_ok=True)
out={}
def probe(name, fn):
    try: out[name]=fn()
    except Exception as e: out[name]={'exception':type(e).__name__, 'message':str(e)}
def line(b=1,a=2):
    return {'name':'Sales','type':'revenue','budget':{'amount':b},'actual':{'amount':a}}
def leaf(name,b=1,a=2,sign='add'):
    return {'name':name,'sign':sign,'leaf':dict(line(b,a),name=name)}
tree=rollup(json.loads(Path('fixtures/pnl.json').read_text()))
reg=build_registry(tree)
hist=[-10,10,-20,20,-30,30]
probe('decimal_rounding',lambda:{'input_euros':1.015,'cents':_c(1.015),'decimal_half_even_expected':102})
probe('bool_money',lambda:decompose_line(line(True,False)))
probe('conflicting_amount_and_units',lambda:decompose_line({'name':'Sales','type':'revenue','budget':{'amount':100,'price':100,'volume':100},'actual':{'amount':110,'price':1,'volume':100}}))
probe('empty_products',lambda:decompose_multiproduct('Sales','revenue',[]))
probe('zero_budget_mix',lambda:decompose_multiproduct('Sales','revenue',[{'name':'New','budget':{'price':10,'volume':0},'actual':{'price':10,'volume':100}}]))
probe('zero_net_joint',lambda:decompose_line({'name':'Sales','type':'revenue','budget':{'price':10,'volume':10},'actual':{'price':20,'volume':5}}))
probe('rate_basket_rollup',lambda:rollup({'name':'Profit','children':[{'name':'Cost','sign':'subtract','leaf':{'name':'Cost','type':'variable_cost','products':[{'name':'Steel','budget':{'rate':8,'volume':100},'actual':{'rate':9,'volume':100}}]}}]}))
probe('leaf_cost_root_favourability',lambda:rollup({'name':'Cost','leaf':{'name':'Cost','type':'fixed_cost','budget':{'amount':100},'actual':{'amount':110}}}))
probe('leaf_and_children',lambda:rollup({'name':'Root','leaf':line(), 'children':[leaf('Ignored',1,100000)]}))
probe('claimed_control_total_ignored',lambda:rollup({'name':'Profit','budget_cents':999999,'actual_cents':0,'children':[leaf('Sales',1,2)]}))
probe('zero_materiality',lambda:classify_variance({'name':'Zero','total_variance_cents':0},0,0))
probe('invalid_history_reason',lambda:classify_variance({'name':'X','total_variance_cents':100},1000,10000,[0,0,float('nan'),0,0,0]))
probe('persistence_invalid_history',lambda:classify_persistence([1,-1,1,-1,1,-1,float('nan')]))
probe('year_end_rewrites_actual',lambda:reforecast(600,1200,4,4,budget_phasing_cents=[150]*4,variance_history_cents=hist))
probe('year_end_no_history',lambda:reforecast(600,1200,4,4))
probe('no_elapsed_probability',lambda:reforecast(0,1200,0,4,variance_history_cents=hist))
probe('bad_phasing_silent_fallback',lambda:reforecast(300,1200,1,4,budget_phasing_cents=[300,300],variance_history_cents=hist))
probe('unknown_persistence',lambda:reforecast(300,1200,1,4,persistence='banana',variance_history_cents=hist))
probe('unaligned_actual_history',lambda:reforecast(100,1200,1,12,actual_history_cents=[10000]*8,variance_history_cents=hist))
probe('fractional_cents_forecast',lambda:reforecast(100.9,1200.5,1,4,variance_history_cents=hist))
probe('forged_reference_passes',lambda:reconcile([{'tier':'computed_fact','text':'Sales were €999,999.00.','refs':{'actual':99999900}}],reg))
probe('empty_percent_refs_pass',lambda:reconcile([{'tier':'observation','text':'P(hit target) 99%.','refs':{}}],reg))
probe('unverified_classification_passes',lambda:reconcile([{'tier':'observation','text':'Classified TOP_PRIORITY with confidence 0.99.','refs':{'quadrant':'TOP_PRIORITY','confidence':.99}}],reg))
probe('unlabelled_causal_hypothesis_passes',lambda:reconcile([{'tier':'hypothesis','text':'The new supplier caused the loss.','refs':{}}],reg))
probe('unknown_tier_passes',lambda:reconcile([{'tier':'fabricated','text':'Definitely verified by the issuer.','refs':{}}],reg))
probe('other_numeric_formats_pass',lambda:reconcile([{'tier':'computed_fact','text':'Actual USD 999999; 99 employees; margin 800 bps; EUR 800 million.','refs':{}}],reg))
def tamper():
    t=deepcopy(tree);t['actual_cents']+=10000000
    p=board_pack(t)
    return {'gate':p['reconciliation'],'reconciles':p['reconciles'],'budget':t['budget_cents'],'actual':t['actual_cents'],'variance':t['total_variance_cents']}
probe('tampered_board_pack',tamper)
probe('root_forecast_omitted',lambda:compose(tree,reforecast_by_line={tree['name']:reforecast(100,1200,1,4,variance_history_cents=hist)}))
probe('leaf_waterfall',lambda:variance_waterfall_svg(rollup({'name':'Sales','leaf':line(100,150)})))
probe('negative_waterfall',lambda:variance_waterfall_svg({'name':'Loss','budget_cents':-100,'actual_cents':-200,'children':[{'name':'Cost','profit_impact_cents':-100,'favourable':False}]}))
def state_cases():
    with tempfile.TemporaryDirectory() as d:
        s=VarianceStore(str(Path(d)/'state.db'))
        try:
            s.append_actuals('v1',[{'line':'A','period':'Q1','amount_cents':100}]);s.append_actuals('v1',[{'line':'A','period':'Q1','amount_cents':200}])
            dup=s.get_actuals('v1')
            s.append_actuals('v2',[{'line':'B','period':'Q2','amount_cents':300.9}])
            latest=s.get_actuals()
            s.record_reforecast('Q1',[{'line':'A','landing_cents':100,'prob_hit':None}],version='rf')
            s.record_reforecast('Q1',[{'line':'A','landing_cents':200,'prob_hit':2}],version='rf')
            walk=s.reforecast_walk('A')
            try:s.set_budget('partial',[{'line':'A','period':'Q1','amount_cents':100},{'line':'B','period':'Q1','amount_cents':10**30}])
            except Exception as e: failure=type(e).__name__
            return {'duplicate_actuals':dup,'latest_actuals':latest,'walk':walk,'partial_failure':failure,'remaining_budget_rows':s.get_budget('partial'),'versions':s.versions('reforecast')}
        finally:s.close()
probe('state_integrity',state_cases)
def collisions():
    t=rollup({'name':'Profit','children':[leaf('Same',1,2),leaf('Same',3,5)]})
    return build_registry(t)['numbers']
probe('duplicate_paths',collisions)
Path('output/agent4-audit/probes.json').write_text(json.dumps(out,indent=2,default=str))
for k,v in out.items():
    print(k, json.dumps(v,default=str)[:600])
