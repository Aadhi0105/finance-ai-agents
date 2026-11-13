import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {parseOperations,elapsed,nextStep} from '../src/operations/data.ts';
import {PrivateClient} from '../src/onboarding/client.ts';
import {formats} from '../src/onboarding/data.ts';

const cases=JSON.parse(readFileSync(new URL('./fixtures/operations.json',import.meta.url),'utf8'));
const privateFixture=JSON.parse(readFileSync(new URL('./fixtures/private-onboarding.json',import.meta.url),'utf8'));
const clone=(name='mixed')=>structuredClone(cases[name]);
const cap=(v,key)=>v.capacities.find(c=>c.key===key);
const check=(v,key)=>v.checks.find(c=>c.key===key);
const token='a'.repeat(43);
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};

test('real backend observations keep operational health, execution and financial review distinct',()=>{
 for(const name of ['empty','mixed','unavailable'])assert.equal(parseOperations(cases[name]).financial_approval,false);
 assert.equal(parseOperations(cases.empty).state,'ok');const v=parseOperations(cases.mixed);
 assert.equal(v.job_counts.queued,1);assert.equal(v.job_counts.failed,1);assert.equal(v.job_counts.review_required,1);assert.equal(v.job_counts.outcome_unknown,1);
 assert.equal(check(v,'jobs').code,'recovery_inspection_required');assert.equal(parseOperations(cases.unavailable).report_total,null);
});

for(const [name,edit] of [
 ['financial approval',v=>v.financial_approval=true],['production approval',v=>v.production_release_approved=true],
 ['live provider access',v=>v.live_data_enabled=true],['paid calls',v=>v.paid_models_enabled=true],['coerced version',v=>v.schema_version=true],
 ['unknown raw log',v=>v.raw_log='/private/secret'],['invented healthy aggregate',v=>v.state='ok'],
 ['dropped job',v=>v.jobs.pop()],['duplicate job',v=>v.jobs.push(v.jobs[0])],['unavailable masquerading as zero',v=>v.unreadable_jobs=1],
 ['false completed count',v=>v.job_counts.completed=1],['unknown progress stage',v=>v.jobs[0].stage='99_percent_complete'],
 ['unbound job fields',v=>v.jobs[0].command='rm'],['fabricated authenticated identity',v=>v.reviewer='authenticated'],
 ['HTML diagnostic',v=>v.checks[0].code='<script>'],['mismatched component',v=>v.checks[0].code='input_database_readable'],
 ['missing component',v=>v.checks.pop()],['missing capacity',v=>v.capacities.pop()],['negative capacity',v=>v.capacities[0].used=-1],
 ['capacity flag cleared',v=>{cap(v,'pending_jobs').used=20;}],['unsafe integer',v=>v.disk_free_bytes=Number.MAX_SAFE_INTEGER+1],
 ['foreign held report path',v=>v.held_reports=['/private/report']],['unknown import state',v=>v.imports[0].state='approved'],
 ['wrong import count',v=>v.import_total=0],['wrong time',v=>v.observed_at='yesterday'],
 ])test('operational delivery refuses '+name,()=>{const v=clone();edit(v);assert.throws(()=>parseOperations(v));});

test('unknown job records do not become zero queue use or a healthy job component',()=>{
 const v=clone('empty');v.job_total=1;v.unreadable_jobs=1;cap(v,'retained_jobs').used=1;
 for(const key of ['pending_jobs','analysis_evidence']){cap(v,key).used=null;cap(v,key).state='unavailable';}
 check(v,'jobs').state='unavailable';check(v,'jobs').code='job_records_unavailable';v.state='unavailable';
 assert.equal(parseOperations(v).job_counts.queued,0); // Only verified rows are counted; one unknown remains explicit.
 check(v,'jobs').state='ok';check(v,'jobs').code='job_records_checked';assert.throws(()=>parseOperations(v));
});

test('work stages and timing use saved receipt dates without invented progress or negative durations',()=>{
 const v=parseOperations(cases.mixed),queued=v.jobs.find(j=>j.status==='queued'),uncertain=v.jobs.find(j=>j.status==='outcome_unknown');
 assert.equal(elapsed(queued,v.observed_at),'Not started');assert.match(nextStep(uncertain),/may already be committed/);
 assert.equal(elapsed({...uncertain,started_at:'2099-01-01T00:00:00Z'},v.observed_at),'Timing unavailable');
 assert.match(nextStep({...queued,restoration_hold:true}),/operator must recheck and release/);
 assert.throws(()=>parseOperations(v,'workspace-foreign'));
});

function setup(handler){const calls=[];const caps={schema_version:2,classification:'private',local_token_required:true,imports_enabled:true,admission_enabled:true,worker_enabled:false,live_data_enabled:false,paid_models_enabled:false,financial_approval:false,max_package_bytes:20_000_000,timeout_seconds_max:600,supported_input_formats:formats,fresh_research_supported:true,local_workflows_supported:true,operations_supported:true};
 const fetcher=async(path,init={})=>{calls.push({path,init});const special=await handler?.(path,init);if(special!==undefined)return special;
  if(path==='/api/execution')return Response.json(caps);if(path==='/api/operations')return Response.json({...clone('empty'),workspace_id:privateFixture.workspace.workspace_id});
  if(path==='/api/workspace')return Response.json(privateFixture.workspace);if(path.startsWith('/api/entities'))return Response.json(privateFixture.entities);if(path.startsWith('/api/datasets'))return Response.json(privateFixture.datasets);throw new Error('Unexpected transport');};
 return {client:new PrivateClient(fetcher),calls};
}

test('Operations-only connection succeeds without loading a broken report inventory or private source data',async()=>{
 const {client,calls}=setup(path=>path==='/api/workspace'?Response.json({error:{code:'input_unavailable'}},{status:503}):undefined);
 await client.connect(token,true);assert.equal(client.getSnapshot().connected,true);assert.equal(client.getSnapshot().operationsOnly,true);assert.equal(client.getSnapshot().workspace,null);
 assert(!calls.some(c=>c.path==='/api/workspace'||c.path.startsWith('/api/entities')||c.path.startsWith('/api/datasets')));
 assert.equal((await client.operations()).job_total,0);await assert.rejects(client.createEntity({name:'Should not be sent'}));
 assert(calls.every(c=>c.init.method===undefined||c.init.method==='GET'));client.disconnect();assert.equal(client.getSnapshot().workspaceId,null);
});

test('normal access and Operations reads bind one authority and keep credentials out of URLs and bodies',async()=>{
 const {client,calls}=setup();await client.connect(token);const view=await client.operations();assert.equal(view.workspace_id,client.getSnapshot().workspaceId);
 const read=calls.find(c=>c.path==='/api/operations');assert.equal(new Headers(read.init.headers).get('Authorization'),'Bearer '+token);
 assert.equal(read.init.cache,'no-store');assert.equal(read.init.redirect,'error');assert(!read.path.includes(token));assert.equal(read.init.body,undefined);
 assert.equal(read.init.credentials,'omit');
});

test('failed normal connection can be followed by explicit operator-only access',async()=>{
 const {client}=setup(path=>path==='/api/workspace'?Response.json({error:{code:'input_unavailable'}},{status:503}):undefined);
 await client.connect(token);assert.equal(client.getSnapshot().connected,false);await client.connect(token,true);assert.equal(client.getSnapshot().operationsOnly,true);
});

test('a transient workspace refresh failure does not destroy the bound diagnostics identity or prevent recovery',async()=>{
 let failed=false;const {client}=setup(path=>path==='/api/workspace'&&failed?Response.json({error:{code:'input_unavailable'}},{status:503}):undefined);
 await client.connect(token);const expected=client.getSnapshot().workspaceId;failed=true;await client.refresh();
 assert.equal(client.getSnapshot().workspace,null);assert.equal(client.getSnapshot().workspaceId,expected);assert.equal((await client.operations()).workspace_id,expected);
 failed=false;await client.refresh();assert.equal(client.getSnapshot().workspace.id,expected);assert.equal(client.getSnapshot().error,'');
});

test('disconnect aborts a read and late observations cannot populate a new connection',async()=>{
 const wait=deferred(),{client}=setup(path=>path==='/api/operations'?wait.promise:undefined);await client.connect(token);
 const reading=client.operations();client.disconnect();wait.resolve(Response.json(clone('empty')));await assert.rejects(reading);assert.equal(client.getSnapshot().connected,false);
});

test('wrong workspace, malformed JSON and oversized diagnostic responses remain unavailable',async()=>{
 for(const make of [()=>Response.json(clone('empty')),()=>Response.json({...clone('empty'),financial_approval:true}),()=>new Response('secret',{headers:{'Content-Type':'application/json'}}),()=>new Response('x'.repeat(1_500_001),{headers:{'Content-Type':'application/json'}})]){
  const {client}=setup(path=>path==='/api/operations'?make():undefined);await client.connect(token);await assert.rejects(client.operations());
 }
});

test('expired access disconnects rather than showing cached operational health',async()=>{
 const {client}=setup(path=>path==='/api/operations'?Response.json({error:{code:'job_access_required'}},{status:403}):undefined);await client.connect(token);
 await assert.rejects(client.operations(),e=>{assert.equal(e.code,'access_required');return true;});assert.equal(client.getSnapshot().connected,false);assert.equal(client.getSnapshot().workspaceId,null);
});
