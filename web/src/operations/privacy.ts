import {InputFailure} from '../onboarding/data.ts';
export const MAX_PRIVACY_BYTES=16_000;
export type PrivacyState='checked'|'attention'|'unavailable';
type Counts={allowed:number;denied:number;pending:number};
export const rights=['local_retention','local_processing','local_backup','model_transfer','sharing'] as const;
type Controls={local_key:'checked'|'unavailable';workspace_files:PrivacyState;browser_credentials:'tab_memory_only';delivery:'protected_no_store';diagnostic_export:'allowlisted_no_identifiers';token_rotation:'stop_and_restart';analyst_identity:'not_authenticated';automatic_session_expiry:false;live_data_enabled:false;paid_models_enabled:false;external_sharing_enabled:false;financial_approval:false;production_release_approved:false};
export type Privacy={schema_version:1;kind:'keystone.privacy';workspace_id:string;observed_at:string;state:PrivacyState;controls:Controls;sources:{state:PrivacyState;records:number|null;held_records:number|null;versions:number|null;held_versions:number|null;rights:Record<typeof rights[number],Counts>|null}};
export type PrivacyDiagnostic={schema_version:1;kind:'keystone.privacy-diagnostic';observed_at:string;state:PrivacyState;controls:Controls;source_use:PrivacyState};
const fail=():never=>{throw new InputFailure('unsupported_response');};
const obj=(v:unknown):Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:fail();
const exact=(v:Record<string,unknown>,keys:readonly string[])=>{if(Object.keys(v).sort().join(',')!==[...keys].sort().join(','))fail();};
const level=(v:unknown):PrivacyState=>typeof v==='string'&&['checked','attention','unavailable'].includes(v)?v as PrivacyState:fail();
const count=(v:unknown,max=1000):number=>typeof v==='number'&&Number.isInteger(v)&&v>=0&&v<=max?v:fail();
function controls(raw:unknown){const v=obj(raw),fixed={browser_credentials:'tab_memory_only',delivery:'protected_no_store',diagnostic_export:'allowlisted_no_identifiers',token_rotation:'stop_and_restart',analyst_identity:'not_authenticated',automatic_session_expiry:false,live_data_enabled:false,paid_models_enabled:false,external_sharing_enabled:false,financial_approval:false,production_release_approved:false};
 exact(v,['local_key','workspace_files',...Object.keys(fixed)]);if(v.local_key!=='checked'&&v.local_key!=='unavailable')fail();level(v.workspace_files);
 for(const [key,value] of Object.entries(fixed))if(v[key]!==value)fail();return v as Controls;
}
function common(v:Record<string,unknown>,source:PrivacyState){
 if(v.schema_version!==1||typeof v.observed_at!=='string'||v.observed_at.length>80||!/(Z|[+-]\d\d:\d\d)$/.test(v.observed_at)||!Number.isFinite(Date.parse(v.observed_at)))fail();
 const c=controls(v.controls),levels=[c.local_key,c.workspace_files,source];
 if(v.state!==(levels.includes('unavailable')?'unavailable':levels.includes('attention')?'attention':'checked'))fail();
}
export function parsePrivacy(raw:unknown,workspace:string):Privacy{
 const v=obj(raw);exact(v,['schema_version','kind','workspace_id','observed_at','state','controls','sources']);
 if(v.kind!=='keystone.privacy'||v.workspace_id!==workspace||!/^workspace-[a-f0-9]{32}$/.test(workspace))fail();
 const s=obj(v.sources);exact(s,['state','records','held_records','versions','held_versions','rights']);const state=level(s.state);
 if(state==='unavailable'){if([s.records,s.held_records,s.versions,s.held_versions,s.rights].some(x=>x!==null))fail();}
 else{
  const records=count(s.records),held=count(s.held_records),versions=count(s.versions,200),heldVersions=count(s.held_versions,200);if(held>records||heldVersions>versions)fail();
  const r=obj(s.rights);exact(r,rights);for(const name of rights){const row=obj(r[name]);exact(row,['allowed','denied','pending']);if(count(row.allowed)+count(row.denied)+count(row.pending)!==records)fail();}
  const backup=obj(r.local_backup);if(state!==((held||heldVersions||backup.denied||backup.pending)?'attention':'checked'))fail();
 }
 common(v,state);return v as unknown as Privacy;
}
export function parsePrivacyDiagnostic(raw:unknown):PrivacyDiagnostic{
 const v=obj(raw);exact(v,['schema_version','kind','observed_at','state','controls','source_use']);if(v.kind!=='keystone.privacy-diagnostic')fail();common(v,level(v.source_use));return v as unknown as PrivacyDiagnostic;
}
