import {InputFailure} from '../onboarding/data.ts';
export const MAX_RECOVERY_BYTES=700_000;
export const jobGuides={
 restored_queue_held:{title:'Restored request is held',next:'Review this exact never-started request, its current source and restored workspace. An operator can explicitly release it after stopping the server and worker.',limit:'Release only removes the restore hold. A later enabled worker may execute it.'},
 queued_waiting:{title:'Request is waiting',next:'Inspect the original request and the Operations worker check. Start the supported worker only when you intend to process the eligible queue.',limit:'A second request creates separate work; it does not recover this one.'},
 work_in_progress:{title:'An attempt is in progress',next:'Follow this original job and recheck Operations. A running process does not prove calculation progress.',limit:'Clearing browser access does not stop the server or cancel the attempt.'},
 worker_interrupted:{title:'The running attempt needs inspection',next:'Stop the owning server and worker. Inspect the saved attempt before considering delivery recovery.',limit:'There is no safe assumption that the calculation failed or can be repeated.'},
 delivery_inspection:{title:'Saved delivery needs inspection',next:'After stopping the server and worker, use the private job recovery command to verify the saved result and current source bindings.',limit:'Recovery can refuse. It does not authorise another financial calculation.'},
 unknown_outcome:{title:'The attempt outcome is unknown',next:'Preserve the original job and inspect its saved proof. Delivery recovery is possible only if the required complete evidence verifies.',limit:'Keep the uncertain original; do not treat an unknown outcome as an unstarted request.'},
 source_hold:{title:'The selected source changed',next:'Inspect the version, permission evidence and exact source binding. Resolve the hold before reviewing any separate new request.',limit:'Do not edit the old admission or bypass its source checks.'},
 failed_attempt:{title:'A recorded attempt failed',next:'Inspect the original job and saved evidence. A complete supported saved proof may be eligible for delivery-only recovery.',limit:'This historical record is not a declaration that the current app is broken. No automatic retry is allowed.'},
 close_state_inspection:{title:'Inspect the accounting outcome first',next:'Check the saved close, commit proof and accounting predecessor. Recover a proven committed result, or use the separate no-commit procedure only when its checks prove no commit.',limit:'A failed process does not prove no accounting commit. Never rerun a close to repair its report.'},
} as const;
export const importGuides={
 import_in_progress:{title:'Input acceptance is pending',next:'Inspect the original import receipt and wait for its saved outcome. Reconnect to the same import identity after a lost acknowledgement.',limit:'Import acceptance is separate from financial execution.'},
 import_inspection:{title:'Interrupted input needs inspection',next:'Stop the server and worker. The recover-import command can accept a complete verified prepared input if its saved evidence passes.',limit:'It never reruns validation or a financial calculation, and incomplete preparation remains held.'},
 import_rejected:{title:'A recorded input was rejected',next:'Read the saved validation receipt. Correct the source package and deliberately inspect a new import if needed.',limit:'A historical rejection is not an automatic repair or retry instruction.'},
} as const;
type JobCode=keyof typeof jobGuides;type ImportCode=keyof typeof importGuides;
type Job={id:string;workflow:'research'|'monitoring'|'events'|'news'|'close';status:string;restoration_hold:boolean;guidance:JobCode};
type Import={id:string;state:string;guidance:ImportCode};
export type Recovery={schema_version:1;kind:'keystone.recovery-support';workspace_id:string;observed_at:string;state:'observed'|'attention'|'unavailable';
 worker:'worker_process_running'|'worker_not_enabled'|'worker_queue_waiting'|'worker_process_stopped';source_checks:'checked'|'held'|'unavailable';job_total:number|null;unreadable_jobs:number|null;import_total:number|null;unreadable_imports:number|null;jobs:Job[];imports:Import[];
 protection:{independent_backup:'not_verified_here';encryption_key_recovery:'not_verified_here';clean_machine_recovery:'not_verified_here';local_restore:'requires_separate_receipt'};
 automatic_recovery:false;automatic_retry:false;financial_approval:false;production_release_approved:false};
const fail=():never=>{throw new InputFailure('unsupported_response');};
const obj=(v:unknown):Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:fail();
const exact=(v:Record<string,unknown>,keys:readonly string[])=>{if(Object.keys(v).sort().join(',')!==[...keys].sort().join(','))fail();};
const count=(v:unknown)=>v===null||typeof v==='number'&&Number.isInteger(v)&&v>=0&&v<=1000;
function jobCode(j:Record<string,unknown>,worker:unknown){if(j.restoration_hold)return 'restored_queue_held';switch(j.status){case 'queued':return 'queued_waiting';case 'running':return worker==='worker_process_running'?'work_in_progress':'worker_interrupted';case 'delivery_failed':return 'delivery_inspection';case 'outcome_unknown':return 'unknown_outcome';case 'source_changed':return 'source_hold';case 'failed':return j.workflow==='close'?'close_state_inspection':'failed_attempt';default:return null;}}
function importCode(state:unknown){if(state==='interrupted'||state==='delivery_failed')return 'import_inspection';if(state==='rejected')return 'import_rejected';if(['reserved','receiving','validating'].includes(String(state)))return 'import_in_progress';return null;}
export function parseRecovery(raw:unknown,workspace:string):Recovery{
 const v=obj(raw);exact(v,['schema_version','kind','workspace_id','observed_at','state','worker','source_checks','job_total','unreadable_jobs','import_total','unreadable_imports','jobs','imports','protection','automatic_recovery','automatic_retry','financial_approval','production_release_approved']);
 if(v.schema_version!==1||v.kind!=='keystone.recovery-support'||v.workspace_id!==workspace||!/^workspace-[a-f0-9]{32}$/.test(workspace)||typeof v.observed_at!=='string'||v.observed_at.length>80||!/(Z|[+-]\d\d:\d\d)$/.test(v.observed_at)||!Number.isFinite(Date.parse(v.observed_at)))fail();
 if(!['worker_process_running','worker_not_enabled','worker_queue_waiting','worker_process_stopped'].includes(String(v.worker))||!['checked','held','unavailable'].includes(String(v.source_checks)))fail();
 for(const flag of ['automatic_recovery','automatic_retry','financial_approval','production_release_approved'])if(v[flag]!==false)fail();
 const protection=obj(v.protection);exact(protection,['independent_backup','encryption_key_recovery','clean_machine_recovery','local_restore']);
 for(const key of ['independent_backup','encryption_key_recovery','clean_machine_recovery'])if(protection[key]!=='not_verified_here')fail();if(protection.local_restore!=='requires_separate_receipt')fail();
 for(const [total,unreadable,raw] of [[v.job_total,v.unreadable_jobs,v.jobs],[v.import_total,v.unreadable_imports,v.imports]]){
  if(!count(total)||!count(unreadable)||(total===null)!==(unreadable===null)||!Array.isArray(raw)||raw.length>1000)fail();
  const items=raw as unknown[];if(total===null?items.length>0:(unreadable as number)>(total as number)||items.length>(total as number)-(unreadable as number))fail();
  const ids=new Set();for(const item of items){const id=obj(item).id;if(ids.has(id))fail();ids.add(id);}
 }
 for(const raw of v.jobs as unknown[]){const j=obj(raw);exact(j,['id','workflow','status','restoration_hold','guidance']);
  if(typeof j.id!=='string'||!/^job-[a-f0-9]{32}$/.test(j.id)||!['research','monitoring','events','news','close'].includes(String(j.workflow))||typeof j.restoration_hold!=='boolean'||j.restoration_hold&&j.status!=='queued'||!Object.hasOwn(jobGuides,String(j.guidance))||jobCode(j,v.worker)!==j.guidance)fail();
 }
 for(const raw of v.imports as unknown[]){const i=obj(raw);exact(i,['id','state','guidance']);if(typeof i.id!=='string'||!/^import-[a-f0-9]{32}$/.test(i.id)||!Object.hasOwn(importGuides,String(i.guidance))||importCode(i.state)!==i.guidance)fail();}
 const jobs=v.jobs as Job[],imports=v.imports as Import[];
 const unknown=v.job_total===null||v.import_total===null||!!v.unreadable_jobs||!!v.unreadable_imports||v.source_checks==='unavailable';
 const attention=jobs.some(j=>!['queued_waiting','work_in_progress'].includes(j.guidance))||imports.some(i=>i.guidance!=='import_in_progress')||v.worker==='worker_process_stopped'||v.source_checks==='held';
 if(v.state!==(unknown?'unavailable':attention?'attention':'observed'))fail();return v as unknown as Recovery;
}
