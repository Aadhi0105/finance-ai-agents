import type {Run} from '../workspace-types';
import type {NativeReport} from '../reports/report-data';

export type ReviewTarget = {
  id:string; kind:'source_inputs'|'financial_mappings'|'calculation_assumptions'|'report_section'|'review_issue';
  title:string; detail:string; availability:'available'|'not_recorded';
  section_refs:string[]; evidence_refs:string[]; issue_refs:string[]; scope_sha256:string;
};
export type ReviewSnapshot = {
  schema_version:1; kind:'keystone.review-snapshot'; policy_version:'review/1.0.0'; snapshot_id:string;
  binding:{workspace_id:string;run_id:string;run_sha256:string;report_view_sha256:string;artifact_hashes:Record<string,string>;
    dataset_id:string|null;version_id:string|null;contract_sha256:string|null;request_sha256:string|null};
  input_acceptance:'accepted_for_processing'|'retained_evidence'; execution:string; evidence_gate:string;
  financial_approval:false; authenticated_reviewer:false; decisions_enabled:false; targets:ReviewTarget[];
};
export const reviewKinds = ['source_inputs','financial_mappings','calculation_assumptions','report_section','review_issue'] as const;
export const reviewLabels:Record<ReviewTarget['kind'],string> = {
  source_inputs:'Source inputs',financial_mappings:'Figure mappings',calculation_assumptions:'Assumptions and method',
  report_section:'Report sections',review_issue:'Unresolved review requirements',
};
const fail=():never=>{throw new Error('Review overview could not be matched to this saved report.');};
const obj=(x:unknown):Record<string,unknown>=>x!==null&&typeof x==='object'&&!Array.isArray(x)?x as Record<string,unknown>:fail();
const hash=(x:unknown):string=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x)?x:fail();
const id=(x:unknown):string=>typeof x==='string'&&/^[a-z0-9][a-z0-9_-]{0,99}$/.test(x)?x:fail();
const text=(x:unknown,max:number):string=>typeof x==='string'&&x.length>0&&x.length<=max?x:fail();
function refs(x:unknown,allowed:Set<string>,limit:number):string[]{
  if(!Array.isArray(x)||x.length>limit||new Set(x).size!==x.length||x.some(v=>typeof v!=='string'||!allowed.has(v)))fail();
  return x as string[];
}
export function canonical(value:unknown):string {
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value!==null&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical((value as Record<string,unknown>)[k])).join(',')+'}';
  return JSON.stringify(value);
}
export async function digest(value:unknown):Promise<string>{return shaText(canonical(value));}
export async function shaText(value:string):Promise<string>{return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),n=>n.toString(16).padStart(2,'0')).join('');}

/** Bind the independently loaded overview to this exact native report/inventory.
 * Only the read-only 5A profile is accepted. Decisions require a later protocol.
 */
export async function parseReview(value:unknown,run:Run,report:NativeReport):Promise<ReviewSnapshot>{
  const envelope=obj(value),s=obj(envelope.snapshot),b=obj(s.binding),progress=obj(envelope.progress);
  const view=run.artifacts.find(a=>a.id===run.native_view?.artifact_id);
  if(s.schema_version!==1||s.kind!=='keystone.review-snapshot'||s.policy_version!=='review/1.0.0'
    ||s.financial_approval!==false||s.authenticated_reviewer!==false||s.decisions_enabled!==false
    ||b.run_id!==run.id||!view||b.report_view_sha256!==view.sha256||s.execution!==run.execution_status
    ||s.evidence_gate!==report.state.evidence_gate||s.input_acceptance!==(run.input_origin?'accepted_for_processing':'retained_evidence'))fail();
  id(b.workspace_id);hash(b.run_sha256);hash(b.report_view_sha256);
  for(const key of ['dataset_id','version_id','contract_sha256'] as const)if(b[key] !== (run.input_origin?.[key]??null))fail();
  if(b.request_sha256!==null)hash(b.request_sha256);
  const hashes=obj(b.artifact_hashes);
  if(Object.keys(hashes).length!==run.artifacts.length||run.artifacts.some(a=>hashes[a.id]!==a.sha256))fail();
  if(!Array.isArray(s.targets)||s.targets.length<1||s.targets.length>223)fail();
  const sections=new Set(report.sections.map(s=>s.id)),evidence=new Set(report.evidence.map(e=>e.id)),issues=new Set(report.review_items.map(i=>i.id));
  const targets=s.targets as unknown[];
  const ids=new Set<string>();
  for(const raw of targets){
    const t=obj(raw),ident=id(t.id);if(ids.has(ident))fail();ids.add(ident);
    if(!reviewKinds.includes(t.kind as ReviewTarget['kind'])||!['available','not_recorded'].includes(String(t.availability)))fail();
    text(t.title,240);text(t.detail,1600);
    refs(t.section_refs,sections,20);refs(t.evidence_refs,evidence,5000);refs(t.issue_refs,issues,200);
    const {scope_sha256,...scope}=t;if(hash(scope_sha256)!==await digest(scope))fail();
  }
  // A valid response must cover every retained section/issue, not a selected subset.
  if(targets.length!==3+sections.size+issues.size)fail();
  for(const [kind,ident] of [['source_inputs','source-inputs'],['financial_mappings','financial-mappings'],['calculation_assumptions','calculation-assumptions']]){
    if(!targets.some(raw=>{const t=obj(raw);return t.kind===kind&&t.id===ident;}))fail();
  }
  for(const section of report.sections)if(!targets.some(raw=>{const t=obj(raw);return t.kind==='report_section'&&t.id==='section-'+section.id&&JSON.stringify(t.section_refs)===JSON.stringify([section.id]);}))fail();
  for(const issue of report.review_items)if(!targets.some(raw=>{const t=obj(raw);return t.kind==='review_issue'&&t.id==='issue-'+issue.id&&JSON.stringify(t.issue_refs)===JSON.stringify([issue.id]);}))fail();
  const {snapshot_id,...scope}=s;
  if(snapshot_id!=='review-'+await digest(scope))fail();
  if(progress.analyst_review!=='not_started'||progress.decision_count!==0||progress.financial_approval!==false||progress.evidence_gate!==s.evidence_gate)fail();
  const states=obj(progress.targets);if(Object.keys(states).length!==targets.length)fail();
  for(const raw of targets){const t=obj(raw);if(states[String(t.id)]!==(t.availability==='available'?'pending':'not_recorded'))fail();}
  return s as unknown as ReviewSnapshot;
}

export async function fetchReview(run:Run,report:NativeReport,signal:AbortSignal,fetcher:typeof fetch=fetch):Promise<ReviewSnapshot>{
  id(run.id);
  const response=await fetcher(`/api/runs/${encodeURIComponent(run.id)}/review`,{signal,cache:'no-store',redirect:'error'});
  if(!response.ok||!response.headers.get('content-type')?.includes('application/json')||Number(response.headers.get('content-length'))>2_000_000)fail();
  const reader=response.body?.getReader()??fail();
  const chunks:Uint8Array[]=[];let length=0;
  try{while(true){signal.throwIfAborted();const result=await reader.read();if(result.done)break;length+=result.value.byteLength;if(length>2_000_000)fail();chunks.push(result.value);}}
  finally{await reader.cancel();}
  const bytes=new Uint8Array(length);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
  const snapshot=await parseReview(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes)),run,report);
  signal.throwIfAborted();return snapshot;
}
