"""Portable, read-only HTML views of saved Agent 4 closes. No model/provider calls."""
from __future__ import annotations
import argparse
from html import escape
import json
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

from agent4.commentary import reconcile, _probability
from agent4.decomposition import euros
from agent4.hierarchy import validate_result
from agent4.output import waterfall_rows, variance_waterfall_svg
from agent4.state import VarianceStore, canonical, digest

CSS = '''
:root{color-scheme:light;--ink:#172c3d;--muted:#536675;--line:#d9e1e7;--paper:#fff;--bg:#f2f5f7;--accent:#14665f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,sans-serif}a{color:#125e88;text-underline-offset:3px}a:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:3px solid #d47b1f;outline-offset:3px}header,main,footer{max-width:1200px;margin:auto;padding:28px}header{padding-top:44px}h1{font-size:clamp(1.8rem,4vw,3rem);line-height:1.12;margin:12px 0;overflow-wrap:anywhere}h2{font-size:1.35rem;margin:0 0 16px}h3{font-size:1.05rem}p{margin:10px 0}.eyebrow{font-size:.8rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}.muted,small{color:var(--muted)}.banner{border-left:4px solid #ac6a17;background:#fff5df;padding:14px 18px;margin:18px 0}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:20px}.card,section{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:22px;margin-bottom:20px}.card{margin:0}.value{font-size:clamp(1.3rem,2.8vw,2rem);font-weight:700;overflow-wrap:anywhere}.badge{display:inline-block;background:#e5f0ed;color:#174f43;border-radius:6px;padding:3px 9px;font-size:.85rem}.warn{background:#fff1d7;color:#75501d}nav{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:.92rem}th,td{padding:12px 10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);overflow-wrap:anywhere}th{background:#f4f7f9;font-weight:650}caption{text-align:left;font-weight:650;margin:12px 0}.scroll{overflow:auto;max-width:100%;border:1px solid var(--line);border-radius:8px}.scroll table{min-width:650px}.chart svg{display:block;max-width:none}.num{font-variant-numeric:tabular-nums;white-space:nowrap}details{border-top:1px solid var(--line);padding:15px 0}summary{cursor:pointer;font-weight:650;overflow-wrap:anywhere}code{font-size:.85em;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7f9;padding:16px;font-size:.82rem}li{margin:8px 0}.meta{display:grid;grid-template-columns:160px minmax(0,1fr);gap:8px 18px}.meta dt{font-weight:650}.meta dd{margin:0;overflow-wrap:anywhere}.node{scroll-margin-top:20px}.skip{position:absolute;left:12px;top:-60px}.skip:focus{top:12px;background:white;padding:8px}@media(max-width:640px){header,main,footer{padding:18px}header{padding-top:28px}.cards{grid-template-columns:1fr}.card,section{padding:17px}.meta{grid-template-columns:1fr;gap:2px}.meta dd{margin-bottom:12px}}@media print{body{background:white}header,main,footer{max-width:none;padding:10px}section{break-inside:avoid}.scroll{overflow:visible}.chart{display:none}details>*{display:block}nav,.skip{display:none}}
'''


def e(value):
    return escape(str(value), quote=True)


def walk(tree):
    yield tree
    for child in tree.get('children', []):
        yield from walk(child)


def anchor(node_id):
    return 'node-'+digest(node_id)[:16]


def table(headers, rows, caption):
    body=''.join('<tr>'+''.join(f'<td>{cell}</td>' for cell in row)+'</tr>' for row in rows)
    if not body:
        body=f'<tr><td colspan="{len(headers)}">No observations available.</td></tr>'
    return f'<div class="scroll" tabindex="0" role="region" aria-label="{e(caption)}"><table><caption>{e(caption)}</caption><thead><tr>'+''.join(f'<th scope="col">{e(h)}</th>' for h in headers)+'</tr></thead><tbody>'+body+'</tbody></table></div>'


def page(title, content, subtitle='Saved close · read-only'):
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; base-uri \'none\'; form-action \'none\'"><title>'+e(title)+'</title><style>'+CSS+'</style></head><body><a class="skip" href="#main">Skip to report</a><header><div class="eyebrow">Keystone / Agent 4</div><h1>'+e(title)+'</h1><p class="muted">'+e(subtitle)+'</p></header><main id="main">'+content+'</main><footer>Saved evidence view. No live refresh, financial approval or business-cause verification is implied.</footer></body></html>'


def validate_bundle(saved):
    bundle=saved['bundle']
    if digest(bundle)!=saved['bundle_digest'] or digest(bundle['request'])!=bundle['request_digest']:
        raise ValueError('saved bundle or request digest mismatch')
    if bundle.get('schema_version')!=1 or bundle['run_id']!=bundle['request']['run_id']:
        raise ValueError('unsupported or inconsistent saved run')
    report=bundle['report'];registry=report['registry'];tree=report['full_hierarchy']
    validate_result(tree)
    if canonical(tree)!=canonical(registry['snapshot']['tree']) or canonical(report['reforecasts'])!=canonical(registry['snapshot']['forecasts']):
        raise ValueError('report differs from frozen registry')
    if report.get('reconciliation',{}).get('passed') is not True or not reconcile(report['commentary'],registry)['passed']:
        raise ValueError('saved commentary does not pass its canonical gate')
    if tree['context']['close_date']!=bundle['request']['close_period'] or tree['context']['entity']!=bundle['request']['entity']:
        raise ValueError('report context does not match request')
    # Reconcile displayed amounts/history and saved forecast inputs against source
    # panels. This is accounting validation, not a rerun of statistical inference.
    from agent4.close import _totals, _periods
    from agent4.contracts import cents
    from datetime import date
    req=bundle['request'];close=req['close_period'];panels={}
    for key in ('budget','effective_actuals'):
        rows=bundle['sources'][key]
        panel={(r['line'],r['period']):cents(r['amount_cents']) for r in rows}
        if len(panel)!=len(rows):
            raise ValueError('duplicate source observations')
        panels[key]=panel
    budget,actual=panels['budget'],panels['effective_actuals']
    if budget!={(r['line'],r['period']):r['amount_cents'] for r in req['budget']['rows']}:
        raise ValueError('budget panel differs from original request')
    for kind in ('budget','actuals'):
        if bundle['lineage'][kind]['version']!=req[kind]['version']:
            raise ValueError('source version differs from request')
    for row in req['actuals']['rows']:
        if actual.get((row['line'],row['period']))!=row['amount_cents']:
            raise ValueError('effective actuals disagree with submitted delta')
    annual=_periods(date.fromisoformat(close).year,req['frequency']);elapsed=annual.index(close)+1
    history=bundle['lineage']['history_periods']
    bt={p:_totals(req['tree'],budget,p) for p in set(annual+history)}
    at={p:_totals(req['tree'],actual,p) for p in set(annual[:elapsed]+history)}
    nodes=list(walk(tree))
    if set(report['reforecasts'])!={n['node_id'] for n in nodes}:
        raise ValueError('saved close forecast coverage changed')
    for node in nodes:
        ident=node['node_id']
        if node['budget_cents']!=bt[close][ident] or node['actual_cents']!=at[close][ident]:
            raise ValueError('source panel disagrees with saved close')
        prior=[{'period':p,'variance_cents':at[p][ident]-bt[p][ident]} for p in history]
        if node['history_snapshot']['prior_observations']!=prior:
            raise ValueError('saved history disagrees with source panels')
        inputs=report['reforecasts'][ident]['inputs']
        expected={'ytd_cents':sum(at[p][ident] for p in annual[:elapsed]),
                  'full_year_budget_cents':sum(bt[p][ident] for p in annual),
                  'budget_phasing_cents':[bt[p][ident] for p in annual],
                  'variance_history_cents':[r['variance_cents'] for r in prior]+[node['total_variance_cents']],
                  'elapsed_periods':elapsed,'total_periods':len(annual),'close_period':close}
        if any(canonical(inputs.get(k))!=canonical(v) for k,v in expected.items()):
            raise ValueError('forecast input disagrees with source panels')
    return bundle


def render_report(saved, related):
    bundle=validate_bundle(saved)
    report=bundle['report'];tree=report['full_hierarchy'];req=bundle['request'];lineage=bundle['lineage']
    nodes=list(walk(tree));forecasts=report['reforecasts'];root_rf=forecasts.get(tree['node_id'])
    priorities={'TOP_PRIORITY':'Priority review','EARLY_WARNING':'Early warning','MATERIAL_SIG_NC':'Material variance · significance unavailable'}
    synthetic=req.get('data_kind')=='synthetic'
    disclosure='Synthetic demonstration data — not a company finance report.' if synthetic else 'Source authenticity is unverified. Budget approval is a caller assertion.'
    content=f'<div class="banner">{e(disclosure)}</div><p><span class="badge">Saved close</span> <span class="badge">Accounting and claim checks passed</span></p>'
    content+=f'<p>Close: <strong>{e(req["close_period"])}</strong> · EUR · {e(req["frequency"])} · Run <code>{e(bundle["run_id"])}</code></p>'
    content+='<nav aria-label="Report sections">'+''.join(f'<a href="#{key}">{label}</a>' for key,label in [('bridge','Variance bridge'),('exceptions','Review priorities'),('forecast','Forecast'),('accounts','Accounts'),('sources','Sources'),('history','Close history')])+'</nav>'
    content+='<div class="cards">'+''.join(f'<div class="card"><div class="muted">{label}</div><div class="value">{euros(value)}</div></div>' for label,value in [('Close budget',tree['budget_cents']),('Close actual',tree['actual_cents']),('Variance · '+('favourable' if tree['favourable'] else 'adverse'),tree['total_variance_cents'])])+'</div>'
    rows=waterfall_rows(tree)
    content+='<section id="bridge"><h2>Budget to actual</h2><p>Step direction shows the amount change. Green means favourable to the reported result; red means adverse. On small screens, scroll the chart and tables sideways to inspect every step and exact value.</p><div class="scroll chart" tabindex="0" role="region" aria-label="Scrollable variance chart">'+variance_waterfall_svg(tree)+'</div>'
    content+=table(['Step / account','Change or anchor','Start','End','Assessment'],[[e(r['label'] if r['kind']=='anchor' else f'{i}. '+r['label']),euros(r['value_cents']),euros(r['start_cents']),euros(r['end_cents']),('Anchor' if r['kind']=='anchor' else ('Favourable' if r['favourable'] else 'Adverse'))] for i,r in enumerate(rows)],'Exact bridge values · EUR')+'</section>'
    exceptions=[n for n in nodes if n['quadrant'] in ('TOP_PRIORITY','EARLY_WARNING','MATERIAL_SIG_NC')]
    content+='<section id="exceptions"><h2>Review priorities</h2><p>Includes material variances whose statistical significance is unavailable. A priority is not a confirmed business cause.</p>'
    content+=(table(['Account','Variance','Review status'],[[f'<a href="#{anchor(n["node_id"])}">{e(n["name"])}</a>',euros(n['total_variance_cents']),e(priorities[n['quadrant']])] for n in exceptions], 'Accounts requiring review') if exceptions else '<p>No accounts meet the review-priority rules. This does not establish that no business risks exist.</p>')+'</section>'
    content+='<section id="forecast"><h2>Year-end forecast</h2>'+forecast_html(root_rf)+'<p class="muted">The close variance above is one reporting period; this forecast uses YTD actuals and annual budget phasing. Ranges and probabilities are conditional model estimates, not calibrated guarantees.</p></section>'
    content+='<section id="accounts"><h2>Account evidence</h2><p>Open an account to inspect its facts, diagnostic limitations, forecast and references.</p>'
    for node in nodes:
        claims=[c for c in report['commentary'] if c['node_id']==node['node_id']]
        content+=f'<details class="node" id="{anchor(node["node_id"])}"><summary>{e(node["name"])} · {euros(node["total_variance_cents"])}</summary>'
        content+='<ul>'+''.join(f'<li>{e(c["text"])}</li>' for c in claims)+'</ul>'
        content+=forecast_html(forecasts.get(node['node_id']))
        content+=table(['Period','Variance'],[[e(p['period']),euros(p['variance_cents'])] for p in node['history_snapshot'].get('prior_observations') or []], 'Prior observations · current close excluded')
        evidence={'node_id':node['node_id'],'source_controls':node.get('source_controls'), 'significance':node['significance'],'persistence':node['persistence'],'history':node['history_snapshot'],'references':[c['refs'] for c in claims]}
        content+='<details><summary>Calculation evidence and references</summary><pre>'+e(json.dumps(evidence,indent=2,ensure_ascii=False))+'</pre></details></details>'
    content+='</section><section id="sources"><h2>Sources and version basis</h2><dl class="meta">'
    for label,value in [('Budget source',lineage['budget']['metadata'].get('source','Unavailable')),('Actuals source',lineage['actuals']['metadata'].get('source','Unavailable')),('Budget version',lineage['budget']['version']),('Actuals as-of version',lineage['actuals']['version']),('Completeness',lineage['completeness']),('Historical budget basis',lineage['history_budget_basis']),('Forecast basis',lineage['forecast_basis']),('Bundle fingerprint',saved['bundle_digest'])]:
        content+=f'<dt>{e(label)}</dt><dd>{e(value)}</dd>'
    content+='</dl><p>Budget approval is supplied by the caller. Source-control matches verify agreement with these panels; they do not authenticate an external ledger.</p>'
    content+=f'<p><a href="{e(bundle["run_id"])}.json" download>Download the full saved evidence (JSON)</a></p>'
    for title, source_rows in [('Original submitted actuals delta',req['actuals']['rows']),('Effective actuals used',bundle['sources']['effective_actuals']),('Selected budget panel',bundle['sources']['budget'])]:
        content+='<details><summary>'+e(title)+'</summary>'+table(['Account ID','Period','Amount · EUR','Source version'],[[e(r['line']),e(r['period']),euros(r['amount_cents']),e(r.get('source_version',lineage['budget' if title=='Selected budget panel' else 'actuals']['version']))] for r in source_rows],title)+'</details>'
    excluded=lineage.get('excluded_incomplete_history_periods',[])
    content+='<p>Excluded incomplete history periods: '+e(', '.join(excluded) or 'none')+'.</p></section>'
    content+='<section id="history"><h2>Close and forecast history</h2><p>This navigation is a snapshot of saved closes at export time. The selected report retains its original source basis, even when later corrections exist.</p>'
    history=[]
    for other in related:
        b=other['bundle'];r=b['report'];rf=r['reforecasts'].get(r['full_hierarchy']['node_id'],{})
        history.append([f'<a href="{e(b["run_id"])}.html">{e(b["run_id"])}</a>'+(' · selected' if b['run_id']==bundle['run_id'] else ''),e(b['request']['close_period']),e(b['lineage']['budget']['version']),e(b['lineage']['actuals']['version']),e(b['request'].get('supersedes') or '—'),euros(rf['projected_landing_cents']) if rf.get('projected_landing_cents') is not None else 'Held / unavailable'])
    content+=table(['Run','Close','Budget','Actuals as of','Corrects','Root forecast · EUR'],history,'Saved close versions')+'</section>'
    return page(req['entity']+' · '+tree['name'],content)


def forecast_html(rf):
    if not rf:
        return '<p class="banner">No forecast was saved for this account.</p>'
    if rf.get('error'):
        return '<div class="banner"><strong>Forecast held for review</strong><p>'+e(rf['error'])+'</p><p>No landing, range or probability is published.</p></div>'
    band=rf.get('band_cents')
    items=[('Landing',euros(rf['projected_landing_cents']) if rf.get('projected_landing_cents') is not None else 'Unavailable'),('Target',euros(rf['target_cents'])),('Range',(' to '.join(euros(v) for v in band)+' · '+e(rf.get('band_confidence','deterministic'))) if band else 'Unavailable'),('P(hit target)',e(_probability(rf))+' · '+e(rf['probability_kind'])),('Method',e(rf['method'])),('Remaining periods',str(rf['inputs']['total_periods']-rf['inputs']['elapsed_periods'])),('Target direction',e(rf['direction'].replace('_',' ')))]
    return '<dl class="meta">'+''.join(f'<dt>{key}</dt><dd>{value}</dd>' for key,value in items)+'</dl><p>'+e(rf.get('reason',rf.get('confidence','')))+'</p><details><summary>Forecast assumptions</summary><ul>'+''.join('<li>'+e(a)+'</li>' for a in rf.get('assumptions',[]))+'</ul></details>'


def export_reports(store, run_id, output_dir):
    """Atomically publish a self-contained navigation snapshot and its evidence."""
    from agent4.close import _safe_run_id
    _safe_run_id(run_id)
    selected=store.get_run(run_id)
    if selected is None:
        raise ValueError('unknown run_id')
    entity=validate_bundle(selected)['request']['entity']
    related=[store.get_run(r[0]) for r in store.con.execute('SELECT run_id FROM a4_runs WHERE entity=? ORDER BY close_period,created_ts,run_id',[entity]).fetchall()]
    files={}
    for saved in related:
        b=validate_bundle(saved);ident=_safe_run_id(b['run_id'])
        files[ident+'.html']=render_report(saved,related)
        files[ident+'.json']=canonical(b)+'\n'
    manifest={name:hashlib.sha256(text.encode('utf-8')).hexdigest() for name,text in files.items()}
    snapshot=digest(manifest)
    files['manifest.json']=canonical({'schema_version':1,'snapshot':snapshot,'files':manifest})+'\n'
    root=Path(output_dir);target=root/('reports-'+snapshot[:20]);staging=None
    try:
        import fcntl
        root.mkdir(parents=True,exist_ok=True)
        with (root/'.agent4-reports.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if target.exists():
                if {p.name for p in target.iterdir()}!=set(files) or any((target/name).read_text(encoding='utf-8')!=text for name,text in files.items()):
                    raise ValueError('report snapshot conflicts with existing files')
            else:
                staging=Path(tempfile.mkdtemp(prefix='.reports-',dir=root))
                for name,text in files.items():
                    with (staging/name).open('w',encoding='utf-8') as f:
                        f.write(text);f.flush();os.fsync(f.fileno())
                fd=os.open(staging,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
                os.replace(staging,target);staging=None
                fd=os.open(root,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
        path=str((target/(run_id+'.html')).resolve())
        store.delivery_event(run_id,'delivered','HTML '+path)
        return {'status':'delivered','html_path':path,'snapshot':snapshot}
    except Exception as exc:
        store.delivery_event(run_id,'failed','HTML '+str(exc))
        raise
    finally:
        if staging is not None:shutil.rmtree(staging)


def render_status(status, message):
    if status not in ('empty','held','error'):
        raise ValueError('invalid status')
    return page({'empty':'No saved closes','held':'Report held for review','error':'Report unavailable'}[status], '<section><h2>'+e(status.title())+'</h2><p>'+e(message)+'</p><p>No financial conclusions are published in this view.</p></section>')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True);parser.add_argument('--run-id',required=True);parser.add_argument('--output-dir',required=True)
    args=parser.parse_args(argv)
    try:
        if not Path(args.db).is_file():raise ValueError('state database does not exist')
        with VarianceStore(args.db) as store:
            print(canonical(export_reports(store,args.run_id,args.output_dir)))
        return 0
    except Exception as exc:
        print(canonical({'status':'report_failed','error':str(exc)}),file=sys.stderr)
        return 2


if __name__=='__main__':sys.exit(main())
