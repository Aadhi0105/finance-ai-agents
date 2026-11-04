import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {formats,parseRun,parseJob} from '../src/onboarding/data.ts';
import {parseVersion,jobRequest,parseCapabilities} from '../src/onboarding/data.ts';
import {parseReport} from '../src/reports/report-data.ts';
import {PrivateClient} from '../src/onboarding/client.ts';
import {plotGeometry} from '../src/reports/chart-layout.ts';
import {datasetRows} from '../src/reports/report-data.ts';

const caps={schema_version:2,classification:'private',local_token_required:true,imports_enabled:true,admission_enabled:true,worker_enabled:true,
 live_data_enabled:false,paid_models_enabled:false,financial_approval:false,max_package_bytes:20_000_000,timeout_seconds_max:600,
 supported_input_formats:formats,fresh_research_supported:true,local_workflows_supported:true};
const json=v=>new Response(JSON.stringify(v),{headers:{'Content-Type':'application/json'}});

for(const w of ['monitoring','events','news']){
 const sample=JSON.parse(readFileSync(new URL('./fixtures/private-local-'+w+'.json',import.meta.url),'utf8'));
 test('new '+w+' keeps its explicit source, recipe and exact counts',()=>{
  const run=parseRun(sample.run),report=parseReport(sample.report,run);
  assert.equal(run.native_view.adapter_id,'local-'+w+'-report');
  assert.equal(report.artifacts[0].source_schema,'keystone.local-workflow-result/1');
  assert.equal(report.state.financial_approval,false);
  assert.equal(report.state.evidence_gate,'held_for_review');
  assert.ok(report.metrics.filter(m=>m.unit==='count').every(m=>m.availability==='available'&&m.value!==null));
  assert.ok(report.charts.some(c=>c.availability==='available'));
 });
 test('new '+w+' request uses exact version, fixed method and zero-call job',()=>{
  const version=parseVersion(sample.version),request=jobRequest(version,120),job=parseJob(sample.job,sample.job.source.workspace_id);
  assert.deepEqual(request,sample.job.request);assert.equal(job.request.schema_version,4);
  assert.equal(job.attempt,1);assert.throws(()=>jobRequest(version,121));
 });
 for(const [name,change] of [
  ['old source schema',s=>s.report.artifacts[0].source_schema='agent3.run_bundle/1'],
  ['wrong recipe',s=>s.run.native_view.adapter_version='2.0.0'],
  ['financial approval',s=>s.report.state.financial_approval=true],
  ['published gate',s=>s.report.state.evidence_gate='passed_evidence_checks'],
  ['missing evidence',s=>s.report.metrics[0].evidence_refs=[]],
  ['saved profile substitution',s=>s.run.input_origin.profile='replay-imported-events']
 ])test('new '+w+' refuses '+name,()=>{
  const s=structuredClone(sample);change(s);assert.throws(()=>parseReport(s.report,parseRun(s.run)));
 });
 for(const [name,change] of [
  ['paid usage allowance',j=>j.max_requests=1],['wrong method',j=>j.request.processing_plan.method='invented'],
  ['time limit expansion',j=>j.request.timeout_seconds=121],['approval in plan',j=>j.request.processing_plan.financial_approval=true]
 ])test('new '+w+' job refuses '+name,()=>{const s=structuredClone(sample);change(s.job);assert.throws(()=>parseJob(s.job,s.job.source.workspace_id));});
 test('lost '+w+' acknowledgement preserves the exact request and key',async()=>{
  const keys=[],bodies=[];let first=true;
  const fetcher=async(path,init={})=>{
   if(path==='/api/execution')return json(caps);
   if(path==='/api/workspace')return json({schema_version:3,kind:'keystone.private-workspace-reports',classification:'private',workspace_id:sample.job.source.workspace_id,
    production_release_approved:false,live_data_enabled:false,paid_models_enabled:false,runs:[]});
   if(path.startsWith('/api/entities?')||path.startsWith('/api/datasets?'))return json({items:[],next_cursor:null});
   if(path.includes('/versions/'))return json(sample.version);
   if(path==='/api/jobs'){
    keys.push(new Headers(init.headers).get('Idempotency-Key'));bodies.push(JSON.parse(init.body));
    if(first){first=false;throw new TypeError('Lost reply');}
    return json({job:sample.job,replayed:true});
   }
   throw Error('Unexpected local request');
  };
  const client=new PrivateClient(fetcher);await client.connect('a'.repeat(43));
  assert.equal(client.getSnapshot().connected,true);
  await client.submit(parseVersion(sample.version),120);assert.equal(client.getSnapshot().jobState,'unconfirmed');
  const job=await client.submit();assert.equal(job.id,sample.job.job_id);
  assert.equal(new Set(keys).size,1);assert.deepEqual(bodies[0],bodies[1]);assert.deepEqual(bodies[0],sample.job.request);client.disconnect();
 });
}

test('old capability inventories remain supported without enabling new formats',()=>{
 const old=structuredClone(caps);delete old.local_workflows_supported;
 old.supported_input_formats={...formats,monitoring:[formats.monitoring[0]],events:[formats.events[0]],news:[formats.news[0]]};
 assert.equal(parseCapabilities(old).localWorkflows,false);
 assert.equal(parseCapabilities(caps).localWorkflows,true);
});

test('event inference cannot become an available number',()=>{
 const s=JSON.parse(readFileSync(new URL('./fixtures/private-local-events.json',import.meta.url),'utf8'));
 const m=s.report.metrics.find(m=>m.id==='p-value');m.value='0.01';m.availability='available';m.reason_codes=[];
 assert.throws(()=>parseReport(s.report,parseRun(s.run)));
});

test('new news diagnostics keep a fixed minus-one to plus-one scale',()=>{
 const s=JSON.parse(readFileSync(new URL('./fixtures/private-local-news.json',import.meta.url),'utf8'));
 const r=parseReport(s.report,parseRun(s.run)),c=r.charts.find(c=>c.id==='daily-tone');
 for(const score of ['0','0.3333333333333333','-1','1']){
  c.series[0].points[0].y=score;const g=plotGeometry(c,datasetRows(c),700);
  assert.equal(Number(g.ticks[0].value),-1);assert.equal(Number(g.ticks.at(-1).value),1);
 }
});
