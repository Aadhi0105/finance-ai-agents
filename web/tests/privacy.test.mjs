import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {parsePrivacy,parsePrivacyDiagnostic,MAX_PRIVACY_BYTES,rights} from '../src/operations/privacy.ts';
import {PrivateClient} from '../src/onboarding/client.ts';
import {formats} from '../src/onboarding/data.ts';
const load=name=>JSON.parse(readFileSync(new URL('./fixtures/'+name+'.json',import.meta.url),'utf8'));
const fixture=load('privacy'),diagnostic=load('privacy-diagnostic'),operations=load('operations').empty;
const clone=()=>structuredClone(fixture),workspace=fixture.workspace_id,token='a'.repeat(43);

test('backend privacy fixture states the local possession and source-use boundary',()=>{
 const view=parsePrivacy(fixture,workspace);assert.equal(view.state,'checked');assert.equal(view.sources.records,0);
 assert.equal(view.controls.analyst_identity,'not_authenticated');assert.equal(view.controls.automatic_session_expiry,false);
 assert.equal(parsePrivacyDiagnostic(diagnostic).kind,'keystone.privacy-diagnostic');
});
for(const [name,edit] of [
 ['foreign workspace',v=>v.workspace_id='workspace-'+'0'.repeat(32)],['coerced schema',v=>v.schema_version=true],
 ['private path',v=>v.path='/Users/private'],['key in controls',v=>v.controls.key=token],['named identity',v=>v.controls.analyst_identity='authenticated'],
 ['sharing enabled',v=>v.controls.external_sharing_enabled=true],['approval',v=>v.controls.financial_approval=true],
 ['paid call',v=>v.controls.paid_models_enabled=true],['new source',v=>v.controls.live_data_enabled=true],['expiry claim',v=>v.controls.automatic_session_expiry=true],
 ['unreported file problem',v=>v.controls.workspace_files='attention'],['unreported key problem',v=>v.controls.local_key='unavailable'],
 ['unknown rights key',v=>v.sources.rights.remote_access={allowed:0,denied:0,pending:0}],['negative count',v=>v.sources.records=-1],
 ['coerced count',v=>v.sources.versions=true],['held count exceeds records',v=>v.sources.held_records=1],['missing rights',v=>v.sources.rights=null],
 ['inconsistent rights totals',v=>v.sources.rights.sharing.denied=1],['unsupported source state',v=>v.sources.state='approved'],
 ['unknown counts called zero',v=>v.sources.state='unavailable'],['invalid date',v=>v.observed_at='now'],['too many versions',v=>v.sources.versions=201],
])test('refuse unsafe/inconsistent privacy response: '+name,()=>{const v=clone();edit(v);assert.throws(()=>parsePrivacy(v,workspace));});

test('held source records and backup restrictions remain attention states',()=>{
 const v=clone();v.state='attention';v.sources.state='attention';v.sources.records=1;v.sources.held_records=1;
 for(const key of rights)v.sources.rights[key]={allowed:0,denied:0,pending:1};
 assert.equal(parsePrivacy(v,workspace).sources.held_records,1);
});
test('source check failure keeps counts unknown',()=>{
 const v=clone();v.state='unavailable';v.sources={state:'unavailable',records:null,held_records:null,versions:null,held_versions:null,rights:null};
 assert.equal(parsePrivacy(v,workspace).sources.records,null);
});
for(const key of ['workspace_id','workspace_name','path','token','counts','log','source_text'])test('redacted download refuses extra '+key,()=>{
 assert.throws(()=>parsePrivacyDiagnostic({...diagnostic,[key]:'private'}));
});

function setup(handler){const calls=[],downloads=[];
 const client=new PrivateClient(async(path,init={})=>{calls.push({path,init});
  if(path==='/api/execution')return Response.json({schema_version:2,classification:'private',local_token_required:true,imports_enabled:true,admission_enabled:true,worker_enabled:false,live_data_enabled:false,paid_models_enabled:false,financial_approval:false,max_package_bytes:20_000_000,timeout_seconds_max:600,supported_input_formats:formats,fresh_research_supported:true,local_workflows_supported:true});
  if(path==='/api/operations')return Response.json({...operations,workspace_id:workspace});
  return handler(path,init);
 });
 client.downloadBytes=(bytes,name)=>downloads.push({bytes:JSON.parse(new TextDecoder().decode(bytes)),name});
 return {client,calls,downloads};
}
test('diagnostic navigation uses protected reads and downloads only validated allowlisted fields',async()=>{
 const {client,calls,downloads}=setup(path=>Response.json(path==='/api/privacy'?fixture:diagnostic));
 await client.connect(token,true);assert.equal((await client.privacy()).workspace_id,workspace);await client.downloadPrivacyDiagnostic();
 assert.deepEqual(downloads,[{bytes:diagnostic,name:'keystone-access-check.json'}]);
 for(const call of calls.filter(c=>c.path.startsWith('/api/privacy'))){assert.equal(new Headers(call.init.headers).get('Authorization'),'Bearer '+token);assert.equal(call.init.cache,'no-store');assert.equal(call.init.redirect,'error');assert.equal(call.init.credentials,'omit');}
 assert(calls.every(c=>!c.init.body&&!c.path.includes(token)));client.disconnect();await assert.rejects(client.privacy());await assert.rejects(client.downloadPrivacyDiagnostic());
});
test('oversized privacy reads and exports never produce a download',async()=>{
 const {client,downloads}=setup(()=>new Response('x'.repeat(MAX_PRIVACY_BYTES+1)));await client.connect(token,true);
 await assert.rejects(client.privacy());await assert.rejects(client.downloadPrivacyDiagnostic());assert.equal(downloads.length,0);client.disconnect();
});
test('a private field injected into a diagnostic prevents its download',async()=>{
 const {client,downloads}=setup(()=>Response.json({...diagnostic,workspace_id:workspace}));await client.connect(token,true);
 await assert.rejects(client.downloadPrivacyDiagnostic());assert.equal(downloads.length,0);client.disconnect();
});
test('late download response after clearing access cannot export previous-session data',async()=>{
 let resolve;const pending=new Promise(r=>resolve=r);const {client,downloads}=setup(()=>pending);await client.connect(token,true);
 const download=client.downloadPrivacyDiagnostic();client.disconnect();resolve(Response.json(diagnostic));await assert.rejects(download);assert.equal(downloads.length,0);
});
test('invalidated server key clears connected data and prevents a diagnostic download',async()=>{
 const {client,downloads}=setup(()=>Response.json({error:{code:'job_access_required'}},{status:403}));await client.connect(token,true);
 await assert.rejects(client.privacy());assert.equal(client.getSnapshot().connected,false);assert.equal(client.getSnapshot().workspaceId,null);
 await assert.rejects(client.downloadPrivacyDiagnostic());assert.equal(downloads.length,0);
});
