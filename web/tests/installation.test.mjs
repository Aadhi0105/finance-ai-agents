import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {parseInstallation,MAX_INSTALLATION_BYTES} from '../src/operations/installation.ts';
import {PrivateClient} from '../src/onboarding/client.ts';
import {formats} from '../src/onboarding/data.ts';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/installation.json',import.meta.url),'utf8'));
const operations=JSON.parse(readFileSync(new URL('./fixtures/operations.json',import.meta.url),'utf8')).empty;
const clone=()=>structuredClone(fixture),workspace=fixture.workspace_id,token='a'.repeat(43);

test('real backend installation observation binds source, runtime, build and schema without approval',()=>{
 const v=parseInstallation(fixture,workspace);assert.equal(v.state,'checked');assert.equal(v.compatibility.versions.jobs,2);
 assert.equal(v.automatic_update,false);assert.equal(v.financial_approval,false);assert.equal(v.frontend.state,'matched');
});
for(const [name,edit] of [
 ['foreign workspace',v=>v.workspace_id='workspace-'+'0'.repeat(32)],['coerced schema',v=>v.schema_version=true],
 ['source path',v=>v.running_source.path='/private/source'],['unknown outer key',v=>v.command='run'],
 ['automatic update',v=>v.automatic_update=true],['automatic migration',v=>v.automatic_migration=true],['production approval',v=>v.production_release_approved=true],['financial approval',v=>v.financial_approval=true],
 ['unavailable source dressed as known',v=>v.current_source.mode='unavailable'],['dirty coercion',v=>v.running_source.dirty=0],['invalid commit',v=>v.running_source.commit='HEAD'],
 ['unreported changed source',v=>v.current_source.sha256='2'.repeat(64)],['invented restart',v=>v.restart_required=true],
 ['unsupported platform called checked',v=>v.runtime.supported=false],['raw runtime error',v=>v.runtime.error='/private'],['runtime path',v=>v.runtime.platform='/Users/private'],
 ['bad lock hash',v=>v.runtime.lock_sha256='latest'],['unreported missing dependency',v=>v.runtime.dependency_mismatches.push({package:'fastapi',expected:'0.162.0',installed:null})],
 ['equal mismatch',v=>{v.state='attention';v.runtime.dependency_mismatches.push({package:'fastapi',expected:'0.162.0',installed:'0.162.0'});}],
 ['stale build called checked',v=>v.frontend.state='stale'],['missing build with claimed hash',v=>v.frontend.state='unavailable'],['invalid build date',v=>v.frontend.built_at='tomorrow'],
 ['unknown format called supported',v=>v.compatibility.versions.jobs=99],['future expected format',v=>v.compatibility.expected.jobs=99],['automatic schema upgrade',v=>v.compatibility.automatic_migration=true],
 ['invalid version type',v=>v.compatibility.versions.inputs=true],['invalid observation date',v=>v.observed_at='now'],
])test('reject inconsistent installation response: '+name,()=>{const v=clone();edit(v);assert.throws(()=>parseInstallation(v,workspace));});

test('changed source, stale build and migration review remain explicit attention states',()=>{
 const v=clone();v.state='attention';v.restart_required=true;v.current_source.sha256='2'.repeat(64);v.frontend.state='stale';
 v.compatibility.state='migration_required';v.compatibility.versions.jobs=1;
 assert.equal(parseInstallation(v,workspace).restart_required,true);
});
test('unavailable source identities do not become an installed release',()=>{
 const v=clone();v.state='attention';v.restart_required=true;v.current_source={mode:'unavailable',commit:null,dirty:null,sha256:null};
 assert.equal(parseInstallation(v,workspace).current_source.mode,'unavailable');
});

function setup(handler){const calls=[];
 const client=new PrivateClient(async(path,init={})=>{calls.push({path,init});
  if(path==='/api/execution')return Response.json({schema_version:2,classification:'private',local_token_required:true,imports_enabled:true,admission_enabled:true,worker_enabled:false,live_data_enabled:false,paid_models_enabled:false,financial_approval:false,max_package_bytes:20_000_000,timeout_seconds_max:600,supported_input_formats:formats,fresh_research_supported:true,local_workflows_supported:true});
  if(path==='/api/operations')return Response.json({...operations,workspace_id:workspace});
  if(path==='/api/installation')return handler(init);
  throw new Error('Unexpected request');
 });return {client,calls};
}
test('installation observation works in diagnostics mode with token only in the header',async()=>{
 const {client,calls}=setup(()=>Response.json(fixture));await client.connect(token,true);
 assert.equal((await client.installation()).workspace_id,workspace);
 const request=calls.find(c=>c.path==='/api/installation');assert.equal(new Headers(request.init.headers).get('Authorization'),'Bearer '+token);
 assert(calls.every(c=>!c.init.body&&!c.path.includes(token)));client.disconnect();await assert.rejects(client.installation());
});
test('oversized installation responses are refused before interpretation',async()=>{
 const {client}=setup(()=>new Response('x'.repeat(MAX_INSTALLATION_BYTES+1)));await client.connect(token,true);await assert.rejects(client.installation());client.disconnect();
});
test('late response after disconnect cannot restore installation data',async()=>{
 let resolve;const pending=new Promise(r=>resolve=r);const {client}=setup(()=>pending);await client.connect(token,true);
 const response=client.installation();client.disconnect();resolve(Response.json(fixture));await assert.rejects(response);
});
test('expired access never produces a healthy installation observation',async()=>{
 const {client}=setup(()=>Response.json({error:{code:'job_access_required'}},{status:403}));await client.connect(token,true);
 await assert.rejects(client.installation());client.disconnect();
});
