import {canonical,digest,type ReviewSnapshot,type ReviewTarget} from './review-data.ts';

export type NoteRequest={schema_version:1;snapshot_id:string;target_id:string;target_sha256:string;
  reviewer_label:string;note_type:'observation'|'question'|'follow_up';text:string;evidence_refs:string[]};
export type ReviewNote={schema_version:1;kind:'keystone.review-note';id:string;sequence:number;recorded_at:string;
  binding:ReviewSnapshot['binding'];request:NoteRequest;target_title:string;target_kind:ReviewTarget['kind'];
  request_key_sha256:string;request_sha256:string;identity_assurance:'local_operator_unverified';financial_approval:false};
export type Notebook={schema_version:1;kind:'keystone.review-notebook';snapshot_id:string;workspace_id:string;run_id:string;
  notes_enabled:boolean;notes:ReviewNote[];earlier_scope_notes:ReviewNote[];analyst_review:'not_started'|'in_review';decision_count:0;financial_approval:false};
const fail=():never=>{throw new Error('Saved review notes could not be matched to this report.');};
const object=(x:unknown):Record<string,unknown>=>x!==null&&typeof x==='object'&&!Array.isArray(x)?x as Record<string,unknown>:fail();
const text=(x:unknown,max:number):string=>typeof x==='string'&&x.trim().length>0&&Array.from(x).length<=max?x:fail();
const hash=(x:unknown)=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x)?x:fail();
const ident=(x:unknown)=>typeof x==='string'&&/^[a-z0-9][a-z0-9_-]{0,99}$/.test(x)?x:fail();

export async function parseNote(value:unknown,snapshot:ReviewSnapshot,current=true):Promise<ReviewNote>{
  const n=object(value),r=object(n.request);
  if(n.schema_version!==1||n.kind!=='keystone.review-note'||typeof n.id!=='string'||!/^note-[a-f0-9]{32}$/.test(n.id)
    ||!Number.isSafeInteger(n.sequence)||Number(n.sequence)<1||n.identity_assurance!=='local_operator_unverified'||n.financial_approval!==false
    ||r.schema_version!==1||typeof r.snapshot_id!=='string'||!/^review-[a-f0-9]{64}$/.test(r.snapshot_id)
    ||canonical(n.binding)!==canonical(snapshot.binding))fail();
  if(Object.keys(r).sort().join(',')!==['schema_version','snapshot_id','target_id','target_sha256','reviewer_label','note_type','text','evidence_refs'].sort().join(','))fail();
  text(n.recorded_at,80);if(!/(?:Z|[+-]\d\d:\d\d)$/.test(String(n.recorded_at))||!Number.isFinite(Date.parse(String(n.recorded_at))))fail();
  ident(r.target_id);hash(r.target_sha256);text(r.reviewer_label,120);text(r.text,2000);text(n.target_title,240);
  if(!['observation','question','follow_up'].includes(String(r.note_type))||!['source_inputs','financial_mappings','calculation_assumptions','report_section','review_issue'].includes(String(n.target_kind)))fail();
  if(!Array.isArray(r.evidence_refs)||r.evidence_refs.length>10||new Set(r.evidence_refs).size!==r.evidence_refs.length)fail();
  const evidence=r.evidence_refs as unknown[];
  evidence.forEach(ident);hash(n.request_key_sha256);hash(n.request_sha256);
  if(n.request_sha256!==await digest({run_id:snapshot.binding.run_id,request:r}))fail();
  if(current){
    const target=snapshot.targets.find(t=>t.id===r.target_id);
    if(r.snapshot_id!==snapshot.snapshot_id||!target||target.availability!=='available'||r.target_sha256!==target.scope_sha256
      ||n.target_title!==target.title||n.target_kind!==target.kind||evidence.some(e=>!target.evidence_refs.includes(String(e))))fail();
  }else if(r.snapshot_id===snapshot.snapshot_id)fail();
  return n as unknown as ReviewNote;
}

export async function parseNotebook(value:unknown,snapshot:ReviewSnapshot):Promise<Notebook>{
  const n=object(value);
  if(n.schema_version!==1||n.kind!=='keystone.review-notebook'||n.snapshot_id!==snapshot.snapshot_id||n.workspace_id!==snapshot.binding.workspace_id
    ||n.run_id!==snapshot.binding.run_id||typeof n.notes_enabled!=='boolean'||n.financial_approval!==false||n.decision_count!==0
    ||!Array.isArray(n.notes)||!Array.isArray(n.earlier_scope_notes)||n.notes.length+n.earlier_scope_notes.length>100
    ||n.analyst_review!==(n.notes.length?'in_review':'not_started'))fail();
  const notes=await Promise.all((n.notes as unknown[]).map(x=>parseNote(x,snapshot)));
  const earlier=await Promise.all((n.earlier_scope_notes as unknown[]).map(x=>parseNote(x,snapshot,false)));
  const all=[...notes,...earlier].sort((a,b)=>a.sequence-b.sequence);
  if(new Set(all.map(n=>n.id)).size!==all.length||new Set(all.map(n=>n.request_key_sha256)).size!==all.length||all.some((n,i)=>n.sequence!==i+1))fail();
  return {...n,notes,earlier_scope_notes:earlier} as Notebook;
}

export async function noteJSON(response:Response,signal?:AbortSignal):Promise<unknown>{
  if(!response.ok||!response.headers.get('content-type')?.includes('application/json')||Number(response.headers.get('content-length'))>2_000_000)fail();
  const reader=response.body?.getReader()??fail(),chunks:Uint8Array[]=[];let total=0;
  try{for(;;){signal?.throwIfAborted();const item=await reader.read();if(item.done)break;total+=item.value.byteLength;if(total>2_000_000)fail();chunks.push(item.value);}}
  finally{await reader.cancel();}
  const bytes=new Uint8Array(total);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.byteLength;}
  signal?.throwIfAborted();return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}

export async function fetchNotebook(snapshot:ReviewSnapshot,fetcher:typeof fetch,signal:AbortSignal):Promise<Notebook>{
  const response=await fetcher(`/api/runs/${encodeURIComponent(snapshot.binding.run_id)}/review-notes`,{signal,cache:'no-store',redirect:'error'});
  const result=await parseNotebook(await noteJSON(response,signal),snapshot);signal.throwIfAborted();return result;
}

/** Map retained section identities to actual reader anchors; unknowns stay unlinked. */
export function reviewSectionAnchor(workflow:string,id:string):string|null{
  const shared=['summary','performance','valuation','peers','market','consensus','external-research','evidence','observations','coverage','method'];
  if(shared.includes(id))return id;
  const maps:Record<string,Record<string,string>>={
    events:{'historical-findings':'observations','event-context':'sample','event-sample':'sample','event-review':'review'},
    news:{'retained-news':'stories','tone':'tone','news-context':'coverage','news-review':'review'},
    monitoring:{'original-cycle':'observations','effective-state':'effective',history:'history',reviews:'corrections',decisions:'corrections','monitor-context':'summary','monitor-coverage':'observations','monitor-corrections':'corrections','monitor-triage':'corrections'},
    close:{'close-results':'bridge',accounts:'accounts',forecast:'forecast','close-basis':'versions','close-diagnostics':'accounts','close-history':'accounts','close-forecast-context':'forecast','close-sources':'versions'},
  };
  return maps[workflow]?.[id]??null;
}
