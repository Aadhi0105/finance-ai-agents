import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import test from 'node:test';
import {parseReview,fetchReview} from '../src/review/review-data.ts';

const snapshots=JSON.parse(readFileSync(new URL('./fixtures/review-snapshots.json',import.meta.url),'utf8'));
function example(name='private-local-research'){
  const {run,report}=JSON.parse(readFileSync(new URL('./fixtures/'+name+'.json',import.meta.url),'utf8'));
  return {run,report,value:structuredClone(snapshots[name])};
}
const canonical=x=>Array.isArray(x)?'['+x.map(canonical).join(',')+']':x!==null&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
const hash=x=>createHash('sha256').update(canonical(x)).digest('hex');
function rebind(value){
  for(const target of value.snapshot.targets){const {scope_sha256,...scope}=target;target.scope_sha256=hash(scope);}
  const {snapshot_id,...scope}=value.snapshot;value.snapshot.snapshot_id='review-'+hash(scope);
}

for(const name of Object.keys(snapshots))test(`review scope matches retained ${name} without claiming a recorded decision`,async()=>{
  const {run,report,value}=example(name);const snapshot=await parseReview(value,run,report);
  assert.equal(snapshot.financial_approval,false);assert.equal(snapshot.decisions_enabled,false);
  assert.equal(snapshot.targets.filter(t=>t.kind==='review_issue').length,report.review_items.length);
  assert.equal(snapshot.targets.filter(t=>t.kind==='report_section').length,report.sections.length);
});

for(const [name,edit] of [
  ['financial approval',v=>v.snapshot.financial_approval=true],
  ['authenticated reviewer',v=>v.snapshot.authenticated_reviewer=true],
  ['write activation',v=>v.snapshot.decisions_enabled=true],
  ['schema version',v=>v.snapshot.schema_version=2],
  ['policy version',v=>v.snapshot.policy_version='review/2.0.0'],
  ['different report',v=>v.snapshot.binding.run_id='another-run'],
  ['different input version',v=>v.snapshot.binding.version_id='version-different'],
  ['different contract',v=>v.snapshot.binding.contract_sha256='0'.repeat(64)],
  ['different artifact',v=>v.snapshot.binding.artifact_hashes[Object.keys(v.snapshot.binding.artifact_hashes)[0]]='0'.repeat(64)],
  ['missing artifact',v=>delete v.snapshot.binding.artifact_hashes[Object.keys(v.snapshot.binding.artifact_hashes)[0]]],
  ['invented input acceptance',v=>v.snapshot.input_acceptance='financially_approved'],
  ['cleared gate',v=>v.snapshot.evidence_gate='passed_evidence_checks'],
  ['inherited decision',v=>v.progress.analyst_review='reviewed_with_limitations'],
  ['hidden decisions',v=>v.progress.decision_count=1],
  ['invented target state',v=>v.progress.targets[v.snapshot.targets[0].id]='acknowledged'],
  ['missing review issue',v=>{const i=v.snapshot.targets.findIndex(t=>t.kind==='review_issue');v.snapshot.targets.splice(i,1);}],
  ['missing report section',v=>{const i=v.snapshot.targets.findIndex(t=>t.kind==='report_section');v.snapshot.targets.splice(i,1);}],
  ['unknown evidence',v=>v.snapshot.targets[0].evidence_refs=['unknown-evidence']],
  ['unknown section',v=>v.snapshot.targets[0].section_refs=['unknown-section']],
  ['unknown issue',v=>v.snapshot.targets[0].issue_refs=['unknown-issue']],
  ['duplicate subject',v=>v.snapshot.targets[1]=v.snapshot.targets[0]],
])test(`refuses ${name} even when content hashes are recomputed`,async()=>{
  const {run,report,value}=example();edit(value);rebind(value);
  await assert.rejects(parseReview(value,run,report));
});

test('a changed target or request cannot retain an old snapshot fingerprint',async()=>{
  for(const edit of [v=>v.snapshot.targets[0].title='Different scope',v=>v.snapshot.binding.request_sha256='0'.repeat(64)]){
    const {run,report,value}=example();edit(value);await assert.rejects(parseReview(value,run,report));
  }
});

test('review reads use the provided protected fetcher without writes or redirects',async()=>{
  const {run,report,value}=example();const signal=new AbortController().signal;
  const calls=[];const fetcher=async(url,init)=>{calls.push({url,init});return Response.json(value);};
  const result=await fetchReview(run,report,signal,fetcher);
  assert.equal(result.snapshot_id,value.snapshot.snapshot_id);assert.equal(calls.length,1);
  assert.equal(calls[0].url,`/api/runs/${run.id}/review`);
  assert.equal(calls[0].init.signal,signal);assert.equal(calls[0].init.redirect,'error');
  assert.equal(calls[0].init.cache,'no-store');assert.equal(calls[0].init.method,undefined);
});

test('failed, oversized, malformed and aborted reads cannot display a default review state',async()=>{
  const {run,report}=example();
  for(const response of [new Response('refused',{status:403}),new Response('not json'),
    new Response('{}',{headers:{'content-type':'application/json','content-length':'2000001'}}),
    new Response(' '.repeat(2_000_001),{headers:{'content-type':'application/json'}})]){
    await assert.rejects(fetchReview(run,report,new AbortController().signal,async()=>response));
  }
  const controller=new AbortController();controller.abort();
  await assert.rejects(fetchReview(run,report,controller.signal,async()=>Response.json(example().value)));
});
