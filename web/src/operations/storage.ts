import {InputFailure} from '../onboarding/data.ts';

export const MAX_STORAGE_BYTES=32_000;
export const storageAreas={
 configuration:['Workspace identity','The saved workspace descriptor.'],
 input_ledger:['Input and review database','Companies, datasets, import receipts, versions, notes, corrections and decisions.'],
 inputs:['Accepted input files','Original supported packages, validation and version contracts.'],
 staging:['Import working files','Includes unfinished and rejected attempts; these are preserved for inspection.'],
 permissions:['Source permission evidence','Saved operator records and their supporting evidence.'],
 reports:['Registered reports','Report inventory, structured results, views and supporting artifacts.'],
 job_ledger:['Job database','Original requests, execution outcomes, recovery holds and event history.'],
 job_evidence:['Saved job evidence','Pinned working inputs and retained result deliveries.'],
 operation_evidence:['Execution receipts','Supervisor receipts, usage records and diagnostic evidence.'],
 accounting:['Accounting state','Canonical close databases and any present companion files.'],
 recovery:['Recovery history','Saved restoration provenance.'],
 runtime:['Local runtime files','Access key, locks and database journals. Contents are never returned here.'],
 unrecognised:['Unrecognised files','Preserve and investigate these before claiming a complete snapshot.'],
} as const;
export type StorageKey=keyof typeof storageAreas;
export type StorageView={schema_version:1;kind:'keystone.storage';workspace_id:string;observed_at:string;state:'observed'|'attention'|'unavailable';
 areas:{key:StorageKey;files:number|null;bytes:number|null;state:'observed'|'attention'|'unavailable'}[];
 total_files:number|null;total_bytes:number|null;disk_free_bytes:number|null;disk_total_bytes:number|null;
 retention_policy:'preserve_until_operator_review';automatic_deletion:false;deletion_supported:false;document_intake_supported:false;
 reference_check:'requires_stopped_audit';backup_protection:'not_established_by_inventory';financial_approval:false;production_release_approved:false};
const fail=():never=>{throw new InputFailure('unsupported_response');};
const obj=(v:unknown):Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:fail();
const exact=(v:Record<string,unknown>,keys:string[])=>{if(Object.keys(v).sort().join(',')!==[...keys].sort().join(','))fail();};
const count=(v:unknown)=>v===null||typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
export function parseStorage(raw:unknown,workspace:string):StorageView{
 const v=obj(raw);
 exact(v,['schema_version','kind','workspace_id','observed_at','state','areas','total_files','total_bytes','disk_free_bytes','disk_total_bytes','retention_policy','automatic_deletion','deletion_supported','document_intake_supported','reference_check','backup_protection','financial_approval','production_release_approved']);
 if(v.schema_version!==1||v.kind!=='keystone.storage'||v.workspace_id!==workspace||!/^workspace-[a-f0-9]{32}$/.test(workspace)||typeof v.observed_at!=='string'||v.observed_at.length>80||!/(Z|[+-]\d\d:\d\d)$/.test(v.observed_at)||!Number.isFinite(Date.parse(v.observed_at)))fail();
 if(v.retention_policy!=='preserve_until_operator_review'||v.reference_check!=='requires_stopped_audit'||v.backup_protection!=='not_established_by_inventory'||[v.automatic_deletion,v.deletion_supported,v.document_intake_supported,v.financial_approval,v.production_release_approved].some(x=>x!==false))fail();
 const keys=Object.keys(storageAreas);
 const rawAreas=Array.isArray(v.areas)?v.areas:fail();
 if(rawAreas.length!==keys.length)fail();
 const areas=rawAreas.map((a,i)=>{const area=obj(a);exact(area,['key','files','bytes','state']);
  if(area.key!==keys[i]||!count(area.files)||!count(area.bytes)||((area.files===null)!==(area.bytes===null)))fail();
  if(area.files===null?area.state!=='unavailable':!['observed',...(area.key==='unrecognised'?['attention']:[])].includes(String(area.state)))fail();
  if(area.key==='unrecognised'&&typeof area.files==='number'&&area.files>0&&area.state!=='attention')fail();
  return area as StorageView['areas'][number];});
 for(const k of ['total_files','total_bytes','disk_free_bytes','disk_total_bytes'])if(!count(v[k]))fail();
 const unknown=areas.some(a=>a.state==='unavailable');
 if(unknown?v.total_files!==null||v.total_bytes!==null:v.total_files!==areas.reduce((n,a)=>n+a.files!,0)||v.total_bytes!==areas.reduce((n,a)=>n+a.bytes!,0))fail();
 if((v.disk_free_bytes===null)!==(v.disk_total_bytes===null)||v.disk_total_bytes===0||typeof v.disk_free_bytes==='number'&&typeof v.disk_total_bytes==='number'&&v.disk_free_bytes>v.disk_total_bytes)fail();
 const expected=unknown||v.disk_free_bytes===null?'unavailable':areas.some(a=>a.state==='attention')||Number(v.disk_free_bytes)<Math.max(100_000_000,Number(v.disk_total_bytes)/20)?'attention':'observed';
 if(v.state!==expected)fail();
 return v as unknown as StorageView;
}
export const storageBytes=(v:number|null)=>v===null?'Unavailable':v>=1e9?(v/1e9).toFixed(2)+' GB':v>=1e6?(v/1e6).toFixed(1)+' MB':v>=1e3?(v/1e3).toFixed(1)+' KB':v+' bytes';
