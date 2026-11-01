import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {parseReport} from '../src/reports/report-data.ts';
import {readingCopy} from '../src/reports/reading-copy.ts';
import {StaticPlot} from '../src/reports/StaticPlot.ts';

const fixture=name=>JSON.parse(readFileSync(new URL('./fixtures/'+name+'.json',import.meta.url),'utf8'));
const saved=name=>{const f=fixture(name);return parseReport(f.report,f.run);};
const svg=chart=>renderToStaticMarkup(createElement(StaticPlot,{chart}));

for(const family of ['research-snapshot','research-legacy','monitoring-snapshot','monitoring-legacy','event-snapshot','event-legacy','news-snapshot','news-legacy','close-snapshot','close-legacy']) {
  test(`all supported families retain every measure, finding, row, source and restriction in the copy: ${family}`,()=>{
    const r=saved(family),before=structuredClone(r),copy=readingCopy(r);
    assert.equal(copy.metrics.length,r.metrics.length);assert.equal(copy.findings.length,r.findings.length);assert.deepEqual(copy.sources,r.sources);
    assert.equal(copy.tables.reduce((n,t)=>n+t.rows.length,0),r.tables.reduce((n,t)=>n+t.rows.length,0));
    assert.equal(copy.evidence.length,r.evidence.length);
    assert(copy.findings.every(f=>!f.references.includes('Unresolved')));
    assert(copy.tables.every(t=>t.rows.every(row=>!row.references.includes('Unresolved'))));
    assert.equal(r.state.financial_approval,false);assert.deepEqual(r,before);
  });
}

test('research scenarios and peers remain discrete points in the reading copy',()=>{
  const r=saved('research-snapshot');
  for(const id of ['valuation-scenarios','peer-multiples']){
    const c=r.charts.find(c=>c.id===id),markup=svg(c);
    assert.match(markup,/data-plot-kind="dot"/);assert(!markup.includes('<polyline'));
    assert.match(markup,/Separate saved observations/);
    const copy=readingCopy(r).charts.find(c=>c.chart.id===id);assert.equal(copy.rows.length,c.series[0].points.length);
  }
});

test('multi-series research plot retains named series and distinct stroke patterns',()=>{
  const c=saved('research-snapshot').charts.find(c=>c.type==='line'&&c.series.length===3),markup=svg(c);
  assert.equal((markup.match(/data-plot-kind="line"/g)||[]).length,3);
  assert.match(markup,/stroke-dasharray="8 5"/);assert.match(markup,/stroke-dasharray="2 4"/);
  for(const series of c.series)assert(markup.includes(series.label));
});

test('reading-copy line segments preserve missing gaps and a real zero',()=>{
  const c=saved('monitoring-snapshot').charts[0];c.series=[c.series[0]];
  c.series[0].points=c.series[0].points.slice(0,3);
  c.series[0].points[0].y='0';c.series[0].points[1].y=null;c.series[0].points[1].reason_codes=['missing'];
  const before=structuredClone(c),markup=svg(c);
  assert.equal((markup.match(/<polyline/g)||[]).length,2);assert.deepEqual(c,before);
});

test('withheld series never become a zero plot or scenario interval',()=>{
  const c=saved('event-snapshot').charts.find(c=>c.id==='event-path'),markup=svg(c);
  assert(!markup.includes('<svg'));assert.match(markup,/Values withheld/);
});

test('printed percentage axes and exact tables use the same display unit',()=>{
  const c=saved('research-snapshot').charts.find(c=>c.y_axis.unit==='fraction'&&c.availability==='available');
  const markup=svg(c);assert.match(markup,/percent \(saved fractions\)/);assert(markup.includes('%'));
});

test('source text remains escaped in static graph titles and legends',()=>{
  const c=saved('monitoring-snapshot').charts[0];c.title='<script>unsafe</script>';c.series[0].label='<img src=x>';
  const markup=svg(c);assert(!markup.includes('<script>'));assert(!markup.includes('<img '));assert(markup.includes('&lt;script&gt;'));
});

test('edge labels remain inside the copied plot for dates and categories',()=>{
  const r=saved('research-snapshot');
  for(const c of [r.charts.find(c=>c.x_axis.kind==='date'&&c.availability==='available'),r.charts.find(c=>c.id==='valuation-scenarios')]){
    const markup=svg(c);assert.match(markup,/text-anchor="start"/);assert.match(markup,/text-anchor="end"/);
  }
});

test('research copy keeps unavailable consensus separate from diagnostic valuation and uncollected brokers',()=>{
  const r=saved('research-snapshot'),copy=readingCopy(r);
  assert.equal(r.analyst_content.market_consensus.availability,'unavailable');
  assert(r.analyst_content.external_research.reason_codes.includes('broker_reports_not_collected'));
  assert.equal(copy.metrics.find(m=>m.id==='weighted-valuation').visibility,'diagnostic');
  assert(copy.charts.some(c=>c.chart.id==='valuation-scenarios'));
});

for(const family of ['research-snapshot','monitoring-snapshot','event-snapshot','news-snapshot','close-snapshot'])
test(`shared reader refuses financial approval changes before export: ${family}`,()=>{
  const {run,report}=fixture(family);report.state.financial_approval=true;
  assert.throws(()=>parseReport(report,run),{code:'saved_evidence_invalid'});
});
