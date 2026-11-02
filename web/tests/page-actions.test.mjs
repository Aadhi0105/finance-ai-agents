import assert from 'node:assert/strict';
import test from 'node:test';
import {PageActions} from '../src/execution/page-actions.ts';
const deferred=()=>{let resolve,reject;return {promise:new Promise((yes,no)=>{resolve=yes;reject=no;}),resolve:value=>resolve(value),reject:error=>reject(error)};};

test('a confirmed job opens while its originating page is still current',async()=>{
  const page=new PageActions(()=> '#/jobs'),wait=deferred();let opened=null;
  const action=page.run(()=>wait.promise,job=>opened=job);wait.resolve('saved-job');await action;assert.equal(opened,'saved-job');
});
test('a delayed admission does not pull a reader back from another page',async()=>{
  let address='#/jobs',finished=false,opened=false;const page=new PageActions(()=>address),wait=deferred();
  const action=page.run(async()=>{await wait.promise;finished=true;return 'saved-job';},()=>opened=true);
  address='#/history';page.moved();wait.resolve();await action;assert(finished);assert(!opened);
});
test('leaving and returning to the same address invalidates the old page action',async()=>{
  const page=new PageActions(()=> '#/jobs'),wait=deferred();let opened=false;
  const action=page.run(()=>wait.promise,()=>opened=true);page.moved();page.moved();wait.resolve();await action;assert(!opened);
});
test('address changes are respected even before their navigation event arrives',async()=>{
  let address='#/jobs';const page=new PageActions(()=>address),wait=deferred();let opened=false;
  const action=page.run(()=>wait.promise,()=>opened=true);address='#/runs/source';wait.resolve();await action;assert(!opened);
});
test('a stale report-opening error cannot replace the new page with an error',async()=>{
  const page=new PageActions(()=> '#/jobs'),wait=deferred();const action=page.run(()=>wait.promise,()=>assert.fail());page.moved();wait.reject(new Error('old request failed'));await action;
});
test('errors for the current action remain visible to its caller',async()=>{
  const page=new PageActions(()=> '#/jobs');await assert.rejects(page.run(async()=>{throw new Error('unavailable');},()=>assert.fail()),/unavailable/);
});
