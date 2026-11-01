import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {parseReport,datasetRows,pointMetric} from '../src/reports/report-data.ts';
import {plotGeometry} from '../src/reports/chart-layout.ts';
import {formatMetric} from '../src/reports/format.ts';
import {readingCopy} from '../src/reports/reading-copy.ts';
import {accountTable,closeAccountOverview,closeAccounts,closeBasis,closeText} from '../src/reports/close-data.ts';
const fixture=(name='close-snapshot')=>JSON.parse(readFileSync(new URL('./fixtures/'+name+'.json',import.meta.url),'utf8'));
const saved=name=>{const f=fixture(name);return parseReport(f.report,f.run);};

test('close preserves exact budget/actual/variance, saved endpoints and separate forecast',()=>{
  const r=saved(),m=id=>r.metrics.find(m=>m.id===id);
  assert.equal(r.agent,'agent4');assert.equal(r.workflow,'close');assert.equal(r.state.financial_approval,false);
  assert.deepEqual(['close-budget-cents','close-actual-cents','close-total-variance-cents'].map(id=>m(id).value),['60','65','5']);
  const bridge=r.charts.find(c=>c.id==='close-bridge');assert.equal(bridge.type,'waterfall');
  assert.deepEqual(bridge.series[0].points.map(p=>[p.start,p.end,p.assessment]),[['0','60','anchor'],['60','70','favourable'],['70','65','adverse'],['0','65','anchor']]);
  assert.equal(m('account-2-total-variance-cents').value,'5');assert.equal(m('account-2-profit-impact').value,'-5');
  assert.equal(m('forecast-projected-landing-cents').value,'780');assert.equal(m('forecast-band-0').value,null);
  assert.equal(closeBasis(r,'budget-assertion'),'Yes (saved assertion)');
});

test('bridge geometry displays supplied cumulative endpoints, not zero-based delta bars',()=>{
  const r=saved(),c=r.charts[0],before=structuredClone(c),g=plotGeometry(c,datasetRows(c),800),p=g.series[0].segments[0];
  assert.equal(g.kind,'waterfall');assert.equal(g.reason,null);
  assert.equal(p[1].startY,p[0].y);assert.equal(p[2].startY,p[1].y);assert(p[2].y>p[2].startY);
  assert.equal(p[3].startY,g.zero);assert.equal(p[3].y,p[2].y);
  assert.deepEqual(c,before);
});

test('cost-root increase plots upward with its saved adverse assessment',()=>{
  const c=saved('close-cost').charts[0],g=plotGeometry(c,datasetRows(c),700),step=g.series[0].segments[0][1];
  assert.equal(step.assessment,'adverse');assert(step.y<step.startY);
  assert.equal(c.series[0].points[1].y,'5');
});

test('negative anchors and sign crossings stay within the graphical scale',()=>{
  const c=saved().charts[0];c.series[0].points=[['Budget','-5','0','-5','anchor'],['Change','10','-5','5','favourable'],['Actual','5','0','5','anchor']].map(([label,y,start,end,assessment],i)=>({id:'p'+i,x:String(i),label,y,start,end,assessment,evidence_refs:['saved'],reason_codes:[]}));
  const g=plotGeometry(c,datasetRows(c),700);assert(g.zero>g.top&&g.zero<g.bottom);
  for(const p of g.series[0].segments[0])assert(p.y>=g.top&&p.y<=g.bottom&&p.startY>=g.top&&p.startY<=g.bottom);
});

test('zero movement is zero-height and large decimal amounts retain exact inspection values',()=>{
  const c=saved().charts[0],point=c.series[0].points[1];point.y='0';point.end=point.start;
  let g=plotGeometry(c,datasetRows(c),700);assert.equal(g.series[0].segments[0][1].startY,g.series[0].segments[0][1].y);
  point.y='0.01';point.start='123456789012345678901234567890.12';point.end='123456789012345678901234567890.13';
  g=plotGeometry(c,datasetRows(c),700);assert.equal(g.reason,null);
  assert.equal(formatMetric({...pointMetric(c,point),value:point.end}),'EUR 123,456,789,012,345,678,901,234,567,890.13');
});

test('missing or malformed endpoints do not become a fabricated bridge',()=>{
  for(const value of [undefined,null,'bad']){const c=saved().charts[0];c.series[0].points[1].start=value;assert(plotGeometry(c,datasetRows(c),700).reason);}
});

test('account search, materiality and unavailable significance remain separate',()=>{
  const r=saved(),before=structuredClone(r);
  assert.equal(closeAccounts(r).rows.length,3);assert.equal(closeAccounts(r,'COST').rows.length,1);
  assert.equal(closeAccounts(r,'','material').rows.length,3);assert.equal(closeAccounts(r,'','unavailable').rows.length,3);
  assert.equal(accountTable(r,'account-prior-observations','cost').rows.length,5);
  assert.deepEqual(r,before);
});

test('compact account table preserves all financial values and evidence while full metadata remains retained',()=>{
  const r=saved(),table=closeAccounts(r),before=structuredClone(table),overview=closeAccountOverview(table);
  assert.equal(overview.rows.length,table.rows.length);assert(overview.columns.length<table.columns.length);
  for(const row of overview.rows){const original=table.rows.find(r=>r.id===row.id);assert.deepEqual(row.evidence_refs,original.evidence_refs);assert.deepEqual(row.cells.filter(c=>c.kind==='metric_ref'),original.cells.filter(c=>c.kind==='metric_ref'));}
  assert.deepEqual(table,before);
});

test('corrected source delta and effective versions retain different scopes',()=>{
  const r=saved('close-corrected');assert.equal(closeBasis(r,'supersedes'),'qa-original');
  assert.equal(r.tables.find(t=>t.id==='submitted-actuals').rows.length,1);
  assert.equal(r.tables.find(t=>t.id==='effective-actuals').rows.length,12);
  assert.equal(r.metrics.find(m=>m.id==='forecast-projected-landing-cents').value,'800');
  assert.equal(r.metrics.find(m=>m.id==='close-actual-cents').value,'65');
});

test('held, populated model interval and closed-year outcome keep distinct publication states',()=>{
  const held=saved('close-held');assert(held.metrics.filter(m=>m.id.startsWith('forecast-')).every(m=>m.value===null));
  const model=saved('close-uncertainty');assert.equal(model.metrics.find(m=>m.id==='forecast-band-0').value,'772.6');
  assert.equal(model.metrics.find(m=>m.id==='forecast-prob-hit-target').visibility,'diagnostic');
  const year=saved('close-yearend');assert.equal(closeText(year.tables.find(t=>t.id==='account-forecasts').rows[0],'state'),'deterministic');
  assert(year.metrics.find(m=>m.id==='forecast-prob-hit-target').label.includes('no remaining horizon'));
});

test('legacy close reader keeps original bridge and explicit absence of newer metadata',()=>{
  const r=saved('close-legacy');assert.equal(closeBasis(r,'budget-version'),'Not retained');assert.equal(r.charts.length,1);
  assert.equal(r.charts[0].series[0].points[1].end,'70');assert.equal(closeAccounts(r).rows.length,3);
});

for(const [name,edit,code='saved_evidence_invalid'] of [
  ['unsupported version',(r,run)=>{run.native_view.adapter_version='9.0.0';},'unsupported_report_schema'],
  ['wrong source family',r=>{r.artifacts[0].source_schema='agent1.model/2';}],
  ['changed source hash',r=>{r.artifacts[0].sha256='f'.repeat(64);}],
  ['financial approval',r=>{r.state.financial_approval=true;}],
  ['missing endpoints',r=>{delete r.charts[0].series[0].points[1].start;}],
  ['nondecimal endpoints',r=>{r.charts[0].series[0].points[1].end='1e3';}],
  ['unknown assessment',r=>{r.charts[0].series[0].points[1].assessment='guaranteed';}],
  ['unregistered graph',r=>{r.charts[0].id='future-profits';}],
  ['delta chart in place of waterfall',r=>{r.charts[0].type='bar';}],
  ['currency swap',r=>{r.charts[0].y_axis.currency='USD';}],
  ['forecast promoted',r=>{r.metrics.find(m=>m.id==='forecast-projected-landing-cents').visibility='main';}],
  ['impossible probability',r=>{Object.assign(r.metrics.find(m=>m.id==='forecast-prob-hit-target'),{value:'1.1',availability:'available',reason_codes:[]});}],
  ['point-only uncertainty promoted',r=>{Object.assign(r.metrics.find(m=>m.id==='forecast-band-0'),{value:'0',availability:'available',reason_codes:[]});}],
  ['unknown metric',r=>{r.metrics[0].id='future-growth';}],
  ['freeform recommendation',r=>{r.summary.template_id='business-cause';},'unsupported_report_schema'],
])test('close refuses '+name,()=>{const {run,report}=fixture();edit(report,run);assert.throws(()=>parseReport(report,run),{code});});

test('held forecast cannot be promoted to an available zero',()=>{
  const {run,report}=fixture('close-held');Object.assign(report.metrics.find(m=>m.id==='forecast-projected-landing-cents'),{value:'0',availability:'available',reason_codes:[]});
  assert.throws(()=>parseReport(report,run),{code:'saved_evidence_invalid'});
});

test('reading copy preserves all source rows and exact bridge endpoints and assessments',()=>{
  for(const name of ['close-snapshot','close-cost','close-held','close-uncertainty','close-yearend','close-corrected','close-legacy']){
    const r=saved(name),copy=readingCopy(r),c=copy.charts.find(c=>c.chart.id==='close-bridge');
    assert.equal(copy.title,'Financial close');assert.equal(c.columns.length,c.rows[0].values.length+1);
    assert.equal(c.rows[1].values.at(-1),r.charts[0].series[0].points[1].assessment);
    assert.equal(copy.tables.reduce((n,t)=>n+t.rows.length,0),r.tables.reduce((n,t)=>n+t.rows.length,0));
    assert(copy.tables.every(t=>t.rows.every(row=>!row.references.includes('Unresolved'))));
  }
});
