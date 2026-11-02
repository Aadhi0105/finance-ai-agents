import assert from 'node:assert/strict';
import test from 'node:test';
import {JobClient} from '../src/execution/job-client.ts';
import {eligibleRuns,JobFailure,nextAction,parseCapabilities,parseDetail,parseJob,parseList,parseRequest,profiles,responseError} from '../src/execution/job-data.ts';

const stamp='2026-11-02T12:00:00+00:00',secret='X'.repeat(43),id='job-'+'a'.repeat(32);
const request={schema_version:1,workflow:'research',source_run_id:'research-example',timeout_seconds:600};
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
function caps(enabled=true,worker=true){return {schema_version:1,admission_enabled:enabled,worker_enabled:enabled&&worker,worker_status:enabled&&worker?'running':'not_enabled',local_token_required:enabled,classification:'synthetic',live_data_enabled:false,paid_models_enabled:false,financial_approval:false,workflows:enabled?Object.keys(profiles):[],profiles:enabled?Object.fromEntries(Object.entries(profiles).map(([k,v])=>[k,v.profile])):{},timeout_seconds_max:600,max_requests:12,max_output_tokens:48000,max_pending_jobs:20,max_retained_jobs:1000};}
function job(state='queued',family='research',letter='a'){
  const ready=['completed','review_required'].includes(state),queued=state==='queued';
  return {schema_version:2,admission_schema_version:1,profile_version:1,job_id:'job-'+letter.repeat(32),operation_id:'web-'+letter.repeat(32),profile:profiles[family].profile,request:{...request,workflow:family,source_run_id:family+'-example'},created_at:stamp,status:state,source:{run_id:family+'-example',workflow:family},live_data_enabled:false,paid_models_enabled:false,financial_approval:false,max_requests:12,max_output_tokens:48000,worker_enabled:true,recovery_required:['outcome_unknown','delivery_failed'].includes(state),result_url:ready?'#/runs/result-'+letter.repeat(32):null,
    execution:{schema_version:1,status:state,attempt:queued?0:1,started_at:queued?null:stamp,inputs_verified_at:queued||state==='source_changed'?null:stamp,finished_at:queued||state==='running'?null:stamp,operation_status:queued||state==='source_changed'?'not_started':ready||state==='delivery_failed'?'review_required':state==='running'?'running':'outcome_unknown',reason:({queued:'waiting',running:'processing',completed:'registered',review_required:'registered',failed:'execution_failed',source_changed:'source_changed',delivery_failed:'delivery_failed',outcome_unknown:'interrupted'})[state],result:ready||state==='delivery_failed'?{run_id:'result-'+letter.repeat(32),manifest_sha256:'1'.repeat(64),run_sha256:'2'.repeat(64),operation_receipt_sha256:'3'.repeat(64)}:null}};
}
const list=(jobs=[])=>({jobs,next_cursor:null,worker_enabled:true});
const detail=(j=job())=>({job:j,events:[{event:'admitted',created_at:stamp},...(j.status==='queued'?[]:[{event:({running:'claimed',completed:'registered',review_required:'registered',failed:'failed',source_changed:'source_changed',delivery_failed:'delivery_failed',outcome_unknown:'interrupted'})[j.status],created_at:stamp}])]});
const defer=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {resolve,promise};};
async function connected(post,options={}){
  const calls=[];
  const client=new JobClient(async(path,init)=>{calls.push({path,init});if(path==='/api/execution')return json(caps());if(init.method==='POST')return post(path,init);return json(list());},options.key||(()=> 'request-identity-one'),options.timeout||12000);
  await client.discover();await client.connect(secret);return {client,calls};
}

test('capabilities admit only the closed offline profile set and enforced ceilings',()=>{
  assert(parseCapabilities(caps()).worker_enabled);assert(!parseCapabilities(caps(false)).admission_enabled);
  for(const mutate of [v=>v.paid_models_enabled=true,v=>v.live_data_enabled=true,v=>v.financial_approval=true,v=>v.timeout_seconds_max=601,v=>v.profiles.research='arbitrary-command',v=>v.workflows=['research'],v=>v.worker_status='stopped',v=>v.max_requests=13,v=>v.schema_version=2]){
    const v=caps();mutate(v);assert.throws(()=>parseCapabilities(v),{code:'unsupported_response'});
  }
});
test('form requests cannot carry paths, commands or expanded limits',()=>{
  assert.deepEqual(parseRequest(request),request);
  for(const value of [{...request,command:'anything'},{...request,timeout_seconds:601},{...request,timeout_seconds:1.1},{...request,source_run_id:'../source'},{...request,schema_version:true},{...request,workflow:'agent1'}])assert.throws(()=>parseRequest(value));
});
for(const family of Object.keys(profiles))test('registered job mapping retains workflow and financial restrictions: '+family,()=>{
  const parsed=parseJob(job('review_required',family));assert.equal(parsed.request.workflow,family);assert.equal(parsed.resultUrl,'#/runs/result-'+'a'.repeat(32));assert.match(nextAction(parsed),/Financial approval has not been granted/);
});
for(const state of ['queued','running','completed','review_required','source_changed','failed','outcome_unknown','delivery_failed'])test('each recorded outcome has readable guidance: '+state,()=>{
  const parsed=parseJob(job(state));assert.equal(parsed.status,state);assert(nextAction(parsed).length>30);
  const saved=parseDetail(detail(job(state)),id);assert.equal(saved.job.status,state);
});
test('job links, identity, state, approval and source cannot be substituted',()=>{
  for(const mutate of [v=>v.result_url='https://example.com',v=>v.result_url='javascript:alert(1)',v=>v.execution.result.run_id='result-'+'b'.repeat(32),v=>v.financial_approval=true,v=>v.source.run_id='other',v=>v.operation_id='other',v=>v.status='approved',v=>v.execution.status='queued',v=>v.execution.result.manifest_sha256='bad',v=>v.execution.finished_at=null,v=>v.execution.started_at='yesterday',v=>v.recovery_required=true,v=>v.schema_version=1]){
    const v=job('review_required');mutate(v);assert.throws(()=>parseJob(v),{code:'unsupported_response'});
  }
});
test('uncertain and delivery-failed jobs expose no report action and require inspection',()=>{
  for(const state of ['outcome_unknown','delivery_failed']){const j=parseJob(job(state));assert.equal(j.resultUrl,null);assert.match(nextAction(j),/without rerunning/);const bad=job(state);bad.recovery_required=false;assert.throws(()=>parseJob(bad));}
});
test('stopped worker does not turn a running job into a completed report',()=>{
  const j=job('running');j.worker_enabled=false;j.recovery_required=true;assert.match(nextAction(parseJob(j)),/inspect/);
  j.recovery_required=false;assert.match(nextAction(parseJob(j)),/inspect/); // admission-only service can observe an older running record
});
test('history and event responses must belong to the selected identities',()=>{
  assert.throws(()=>parseList(list([job(),job()])));assert.throws(()=>parseList({...list([job()]),next_cursor:'job-'+'b'.repeat(32)}));
  assert.throws(()=>parseDetail(detail(), 'job-'+'b'.repeat(32)));
  const d=detail(job('review_required'));d.events.at(-1).event='claimed';assert.throws(()=>parseDetail(d,id));
});
test('only native reports with matching agent/workflow can become sources',()=>{
  const r={id:'research-example',workflow:'research',agent:'agent1',native_view:{view_schema_version:1}};
  assert.deepEqual(eligibleRuns([r,{...r,id:'../bad'},{...r,native_view:null},{...r,agent:'agent4'},{...r,workflow:'upload'}]),[r]);
});
test('server text and credentials cannot escape through error messages',async()=>{
  for(const data of [{error:{code:'unknown',message:secret}},{detail:secret},[secret]]){
    const error=await responseError(json(data,503));assert(!error.message.includes(secret));assert.equal(error.code,'unsupported_response');
  }
  const error=await responseError(json({error:{code:'job_access_required',message:secret}},403));assert.equal(error.code,'job_access_required');assert(!error.message.includes(secret));
});
test('read-only server never sends credentials or job mutations',async()=>{
  const calls=[];const client=new JobClient(async(path,init)=>{calls.push({path,init});return json(caps(false));});
  await client.discover();await client.connect(secret);assert.equal(await client.submit(request),null);
  assert(calls.every(c=>c.path==='/api/execution'&&!c.init.headers.Authorization));assert(!JSON.stringify(client.getSnapshot()).includes(secret));
});
test('token stays out of snapshots, URLs and request bodies; disconnect clears protected data',async()=>{
  const {client,calls}=await connected(()=>json({job:job(),replayed:false},202));
  assert(client.getSnapshot().connected);assert(!JSON.stringify(client.getSnapshot()).includes(secret));await client.submit(request);
  for(const {path,init} of calls){assert(!path.includes(secret));assert(!String(init.body).includes(secret));assert.equal(init.credentials,'omit');assert.equal(init.redirect,'error');assert.equal(init.cache,'no-store');}
  assert(calls.find(c=>c.init.method==='POST').init.headers.Authorization==='Bearer '+secret);
  client.disconnect();assert(!client.getSnapshot().connected);assert.deepEqual(client.getSnapshot().jobs,[]);assert.equal(client.getSnapshot().detail,null);
});
test('double-clicks cannot dispatch a second in-flight submission',async()=>{
  const wait=defer();let count=0;const {client}=await connected(()=>{count++;return wait.promise;});
  const first=client.submit(request);assert.equal(await client.submit(request),null);assert.equal(count,1);
  wait.resolve(json({job:job(),replayed:false},202));assert.equal((await first).id,id);assert.equal(client.getSnapshot().pending,null);
});
test('lost successful response is reconciled with the exact same request and key',async()=>{
  let count=0;const sent=[];const {client}=await connected((path,init)=>{sent.push(init);if(++count===1)throw new Error('network failed '+secret);return json({job:job(),replayed:true},200);});
  assert.equal(await client.submit(request),null);assert.equal(client.getSnapshot().pending.state,'unconfirmed');assert(!JSON.stringify(client.getSnapshot()).includes(secret));
  await assert.rejects(client.submit({...request,workflow:'news'}),{code:'request_pending'});
  client.editRefused();assert(client.getSnapshot().pending);assert.equal((await client.submit()).id,id);
  assert.equal(sent.length,2);assert.equal(sent[0].body,sent[1].body);assert.equal(sent[0].headers['Idempotency-Key'],sent[1].headers['Idempotency-Key']);
});
test('HTTP success with a malformed or substituted job retains the original submission',async()=>{
  for(const result of [{job:job(),replayed:true},{job:{...job(),financial_approval:true},replayed:false},{job:job('queued','news'),replayed:false}]){
    const {client}=await connected(()=>json(result,202));assert.equal(await client.submit(request),null);assert.equal(client.getSnapshot().pending.state,'unconfirmed');
  }
});
test('only explicit pre-admission refusals allow editing into a new request',async()=>{
  let refuse=true;let key=0;const {client}=await connected(()=>refuse?json({error:{code:'job_source_unavailable'}},503):json({job:job(),replayed:false},202),{key:()=> 'identity-'+(++key)});
  await client.submit(request);assert.equal(client.getSnapshot().pending.state,'refused');client.editRefused();assert.equal(client.getSnapshot().pending,null);
  refuse=false;await client.submit(request);assert.equal(key,2);
  const {client:other}=await connected(()=>json({error:{code:'job_store_unavailable'}},503));await other.submit(request);other.editRefused();assert.equal(other.getSnapshot().pending.state,'unconfirmed');
});
test('expired access clears protected history while preserving an unresolved request',async()=>{
  const {client}=await connected(()=>json({error:{code:'job_access_required'}},403));await client.submit(request);
  assert(!client.getSnapshot().connected);assert.deepEqual(client.getSnapshot().jobs,[]);assert.equal(client.getSnapshot().pending.state,'unconfirmed');
});
test('clearing access while a submission is outstanding cannot restore access on its late response',async()=>{
  const wait=defer(),{client}=await connected(()=>wait.promise);const pending=client.submit(request);client.disconnect();wait.resolve(json({job:job(),replayed:false},202));
  assert.equal(await pending,null);assert(!client.getSnapshot().connected);assert.equal(client.getSnapshot().pending.state,'unconfirmed');
  await client.connect(secret);assert(client.getSnapshot().connected);
});
test('a late connection result cannot undo an explicit disconnect',async()=>{
  const wait=defer();const client=new JobClient(async path=>path==='/api/execution'?json(caps()):wait.promise);
  await client.discover();const pending=client.connect(secret);client.disconnect();wait.resolve(json(list([job()])));await pending;assert(!client.getSnapshot().connected);assert.deepEqual(client.getSnapshot().jobs,[]);
});
test('switching jobs ignores a late response for the previous job',async()=>{
  const old=defer(),newId='job-'+'b'.repeat(32);
  const client=new JobClient(async path=>path==='/api/execution'?json(caps()):path.includes('?')?json(list()):path.endsWith(newId)?json(detail(job('queued','research','b'))):old.promise);
  await client.discover();await client.connect(secret);client.select(id);client.select(newId);await client.loadDetail();
  old.resolve(json(detail()));await new Promise(resolve=>setImmediate(resolve));assert.equal(client.getSnapshot().detail.job.id,newId);
});
test('changing history page ignores earlier page responses and uses only validated cursors',async()=>{
  const old=defer(),cursor='job-'+'b'.repeat(32);let first=true;
  const client=new JobClient(async path=>path==='/api/execution'?json(caps()):first?(first=false,json(list())):path.includes('before=')?json(list([job('queued','news','c')])):old.promise);
  await client.discover();await client.connect(secret);const pending=client.loadList();await client.loadList(cursor);old.resolve(json(list([job()])));await pending;
  assert.equal(client.getSnapshot().cursor,cursor);assert.equal(client.getSnapshot().jobs[0].request.workflow,'news');
});
test('failed status reads clear the previous confirmed report action',async()=>{
  let fail=false;const client=new JobClient(async path=>path==='/api/execution'?json(caps()):path.includes('?')?json(list()):fail?json({error:{code:'job_store_unavailable'}},503):json(detail(job('review_required'))));
  await client.discover();await client.connect(secret);client.select(id);await client.loadDetail();assert(client.getSnapshot().detail.job.resultUrl);
  fail=true;await client.loadDetail();assert.equal(client.getSnapshot().detail,null);assert(client.getSnapshot().detailError);
});
test('request deadlines preserve ambiguous submissions for reconciliation',async()=>{
  const {client}=await connected((path,init)=>new Promise((resolve,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('timeout')),{once:true})),{timeout:20});
  await client.submit(request);assert.equal(client.getSnapshot().pending.state,'unconfirmed');
});
test('queue-only jobs retain a waiting state without offering a report',()=>{
  const raw=job();raw.worker_enabled=false;const j=parseJob(raw);assert.equal(j.resultUrl,null);assert.match(nextAction(j),/enable the worker/);
});
test('capability connection failures also recheck and clear stale protected detail',async()=>{
  let fail=false;const client=new JobClient(async path=>{if(fail)throw new Error('offline');return path==='/api/execution'?json(caps()):path.includes('?')?json(list()):json(detail(job('review_required')));});
  await client.discover();await client.connect(secret);client.select(id);await client.loadDetail();assert(client.getSnapshot().detail.job.resultUrl);
  fail=true;await client.refresh();assert.equal(client.getSnapshot().detail,null);assert.equal(client.getSnapshot().capabilities,null);assert(client.getSnapshot().capabilityError);
});
test('turning off admission clears local access and blocks further submissions',async()=>{
  let enabled=true,posts=0;const client=new JobClient(async(path,init)=>{if(init.method==='POST')posts++;return path==='/api/execution'?json(caps(enabled)):json(list([job()]));});
  await client.discover();await client.connect(secret);enabled=false;await client.refresh();assert(!client.getSnapshot().connected);assert.deepEqual(client.getSnapshot().jobs,[]);await client.submit(request);assert.equal(posts,0);
});
test('a claimed refusal with an unexpected HTTP status remains unresolved',async()=>{
  const {client}=await connected(()=>json({error:{code:'job_source_unavailable'}},500));await client.submit(request);assert.equal(client.getSnapshot().pending.state,'unconfirmed');client.editRefused();assert(client.getSnapshot().pending);
});
test('changing history pages clears old rows and marks loading until the new page is confirmed',async()=>{
  const wait=defer(),cursor='job-'+'b'.repeat(32);
  const client=new JobClient(async path=>path==='/api/execution'?json(caps()):path.includes('before=')?wait.promise:json(list([job()])));
  await client.discover();await client.connect(secret);const pending=client.loadList(cursor);
  assert(client.getSnapshot().listing);assert.deepEqual(client.getSnapshot().jobs,[]);assert.equal(client.getSnapshot().checkedAt,null);
  wait.resolve(json(list([job('queued','news','c')])));await pending;
  assert(!client.getSnapshot().listing);assert.equal(client.getSnapshot().jobs[0].request.workflow,'news');
});
