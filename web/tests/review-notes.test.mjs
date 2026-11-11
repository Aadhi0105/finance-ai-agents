import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {digest,shaText} from '../src/review/review-data.ts';
import {parseNotebook,parseNote,reviewSectionAnchor} from '../src/review/notes-data.ts';
import {ReviewNoteClient} from '../src/review/note-client.ts';
import {PrivateClient} from '../src/onboarding/client.ts';
import {formats} from '../src/onboarding/data.ts';

const snapshots=JSON.parse(readFileSync(new URL('./fixtures/review-snapshots.json',import.meta.url),'utf8'));
const fixture=JSON.parse(readFileSync(new URL('./fixtures/review-notebook.json',import.meta.url),'utf8'));
const example=()=>({snapshot:structuredClone(snapshots['private-local-research'].snapshot),book:structuredClone(fixture)});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
async function response(snapshot,body,key){
  const note=structuredClone(fixture.notes[0]);note.binding=structuredClone(snapshot.binding);note.request=structuredClone(body);
  const target=snapshot.targets.find(t=>t.id===body.target_id);note.target_title=target.title;note.target_kind=target.kind;
  note.request_key_sha256=await shaText(key);note.request_sha256=await digest({run_id:snapshot.binding.run_id,request:body});
  return {note,replayed:false,financial_approval:false};
}

test('a captured private notebook records activity without decisions or financial approval',async()=>{
  const {snapshot,book}=example();const parsed=await parseNotebook(book,snapshot);
  assert.equal(parsed.analyst_review,'in_review');assert.equal(parsed.decision_count,0);assert.equal(parsed.financial_approval,false);
  assert.equal(parsed.notes[0].request.note_type,'question');assert.equal(snapshot.decisions_enabled,false);
});

for(const [name,edit] of [
  ['approval',b=>b.financial_approval=true],['completed review',b=>b.analyst_review='reviewed_with_limitations'],
  ['decision inference',b=>b.decision_count=1],['wrong workspace',b=>b.workspace_id='workspace-other'],
  ['wrong scope',b=>b.snapshot_id='review-'+'0'.repeat(64)],['dropped sequence',b=>b.notes[0].sequence=2],
  ['wrong input binding',b=>b.notes[0].binding.version_id='version-other'],['wrong subject',b=>b.notes[0].request.target_id='unknown'],
  ['invented authenticated attribution',b=>b.notes[0].identity_assurance='authenticated'],
  ['old-scope inheritance',b=>b.notes[0].request.snapshot_id='review-'+'0'.repeat(64)],
  ['duplicate note',b=>b.notes.push(b.notes[0])],['false permission type',b=>b.notes_enabled=1],
])test('notebook refuses '+name,async()=>{
  const {snapshot,book}=example();edit(book);await assert.rejects(parseNotebook(book,snapshot));
});

test('note text remains plain data and a changed body needs its matching fingerprint',async()=>{
  const {snapshot,book}=example();book.notes[0].request.text='<b>Literal analyst text</b>';
  await assert.rejects(parseNote(book.notes[0],snapshot));
  book.notes[0].request_sha256=await digest({run_id:snapshot.binding.run_id,request:book.notes[0].request});
  assert.equal((await parseNote(book.notes[0],snapshot)).request.text,'<b>Literal analyst text</b>');
});

test('rapid submissions use one frozen request and one key',async()=>{
  const {snapshot,book}=example(),wait=deferred(),calls=[];
  const client=new ReviewNoteClient(async(...args)=>{calls.push(args);return wait.promise;},()=> 'note-fixed-request');
  client.activate(snapshot.binding.workspace_id);const body=structuredClone(book.notes[0].request);
  const saving=client.submit(snapshot,body);body.text='Later unsaved edit';
  assert.equal(await client.submit(),null);assert.equal(calls.length,1);
  const sent=calls[0];assert.notEqual(sent[1].text,body.text);
  wait.resolve(await response(snapshot,sent[1],sent[2]));await saving;
  assert.equal(client.getSnapshot().phase,'idle');assert.equal(client.getSnapshot().lastSavedId,book.notes[0].id);
});

test('lost acknowledgement retries the identical body and original identity',async()=>{
  const {snapshot,book}=example(),calls=[];let first=true;
  const client=new ReviewNoteClient(async(...args)=>{calls.push(structuredClone(args));if(first){first=false;throw new TypeError('lost response');}return response(snapshot,args[1],args[2]);},()=> 'note-stable-key');
  client.activate(snapshot.binding.workspace_id);
  await assert.rejects(client.submit(snapshot,book.notes[0].request));assert.equal(client.getSnapshot().phase,'unconfirmed');
  await assert.rejects(client.submit(snapshot,{...book.notes[0].request,text:'New text'}));
  await client.submit();assert.equal(calls.length,2);assert.deepEqual(calls[0],calls[1]);
});

test('an uncertain note can be confirmed from saved history without another POST',async()=>{
  const {snapshot,book}=example();let saved,calls=0;
  const client=new ReviewNoteClient(async(path,body,key)=>{calls++;saved=await response(snapshot,body,key);throw new Error('reply lost');},()=> 'note-reconcile-key');
  client.activate(snapshot.binding.workspace_id);await assert.rejects(client.submit(snapshot,book.notes[0].request));
  book.notes=[saved.note];const parsed=await parseNotebook(book,snapshot);
  assert.equal((await client.reconcile(parsed)).id,saved.note.id);assert.equal(calls,1);assert.equal(client.getSnapshot().phase,'idle');
});

test('disconnect hides pending metadata and late replies cannot confirm another session',async()=>{
  const {snapshot,book}=example(),wait=deferred();
  const client=new ReviewNoteClient(()=>wait.promise,()=> 'note-disconnect-key');client.activate(snapshot.binding.workspace_id);
  const saving=client.submit(snapshot,book.notes[0].request);client.clearAccess();
  assert.equal(client.getSnapshot().runId,null);assert.equal(client.pendingRequest(snapshot.snapshot_id),null);
  client.activate('workspace-other');assert.equal(client.getSnapshot().foreignPending,true);
  wait.resolve(await response(snapshot,book.notes[0].request,'note-disconnect-key'));await assert.rejects(saving);
  assert.equal(client.getSnapshot().lastSavedId,null);await assert.rejects(client.submit());
  client.activate(snapshot.binding.workspace_id);assert.equal(client.getSnapshot().phase,'unconfirmed');
});

test('a later refusal cannot discard a previously unconfirmed note',async()=>{
  const {snapshot,book}=example();let attempt=0;
  const client=new ReviewNoteClient(async()=>{if(attempt++===0)throw new Error('lost');throw Object.assign(new Error('refused'),{refused:true});});
  client.activate(snapshot.binding.workspace_id);await assert.rejects(client.submit(snapshot,book.notes[0].request));
  await assert.rejects(client.submit());client.acknowledgeRefusal();assert.equal(client.getSnapshot().phase,'unconfirmed');
  assert(client.pendingRequest(snapshot.snapshot_id));
});

test('a definitive initial refusal allows explicit correction without pretending the note was saved',async()=>{
  const {snapshot,book}=example();
  const client=new ReviewNoteClient(async()=>{throw Object.assign(new Error('refused'),{refused:true});});client.activate(snapshot.binding.workspace_id);
  await assert.rejects(client.submit(snapshot,book.notes[0].request));assert.equal(client.getSnapshot().phase,'refused');
  client.acknowledgeRefusal();assert.equal(client.getSnapshot().phase,'idle');assert.equal(client.getSnapshot().lastSavedId,null);
});

test('a malformed acknowledgement remains unconfirmed',async()=>{
  const {snapshot,book}=example();
  const client=new ReviewNoteClient(async()=>({note:book.notes[0],replayed:false,financial_approval:true}));client.activate(snapshot.binding.workspace_id);
  await assert.rejects(client.submit(snapshot,book.notes[0].request));assert.equal(client.getSnapshot().phase,'unconfirmed');
});

test('source section navigation targets actual reader sections and leaves unknown sections unlinked',()=>{
  assert.equal(reviewSectionAnchor('events','event-sample'),'sample');
  assert.equal(reviewSectionAnchor('monitoring','monitor-corrections'),'corrections');
  assert.equal(reviewSectionAnchor('close','close-sources'),'versions');
  assert.equal(reviewSectionAnchor('news','retained-news'),'stories');
  assert.equal(reviewSectionAnchor('research','valuation'),'valuation');
  assert.equal(reviewSectionAnchor('research','invented'),null);
});

test('private note transport keeps credentials in headers and binds writes to the connected workspace',async()=>{
  const f=JSON.parse(readFileSync(new URL('./fixtures/private-onboarding.json',import.meta.url),'utf8'));
  const {snapshot,book}=example();snapshot.binding.workspace_id=f.workspace.workspace_id;
  const {snapshot_id,...scope}=snapshot;snapshot.snapshot_id='review-'+await digest(scope);
  const body={...book.notes[0].request,snapshot_id:snapshot.snapshot_id},calls=[];
  const token='a'.repeat(43),json=value=>Response.json(value);
  const transport=async(path,init)=>{
    calls.push({path,init});
    if(path==='/api/execution')return json({schema_version:2,classification:'private',local_token_required:true,live_data_enabled:false,paid_models_enabled:false,financial_approval:false,
      max_package_bytes:20_000_000,timeout_seconds_max:600,imports_enabled:true,admission_enabled:true,worker_enabled:false,supported_input_formats:formats,fresh_research_supported:true,local_workflows_supported:true});
    if(path==='/api/workspace')return json(f.workspace);
    if(path.startsWith('/api/entities'))return json(f.entities);
    if(path.startsWith('/api/datasets'))return json(f.datasets);
    if(path.endsWith('/review-notes'))return json(await response(snapshot,JSON.parse(init.body),new Headers(init.headers).get('Idempotency-Key')));
    throw new Error('Unexpected transport');
  };
  const client=new PrivateClient(transport);await client.connect(token);assert.equal(client.getSnapshot().connected,true);
  await client.reviewNotes.submit(snapshot,body);
  const write=calls.find(c=>c.init.method==='POST');assert(write);
  assert.equal(write.path,`/api/runs/${snapshot.binding.run_id}/review-notes`);
  assert.equal(new Headers(write.init.headers).get('Authorization'),'Bearer '+token);
  assert(!write.path.includes(token)&&!write.init.body.includes(token));assert.equal(write.init.redirect,'error');
  const other=structuredClone(snapshot);other.binding.workspace_id='workspace-other';
  await assert.rejects(client.reviewNotes.submit(other,body));assert.equal(calls.filter(c=>c.init.method==='POST').length,1);
});
