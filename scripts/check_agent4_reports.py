"""Generate reproducible synthetic browser acceptance cases (no provider calls)."""
import json
from pathlib import Path
import sys
import tempfile
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent4.close import execute_close, _periods
from agent4.report import export_reports, render_status, page
from agent4.state import VarianceStore


def main():
    base=Path('output/agent4-batch4');base.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='acceptance-',dir=base))
    fixture=json.loads(Path('fixtures/agent4/close-june.json').read_text())
    links={}
    with VarianceStore(root/'state.duckdb') as store:
        execute_close(store,fixture)
        corrected=deepcopy(fixture);corrected.update(run_id='corrected',supersedes='close-june')
        corrected['actuals']={'version':'restated','source':'synthetic-correction','rows':[{'line':'sales','period':'2026-01-31','amount_cents':12000}]}
        execute_close(store,corrected)
        links['Original and corrected closes']=export_reports(store,'corrected',root)['html_path']
        for case in ('loss','many','held','uncertainty','zero','leaf'):
            req=deepcopy(fixture);req['entity']='Synthetic '+case;req['run_id']=case
            req['budget']['version']=case+'-budget';req['actuals']['version']=case+'-actuals'
            if case=='loss':
                for r in req['budget']['rows']:
                    if r['line']=='cost':r['amount_cents']=20000
                for r in req['actuals']['rows']:
                    if r['line']=='cost':r['amount_cents']=25000
            if case=='held':
                for r in req['budget']['rows']:
                    if r['line']=='sales':r['amount_cents']=0
            if case=='zero':
                for r in req['actuals']['rows']:r['amount_cents']=10000 if r['line']=='sales' else 4000
            if case=='leaf':
                req['tree']={'name':'Standalone cost account','node_id':'cost','root_measure':'cost','leaf':{'type':'fixed_cost'}}
                for kind in ('budget','actuals'):req[kind]['rows']=[r for r in req[kind]['rows'] if r['line']=='cost']
            if case=='uncertainty':
                for i,p in enumerate(_periods(2025,'monthly')):
                    for line,amount in [('sales',10000),('cost',4000)]:
                        req['budget']['rows'].append(dict(line=line,period=p,amount_cents=amount))
                        req['actuals']['rows'].append(dict(line=line,period=p,amount_cents=amount+(-1 if i%2 else 1)*(i+1)*50))
            if case=='many':
                req['tree']['children']=[{'name':f'Division {i+1:02d} — international aftermarket services and maintenance agreements','node_id':f'account-{i}','sign':'add','leaf':{'type':'revenue'}} for i in range(24)]
                for kind in ('budget','actuals'):
                    req[kind]['rows']=[dict(line=n['node_id'],period=p,amount_cents=10000 if kind=='budget' else 10000+i*17) for i,n in enumerate(req['tree']['children']) for p in _periods(2026,'monthly') if kind=='budget' or p<='2026-06-30']
            execute_close(store,req);links[case]=export_reports(store,case,root)['html_path']
    for state in ('empty','held','error'):
        target=root/(state+'-state.html');target.write_text(render_status(state,'Synthetic presentation-state example. No approved financial result is available.'),encoding='utf-8');links[state+' state']=str(target.resolve())
    html=page('Agent 4 · browser acceptance','<section><h2>Synthetic cases</h2><ul>'+''.join(f'<li><a href="{Path(path).relative_to(root.resolve())}">{label}</a></li>' for label,path in links.items())+'</ul></section>')
    (root/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps({'directory':str(root.resolve()),'index':str((root/'index.html').resolve()),'cases':links},indent=2))


if __name__=='__main__':main()
