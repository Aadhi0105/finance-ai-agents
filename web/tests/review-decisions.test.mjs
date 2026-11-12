import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {digest,shaText} from '../src/review/review-data.ts';
import {parseJournal,parseDecisionRecord,fetchJournal} from '../src/review/decisions-data.ts';
import {ReviewDecisionClient} from '../src/review/decision-client.ts';
import {PrivateClient} from '../src/onboarding/client.ts';
import {formats} from '../src/onboarding/data.ts';

const snapshots=JSON.parse(readFileSync(new URL('./fixtures/review-snapshots.json',import.meta.url),'utf8'));
const example=()=>structuredClone(snapshots['private-local-research'].snapshot);
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
async function fixture(actions=['acknowledged'],snapshot=example(),key='decision-fixed-key'){
  const target=snapshot.targets.find(t=>t.availability==='available'),records=[];
  for(const [i,action] of actions.entries()){
    const t=typeof action==='string'?target:action.target,disposition=typeof action==='string'?action:action.disposition;
    const request={schema_version:1,snapshot_id:snapshot.snapshot_id,target_id:t.id,target_sha256:t.scope_sha256,expected_sequence:i,
      disposition,reviewer_label:'Fictional analyst',reason:'Reviewed this item and its saved limitations.',note_ids:[],correction_ids:[]};
    const id='decision-'+(i+1).toString(16).padStart(32,'0');
    const decision={schema_version:1,kind:'keystone.review-decision',id,sequence:i+1,snapshot_id:request.snapshot_id,target_id:t.id,target_sha256:t.scope_sha256,
      disposition,reviewer_label:request.reviewer_label,reason:request.reason,recorded_at:'2026-11-12T12:00:00Z',identity_assurance:'local_operator_unverified',financial_approval:false};
    records.push({schema_version:1,kind:'keystone.review-decision-record',id,ordinal:i+1,binding:structuredClone(snapshot.binding),request,decision,
      target_title:t.title,target_kind:t.kind,request_key_sha256:await shaText(i===0?key:key+i),request_sha256:await digest({run_id:snapshot.binding.run_id,request}),financial_approval:false});
  }
  const targets=Object.fromEntries(snapshot.targets.map(t=>[t.id,t.availability==='available'?'pending':'not_recorded'])),latest=new Map();
  for(const r of records){targets[r.request.target_id]=r.decision.disposition==='reopened'?'pending':r.decision.disposition;
    latest.set(r.request.target_id,{decision:r.decision,ordinal:r.ordinal,target_title:r.target_title,target_kind:r.target_kind,note_ids:[],correction_ids:[]});}
  const available=Object.values(targets).filter(s=>s!=='not_recorded');
  const analyst_review=!records.length?'not_started':available.includes('changes_requested')?'changes_requested':available.every(s=>s==='acknowledged')?'reviewed_with_limitations':'in_review';
  const journal={schema_version:1,kind:'keystone.review-journal',protocol_version:'dispositions/1.0.0',snapshot_id:snapshot.snapshot_id,binding:structuredClone(snapshot.binding),
    decisions_enabled:true,last_sequence:records.length,current_count:records.length,earlier_scope_count:0,
    progress:{analyst_review,targets,decision_count:records.length,financial_approval:false,evidence_gate:snapshot.evidence_gate},latest_events:[...latest.values()],
    records:records.slice(-25).reverse(),financial_approval:false,page:{before:null,before_ordinal:records.length+1,next_cursor:records.length>25?records.at(-25).id:null,limit:25,total:records.length}};
  return {snapshot,records,journal,body:records[0]?.request,record:records[0],key};
}
const acknowledgement=f=>({record:f.record,replayed:false,financial_approval:false});

test('acknowledgement, changes requested and reopening retain independent financial restrictions',async()=>{
  for(const [actions,state] of [[[],'not_started'],[['acknowledged'],'in_review'],[['changes_requested'],'changes_requested'],[['changes_requested','reopened'],'in_review']]){
    const f=await fixture(actions),j=await parseJournal(f.journal,f.snapshot);assert.equal(j.progress.analyst_review,state);
    assert.equal(j.progress.financial_approval,false);assert.equal(j.progress.evidence_gate,f.snapshot.evidence_gate);
  }
  const s=example(),f=await fixture(s.targets.filter(t=>t.availability==='available').map(target=>({target,disposition:'acknowledged'})),s);
  assert.equal((await parseJournal(f.journal,s)).progress.analyst_review,'reviewed_with_limitations');assert.equal(s.decisions_enabled,false);
});

for(const [name,edit] of [
  ['approval',j=>j.financial_approval=true],['progress approval',j=>j.progress.financial_approval=true],
  ['changed gate',j=>j.progress.evidence_gate='released'],['false completion',j=>j.progress.analyst_review='reviewed_with_limitations'],
  ['wrong workspace',j=>j.binding.workspace_id='workspace-wrong'],['wrong snapshot',j=>j.snapshot_id='review-'+'0'.repeat(64)],
  ['coerced count',j=>j.last_sequence=true],['missing event',j=>j.latest_events=[]],['duplicate latest',j=>j.latest_events.push(j.latest_events[0])],
  ['missing history',j=>j.records=[]],['dropped ordinal',j=>j.records[0].ordinal=3],['invented authentication',j=>j.records[0].decision.identity_assurance='authenticated'],
  ['unknown target',j=>j.records[0].decision.target_id='invented'],['rewritten reason',j=>j.records[0].request.reason='Rewritten'],
  ['unbound attachment',j=>j.records[0].request.note_ids=['note-'+'a'.repeat(32)]],['extra capability',j=>j.approved=true],
])test('journal parsing refuses '+name,async()=>{const f=await fixture();edit(f.journal);await assert.rejects(parseJournal(f.journal,f.snapshot));});

test('pages retain the latest overall state and refuse a mixed revision or missing page record',async()=>{
  const f=await fixture(Array.from({length:30},(_,i)=>i%2?'reopened':'acknowledged'));
  const first=await parseJournal(f.journal,f.snapshot);assert.equal(first.records.length,25);
  const cursor={id:first.page.next_cursor,ordinal:6,revision:30},older=structuredClone(f.journal);
  older.page={before:cursor.id,before_ordinal:6,next_cursor:null,limit:25,total:30};older.records=f.records.slice(0,5).reverse();
  assert.equal((await parseJournal(older,f.snapshot,cursor)).records[0].ordinal,5);
  await assert.rejects(parseJournal(older,f.snapshot,{...cursor,revision:29}));older.records.pop();await assert.rejects(parseJournal(older,f.snapshot,cursor));
});

test('a changed review definition retains earlier-scope history without inheriting progress',async()=>{
  const f=await fixture(),changed=structuredClone(f.snapshot);changed.targets[0].detail='New review wording.';
  changed.snapshot_id='review-'+await digest({...changed,snapshot_id:undefined});
  const h=f.journal;h.snapshot_id=changed.snapshot_id;h.current_count=0;h.earlier_scope_count=1;h.latest_events=[];
  h.progress={analyst_review:'not_started',targets:Object.fromEntries(changed.targets.map(t=>[t.id,t.availability==='available'?'pending':'not_recorded'])),decision_count:0,financial_approval:false,evidence_gate:changed.evidence_gate};
  assert.equal((await parseJournal(h,changed)).earlier_scope_count,1);await assert.rejects(parseDecisionRecord(f.record,changed,true));
});

test('double clicks freeze one body and key; lost replies retry that same submission',async()=>{
  const f=await fixture(),wait=deferred(),calls=[];let count=0;
  const client=new ReviewDecisionClient(async(...args)=>{calls.push(structuredClone(args));if(count++===0)return wait.promise;return acknowledgement(f);},()=>f.key);
  client.activate(f.snapshot.binding.workspace_id);const body=structuredClone(f.body),saving=client.submit(f.snapshot,body);body.reason='Later draft';
  assert.equal(await client.submit(),null);assert.equal(calls.length,1);wait.reject(new Error('Lost reply'));await assert.rejects(saving);
  assert.equal(client.getSnapshot().phase,'unconfirmed');await assert.rejects(client.submit(f.snapshot,{...f.body,expected_sequence:99}));
  await client.submit();assert.deepEqual(calls[0],calls[1]);assert.equal(client.getSnapshot().lastSavedId,f.record.id);
});

test('saved history confirms without another POST, including when an older failure arrives later',async()=>{
  const f=await fixture(),wait=deferred();let count=0;
  const client=new ReviewDecisionClient(()=>{count++;return wait.promise;},()=>f.key);client.activate(f.snapshot.binding.workspace_id);
  const saving=client.submit(f.snapshot,f.body);const j=await parseJournal(f.journal,f.snapshot);
  assert.equal((await client.reconcile(j)).id,f.record.id);wait.reject(new Error('Late lost acknowledgement'));
  assert.equal((await saving).id,f.record.id);assert.equal(client.getSnapshot().phase,'idle');assert.equal(count,1);
});

test('disconnect hides pending metadata and a late response cannot confirm another workspace',async()=>{
  const f=await fixture(),wait=deferred(),client=new ReviewDecisionClient(()=>wait.promise,()=>f.key);client.activate(f.snapshot.binding.workspace_id);
  const saving=client.submit(f.snapshot,f.body);client.clearAccess();assert.equal(client.pendingRequest(f.snapshot.snapshot_id),null);
  client.activate('workspace-other');assert.equal(client.getSnapshot().foreignPending,true);wait.resolve(acknowledgement(f));await assert.rejects(saving);
  await assert.rejects(client.submit());assert.equal(client.getSnapshot().lastSavedId,null);client.activate(f.snapshot.binding.workspace_id);
  assert.equal(client.getSnapshot().phase,'unconfirmed');await client.submit();assert.equal(client.getSnapshot().phase,'idle');
});

test('initial refusals can restore a draft; an uncertain earlier outcome stays recoverable after refusal',async()=>{
  const f=await fixture();let count=0;
  const client=new ReviewDecisionClient(async()=>{if(count++===0)throw new Error('Lost');throw Object.assign(new Error('Refused'),{refused:true});},()=>f.key);
  client.activate(f.snapshot.binding.workspace_id);await assert.rejects(client.submit(f.snapshot,f.body));await assert.rejects(client.submit());client.acknowledgeRefusal();assert.equal(client.getSnapshot().phase,'unconfirmed');
  const initial=new ReviewDecisionClient(async()=>{throw Object.assign(new Error('Stale history'),{refused:true});});initial.activate(f.snapshot.binding.workspace_id);
  await assert.rejects(initial.submit(f.snapshot,f.body));assert.equal(initial.getSnapshot().phase,'refused');initial.acknowledgeRefusal();assert.equal(initial.getSnapshot().phase,'idle');
});

test('malformed and approval-promoting acknowledgements remain unconfirmed',async()=>{
  const f=await fixture();for(const edit of [r=>r.financial_approval=true,r=>r.record.request_key_sha256='0'.repeat(64),r=>r.record.request.expected_sequence=99]){
    const response=structuredClone(acknowledgement(f));edit(response);
    const client=new ReviewDecisionClient(async()=>response,()=>f.key);client.activate(f.snapshot.binding.workspace_id);
    await assert.rejects(client.submit(f.snapshot,f.body));assert.equal(client.getSnapshot().phase,'unconfirmed');
  }
});

test('journal reads are bounded, abortable and use revision-bound page URLs',async()=>{
  const f=await fixture(),controller=new AbortController();
  await assert.rejects(fetchJournal(f.snapshot,async()=>new Response('x'.repeat(4_000_001),{headers:{'Content-Type':'application/json'}}),controller.signal));
  await assert.rejects(fetchJournal(f.snapshot,async()=>new Response('<html/>',{headers:{'Content-Type':'text/html'}}),controller.signal));
  const calls=[];await fetchJournal(f.snapshot,async(...a)=>{calls.push(a);return Response.json(f.journal);},controller.signal);
  assert.equal(calls[0][1].cache,'no-store');assert.equal(calls[0][1].redirect,'error');controller.abort();
  await assert.rejects(fetchJournal(f.snapshot,async()=>Response.json(f.journal),controller.signal));
});

test('private decision transport uses connected authority and keeps credentials out of URL and body',async()=>{
  const pf=JSON.parse(readFileSync(new URL('./fixtures/private-onboarding.json',import.meta.url),'utf8')),s=example();s.binding.workspace_id=pf.workspace.workspace_id;
  const f=await fixture(['acknowledged'],s),calls=[],token='a'.repeat(43);
  const transport=async(path,init)=>{calls.push({path,init});
    if(path==='/api/execution')return Response.json({schema_version:2,classification:'private',local_token_required:true,live_data_enabled:false,paid_models_enabled:false,financial_approval:false,max_package_bytes:20_000_000,timeout_seconds_max:600,imports_enabled:true,admission_enabled:true,worker_enabled:false,supported_input_formats:formats,fresh_research_supported:true,local_workflows_supported:true});
    if(path==='/api/workspace')return Response.json(pf.workspace);if(path.startsWith('/api/entities'))return Response.json(pf.entities);if(path.startsWith('/api/datasets'))return Response.json(pf.datasets);
    if(path.endsWith('/review-decisions')){f.record.request_key_sha256=await shaText(new Headers(init.headers).get('Idempotency-Key'));return Response.json(acknowledgement(f));}throw new Error('Unexpected transport');};
  const client=new PrivateClient(transport);await client.connect(token);await client.reviewDecisions.submit(s,f.body);
  const write=calls.find(c=>c.init.method==='POST');assert.equal(new Headers(write.init.headers).get('Authorization'),'Bearer '+token);
  assert(!write.path.includes(token)&&!write.init.body.includes(token));client.disconnect();assert.equal(client.reviewDecisions.getSnapshot().lastSavedId,null);
});
