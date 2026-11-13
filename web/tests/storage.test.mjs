import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {parseStorage,storageBytes,MAX_STORAGE_BYTES} from '../src/operations/storage.ts';
import {PrivateClient} from '../src/onboarding/client.ts';
import {formats} from '../src/onboarding/data.ts';

const example=JSON.parse(readFileSync(new URL('./fixtures/storage.json',import.meta.url),'utf8'));
const ops=JSON.parse(readFileSync(new URL('./fixtures/operations.json',import.meta.url),'utf8')).empty;
const clone=()=>structuredClone(example),workspace=example.workspace_id,token='a'.repeat(43);
const area=(v,key)=>v.areas.find(a=>a.key===key);

test('backend storage contract accounts for the whole root without claiming verification or backup',()=>{
 const view=parseStorage(example,workspace);assert.equal(view.state,'observed');assert.equal(view.areas.length,13);
 assert.equal(view.total_bytes,view.areas.reduce((n,a)=>n+a.bytes,0));
 assert.equal(view.reference_check,'requires_stopped_audit');assert.equal(view.automatic_deletion,false);
 assert.equal(view.document_intake_supported,false);assert.equal(view.backup_protection,'not_established_by_inventory');
});

for(const [name,edit] of [
 ['foreign workspace',v=>v.workspace_id='workspace-'+'0'.repeat(32)],['coerced schema',v=>v.schema_version=true],
 ['paths',v=>v.root='/private/source'],['financial approval',v=>v.financial_approval=true],['automatic deletion',v=>v.automatic_deletion=true],
 ['document intake claim',v=>v.document_intake_supported=true],['invented backup',v=>v.backup_protection='verified'],
 ['extra category',v=>v.areas.push(v.areas[0])],['missing category',v=>v.areas.pop()],['reordered areas',v=>v.areas.reverse()],
 ['invented size',v=>v.total_bytes++],['invented count',v=>v.total_files++],['unsafe integer',v=>v.total_bytes=Number.MAX_SAFE_INTEGER+1],
 ['negative size',v=>v.areas[0].bytes=-1],['null count disguised as zero',v=>v.areas[0].files=null],
 ['false healthy unreadable',v=>{v.areas[0].state='unavailable';v.areas[0].files=null;v.areas[0].bytes=null;v.total_files=null;v.total_bytes=null;}],
 ['unrecognised files called checked',v=>{area(v,'unrecognised').files=1;v.total_files++;}],
 ['false healthy low disk',v=>v.disk_free_bytes=1],['invalid disk',v=>v.disk_free_bytes=v.disk_total_bytes+1],
 ['missing disk half',v=>v.disk_free_bytes=null],['bad time',v=>v.observed_at='yesterday'],
 ['area raw contents',v=>v.areas[0].contents='secret'],
])test('reject storage response: '+name,()=>{const v=clone();edit(v);assert.throws(()=>parseStorage(v,workspace));});

test('unknown storage remains unknown while independent counts survive',()=>{
 const v=clone();v.state='unavailable';area(v,'inputs').state='unavailable';area(v,'inputs').files=null;area(v,'inputs').bytes=null;v.total_files=null;v.total_bytes=null;
 assert.equal(parseStorage(v,workspace).total_bytes,null);assert.equal(parseStorage(v,workspace).areas[0].files,1);
});
test('unrecognised empty directories and files require inspection',()=>{
 const v=clone();v.state='attention';area(v,'unrecognised').state='attention';assert.equal(parseStorage(v,workspace).state,'attention');
 area(v,'unrecognised').files=1;v.total_files++;assert.equal(parseStorage(v,workspace).state,'attention');
});
test('formatting distinguishes zero, unavailable, bytes and decimal capacity units',()=>{
 assert.equal(storageBytes(0),'0 bytes');assert.equal(storageBytes(null),'Unavailable');assert.equal(storageBytes(1200),'1.2 KB');assert.equal(storageBytes(1000000),'1.0 MB');assert.equal(storageBytes(1000000000),'1.00 GB');
});

function clientWith(storageResponse){
 const calls=[];const current={...ops,workspace_id:workspace};
 const client=new PrivateClient(async(path,init={})=>{calls.push({path,init});
  if(path==='/api/execution')return Response.json({schema_version:2,classification:'private',local_token_required:true,imports_enabled:true,admission_enabled:true,worker_enabled:false,live_data_enabled:false,paid_models_enabled:false,financial_approval:false,max_package_bytes:20_000_000,timeout_seconds_max:600,supported_input_formats:formats,operations_supported:true,fresh_research_supported:true,local_workflows_supported:true});
  if(path==='/api/operations')return Response.json(current);
  if(path==='/api/storage')return storageResponse(init);
  throw new Error('Unexpected route');
 });return {client,calls};
}
test('storage uses protected bounded GET and works in operator diagnostics mode',async()=>{
 const {client,calls}=clientWith(()=>Response.json(example));await client.connect(token,true);
 assert.equal((await client.storage()).workspace_id,workspace);
 const call=calls.find(c=>c.path==='/api/storage');assert.equal(new Headers(call.init.headers).get('Authorization'),'Bearer '+token);
 assert(!call.path.includes(token));assert(!calls.some(c=>c.init.body));client.disconnect();await assert.rejects(client.storage());
});
test('storage refuses oversized transport instead of parsing unbounded content',async()=>{
 const {client}=clientWith(()=>new Response('x'.repeat(MAX_STORAGE_BYTES+1)));await client.connect(token,true);
 await assert.rejects(client.storage());client.disconnect();
});
test('disconnect discards a late storage response',async()=>{
 let resolve;const pending=new Promise(r=>resolve=r);const {client}=clientWith(()=>pending);await client.connect(token,true);
 const read=client.storage();client.disconnect();resolve(Response.json(example));await assert.rejects(read);
});
test('expired access cannot masquerade as an empty storage inventory',async()=>{
 const {client}=clientWith(()=>Response.json({error:{code:'access_required'}},{status:403}));await client.connect(token,true);
 await assert.rejects(client.storage());client.disconnect();
});
