import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {digest,shaText} from '../src/review/review-data.ts';
import {parseCorrection,parseCorrections,fetchCorrections} from '../src/review/corrections-data.ts';
import {ReviewCorrectionClient} from '../src/review/correction-client.ts';
import {PrivateClient} from '../src/onboarding/client.ts';
import {formats} from '../src/onboarding/data.ts';

const snapshots=JSON.parse(readFileSync(new URL('./fixtures/review-snapshots.json',import.meta.url),'utf8'));
const example=()=>structuredClone(snapshots['private-local-research'].snapshot);
const deferred=()=>{let resolve;const promise=new Promise(a=>resolve=a);return {promise,resolve};};
async function fixture(snapshot=example(),key='correction-fixed-key'){
  const target=snapshot.targets[0],b=snapshot.binding;
  const replacement={dataset_id:b.dataset_id,version_id:'version-'+'b'.repeat(32),contract_sha256:'c'.repeat(64),payload_sha256:'d'.repeat(64)};
  const cell=async text=>({present:true,text,truncated:false,sha256:await shaText(text)});
  const changes=[{path:'/payload/periods/2/observations/operating_income/value',before:await cell('"120000000"'),after:await cell('"130000000"')}];
  const comparison={replacement,change_count:1,change_sha256:await digest(changes),changes};
  const body={schema_version:1,snapshot_id:snapshot.snapshot_id,target_id:target.id,target_sha256:target.scope_sha256,replacement,
    change_sha256:comparison.change_sha256,reviewer_label:'Fictional analyst',reason:'Correct the operating-income input using the revised source.'};
  const record={schema_version:1,kind:'keystone.review-correction',id:'correction-'+'a'.repeat(32),sequence:1,recorded_at:'2026-11-11T12:00:00Z',
    binding:structuredClone(b),request:body,target_title:target.title,target_kind:target.kind,change_count:1,request_key_sha256:await shaText(key),
    request_sha256:await digest({run_id:b.run_id,request:body}),identity_assurance:'local_operator_unverified',financial_approval:false};
  const history={schema_version:1,kind:'keystone.review-corrections',snapshot_id:snapshot.snapshot_id,workspace_id:b.workspace_id,run_id:b.run_id,corrections_enabled:true,
    source:{dataset_id:b.dataset_id,version_id:b.version_id,contract_sha256:b.contract_sha256,payload_sha256:'e'.repeat(64)},incoming:[],
    outgoing:[{record,affected_reports:[{id:b.run_id,title:'Fictional original research',execution:'completed'}],replacement_reports:[]}],candidates:[],comparison:null,financial_approval:false};
  return {snapshot,body,record,history,comparison,key};
}
const acknowledgement=f=>({correction:f.record,replayed:false,financial_approval:false});

test('correction lineage binds two versions without rewriting a report or granting approval',async()=>{
  const f=await fixture(),h=await parseCorrections(f.history,f.snapshot);
  assert.equal(h.financial_approval,false);assert.equal(h.outgoing[0].record.binding.version_id,f.snapshot.binding.version_id);
  assert.notEqual(h.outgoing[0].record.request.replacement.version_id,f.snapshot.binding.version_id);
  assert.equal(h.outgoing[0].replacement_reports.length,0);
});

for(const [name,edit] of [
  ['approval',h=>h.financial_approval=true],['wrong workspace',h=>h.workspace_id='workspace-other'],
  ['wrong source version',h=>h.source.version_id='version-other'],['wrong source contract',h=>h.source.contract_sha256='0'.repeat(64)],
  ['wrong snapshot',h=>h.snapshot_id='review-'+'0'.repeat(64)],['capability coercion',h=>h.corrections_enabled=1],
  ['dropped affected report',h=>h.outgoing[0].affected_reports=[]],['duplicate lineage',h=>h.outgoing.push(h.outgoing[0])],
  ['invented authenticated identity',h=>h.outgoing[0].record.identity_assurance='authenticated'],
  ['changed explanation',h=>h.outgoing[0].record.request.reason='Tampered reason'],
  ['wrong input binding',h=>h.outgoing[0].record.binding.contract_sha256='0'.repeat(64)],
  ['unknown review target',h=>h.outgoing[0].record.request.target_id='invented'],
])test('correction delivery refuses '+name,async()=>{const f=await fixture();edit(f.history);await assert.rejects(parseCorrections(f.history,f.snapshot));});

test('the field comparison verifies values and hashes and keeps numeric JSON text exact',async()=>{
  const f=await fixture();f.history.outgoing=[];f.history.candidates=[{pin:f.comparison.replacement,created_at:'2026-11-11T12:00:00Z',period:'2025-12-31'}];f.history.comparison=f.comparison;
  for(const raw of ['1.0','9007199254740993']){
    f.comparison.changes[0].before={present:true,text:raw,truncated:false,sha256:await shaText(raw)};
    f.comparison.change_sha256=await digest(f.comparison.changes);
    const parsed=await parseCorrections(f.history,f.snapshot,f.comparison.replacement.version_id);
    assert.equal(parsed.comparison.changes[0].before.text,raw);
  }
  f.comparison.changes[0].after.text='"999999999"';await assert.rejects(parseCorrections(f.history,f.snapshot,f.comparison.replacement.version_id));
});

test('a replacement report sees its incoming source link but starts a separate review',async()=>{
  const f=await fixture(),next=structuredClone(f.snapshot),p=f.body.replacement;
  next.binding.run_id='result-'+'c'.repeat(32);next.binding.version_id=p.version_id;next.binding.contract_sha256=p.contract_sha256;
  const {snapshot_id,...scope}=next;next.snapshot_id='review-'+await digest(scope);
  f.history.source=p;f.history.run_id=next.binding.run_id;f.history.snapshot_id=next.snapshot_id;
  f.history.incoming=f.history.outgoing;f.history.outgoing=[];f.history.incoming[0].replacement_reports=[{id:next.binding.run_id,title:'Fictional revised research',execution:'completed'}];
  const h=await parseCorrections(f.history,next);assert.equal(h.incoming.length,1);assert.equal(next.decisions_enabled,false);
  f.history.incoming[0].record.request.replacement.contract_sha256='0'.repeat(64);await assert.rejects(parseCorrections(f.history,next));
});

test('double clicks retain a frozen request and a single submission identity',async()=>{
  const f=await fixture(),wait=deferred(),calls=[];
  const client=new ReviewCorrectionClient(async(...args)=>{calls.push(args);return wait.promise;},()=>f.key);client.activate(f.snapshot.binding.workspace_id);
  const body=structuredClone(f.body),saving=client.submit(f.snapshot,body);body.reason='A later draft';
  assert.equal(await client.submit(),null);assert.equal(calls.length,1);assert.equal(calls[0][1].reason,f.body.reason);
  wait.resolve(acknowledgement(f));await saving;assert.equal(client.getSnapshot().phase,'idle');
});

test('a lost correction acknowledgement retries the identical body and original key',async()=>{
  const f=await fixture(),calls=[];let count=0;
  const client=new ReviewCorrectionClient(async(...args)=>{calls.push(structuredClone(args));if(count++===0)throw new Error('Lost reply');return acknowledgement(f);},()=>f.key);
  client.activate(f.snapshot.binding.workspace_id);await assert.rejects(client.submit(f.snapshot,f.body));
  assert.equal(client.getSnapshot().phase,'unconfirmed');await assert.rejects(client.submit(f.snapshot,{...f.body,reason:'Another correction'}));
  await client.submit();assert.deepEqual(calls[0],calls[1]);assert.equal(client.getSnapshot().lastSavedId,f.record.id);
});

test('saved history confirms a correction without a second POST',async()=>{
  const f=await fixture();let count=0;
  const client=new ReviewCorrectionClient(async()=>{count++;throw new Error('Reply lost');},()=>f.key);client.activate(f.snapshot.binding.workspace_id);
  await assert.rejects(client.submit(f.snapshot,f.body));const h=await parseCorrections(f.history,f.snapshot);
  assert.equal((await client.reconcile(h)).id,f.record.id);assert.equal(count,1);assert.equal(client.getSnapshot().phase,'idle');
});

test('disconnect hides pending corrections and late replies cannot confirm another workspace',async()=>{
  const f=await fixture(),wait=deferred(),client=new ReviewCorrectionClient(()=>wait.promise,()=>f.key);client.activate(f.snapshot.binding.workspace_id);
  const saving=client.submit(f.snapshot,f.body);client.clearAccess();assert.equal(client.pendingRequest(f.snapshot.snapshot_id),null);
  client.activate('workspace-other');assert.equal(client.getSnapshot().foreignPending,true);
  wait.resolve(acknowledgement(f));await assert.rejects(saving);await assert.rejects(client.submit());assert.equal(client.getSnapshot().lastSavedId,null);
  client.activate(f.snapshot.binding.workspace_id);assert.equal(client.getSnapshot().phase,'unconfirmed');
});

test('a later refusal preserves an uncertain correction while an initial refusal can be acknowledged',async()=>{
  const f=await fixture();let count=0;
  const client=new ReviewCorrectionClient(async()=>{if(count++===0)throw new Error('Lost');throw Object.assign(new Error('Refused'),{refused:true});},()=>f.key);
  client.activate(f.snapshot.binding.workspace_id);await assert.rejects(client.submit(f.snapshot,f.body));await assert.rejects(client.submit());client.acknowledgeRefusal();assert.equal(client.getSnapshot().phase,'unconfirmed');
  const initial=new ReviewCorrectionClient(async()=>{throw Object.assign(new Error('Refused'),{refused:true});});initial.activate(f.snapshot.binding.workspace_id);
  await assert.rejects(initial.submit(f.snapshot,f.body));assert.equal(initial.getSnapshot().phase,'refused');initial.acknowledgeRefusal();assert.equal(initial.getSnapshot().phase,'idle');
});

test('malformed or approval-promoting replies remain unconfirmed',async()=>{
  const f=await fixture();const client=new ReviewCorrectionClient(async()=>({...acknowledgement(f),financial_approval:true}),()=>f.key);client.activate(f.snapshot.binding.workspace_id);
  await assert.rejects(client.submit(f.snapshot,f.body));assert.equal(client.getSnapshot().phase,'unconfirmed');
  const bad=structuredClone(f.record);bad.request.reason='Different';await assert.rejects(parseCorrection(bad,f.snapshot,true));
});

test('correction reads are bounded, abortable and matched to the selected comparison',async()=>{
  const f=await fixture(),controller=new AbortController();
  await assert.rejects(fetchCorrections(f.snapshot,async()=>Response.json(f.history),controller.signal,'version-wrong'));
  await assert.rejects(fetchCorrections(f.snapshot,async()=>new Response('x'.repeat(2_000_001),{headers:{'Content-Type':'application/json'}}),controller.signal));
  controller.abort();await assert.rejects(fetchCorrections(f.snapshot,async()=>Response.json(f.history),controller.signal));
});

test('private correction transport uses the connected authority and never places credentials in the body or URL',async()=>{
  const privateFixture=JSON.parse(readFileSync(new URL('./fixtures/private-onboarding.json',import.meta.url),'utf8'));
  const snapshot=example();snapshot.binding.workspace_id=privateFixture.workspace.workspace_id;
  const {snapshot_id,...scope}=snapshot;snapshot.snapshot_id='review-'+await digest(scope);
  const f=await fixture(snapshot),calls=[],token='a'.repeat(43);
  const transport=async(path,init)=>{calls.push({path,init});
    if(path==='/api/execution')return Response.json({schema_version:2,classification:'private',local_token_required:true,live_data_enabled:false,paid_models_enabled:false,financial_approval:false,max_package_bytes:20_000_000,timeout_seconds_max:600,imports_enabled:true,admission_enabled:true,worker_enabled:false,supported_input_formats:formats,fresh_research_supported:true,local_workflows_supported:true});
    if(path==='/api/workspace')return Response.json(privateFixture.workspace);if(path.startsWith('/api/entities'))return Response.json(privateFixture.entities);if(path.startsWith('/api/datasets'))return Response.json(privateFixture.datasets);
    if(path.endsWith('/review-corrections')){const key=new Headers(init.headers).get('Idempotency-Key');f.record.request_key_sha256=await shaText(key);return Response.json(acknowledgement(f));}throw new Error('Unexpected transport');};
  const client=new PrivateClient(transport);await client.connect(token);await client.reviewCorrections.submit(snapshot,f.body);
  const write=calls.find(c=>c.init.method==='POST');assert.equal(new Headers(write.init.headers).get('Authorization'),'Bearer '+token);assert(!write.path.includes(token)&&!write.init.body.includes(token));
  client.disconnect();assert.equal(client.reviewCorrections.getSnapshot().lastSavedId,null);
});
