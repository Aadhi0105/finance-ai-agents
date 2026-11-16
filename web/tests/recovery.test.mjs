import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {parseRecovery,MAX_RECOVERY_BYTES,jobGuides,importGuides} from '../src/operations/recovery.ts';
import {PrivateClient} from '../src/onboarding/client.ts';
import {formats} from '../src/onboarding/data.ts';
const fixtures=JSON.parse(readFileSync(new URL('./fixtures/recovery.json',import.meta.url),'utf8'));
const operations=JSON.parse(readFileSync(new URL('./fixtures/operations.json',import.meta.url),'utf8')).empty;
const clone=()=>structuredClone(fixtures.cases),workspace=fixtures.empty.workspace_id,token='a'.repeat(43);
test('empty guidance is an observation, never independent protection or recovery permission',()=>{
 const v=parseRecovery(fixtures.empty,workspace);assert.equal(v.state,'observed');assert.equal(v.jobs.length,0);
 assert.equal(v.protection.independent_backup,'not_verified_here');assert.equal(v.automatic_retry,false);
});
test('backend cases distinguish restored queues, proof inspection, unknown outcomes and no-commit close inspection',()=>{
 const v=parseRecovery(fixtures.cases,workspace);assert.equal(v.state,'attention');
 assert.deepEqual(v.jobs.map(j=>j.guidance),['restored_queue_held','queued_waiting','worker_interrupted','delivery_inspection','unknown_outcome','source_hold','close_state_inspection','failed_attempt']);
 for(const j of v.jobs)assert(jobGuides[j.guidance].limit.length>0);
 for(const i of v.imports)assert(importGuides[i.guidance].limit.length>0);
});
for(const [name,edit] of [
 ['foreign workspace',v=>v.workspace_id='workspace-'+'0'.repeat(32)],['coerced schema',v=>v.schema_version=true],
 ['raw path',v=>v.path='/Users/private'],['automatic recovery',v=>v.automatic_recovery=true],['automatic retry',v=>v.automatic_retry=true],
 ['financial approval',v=>v.financial_approval=true],['production approval',v=>v.production_release_approved=true],
 ['independent protection claim',v=>v.protection.independent_backup='verified'],['clean machine claim',v=>v.protection.clean_machine_recovery='verified'],
 ['unproved local receipt',v=>v.protection.local_restore='verified'],['recovery secret',v=>v.protection.key=token],
 ['healthy state with held cases',v=>v.state='observed'],['unreported unreadable record',v=>{v.unreadable_jobs=1;v.job_total++;}],
 ['negative count',v=>v.job_total=-1],['coerced count',v=>v.unreadable_imports=false],['inventory overflow',v=>v.job_total=1001],
 ['count too small',v=>v.job_total=1],['half unknown count',v=>v.job_total=null],['unknown inventory with cases',v=>{v.job_total=null;v.unreadable_jobs=null;v.state='unavailable';}],
 ['duplicate job',v=>v.jobs[1]=v.jobs[0]],['duplicate import',v=>v.imports[1]=v.imports[0]],
 ['command injection',v=>v.jobs[0].command='run'],['url instead of id',v=>v.jobs[0].id='https://foreign.example'],
 ['retry guidance for unknown',v=>v.jobs[4].guidance='queued_waiting'],['release for started job',v=>{v.jobs[4].restoration_hold=true;v.jobs[4].guidance='restored_queue_held';}],
 ['invalid job status',v=>v.jobs[0].status='restart'],['wrong close guidance',v=>v.jobs[6].guidance='failed_attempt'],
 ['invented import guidance',v=>v.imports[0].guidance='run_calculation'],['mismatched import state',v=>v.imports[0].state='accepted'],
 ['invented worker',v=>v.worker='healthy'],['unreported source hold',v=>{v.state='observed';v.source_checks='held';}],['invalid date',v=>v.observed_at='tomorrow'],
])test('refuse unsafe recovery observation: '+name,()=>{const v=clone();edit(v);assert.throws(()=>parseRecovery(v,workspace));});
test('unknown inventory retains partial readable cases',()=>{
 const v=clone();v.state='unavailable';v.job_total++;v.unreadable_jobs=1;
 assert.equal(parseRecovery(v,workspace).unreadable_jobs,1);
});
test('running worker changes running-attempt guidance without allowing recovery',()=>{
 const v=clone();v.worker='worker_process_running';v.jobs[2].guidance='work_in_progress';assert.equal(parseRecovery(v,workspace).jobs[2].guidance,'work_in_progress');
});
test('unreadable empty inventory does not become a confirmed empty queue',()=>{
 const v=structuredClone(fixtures.empty);Object.assign(v,{job_total:null,unreadable_jobs:null,state:'unavailable'});assert.equal(parseRecovery(v,workspace).job_total,null);
});
function setup(handler){const calls=[];
 const client=new PrivateClient(async(path,init={})=>{calls.push({path,init});
  if(path==='/api/execution')return Response.json({schema_version:2,classification:'private',local_token_required:true,imports_enabled:true,admission_enabled:true,worker_enabled:false,live_data_enabled:false,paid_models_enabled:false,financial_approval:false,max_package_bytes:20_000_000,timeout_seconds_max:600,supported_input_formats:formats,fresh_research_supported:true,local_workflows_supported:true});
  if(path==='/api/operations')return Response.json({...operations,workspace_id:workspace});
  if(path==='/api/recovery')return handler(init);throw new Error('Unexpected request');
 });return {client,calls};
}
test('diagnostic navigation reads recovery guidance with header-only credentials',async()=>{
 const {client,calls}=setup(()=>Response.json(fixtures.cases));await client.connect(token,true);
 assert.equal((await client.recovery()).jobs.length,8);
 const request=calls.find(c=>c.path==='/api/recovery');assert.equal(new Headers(request.init.headers).get('Authorization'),'Bearer '+token);assert.equal(request.init.redirect,'error');assert.equal(request.init.cache,'no-store');
 assert(calls.every(c=>!c.init.body&&!c.path.includes(token)));client.disconnect();await assert.rejects(client.recovery());
});
test('oversized recovery observations are refused before interpretation',async()=>{
 const {client}=setup(()=>new Response('x'.repeat(MAX_RECOVERY_BYTES+1)));await client.connect(token,true);await assert.rejects(client.recovery());client.disconnect();
});
test('late response cannot restore guidance after disconnect',async()=>{
 let resolve;const pending=new Promise(r=>resolve=r);const {client}=setup(()=>pending);await client.connect(token,true);
 const response=client.recovery();client.disconnect();resolve(Response.json(fixtures.cases));await assert.rejects(response);
});
test('invalidated access clears recovery connection',async()=>{
 const {client}=setup(()=>Response.json({error:{code:'job_access_required'}},{status:403}));await client.connect(token,true);
 await assert.rejects(client.recovery());assert.equal(client.getSnapshot().connected,false);assert.equal(client.getSnapshot().workspaceId,null);
});
