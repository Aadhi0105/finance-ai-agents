import {InputFailure} from '../onboarding/data.ts';
export const MAX_OPERATIONS_BYTES=1_500_000;
export const jobStates=['queued','running','completed','review_required','source_changed','failed','outcome_unknown','delivery_failed'] as const;
export const importStates=['reserved','receiving','validating','accepted','rejected','interrupted','delivery_failed'] as const;
export type JobState=typeof jobStates[number];
export type Level='ok'|'attention'|'unavailable'|'disabled';
export const components=['jobs','inputs','reports','worker','storage'] as const;
export const checkCopy={
  job_records_checked:['Saved jobs are readable','Admission, execution and latest-event records were checked. Historical failures appear below.'],
  job_records_unavailable:['Some job records cannot be checked','Preserve the workspace. Inspect the affected job ledger before submitting work that could repeat a calculation.'],
  recovery_inspection_required:['Saved work needs inspection','Open the held job. A calculation may already be committed; use the existing operator recovery procedure before creating another request.'],
  input_database_readable:['Input database is readable','SQLite and import receipt checks passed. This does not validate every retained source or review record.'],
  input_database_unavailable:['Input records need inspection','Preserve the input ledger and original packages. Inspect receipts and the local troubleshooting guide before retrying.'],
  report_sources_checked:['Registered reports were checked','Registered file inventory and current source permissions were rechecked. Financial approval remains separate.'],
  report_sources_held:['Some report sources are held','Recheck current source permission, validation and saved job evidence. A restriction must be reviewed through its existing operator procedure.'],
  report_inventory_unavailable:['Report inventory is unavailable','Preserve the registered files. Check their inventory and use verified recovery procedures; do not regenerate missing evidence as a substitute.'],
  worker_process_running:['Worker process is available','The server-owned process was running when checked. This is not a heartbeat or a guarantee that a particular job is progressing.'],
  worker_not_enabled:['Worker is intentionally disabled','No known active job is waiting. Start the supported server with its worker enabled when you intend to process queued work.'],
  worker_queue_waiting:['Queued work is waiting for the worker','Use the supported launcher or restart this server with its worker enabled. Preserve the original request; a new submission does not start this worker.'],
  worker_process_stopped:['Requested worker is stopped','Inspect saved job outcomes before restarting. An interrupted calculation may need recovery, rather than another processing request.'],
  storage_observed:['Local storage was observed','Database sizes and the measured storage for inputs, reports and their reservations appear below. Unreadable reservations stay unavailable. Backup protection is a separate check.'],
  storage_near_limit:['Free disk space is low','Preserve evidence and review storage before importing or running more work. This advisory threshold does not change admission limits.'],
  storage_unavailable:['Storage could not be measured safely','A private path, permission or bounded scan could not be checked. Preserve files and ask the local operator to inspect storage.'],
} as const;
export type CheckCode=keyof typeof checkCopy;
export const componentLabels={jobs:'Job records',inputs:'Input records',reports:'Saved reports',worker:'Local worker',storage:'Storage'};
export const capacityLabels={pending_jobs:'Active jobs',retained_jobs:'Retained jobs',pending_imports:'Unfinished imports',retained_imports:'Retained imports',datasets:'Datasets',versions:'Input versions',notes:'Review notes',corrections:'Correction links',decisions:'Review decisions',input_ledger:'Input database',job_ledger:'Job database',input_storage:'Inputs, staging & reservations',analysis_evidence:'Analysis evidence & reservations'};
export const capacityKeys=Object.keys(capacityLabels) as (keyof typeof capacityLabels)[];
export type Capacity={key:typeof capacityKeys[number];used:number|null;limit:number;state:Exclude<Level,'disabled'>};
export type OperationJob={id:string;workflow:'research'|'monitoring'|'events'|'news'|'close';status:JobState;created_at:string;started_at:string|null;finished_at:string|null;stage:string;timeout_seconds:number;restoration_hold:boolean;recovery_required:boolean};
export type OperationImport={id:string;state:typeof importStates[number];created_at:string};
export type Operations={schema_version:1;kind:'keystone.operations';workspace_id:string;observed_at:string;state:Exclude<Level,'disabled'>;
  checks:{key:typeof components[number];state:Level;code:CheckCode}[];capacities:Capacity[];jobs:OperationJob[];job_total:number|null;unreadable_jobs:number|null;job_counts:Record<JobState,number>|null;
  imports:OperationImport[];import_total:number|null;unreadable_imports:number|null;report_total:number|null;held_reports:string[];disk_free_bytes:number|null;disk_total_bytes:number|null;
  live_data_enabled:false;paid_models_enabled:false;financial_approval:false;production_release_approved:false};
const fail=():never=>{throw new InputFailure('unsupported_response');};
const obj=(v:unknown):Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:fail();
const exact=(v:Record<string,unknown>,keys:string[])=>{if(Object.keys(v).sort().join(',')!==keys.sort().join(','))fail();};
const num=(v:unknown,max=Number.MAX_SAFE_INTEGER)=>Number.isSafeInteger(v)&&Number(v)>=0&&Number(v)<=max?Number(v):fail();
const nullable=(v:unknown,max=Number.MAX_SAFE_INTEGER)=>v===null?null:num(v,max);
const list=(v:unknown,max:number)=>Array.isArray(v)&&v.length<=max?v:fail();
const id=(v:unknown,prefix?:string)=>typeof v==='string'&&(prefix?new RegExp('^'+prefix+'-[a-f0-9]{32}$'):/^[a-z0-9][a-z0-9_-]{0,79}$/).test(v)?v:fail();
const time=(v:unknown)=>typeof v==='string'&&v.length<=80&&/(?:Z|[+-]\d\d:\d\d)$/.test(v)&&Number.isFinite(Date.parse(v))?v:fail();
const bool=(v:unknown)=>typeof v==='boolean'?v:fail();
const codes:Record<typeof components[number],CheckCode[]>={jobs:['job_records_checked','job_records_unavailable','recovery_inspection_required'],inputs:['input_database_readable','input_database_unavailable'],reports:['report_sources_checked','report_sources_held','report_inventory_unavailable'],worker:['worker_process_running','worker_not_enabled','worker_queue_waiting','worker_process_stopped'],storage:['storage_observed','storage_near_limit','storage_unavailable']};
const levels:Record<CheckCode,Level>={job_records_checked:'ok',job_records_unavailable:'unavailable',recovery_inspection_required:'attention',input_database_readable:'ok',input_database_unavailable:'unavailable',report_sources_checked:'ok',report_sources_held:'attention',report_inventory_unavailable:'unavailable',worker_process_running:'ok',worker_not_enabled:'disabled',worker_queue_waiting:'attention',worker_process_stopped:'attention',storage_observed:'ok',storage_near_limit:'attention',storage_unavailable:'unavailable'};

export function parseOperations(value:unknown,expectedWorkspace?:string):Operations{
  const r=obj(value);exact(r,['schema_version','kind','workspace_id','observed_at','state','checks','capacities','jobs','job_total','unreadable_jobs','job_counts','imports','import_total','unreadable_imports','report_total','held_reports','disk_free_bytes','disk_total_bytes','live_data_enabled','paid_models_enabled','financial_approval','production_release_approved']);
  if(r.schema_version!==1||r.kind!=='keystone.operations'||r.live_data_enabled!==false||r.paid_models_enabled!==false||r.financial_approval!==false||r.production_release_approved!==false)fail();
  id(r.workspace_id);time(r.observed_at);if(expectedWorkspace&&r.workspace_id!==expectedWorkspace)fail();
  const checks=list(r.checks,5).map((v,i)=>{const c=obj(v);exact(c,['key','state','code']);const key=components[i];if(c.key!==key||!codes[key].includes(c.code as CheckCode)||levels[c.code as CheckCode]!==c.state)fail();return c;});if(checks.length!==5)fail();
  const capacities=list(r.capacities,13).map((v,i)=>{const c=obj(v);exact(c,['key','used','limit','state']);if(c.key!==capacityKeys[i])fail();const used=nullable(c.used),limit=num(c.limit);if(!limit||c.state!==(used===null?'unavailable':used>=Math.ceil(limit*.8)?'attention':'ok'))fail();return c;});if(capacities.length!==13)fail();
  const jobs=list(r.jobs,1000).map(v=>{const j=obj(v);exact(j,['id','workflow','status','created_at','started_at','finished_at','stage','timeout_seconds','restoration_hold','recovery_required']);
    id(j.id,'job');if(!['research','monitoring','events','news','close'].includes(String(j.workflow))||!jobStates.includes(j.status as JobState))fail();
    time(j.created_at);for(const k of ['started_at','finished_at'])if(j[k]!==null)time(j[k]);const timeout=num(j.timeout_seconds,600);if(!timeout)fail();bool(j.restoration_hold);bool(j.recovery_required);
    const stages={queued:['admitted'],running:['claimed','inputs_verified','prepared'],completed:['registered','recovered'],review_required:['registered','recovered'],source_changed:['source_changed'],failed:['failed'],outcome_unknown:['interrupted'],delivery_failed:['delivery_failed']};
    if(!stages[j.status as JobState].includes(String(j.stage))||j.restoration_hold&&(j.status!=='queued'||!j.recovery_required)
      ||j.status==='queued'&&(j.started_at!==null||j.finished_at!==null)||j.status!=='queued'&&j.started_at===null
      ||['queued','running'].includes(String(j.status))!==(j.finished_at===null)||['outcome_unknown','delivery_failed'].includes(String(j.status))&&!j.recovery_required)fail();return j;});
  if(new Set(jobs.map(j=>j.id)).size!==jobs.length)fail();const total=nullable(r.job_total,1000),unknown=nullable(r.unreadable_jobs,1000);
  if(total===null){if(unknown!==null||r.job_counts!==null||jobs.length)fail();}else{const counts=obj(r.job_counts);exact(counts,[...jobStates]);if(unknown===null||jobs.length+unknown!==total)fail();for(const s of jobStates)if(num(counts[s],1000)!==jobs.filter(j=>j.status===s).length)fail();}
  const imports=list(r.imports,1000).map(v=>{const q=obj(v);exact(q,['id','state','created_at']);id(q.id,'import');time(q.created_at);if(!importStates.includes(q.state as OperationImport['state']))fail();return q;});
  if(new Set(imports.map(i=>i.id)).size!==imports.length)fail();const importTotal=nullable(r.import_total,1000),unknownImports=nullable(r.unreadable_imports,1000);
  if(importTotal===null?unknownImports!==null||imports.length:unknownImports===null||imports.length+unknownImports!==importTotal)fail();
  const cap=Object.fromEntries(capacities.map(c=>[c.key,c.used]));
  if(cap.retained_jobs!==total||cap.pending_jobs!==(total===null||unknown?null:jobs.filter(j=>['queued','running'].includes(String(j.status))).length)
    ||cap.retained_imports!==importTotal||cap.pending_imports!==(importTotal===null||unknownImports?null:imports.filter(i=>!['accepted','rejected'].includes(String(i.state))).length))fail();
  const reports=nullable(r.report_total,100),held=list(r.held_reports,100);held.forEach(v=>id(v));if(new Set(held).size!==held.length||(reports===null?held.length>0:held.length>reports))fail();
  const free=nullable(r.disk_free_bytes),disk=nullable(r.disk_total_bytes);if(free===null?disk!==null:disk===null||disk===0||free>disk)fail();
  const by=Object.fromEntries(checks.map(c=>[c.key,c.code]));
  if(by.jobs!==(total===null||unknown?'job_records_unavailable':jobs.some(j=>j.recovery_required)?'recovery_inspection_required':'job_records_checked')
    ||by.inputs!==(importTotal===null||unknownImports?'input_database_unavailable':'input_database_readable')
    ||by.reports!==(reports===null?'report_inventory_unavailable':held.length?'report_sources_held':'report_sources_checked'))fail();
  const active=jobs.some(j=>j.status==='queued'||j.status==='running');
  if(by.worker==='worker_not_enabled'&&active||by.worker==='worker_queue_waiting'&&!active)fail();
  if(by.storage!=='storage_unavailable'&&(free===null||disk===null||by.storage!==(free<Math.max(100_000_000,Math.floor(disk/20))?'storage_near_limit':'storage_observed')))fail();
  const states=[...checks,...capacities].map(c=>c.state);if(r.state!==(states.includes('unavailable')?'unavailable':states.includes('attention')?'attention':'ok'))fail();
  return r as unknown as Operations;
}

export const stageLabels={admitted:'Waiting to be claimed',claimed:'Checking pinned inputs',inputs_verified:'Processing checked inputs',prepared:'Saved result awaiting registration',registered:'Report registered',recovered:'Saved report delivered through recovery',failed:'Attempt failed · inspect evidence',source_changed:'Source changed · processing held',interrupted:'Outcome uncertain · operator inspection',delivery_failed:'Result saved · delivery needs recovery'} as Record<string,string>;
export function nextStep(j:OperationJob):string{
  return j.restoration_hold?'Restored queued work is held. The operator must recheck and release this original request.':j.recovery_required?'Inspect this saved job before another request. A calculation may already be committed.':j.status==='queued'?'Keep this request. Check the worker status; submitting another job does not advance it.':j.status==='running'?'Follow the saved execution stage. Leaving this page does not cancel processing.':j.status==='source_changed'?'Inspect the selected input and current source permissions before choosing further processing.':j.status==='failed'?'Inspect the original failure and evidence before deciding whether a new request is appropriate.':'Open the registered report and complete its financial review.';
}
export function elapsed(j:OperationJob,observed:string):string{
  if(!j.started_at)return 'Not started';const seconds=Math.floor((Date.parse(j.finished_at??observed)-Date.parse(j.started_at))/1000);
  if(!Number.isFinite(seconds)||seconds<0)return 'Timing unavailable';return seconds<60?seconds+' seconds':seconds<3600?Math.floor(seconds/60)+' minutes':Math.floor(seconds/3600)+' hours';
}
