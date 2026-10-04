"""Run after agent4_probe.py; independent arithmetic controls and chart evidence."""
import json, random
from pathlib import Path
from decimal import Decimal, ROUND_HALF_EVEN
from agent4.decomposition import decompose_line
from agent4.hierarchy import rollup
from agent4.persistence import classify_persistence
from agent4.output import board_pack
from agent4.commentary import compose
from agent4.reforecast import reforecast
from agent4.materiality import _significance
random.seed(4)
results={}
errors=[]
for i in range(2000):
    bp=random.randint(1,10000); ap=random.randint(1,10000); bv=random.randint(0,1000); av=random.randint(0,1000)
    r=decompose_line({'name':'X','type':'revenue','budget':{'price':bp/100,'volume':bv},'actual':{'price':ap/100,'volume':av}})
    expected=ap*av-bp*bv
    if r['total_variance_cents']!=expected:errors.append(i)
results['independent_integer_cent_controls']={'cases':2000,'mismatches':len(errors)}
pnl=json.loads(Path('fixtures/pnl.json').read_text());tree=rollup(pnl)
rows=[]
def collect(n):
    if n.get('history') and n.get('leaf'):
        d=decompose_line(n['leaf']);h=n['history']; old=classify_persistence(h);new=classify_persistence(h+[d['total_variance_cents']])
        rows.append({'name':n['name'],'current':d['total_variance_cents'],'last_history':h[-1], 'history_only_verdict':old['persistence'],'current_included_verdict':new['persistence']})
    for c in n.get('children',[]):collect(c)
collect(pnl);results['history_semantics']=rows
rf=reforecast(100,1200,1,4,variance_history_cents=[-10,10,-20,20,-30,30])
claims=compose(tree,reforecast_by_line={tree['name']:rf})
results['root_forecast_claim_count']=sum('Reforecast' in c['text'] for c in claims)
claims=compose(tree,reforecast_by_line={'Materials':rf})
results['child_forecast_claims']=[c for c in claims if 'Reforecast' in c['text']]
results['lost_zero_dispersion_context']=_significance([0]*6,500)
Path('output/agent4-audit/extended.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
# Test-only visual wrapper around actual renderer output; not a product report.
probes=json.loads(Path('output/agent4-audit/probes.json').read_text())
from html import escape
html='<html><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{font:16px system-ui;margin:24px}section{max-width:900px;border:1px solid #ddd;padding:20px;margin:20px 0}svg{width:100%}</style><h1>Agent 4 audit — synthetic renderer evidence</h1><p>Review-only wrapper, not an operational board report.</p>'
for title,svg in [('Normal fixture',board_pack(tree)['waterfall_svg']),('All-negative profit',probes['negative_waterfall']),('Single leaf',probes['leaf_waterfall'])]:
    html+='<section><h2>'+escape(title)+'</h2>'+svg+'</section>'
Path('output/agent4-audit/visual.html').write_text(html)
