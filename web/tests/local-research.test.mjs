import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {parseRun,parseJob,parseCapabilities} from '../src/onboarding/data.ts';
import {parseReport} from '../src/reports/report-data.ts';
import {canonicalLocal} from '../src/onboarding/client.ts';
const sample=JSON.parse(readFileSync(new URL('./fixtures/private-local-research.json',import.meta.url),'utf8'));

test('new local research uses its explicit source family and recipe',()=>{
 const run=parseRun(sample.run),report=parseReport(sample.report,run);
 assert.equal(run.native_view.adapter_id,'agent1-local-report');
 assert.equal(report.artifacts[0].source_schema,'agent1.local-analysis/1');
 assert.equal(report.summary.template_id,'local-research-summary-v1');
 assert.equal(report.state.financial_approval,false);
 assert.ok(report.metrics.some(m=>m.id==='weighted-per-share'&&Number(m.value)===100));
 assert.equal(report.charts.filter(c=>c.availability==='available').length,3);
});

test('local job keeps exact reviewed plan, source and zero-call policy',()=>{
 const job=parseJob(sample.job,sample.job.source.workspace_id);
 assert.equal(job.request.schema_version,3);
 assert.equal(job.request.analysis_plan.valuation.horizon_years,1);
 assert.equal(canonicalLocal(job.request),canonicalLocal(sample.job.request));
 assert.equal(job.attempt,1);
});

for(const [name,change] of [
 ['old source family',v=>v.report.artifacts[0].source_schema='agent1.model/2'],
 ['wrong adapter',v=>v.run.native_view.adapter_id='agent1-native-report'],
 ['approval',v=>v.report.state.financial_approval=true],
 ['lost evidence',v=>v.report.metrics[0].evidence_refs=[]],
 ['unsupported recipe',v=>v.run.native_view.adapter_version='2.0.0']
])test('local reader refuses '+name,()=>{const v=structuredClone(sample);change(v);assert.throws(()=>parseReport(v.report,parseRun(v.run)));});

test('canonical review hashes use sorted keys and literal Unicode',()=>{
 assert.equal(canonicalLocal({z:'€',a:{y:2,x:1}}),'{"a":{"x":1,"y":2},"z":"€"}');
});

test('local kit byte limit refuses oversized files before transfer',async()=>{
 const {PrivateClient}=await import('../src/onboarding/client.ts');
 const {formats}=await import('../src/onboarding/data.ts');let calls=0;
 const client=new PrivateClient(async()=>{calls++;return new Response(JSON.stringify({schema_version:2,classification:'private',local_token_required:true,
  imports_enabled:true,admission_enabled:true,worker_enabled:true,live_data_enabled:false,paid_models_enabled:false,financial_approval:false,
  max_package_bytes:20_000_000,timeout_seconds_max:600,supported_input_formats:formats,local_workflows_supported:true,fresh_research_supported:true}),{headers:{'Content-Type':'application/json'}});});
 await client.discover();
 await assert.rejects(()=>client.inspect({id:'dataset-test',entity_id:'entity-test',workflow:'research',title:'Test',payload_format:'agent1.financial-kit/1'},new File([' '.repeat(1_000_001)],'too-large.json')),/1 MB/);
 assert.equal(calls,1);client.disconnect();
});
