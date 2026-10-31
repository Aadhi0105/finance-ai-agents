import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {datasetRows,fetchReport,parseReport,pointMetric,ReportFailure} from '../src/reports/report-data.ts';
import {formatMetric} from '../src/reports/format.ts';
import {filterNewsStories,newsBasis,newsCoverage,newsStories,scorerName} from '../src/reports/news-data.ts';
import {plotGeometry} from '../src/reports/chart-layout.ts';

const fixture=JSON.parse(readFileSync(new URL('./fixtures/news-snapshot.json',import.meta.url),'utf8'));
const snapshot=()=>structuredClone(fixture);
const failure=code=>e=>e instanceof ReportFailure&&e.code===code;

test('native news retains exact diagnostics, coverage, cutoff and a withheld published result',()=>{
  const {report,run}=snapshot(),r=parseReport(report,run);
  assert.equal(r.workflow,'news');assert.equal(r.agent,'agent3');
  assert.equal(r.state.financial_approval,false);assert.equal(r.state.evidence_gate,'held_for_review');
  assert.equal(r.metrics.find(m=>m.id==='published-tone-0').value,null);
  assert.equal(r.metrics.find(m=>m.id==='diagnostic-tone-0').value,'0.0');
  assert.equal(newsBasis(r,'cutoff'),'2026-01-28T23:59:00+00:00');
  assert.equal(newsStories(r).length,2);
  const c=r.charts.find(c=>c.id==='news-story-tone');
  assert.equal(formatMetric(pointMetric(c,datasetRows(c)[0].points[0])),'0.3');
  assert.equal(formatMetric(pointMetric(c,datasetRows(c)[1].points[0])),'−0.3');
});

test('old news adapter displays only retained metadata without inventing a graph or retrieval state',()=>{
  const fixture=JSON.parse(readFileSync(new URL('./fixtures/news-legacy.json',import.meta.url),'utf8'));
  const r=parseReport(fixture.report,fixture.run);
  assert.equal(r.charts.length,0);assert.equal(newsStories(r).length,2);
  assert(newsStories(r).every(s=>!s.hasDetail&&s.retrieved==='Not retained'));
  assert.equal(newsCoverage(r).title,'Coverage detail not retained');
});

for(const [name,edit,code='saved_evidence_invalid'] of [
  ['wrong workflow',(r)=>{r.workflow='events';}],
  ['unknown adapter',(r,run)=>{run.native_view.adapter_version='3.0.0';},'unsupported_report_schema'],
  ['changed source hash',r=>{r.artifacts[0].sha256='f'.repeat(64);}],
  ['wrong source family',r=>{r.artifacts[0].source_schema='agent1.model/2';}],
  ['financial approval',r=>{r.state.financial_approval=true;}],
  ['published tone promoted to available',r=>{Object.assign(r.metrics.find(m=>m.id==='published-tone-0'),{availability:'available',value:'0',reason_codes:[]});}],
  ['withheld tone filled with zero',r=>{r.metrics.find(m=>m.id==='published-tone-0').value='0';}],
  ['diagnostic average promoted',r=>{r.metrics.find(m=>m.id==='diagnostic-tone-0').visibility='main';}],
  ['diagnostic out of range',r=>{r.metrics.find(m=>m.id==='diagnostic-tone-0').value='1.2';}],
  ['diagnostic plot promoted',r=>{r.charts.find(c=>c.id==='news-story-tone').visibility='main';}],
  ['score plotted as percentage',r=>{r.charts.find(c=>c.id==='news-story-tone').y_axis.unit='fraction';}],
  ['story score out of range',r=>{r.charts.find(c=>c.id==='news-story-tone').series[0].points[0].y='-2';}],
  ['negative input count',r=>{r.charts.find(c=>c.id==='news-coverage').series[0].points[0].y='-1';}],
  ['categorical scores recast as session history',r=>{r.charts.find(c=>c.id==='news-story-tone').x_axis.kind='relative_session';}],
  ['unknown prediction chart',r=>{r.charts.find(c=>c.id==='news-story-tone').id='future-price';}],
  ['invented consensus',r=>{r.analyst_content.market_consensus.availability='available';r.analyst_content.market_consensus.metric_refs=['diagnostic-tone-0'];}],
  ['invented future probability metric',r=>{r.metrics.find(m=>m.id==='diagnostic-tone-0').id='probability-next-rise';r.tables=[];r.sections=[];}],
  ['missing story evidence',r=>{r.tables.find(t=>t.id==='retained-headlines').rows[0].evidence_refs=['missing'];}],
  ['broken table columns',r=>{r.tables.find(t=>t.id==='news-story-details').rows[0].cells.pop();}],
  ['unknown prose template',r=>{r.summary.template_id='free-form-company-outlook';},'unsupported_report_schema'],
]) test(`news reader refuses ${name}`,()=>{
  const {report,run}=snapshot();edit(report,run);
  assert.throws(()=>parseReport(report,run),failure(code));
});

test('news template cannot be used by another family or the original news adapter',()=>{
  const event=JSON.parse(readFileSync(new URL('./fixtures/event-snapshot.json',import.meta.url),'utf8'));
  event.report.summary.template_id='news-study-summary-v1';
  assert.throws(()=>parseReport(event.report,event.run),failure('unsupported_report_schema'));
  const old=JSON.parse(readFileSync(new URL('./fixtures/news-legacy.json',import.meta.url),'utf8'));
  old.report.summary.template_id='news-study-summary-v1';
  assert.throws(()=>parseReport(old.report,old.run),failure('unsupported_report_schema'));
});

test('null and actual zero story diagnostics remain distinct and neither supplies published tone',()=>{
  const {report,run}=snapshot(),r=parseReport(report,run),c=r.charts.find(c=>c.id==='news-story-tone');
  c.series[0].points[0].y=null;c.series[0].points[0].reason_codes=['unavailable'];
  c.series[0].points[1].y='0';
  assert.equal(formatMetric(pointMetric(c,datasetRows(c)[0].points[0])),'Unavailable');
  assert.equal(formatMetric(pointMetric(c,datasetRows(c)[1].points[0])),'0');
  assert.equal(r.metrics.find(m=>m.id==='published-tone-0').value,null);
});

test('story tone plots retain a fixed minus-one to plus-one scale, including a genuine zero',()=>{
  const {report,run}=snapshot(),r=parseReport(report,run),c=r.charts.find(c=>c.id==='news-story-tone');
  const g=plotGeometry(c,datasetRows(c),700);
  assert.equal(Number(g.ticks[0].value),-1);assert.equal(Number(g.ticks.at(-1).value),1);
  c.series[0].points.forEach(p=>p.y='0');
  const zero=plotGeometry(c,datasetRows(c),700);
  assert.equal(Number(zero.ticks[0].value),-1);assert.equal(Number(zero.ticks.at(-1).value),1);
  assert.equal(zero.zero,(zero.top+zero.bottom)/2);
});

test('news count axes use whole records and keep an empty-input zero at the baseline',()=>{
  const {report,run}=snapshot(),r=parseReport(report,run),c=r.charts.find(c=>c.id==='news-coverage');
  const g=plotGeometry(c,datasetRows(c),700);
  assert(g.ticks.every(t=>Number.isInteger(Number(t.value))));
  assert.equal(g.ticks[0].value,'0');assert.equal(g.zero,g.bottom);
  c.series[0].points.forEach(p=>p.y='0');
  const empty=plotGeometry(c,datasetRows(c),700);
  assert(empty.ticks.every(t=>Number.isInteger(Number(t.value))));
  assert.equal(empty.zero,empty.bottom);assert.equal(Number(empty.ticks.at(-1).value),1);
});

test('headline search changes only matching display records, retaining scope, evidence and coverage',()=>{
  const {report,run}=snapshot(),r=parseReport(report,run),before=structuredClone(r);
  const stories=newsStories(r);
  assert.equal(filterNewsStories(stories,'DELIVERY').length,1);
  assert.equal(filterNewsStories(stories,'synthetic bulletin').length,2);
  assert.equal(filterNewsStories(stories,'unmatched').length,0);
  assert.equal(filterNewsStories(stories,'  ').length,2);
  assert.deepEqual(r,before);
  assert(stories.every(s=>s.refs.length&&s.published&&s.scope.includes('scope unspecified')));
  assert.equal(scorerName('stub'),'Synthetic fixture scorer');
});

test('all empty, failed and unknown coverage descriptions stay distinct without inferring no company news',()=>{
  const {report,run}=snapshot(),r=parseReport(report,run),cell=r.tables.find(t=>t.id==='news-basis').rows[0].cells.find(c=>c.column_id==='value');
  const titles=[];
  for(const state of ['empty_saved_input','recorded_empty_response','no_relevant_records','retrieval_failed','coverage_unknown']) {
    cell.text=state;titles.push(newsCoverage(r).title);
    assert(newsCoverage(r).description.length>30);
  }
  assert.equal(new Set(titles).size,5);
  cell.text='unexpected_future_state';assert.equal(newsCoverage(r).title,'Coverage detail not retained');
});

test('recorded URLs and hostile-looking headlines remain data without HTML or link rewriting',()=>{
  const {report,run}=snapshot(),r=parseReport(report,run);
  r.tables.find(t=>t.id==='retained-headlines').rows[0].cells.find(c=>c.column_id==='headline').text='<img src=x onerror=alert(1)>';
  r.tables.find(t=>t.id==='news-story-details').rows[0].cells.find(c=>c.column_id==='url').text='javascript:alert(1)';
  const stories=newsStories(r);
  assert.equal(stories[0].headline,'<img src=x onerror=alert(1)>');
  assert.equal(stories[0].url,'javascript:alert(1)');
  assert.equal(filterNewsStories(stories,'onerror').length,1);
});

test('news reads use the source-bound uncached abortable report endpoint',async t=>{
  const {report,run}=snapshot(),controller=new AbortController();
  const mock=t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(report),{headers:{'content-type':'application/json'}}));
  assert.equal((await fetchReport(run,controller.signal)).workflow,'news');
  assert.equal(mock.mock.calls[0].arguments[0],'/api/runs/news-example/report-view');
  assert.equal(mock.mock.calls[0].arguments[1].cache,'no-store');
  assert.equal(mock.mock.calls[0].arguments[1].signal,controller.signal);
});
