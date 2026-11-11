import {canonical,digest,shaText,reviewKinds,type ReviewSnapshot,type ReviewTarget} from './review-data.ts';
import {noteJSON} from './notes-data.ts';

export type VersionPin={dataset_id:string;version_id:string;contract_sha256:string;payload_sha256:string};
export type CorrectionRequest={schema_version:1;snapshot_id:string;target_id:string;target_sha256:string;replacement:VersionPin;change_sha256:string;reviewer_label:string;reason:string};
export type Correction={schema_version:1;kind:'keystone.review-correction';id:string;sequence:number;recorded_at:string;binding:ReviewSnapshot['binding'];request:CorrectionRequest;
  target_title:string;target_kind:ReviewTarget['kind'];change_count:number;request_key_sha256:string;request_sha256:string;identity_assurance:'local_operator_unverified';financial_approval:false};
export type ReportLink={id:string;title:string;execution:string};
export type CorrectionLink={record:Correction;affected_reports:ReportLink[];replacement_reports:ReportLink[]};
export type ChangeCell={present:boolean;text:string;truncated:boolean;sha256:string|null};
export type Change={path:string;before:ChangeCell;after:ChangeCell};
export type Comparison={replacement:VersionPin;change_count:number;change_sha256:string;changes:Change[]};
export type CorrectionHistory={schema_version:1;kind:'keystone.review-corrections';snapshot_id:string;workspace_id:string;run_id:string;corrections_enabled:boolean;source:VersionPin;
  incoming:CorrectionLink[];outgoing:CorrectionLink[];candidates:{pin:VersionPin;created_at:string;period:string}[];comparison:Comparison|null;financial_approval:false};
const fail=():never=>{throw new Error('Correction evidence could not be matched to this report.');};
const obj=(x:unknown):Record<string,unknown>=>x!==null&&typeof x==='object'&&!Array.isArray(x)?x as Record<string,unknown>:fail();
const id=(x:unknown):string=>typeof x==='string'&&/^[a-z0-9][a-z0-9_-]{0,99}$/.test(x)?x:fail();
const hash=(x:unknown):string=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x)?x:fail();
const text=(x:unknown,n:number):string=>typeof x==='string'&&x.trim().length>0&&Array.from(x).length<=n?x:fail();
const time=(x:unknown)=>{const v=text(x,80);if(!/(?:Z|[+-]\d\d:\d\d)$/.test(v)||!Number.isFinite(Date.parse(v)))fail();return v;};
const keys=(x:Record<string,unknown>,names:string[])=>{if(Object.keys(x).sort().join(',')!==names.sort().join(','))fail();};
function pin(value:unknown):VersionPin{const p=obj(value);keys(p,['dataset_id','version_id','contract_sha256','payload_sha256']);return {dataset_id:id(p.dataset_id),version_id:id(p.version_id),contract_sha256:hash(p.contract_sha256),payload_sha256:hash(p.payload_sha256)};}

export async function parseCorrection(value:unknown,snapshot:ReviewSnapshot,exact=false):Promise<Correction>{
  const r=obj(value),q=obj(r.request),b=obj(r.binding);
  if(r.schema_version!==1||r.kind!=='keystone.review-correction'||typeof r.id!=='string'||!/^correction-[a-f0-9]{32}$/.test(r.id)
    ||!Number.isSafeInteger(r.sequence)||Number(r.sequence)<1||!Number.isSafeInteger(r.change_count)||Number(r.change_count)<1||Number(r.change_count)>200
    ||r.financial_approval!==false||r.identity_assurance!=='local_operator_unverified'||q.schema_version!==1
    ||b.workspace_id!==snapshot.binding.workspace_id||typeof q.snapshot_id!=='string'||!/^review-[a-f0-9]{64}$/.test(q.snapshot_id))fail();
  keys(q,['schema_version','snapshot_id','target_id','target_sha256','replacement','change_sha256','reviewer_label','reason']);
  keys(b,['workspace_id','run_id','run_sha256','report_view_sha256','artifact_hashes','dataset_id','version_id','contract_sha256','request_sha256']);
  id(b.run_id);id(b.dataset_id);id(b.version_id);hash(b.run_sha256);hash(b.report_view_sha256);hash(b.contract_sha256);hash(b.request_sha256);
  const artifacts=obj(b.artifact_hashes);if(!Object.keys(artifacts).length||Object.keys(artifacts).length>40)fail();for(const [k,v] of Object.entries(artifacts)){id(k);hash(v);}
  id(q.target_id);hash(q.target_sha256);hash(q.change_sha256);text(q.reviewer_label,120);text(q.reason,2000);text(r.target_title,240);time(r.recorded_at);
  const p=pin(q.replacement);
  if(p.dataset_id!==b.dataset_id||p.version_id===b.version_id||!reviewKinds.includes(r.target_kind as ReviewTarget['kind']))fail();
  hash(r.request_key_sha256);hash(r.request_sha256);if(r.request_sha256!==await digest({run_id:b.run_id,request:q}))fail();
  if(b.run_id===snapshot.binding.run_id&&canonical(b)!==canonical(snapshot.binding))fail();
  if(exact||b.run_id===snapshot.binding.run_id&&q.snapshot_id===snapshot.snapshot_id){
    const t=snapshot.targets.find(t=>t.id===q.target_id);
    if(canonical(b)!==canonical(snapshot.binding)||q.snapshot_id!==snapshot.snapshot_id||!t||t.availability!=='available'||q.target_sha256!==t.scope_sha256||r.target_title!==t.title||r.target_kind!==t.kind)fail();
  }
  return r as unknown as Correction;
}

async function parseComparison(value:unknown):Promise<Comparison>{
  const c=obj(value);pin(c.replacement);hash(c.change_sha256);
  if(!Array.isArray(c.changes)||!Number.isSafeInteger(c.change_count)||c.change_count!==c.changes.length||c.changes.length<1||c.changes.length>200)fail();
  const paths=new Set<string>();
  for(const raw of c.changes as unknown[]){const d=obj(raw),path=text(d.path,2048);if(!path.startsWith('/')||paths.has(path))fail();paths.add(path);
    for(const key of ['before','after']){const cell=obj(d[key]);keys(cell,['present','text','truncated','sha256']);
      if(typeof cell.present!=='boolean'||typeof cell.truncated!=='boolean'||typeof cell.text!=='string'||Array.from(cell.text).length>500)fail();
      if(cell.present)hash(cell.sha256);else if(cell.text!==''||cell.truncated||cell.sha256!==null)fail();
      // Hash the retained JSON text directly: parsing then stringifying would
      // reinterpret Python floats (1.0) and large integer observations.
      if(cell.present&&!cell.truncated){try{JSON.parse(cell.text as string);}catch{fail();}if(await shaText(cell.text as string)!==cell.sha256)fail();}
    }
    if(canonical(d.before)===canonical(d.after))fail();
  }
  if(await digest(c.changes)!==c.change_sha256)fail();return c as unknown as Comparison;
}

export async function parseCorrections(value:unknown,snapshot:ReviewSnapshot,replacementId?:string):Promise<CorrectionHistory>{
  const h=obj(value),source=pin(h.source),b=snapshot.binding;
  if(h.schema_version!==1||h.kind!=='keystone.review-corrections'||h.snapshot_id!==snapshot.snapshot_id||h.workspace_id!==b.workspace_id||h.run_id!==b.run_id
    ||h.financial_approval!==false||typeof h.corrections_enabled!=='boolean'||source.dataset_id!==b.dataset_id||source.version_id!==b.version_id||source.contract_sha256!==b.contract_sha256
    ||!Array.isArray(h.incoming)||!Array.isArray(h.outgoing)||h.incoming.length>1||h.outgoing.length>1||!Array.isArray(h.candidates)||h.candidates.length>200)fail();
  const reportLinks=(value:unknown)=>{if(!Array.isArray(value)||value.length>100)fail();const links=value as unknown[];const ids=new Set<string>();
    for(const raw of links){const r=obj(raw);id(r.id);text(r.title,160);if(ids.has(String(r.id))||!['completed','held','refused','unavailable','failed'].includes(String(r.execution)))fail();ids.add(String(r.id));}return value as ReportLink[];};
  const parseLink=async(raw:unknown,incoming:boolean)=>{const link=obj(raw),record=await parseCorrection(link.record,snapshot),p=record.request.replacement;
    if(incoming?canonical(p)!==canonical(source):record.binding.version_id!==b.version_id||record.binding.contract_sha256!==b.contract_sha256||record.binding.dataset_id!==b.dataset_id)fail();
    const affected=reportLinks(link.affected_reports),replacement=reportLinks(link.replacement_reports);
    if(!affected.some(r=>r.id===record.binding.run_id)||(incoming?!replacement.some(r=>r.id===b.run_id):!affected.some(r=>r.id===b.run_id)))fail();
    return {record,affected_reports:affected,replacement_reports:replacement};};
  const incoming=await Promise.all((h.incoming as unknown[]).map(x=>parseLink(x,true))),outgoing=await Promise.all((h.outgoing as unknown[]).map(x=>parseLink(x,false)));
  if(new Set([...incoming,...outgoing].map(x=>x.record.id)).size!==incoming.length+outgoing.length)fail();
  const candidates=(h.candidates as unknown[]).map(raw=>{const c=obj(raw),p=pin(c.pin);if(p.dataset_id!==source.dataset_id||p.version_id===source.version_id)fail();return {pin:p,created_at:time(c.created_at),period:text(c.period,120)};});
  if(new Set(candidates.map(c=>c.pin.version_id)).size!==candidates.length||outgoing.length&&candidates.length)fail();
  const comparison=h.comparison===null?null:await parseComparison(h.comparison);
  if(replacementId?(!comparison||comparison.replacement.version_id!==replacementId):comparison!==null)fail();
  if(comparison&&(comparison.replacement.dataset_id!==source.dataset_id||comparison.replacement.version_id===source.version_id))fail();
  return {...h,incoming,outgoing,candidates,comparison} as CorrectionHistory;
}

export async function fetchCorrections(snapshot:ReviewSnapshot,fetcher:typeof fetch,signal:AbortSignal,replacementId?:string):Promise<CorrectionHistory>{
  const path=`/api/runs/${encodeURIComponent(snapshot.binding.run_id)}/review-corrections`+(replacementId?`?replacement_version_id=${encodeURIComponent(replacementId)}`:'');
  const result=await fetcher(path,{signal,cache:'no-store',redirect:'error'});
  const value=await parseCorrections(await noteJSON(result,signal),snapshot,replacementId);signal.throwIfAborted();return value;
}
