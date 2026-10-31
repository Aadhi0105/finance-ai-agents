import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {nearestObservation, plotGeometry, tickIndices} from '../src/reports/chart-layout.ts';
import {datasetRows, parseReport, pointMetric} from '../src/reports/report-data.ts';
import {formatMetric} from '../src/reports/format.ts';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/research-snapshot.json',import.meta.url),'utf8'));
const report = () => parseReport(structuredClone(fixture.report), structuredClone(fixture.run));
const chart = (id='prices') => report().charts.find(c=>c.id===id);
function custom(type, values) {
  const c=chart('revenue-by-year');
  c.type=type;
  c.series=[{id:'series',label:'Saved values',points:values.map((y,i)=>({id:'p'+i,x:String(i),label:String(i),y,evidence_refs:['source-'+i],reason_codes:y===null?['missing']:[]}))}];
  return c;
}

test('all eight saved research chart families have bounded finite native geometry',()=>{
  const saved=report();
  assert.equal(saved.charts.length,8);
  for(const c of saved.charts) {
    const rows=datasetRows(c), g=plotGeometry(c,rows,320);
    assert.equal(g.reason,null,c.id);
    for(const {segments} of g.series)for(const p of segments.flat()) {
      assert(Number.isFinite(p.x)&&Number.isFinite(p.y),c.id);
      assert(p.x>=g.left&&p.x<=g.right&&p.y>=g.top-.001&&p.y<=g.bottom+.001,c.id);
    }
    assert(g.ticks.length>=2);
  }
});

test('geometry does not mutate original decimals, points, dates, evidence or missing reasons',()=>{
  const c=chart(), before=structuredClone(c), rows=datasetRows(c);
  plotGeometry(c,rows,700); plotGeometry(c,rows,320,[c.series[0].id]);
  assert.deepEqual(c,before);
  assert.equal(formatMetric(pointMetric(c,rows[0].points[0])),'EUR 670.63');
  assert.equal(formatMetric(pointMetric(c,rows[0].points[1])),'Unavailable');
});

test('null or absent observations break a line without losing isolated points or treating gaps as zero',()=>{
  const c=custom('line',['1',null,'3','4',null,'0']);
  const g=plotGeometry(c,datasetRows(c),700);
  assert.deepEqual(g.series[0].segments.map(s=>s.map(p=>p.row)),[[0],[2,3],[5]]);
  assert(g.series[0].segments.flat().some(p=>p.row===5));
  assert(!g.series[0].segments.flat().some(p=>p.row===1));
});

test('bar geometry uses a genuine zero baseline for positive, negative and mixed values',()=>{
  for(const values of [['2','4'],['-2','-4'],['-2','4']]) {
    const c=custom('bar',values),g=plotGeometry(c,datasetRows(c),500);
    assert.equal(g.kind,'bar');
    assert(g.ticks.some(t=>t.value==='0'));
    for(const p of g.series[0].segments.flat())assert(Number(values[p.row])<0?p.y>g.zero:p.y<g.zero);
  }
});

test('very large close decimal amounts retain distinct vertical coordinates',()=>{
  const c=custom('line',['123456789012345678901234567890.01','123456789012345678901234567890.02']);
  const g=plotGeometry(c,datasetRows(c),700), points=g.series[0].segments[0];
  assert(points[1].y<points[0].y);
  assert.equal(c.series[0].points[0].y,'123456789012345678901234567890.01');
  assert.equal(g.ticks.length,new Set(g.ticks.map(t=>t.value)).size);
});

test('flat, zero and single-point series have usable scales and a centred single observation',()=>{
  for(const values of [['0'],['7'],['0','0'],['-2','-2']]) {
    const c=custom('line',values),g=plotGeometry(c,datasetRows(c),320);
    assert.equal(g.reason,null);
    assert(g.ticks.length>=2);
    assert(g.series[0].segments.flat().every(p=>Number.isFinite(p.y)));
    if(values.length===1)assert.equal(g.xs[0],(g.left+g.right)/2);
  }
});

test('withheld, all-null and unsupported series never produce guessed graphical values',()=>{
  const c=custom('line',['5']); c.availability='withheld';
  let g=plotGeometry(c,datasetRows(c),700);
  assert(g.reason); assert.deepEqual(g.series,[]);
  c.availability='available'; c.type='unrecognised';
  g=plotGeometry(c,datasetRows(c),700); assert(g.reason); assert.deepEqual(g.series,[]);
  const empty=custom('line',[null,null]);
  g=plotGeometry(empty,datasetRows(empty),700); assert(g.reason); assert.deepEqual(g.series,[]);
});

test('scenario and peer charts remain discrete dots without an interval or fitted path',()=>{
  for(const id of ['valuation-scenarios','peer-multiples']) {
    const c=chart(id),g=plotGeometry(c,datasetRows(c),700);
    assert.equal(g.kind,'dot');
    assert.equal(c.visibility,'diagnostic');
  }
});

test('series visibility affects only the plot; exact table rows and inspection values remain unchanged',()=>{
  const c=chart(), rows=datasetRows(c), before=structuredClone(rows);
  const g=plotGeometry(c,rows,700,[c.series[0].id]);
  assert.deepEqual(g.series.map(s=>s.index),[1,2]);
  assert.deepEqual(rows,before);
  const empty=plotGeometry(c,rows,700,c.series.map(s=>s.id));
  assert.match(empty.reason,/All series are hidden/); assert.deepEqual(empty.series,[]);
});

test('date union is chronological and spacing reflects actual dates, including missing rows in one series',()=>{
  const c=custom('line',['1','3']); c.x_axis.kind='date';
  c.series[0].points[0].x='2025-01-01';c.series[0].points[1].x='2025-01-04';
  c.series.push({id:'second',label:'Second',points:[{...c.series[0].points[0],id:'other',x:'2025-01-02',y:'2'}]});
  const rows=datasetRows(c),g=plotGeometry(c,rows,700);
  assert.deepEqual(rows.map(r=>r.x),['2025-01-01','2025-01-02','2025-01-04']);
  assert.equal(rows[1].points[0],null);
  assert(Math.abs((g.xs[1]-g.xs[0])/(g.xs[2]-g.xs[0])-1/3)<1e-10);
  assert.equal(g.series[0].segments.length,2);
});

test('pointer selection clamps at boundaries and finds the nearest actual observation',()=>{
  assert.equal(nearestObservation([20,50,90],-100),0);
  assert.equal(nearestObservation([20,50,90],42),1);
  assert.equal(nearestObservation([20,50,90],1000),2);
  assert.equal(nearestObservation([20],100),0);
  const ticks=tickIndices(Array.from({length:5000},(_,i)=>i*2),320);
  assert.equal(ticks[0],0);assert.equal(ticks.at(-1),4999);assert.equal(ticks.length,3);
});

test('the largest per-series point allowance is retained in geometry without downsampling',()=>{
  const c=custom('line',Array.from({length:5000},(_,i)=>String(i)));
  const g=plotGeometry(c,datasetRows(c),700);
  assert.equal(g.series[0].segments[0].length,5000);
  assert.equal(g.xs.length,5000);
});

test('the aggregate 20,000-point chart allowance is retained, and one more point is refused',()=>{
  const raw=structuredClone(fixture.report), run=structuredClone(fixture.run);
  const c=raw.charts.find(c=>c.id==='revenue-by-year'), original=c.series[0].points[0];
  c.type='line';
  c.series=Array.from({length:4},(_,i)=>({id:'s'+i,label:'Series '+i,points:Array.from({length:5000},(_,j)=>({...original,id:'p'+j,x:String(j),label:String(j),y:String(j+i)}))}));
  raw.charts=[c];
  raw.sections.forEach(s=>s.chart_refs=s.chart_refs.filter(id=>id===c.id));
  const parsed=parseReport(raw,run), saved=parsed.charts[0], rows=datasetRows(saved), g=plotGeometry(saved,rows,700);
  assert.equal(g.series.reduce((n,s)=>n+s.segments.flat().length,0),20000);
  c.series.push({id:'extra',label:'Over limit',points:[original]});
  assert.throws(()=>parseReport(raw,run),{code:'saved_evidence_invalid'});
});
