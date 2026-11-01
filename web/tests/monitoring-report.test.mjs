import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {parseReport,datasetRows,pointMetric} from '../src/reports/report-data.ts';
import {filterMonitoringItems,historyForItem,monitoringBasis,monitoringClassification,monitoringItems,monitoringPeriod} from '../src/reports/monitoring-data.ts';
import {formatMetric} from '../src/reports/format.ts';
import {readingCopy} from '../src/reports/reading-copy.ts';
import {plotGeometry} from '../src/reports/chart-layout.ts';
const fixture=(name='monitoring-snapshot')=>JSON.parse(readFileSync(new URL('./fixtures/'+name+'.json',import.meta.url),'utf8'));
const saved=name=>{const f=fixture(name);return parseReport(f.report,f.run);};

test('native monitoring retains distinct original, surfaced and effective scopes',()=>{
  const r=saved(),by=id=>r.metrics.find(m=>m.id===id).value;
  assert.equal(r.agent,'agent2');assert.equal(r.workflow,'monitoring');
  assert.equal(by('cycle-breaches'),'1');assert.equal(by('surfaced-items'),'2');assert.equal(by('effective-breaches'),'2');
  assert.equal(r.state.financial_approval,false);
  const original=monitoringItems(r,'cycle'),effective=monitoringItems(r,'effective');
  assert.equal(original.length,4);assert.equal(effective.length,5);
  assert.equal(original[0].attention,'Surfaced for attention');assert.equal(original[0].breach,'No recorded breach');
  assert.equal(formatMetric(original[1].value),'2.1×');assert.equal(original[1].direction,'At or above');
  assert.equal(effective.find(i=>i.item==='delta_leverage').observed,'2026-01-07');
  assert.equal(monitoringBasis(r,'cycle'),'9');
});

test('search and attention filters retain their scope without changing results',()=>{
  const r=saved(),before=structuredClone(r),items=monitoringItems(r,'cycle');
  assert.equal(filterMonitoringItems(items,'','breaches').length,1);
  assert.equal(filterMonitoringItems(items,'','surfaced').length,2);
  assert.equal(filterMonitoringItems(items,' BETA ','all').length,1);
  assert.equal(filterMonitoringItems(items,'missing','all').length,0);
  assert.deepEqual(r,before);
});

test('only actually retained item histories map to interactive plots',()=>{
  const r=saved(),chart=historyForItem(r,'acme_leverage');
  assert(chart);assert.equal(historyForItem(r,'delta_leverage'),undefined);
  const rows=datasetRows(chart),g=plotGeometry(chart,rows,700);
  assert.equal(rows.length,9);assert.equal(g.kind,'line');assert.equal(g.reason,null);
  assert.equal(rows.at(-1).x,'2026-01-09');assert.equal(formatMetric(pointMetric(chart,rows.at(-1).points[0])),'3.47×');
});

test('pending corrections do not replace retained values or generate corrected history',()=>{
  const r=saved('monitoring-pending'),effective=monitoringItems(r,'effective');
  assert.equal(formatMetric(effective[0].value),'5.0×');
  assert(effective[0].state.includes('correction review pending'));
  assert.equal(filterMonitoringItems(effective,'','pending').length,1);
  assert.equal(r.metrics.find(m=>m.id==='pending-value-0').value,'2');
  assert.equal(r.tables.find(t=>t.id==='decision-observations').rows.length,0);
});

test('replacement definitions keep retired evidence and separate before/after records',()=>{
  const r=saved('monitoring-replaced');
  assert(monitoringItems(r,'effective').some(i=>i.state.includes('retired series; replacement item: qa_ratio_v2')));
  assert.equal(r.metrics.find(m=>m.id==='effective-breaches').value,'0');
  assert(r.tables.find(t=>t.id==='decision-observations').rows.length>0);
});

test('legacy 1.0 is readable without inventing missing context or item associations',()=>{
  const r=saved('monitoring-legacy');
  assert.equal(monitoringBasis(r,'export'),'Not retained');
  assert(monitoringItems(r,'cycle').every(i=>i.item==='Not retained'));
  assert.equal(r.metrics.find(m=>m.id==='cycle-breaches'),undefined);
  assert.equal(r.charts[0].series[0].points.length,9);
});

for(const [name,edit,code='saved_evidence_invalid'] of [
  ['wrong family',(r,run)=>{run.agent='agent1';},'unsupported_report_schema'],
  ['unsupported version',(r,run)=>{run.native_view.adapter_version='2.0.0';},'unsupported_report_schema'],
  ['wrong source family',r=>{r.artifacts[0].source_schema='agent1.model/2';}],
  ['altered registered hash',r=>{r.artifacts[0].sha256='f'.repeat(64);}],
  ['financial approval',r=>{r.state.financial_approval=true;}],
  ['negative count',r=>{r.metrics.find(m=>m.id==='cycle-breaches').value='-1';}],
  ['invented probability',r=>{r.metrics.find(m=>m.id==='cycle-breaches').unit='fraction';}],
  ['unknown financial metric',r=>{r.metrics.find(m=>m.id==='cycle-breaches').id='future-breach-probability';}],
  ['wrong historical unit',r=>{r.charts[0].y_axis.unit='fraction';}],
  ['invented future chart',r=>{r.charts[0].id='future-probability';}],
  ['history recast as categories',r=>{r.charts[0].x_axis.kind='category';}],
  ['broken observation refs',r=>{r.tables[0].rows[0].evidence_refs=['absent'];}],
  ['unregistered prose',r=>{r.summary.template_id='financial-recommendation';},'unsupported_report_schema'],
]) test('monitoring refuses '+name,()=>{
  const {run,report}=fixture();edit(report,run);assert.throws(()=>parseReport(report,run),{code});
});

test('monitoring summary template is confined to monitoring 1.1',()=>{
  const {run,report}=fixture();run.native_view.adapter_version='1.0.0';
  assert.throws(()=>parseReport(report,run),{code:'unsupported_report_schema'});
});

test('complete copy preserves every scope, actual history and correction source',()=>{
  for(const name of ['monitoring-snapshot','monitoring-pending','monitoring-replaced','monitoring-legacy']){
    const r=saved(name),copy=readingCopy(r),before=structuredClone(r);
    assert.equal(copy.title,'Financial monitoring');assert.equal(copy.metrics.length,r.metrics.length);
    assert.equal(copy.tables.reduce((n,t)=>n+t.rows.length,0),r.tables.reduce((n,t)=>n+t.rows.length,0));
    assert.equal(copy.evidence.length,r.evidence.length);
    assert(copy.tables.every(t=>t.rows.every(row=>!row.references.includes('Unresolved'))));
    assert.deepEqual(r,before);
  }
});

test('zero history remains zero and a missing point remains a gap in both graph and copy',()=>{
  const r=saved(),c=r.charts[0];c.series[0].points[0].y='0';
  c.series[0].points[1].y=null;c.series[0].points[1].reason_codes=['not_retained'];
  const rows=datasetRows(c),geometry=plotGeometry(c,rows,700),copy=readingCopy(r);
  assert.equal(formatMetric(pointMetric(c,rows[0].points[0])),'0×');
  assert.equal(copy.charts[0].rows[1].values[0],'Unavailable');
  assert.equal(geometry.series[0].segments.length,2);
});

test('readable classification retains correction qualifiers and export time is labelled separately',()=>{
  assert.equal(monitoringClassification('NEW_BREACH · correction review pending; retained observation'),'New breach · correction review pending; retained observation');
  assert.equal(monitoringPeriod('Snapshot export: 2026-01-09T15:00:00+00:00'),'Snapshot export: 9 Jan 2026, 15:00 UTC');
  assert.equal(monitoringPeriod('2026-01-09 · cycle 9'),'2026-01-09 · cycle 9');
});
