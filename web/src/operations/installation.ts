import {InputFailure} from '../onboarding/data.ts';
type Source={mode:'checkout'|'staged'|'unavailable';commit:string|null;dirty:boolean|null;sha256:string|null};
export type Installation={schema_version:1;kind:'keystone.installation';workspace_id:string;observed_at:string;state:'checked'|'attention';
 running_source:Source;current_source:Source;restart_required:boolean;
 runtime:{platform:string;architecture:string;python:string;supported:boolean;dependency_mismatches:{package:string;expected:string;installed:string|null}[];lock_sha256:string};
 frontend:{state:'matched'|'stale'|'unavailable';source_sha256:string|null;built_at:string|null};
 compatibility:{state:'compatible'|'migration_required'|'unsupported'|'unavailable';versions:{inputs:number|null;jobs:number|null;catalog:number|null};expected:{inputs:1;jobs:2;catalog:3};automatic_migration:false};
 automatic_update:false;automatic_migration:false;financial_approval:false;production_release_approved:false};
export const MAX_INSTALLATION_BYTES=32_000;
const fail=():never=>{throw new InputFailure('unsupported_response');};
const obj=(v:unknown):Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:fail();
const exact=(v:Record<string,unknown>,keys:string[])=>{if(Object.keys(v).sort().join(',')!==[...keys].sort().join(','))fail();};
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const instant=(v:unknown)=>typeof v==='string'&&v.length<=80&&/(Z|[+-]\d\d:\d\d)$/.test(v)&&Number.isFinite(Date.parse(v));
function source(raw:unknown){const v=obj(raw);exact(v,['mode','commit','dirty','sha256']);
 if(!['checkout','staged','unavailable'].includes(String(v.mode))||v.commit!==null&&(typeof v.commit!=='string'||!/^[a-f0-9]{40}$/.test(v.commit))||v.dirty!==null&&typeof v.dirty!=='boolean'||v.sha256!==null&&!hash(v.sha256))fail();
 if(v.mode==='unavailable'?(v.commit!==null||v.dirty!==null||v.sha256!==null):(v.commit===null||v.dirty===null||v.sha256===null))fail();
 return v as Source;
}
export function parseInstallation(raw:unknown,workspace:string):Installation{
 const v=obj(raw);exact(v,['schema_version','kind','workspace_id','observed_at','state','running_source','current_source','restart_required','runtime','frontend','compatibility','automatic_update','automatic_migration','financial_approval','production_release_approved']);
 if(v.schema_version!==1||v.kind!=='keystone.installation'||v.workspace_id!==workspace||!/^workspace-[a-f0-9]{32}$/.test(workspace)||!instant(v.observed_at)||typeof v.restart_required!=='boolean'||[v.automatic_update,v.automatic_migration,v.financial_approval,v.production_release_approved].some(x=>x!==false))fail();
 const running=source(v.running_source),current=source(v.current_source),runtime=obj(v.runtime),frontend=obj(v.frontend),compat=obj(v.compatibility);
 exact(runtime,['platform','architecture','python','supported','dependency_mismatches','lock_sha256']);
 for(const key of ['platform','architecture','python'])if(typeof runtime[key]!=='string'||!(runtime[key] as string).length||(runtime[key] as string).length>80||!(/^[A-Za-z0-9_.+ -]+$/).test(runtime[key] as string))fail();
 if(typeof runtime.supported!=='boolean'||!hash(runtime.lock_sha256)||!Array.isArray(runtime.dependency_mismatches)||runtime.dependency_mismatches.length>100)fail();
 const mismatches=runtime.dependency_mismatches as unknown[];const names=new Set();
 for(const raw of mismatches){const m=obj(raw);exact(m,['package','expected','installed']);
  if(typeof m.package!=='string'||!/^[A-Za-z0-9_.-]{1,80}$/.test(m.package)||typeof m.expected!=='string'||!/^[A-Za-z0-9_.+!-]{1,80}$/.test(m.expected)||m.installed!==null&&(typeof m.installed!=='string'||!/^[A-Za-z0-9_.+!-]{1,80}$/.test(m.installed))||m.installed===m.expected||names.has(m.package))fail();names.add(m.package);
 }
 exact(frontend,['state','source_sha256','built_at']);if(!['matched','stale','unavailable'].includes(String(frontend.state)))fail();
 if(frontend.state==='unavailable'?frontend.source_sha256!==null||frontend.built_at!==null:!hash(frontend.source_sha256)||!instant(frontend.built_at))fail();
 exact(compat,['state','versions','expected','automatic_migration']);if(!['compatible','migration_required','unsupported','unavailable'].includes(String(compat.state))||compat.automatic_migration!==false)fail();
 const versions=obj(compat.versions),expected=obj(compat.expected);exact(versions,['inputs','jobs','catalog']);exact(expected,['inputs','jobs','catalog']);
 if(expected.inputs!==1||expected.jobs!==2||expected.catalog!==3)fail();
 for(const value of Object.values(versions))if(value!==null&&(typeof value!=='number'||!Number.isInteger(value)||value<0||value>2147483647))fail();
 if(compat.state==='compatible'&&(versions.inputs!==1||versions.jobs!==null&&versions.jobs!==2||versions.catalog!==3))fail();
 const restart=running.sha256===null||current.sha256===null||running.sha256!==current.sha256;
 const attention=restart||!runtime.supported||mismatches.length>0||frontend.state!=='matched'||compat.state!=='compatible';
 if(v.restart_required!==restart||v.state!==(attention?'attention':'checked'))fail();
 return v as unknown as Installation;
}
