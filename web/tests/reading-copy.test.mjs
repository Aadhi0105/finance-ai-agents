import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {parseReport} from '../src/reports/report-data.ts';
import {readingCopy} from '../src/reports/reading-copy.ts';

function saved(name){const f=JSON.parse(readFileSync(new URL('./fixtures/'+name,import.meta.url),'utf8'));return parseReport(f.report,f.run);}

for(const family of ['event-snapshot.json','event-legacy.json','news-snapshot.json','news-legacy.json'])
test(`complete reading copy retains all source rows, measures, references and restrictions: ${family}`,()=>{
  const report=saved(family),before=structuredClone(report),copy=readingCopy(report);
  assert.equal(copy.metrics.length,report.metrics.length);
  assert.equal(copy.tables.reduce((n,t)=>n+t.rows.length,0),report.tables.reduce((n,t)=>n+t.rows.length,0));
  assert.equal(copy.charts.reduce((n,c)=>n+c.rows.length,0),report.charts.reduce((n,c)=>n+Math.max(0,...c.series.map(s=>s.points.length)),0));
  assert.equal(copy.evidence.length,report.evidence.length);
  assert(copy.evidence.every(e=>e.label.startsWith('E')&&e.artifact&&e.description));
  assert(copy.metrics.every(m=>!m.references.includes('Unresolved')));
  assert.deepEqual(report,before);
});

test('reading copy keeps every story/table row beyond screen pagination and zero separate from withheld',()=>{
  const report=saved('news-snapshot.json'),table=report.tables.find(t=>t.id==='retained-headlines'),original=table.rows[0];
  table.rows=Array.from({length:40},(_,i)=>({...structuredClone(original),id:'row-'+i}));
  const copy=readingCopy(report);
  assert.equal(copy.tables.find(t=>t.id===table.id).rows.length,40);
  assert.equal(copy.metrics.find(m=>m.id==='published-tone-0').display,'Withheld');
  assert.equal(copy.metrics.find(m=>m.id==='published-tone-0').value,null);
  assert.equal(copy.metrics.find(m=>m.id==='diagnostic-tone-0').value,'0.0');
});

test('reading copy represents missing event points without zero substitution',()=>{
  const report=saved('event-snapshot.json'),c=report.charts.find(c=>c.id==='event-cases');
  c.series[0].points[0].y=null;c.series[0].points[0].reason_codes=['missing'];c.series[0].points[1].y='0';
  const copy=readingCopy(report),rows=copy.charts.find(c=>c.chart.id==='event-cases').rows;
  assert.equal(rows[0].values[0],'Unavailable');assert.equal(rows[1].values[0],'0.00%');
  assert.equal(copy.charts.find(c=>c.chart.id==='event-path').rows.length,0);
});

test('reading-copy text and addresses remain data, never trusted HTML or navigable links',()=>{
  const report=saved('news-snapshot.json');report.tables[0].rows[0].cells[0].text='<script>bad()</script>';
  const copy=readingCopy(report);assert.equal(copy.tables[0].rows[0].values[0],'<script>bad()</script>');
  assert.equal(typeof copy.tables[0].rows[0].values[0],'string');
});

test('reading-copy scope does not silently admit another native reader',()=>{
  assert.throws(()=>readingCopy(saved('research-snapshot.json')),{code:'unsupported_report_schema'});
});

test('only news 1.2 admits the incomplete-attempt summary template',()=>{
  const f=JSON.parse(readFileSync(new URL('./fixtures/news-incomplete.json',import.meta.url),'utf8'));
  assert.equal(parseReport(f.report,f.run).workflow,'news');
  for(const version of ['1.0.0','1.1.0']){
    f.run.native_view.adapter_version=version;assert.throws(()=>parseReport(f.report,f.run),{code:'unsupported_report_schema'});
  }
});

test('an incomplete news summary cannot mask a completed result or populated figures',()=>{
  const fixture=()=>JSON.parse(readFileSync(new URL('./fixtures/news-incomplete.json',import.meta.url),'utf8'));
  const completed=fixture();completed.run.execution_status=completed.report.state.execution='completed';
  assert.throws(()=>parseReport(completed.report,completed.run),{code:'saved_evidence_invalid'});
  const populated=fixture();Object.assign(populated.report.metrics[0],{availability:'available',value:'0',reason_codes:[]});
  assert.throws(()=>parseReport(populated.report,populated.run),{code:'saved_evidence_invalid'});
});
