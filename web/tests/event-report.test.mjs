import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {datasetRows, fetchReport, parseReport, pointMetric, ReportFailure} from '../src/reports/report-data.ts';
import {formatMetric} from '../src/reports/format.ts';

const fixture=JSON.parse(readFileSync(new URL('./fixtures/event-snapshot.json',import.meta.url),'utf8'));
const snapshot=()=>structuredClone(fixture);
const failure=code=>e=>e instanceof ReportFailure&&e.code===code;

test('event reader accepts the source-bound 1.1 view without changing held or diagnostic states',()=>{
  const {report,run}=snapshot(),parsed=parseReport(report,run);
  assert.equal(parsed.agent,'agent3');assert.equal(parsed.workflow,'events');
  assert.equal(parsed.state.execution,'held');assert.equal(parsed.state.financial_approval,false);
  assert.equal(parsed.metrics.find(m=>m.id==='event-count').value,'8');
  assert.equal(parsed.metrics.find(m=>m.id==='issuer-count').value,'8');
  assert.equal(parsed.metrics.find(m=>m.id==='mean-car').visibility,'diagnostic');
  assert.equal(parsed.metrics.find(m=>m.id==='p-value').value,null);
  assert(parsed.tables.some(t=>t.id==='event-case-metadata'));
  assert(parsed.tables.some(t=>t.id==='event-gates'));
});

test('event 1.0 remains readable without inventing case metadata, review explanations or a dated path',()=>{
  const old=JSON.parse(readFileSync(new URL('./fixtures/event-legacy.json',import.meta.url),'utf8'));
  const parsed=parseReport(old.report,old.run);
  assert.equal(parsed.tables.length,0);
  assert.equal(parsed.summary.template_id,'saved-summary-v1');
  assert.equal(parsed.charts.find(c=>c.id==='event-path').availability,'withheld');
  assert.deepEqual(parsed.charts.find(c=>c.id==='event-path').series,[]);
});

for(const [name,edit,code='saved_evidence_invalid'] of [
  ['wrong workflow',(r,run)=>{r.workflow='news';}],
  ['wrong source schema',r=>{r.artifacts[0].source_schema='agent1.model/2';}],
  ['changed source digest',r=>{r.artifacts[0].sha256='0'.repeat(64);}],
  ['unsupported event adapter',(r,run)=>{run.native_view.adapter_version='2.0.0';},'unsupported_report_schema'],
  ['approval upgrade',r=>{r.state.financial_approval=true;}],
  ['mean promoted to main',r=>{r.metrics.find(m=>m.id==='mean-car').visibility='main';}],
  ['inference promoted to main',r=>{r.metrics.find(m=>m.id==='p-value').visibility='main';}],
  ['case chart promoted to main',r=>{r.charts.find(c=>c.id==='event-cases').visibility='main';}],
  ['case bars relabelled as a calendar path',r=>{r.charts.find(c=>c.id==='event-cases').x_axis.kind='relative_session';}],
  ['case units changed to raw prices',r=>{r.charts.find(c=>c.id==='event-cases').y_axis={unit:'currency',currency:'EUR',label:'Price'};}],
  ['unknown event chart',r=>{r.charts.find(c=>c.id==='event-cases').id='next-return-forecast';}],
  ['fabricated consensus',r=>{r.analyst_content.market_consensus.availability='available';r.analyst_content.market_consensus.metric_refs=['mean-car'];}],
  ['withheld numeric p-value',r=>{r.metrics.find(m=>m.id==='p-value').value='0';}],
  ['invalid available p-value',r=>{Object.assign(r.metrics.find(m=>m.id==='p-value'),{availability:'available',value:'2',reason_codes:[]});}],
  ['broken review reference',r=>{r.charts[0].review_refs=['missing'];}],
  ['broken case metadata columns',r=>{r.tables.find(t=>t.id==='event-case-metadata').rows[0].cells.pop();}],
]) test(`event reader refuses ${name}`,()=>{
  const {report,run}=snapshot();edit(report,run);
  assert.throws(()=>parseReport(report,run),failure(code));
});

test('populating an event-relative path requires a new supported projection, not guessed positions',()=>{
  const {report,run}=snapshot(),c=report.charts.find(c=>c.id==='event-path');
  c.availability='available';c.reason_codes=[];
  c.series=[{id:'guessed-path',label:'Unsupported path',points:[{id:'guessed',x:'0',label:'Event session',y:'0.1',evidence_refs:[report.evidence[0].id],reason_codes:[]}]}];
  assert.throws(()=>parseReport(report,run),failure('unsupported_report_schema'));
});

test('an event projection cannot masquerade as a news projection',()=>{
  const {report,run}=snapshot();run.workflow='news';report.workflow='news';run.native_view.adapter_id='agent3-news-report';
  assert.throws(()=>parseReport(report,run),failure('unsupported_report_schema'));
});

test('event templates are not admitted into research or an older event adapter',()=>{
  const research=JSON.parse(readFileSync(new URL('./fixtures/research-snapshot.json',import.meta.url),'utf8'));
  research.report.summary.template_id='event-study-summary-v1';
  assert.throws(()=>parseReport(research.report,research.run),failure('unsupported_report_schema'));
  const old=JSON.parse(readFileSync(new URL('./fixtures/event-legacy.json',import.meta.url),'utf8'));
  old.report.summary.template_id='event-study-summary-v1';
  assert.throws(()=>parseReport(old.report,old.run),failure('unsupported_report_schema'));
});

test('retained event identities and missing values survive chart/table alignment without a forecast or zero fill',()=>{
  const {report,run}=snapshot();const parsed=parseReport(report,run),chart=parsed.charts.find(c=>c.id==='event-cases');
  const rows=datasetRows(chart);
  assert.equal(rows.length,8);assert.equal(new Set(rows.map(r=>r.x)).size,8);
  assert.match(rows[0].label,/Recorded event: 2026-01-28/);
  assert.match(rows[0].label,/timing requires review/);
  chart.series[0].points[1].y=null;chart.series[0].points[1].reason_codes=['case_car_not_retained'];
  chart.series[0].points[2].y='0';
  assert.equal(formatMetric(pointMetric(chart,datasetRows(chart)[1].points[0])),'Unavailable');
  assert.equal(formatMetric(pointMetric(chart,datasetRows(chart)[2].points[0])),'0.00%');
  assert.equal(datasetRows(chart).length,8);
});

test('a real saved zero p-value is a diagnostic value, not a missing result or financial approval',()=>{
  const {report,run}=snapshot();Object.assign(report.metrics.find(m=>m.id==='p-value'),{availability:'available',value:'0',reason_codes:[]});
  const parsed=parseReport(report,run),m=parsed.metrics.find(m=>m.id==='p-value');
  assert.equal(formatMetric(m),'0');assert.equal(m.visibility,'diagnostic');assert.equal(parsed.state.financial_approval,false);
});

test('event reads use the same uncached, abortable, saved-run endpoint as the research reader',async t=>{
  const {report,run}=snapshot(),controller=new AbortController();
  const mock=t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(report),{headers:{'content-type':'application/json'}}));
  const parsed=await fetchReport(run,controller.signal);
  assert.equal(parsed.workflow,'events');
  assert.equal(mock.mock.calls[0].arguments[0],'/api/runs/events-example/report-view');
  assert.equal(mock.mock.calls[0].arguments[1].cache,'no-store');
  assert.equal(mock.mock.calls[0].arguments[1].signal,controller.signal);
  assert.equal(mock.mock.calls[0].arguments[1].method,undefined);
});
