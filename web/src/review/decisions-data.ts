import {canonical,digest,reviewKinds,type ReviewSnapshot,type ReviewTarget} from './review-data.ts';

export type Disposition='acknowledged'|'changes_requested'|'reopened';
export type SubjectState='pending'|'not_recorded'|'acknowledged'|'changes_requested';
export type ReviewState='not_started'|'in_review'|'changes_requested'|'reviewed_with_limitations';
export type DecisionRequest={schema_version:1;snapshot_id:string;target_id:string;target_sha256:string;expected_sequence:number;
  disposition:Disposition;reviewer_label:string;reason:string;note_ids:string[];correction_ids:string[]};
export type Decision={schema_version:1;kind:'keystone.review-decision';id:string;sequence:number;snapshot_id:string;target_id:string;target_sha256:string;
  disposition:Disposition;reviewer_label:string;reason:string;recorded_at:string;identity_assurance:'local_operator_unverified';financial_approval:false};
export type DecisionRecord={schema_version:1;kind:'keystone.review-decision-record';id:string;ordinal:number;binding:ReviewSnapshot['binding'];request:DecisionRequest;
  decision:Decision;target_title:string;target_kind:ReviewTarget['kind'];request_key_sha256:string;request_sha256:string;financial_approval:false};
export type LatestEvent={decision:Decision;ordinal:number;target_title:string;target_kind:ReviewTarget['kind'];note_ids:string[];correction_ids:string[]};
export type Progress={analyst_review:ReviewState;targets:Record<string,SubjectState>;decision_count:number;financial_approval:false;evidence_gate:string};
export type DecisionJournal={schema_version:1;kind:'keystone.review-journal';protocol_version:'dispositions/1.0.0';snapshot_id:string;binding:ReviewSnapshot['binding'];
  decisions_enabled:boolean;last_sequence:number;current_count:number;earlier_scope_count:number;progress:Progress;latest_events:LatestEvent[];records:DecisionRecord[];financial_approval:false;
  page:{before:string|null;before_ordinal:number;next_cursor:string|null;limit:25;total:number}};
export type JournalState={kind:'checking'}|{kind:'unavailable'}|{kind:'ready';journal:DecisionJournal};
export type JournalCursor={id:string;ordinal:number;revision:number};
export const dispositionLabels={acknowledged:'Acknowledge item',changes_requested:'Request changes',reopened:'Reopen item'};
export const subjectLabels:Record<SubjectState,string>={pending:'Awaiting review',not_recorded:'Not recorded',acknowledged:'Acknowledged · restrictions remain',changes_requested:'Changes requested'};
export const reviewStateLabels:Record<ReviewState,string>={not_started:'Not started',in_review:'In progress',changes_requested:'Changes requested',reviewed_with_limitations:'Reviewed with limitations'};
const fail=():never=>{throw new Error('Saved decisions could not be matched to this exact report and history.');};
const obj=(v:unknown):Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:fail();
const keys=(v:Record<string,unknown>,allowed:string[])=>{if(Object.keys(v).sort().join(',')!==allowed.sort().join(','))fail();};
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v)?v:fail();
const ident=(v:unknown)=>typeof v==='string'&&/^[a-z0-9][a-z0-9_-]{0,99}$/.test(v)?v:fail();
const text=(v:unknown,max:number)=>typeof v==='string'&&v.trim().length>0&&Array.from(v).length<=max?v:fail();
const integer=(v:unknown,min=0,max=1000)=>Number.isSafeInteger(v)&&Number(v)>=min&&Number(v)<=max?Number(v):fail();
const decisionId=(v:unknown)=>typeof v==='string'&&/^decision-[a-f0-9]{32}$/.test(v)?v:fail();
const refs=(v:unknown,prefix:string,max:number)=>{if(!Array.isArray(v)||v.length>max||new Set(v).size!==v.length||v.some(x=>typeof x!=='string'||!new RegExp('^'+prefix+'-[a-f0-9]{32}$').test(x)))fail();return v as string[];};

function parseEvent(value:unknown,snapshot:ReviewSnapshot,current:boolean):Decision{
  const d=obj(value);keys(d,['schema_version','kind','id','sequence','snapshot_id','target_id','target_sha256','disposition','reviewer_label','reason','recorded_at','identity_assurance','financial_approval']);
  if(d.schema_version!==1||d.kind!=='keystone.review-decision'||d.identity_assurance!=='local_operator_unverified'||d.financial_approval!==false
    ||!['acknowledged','changes_requested','reopened'].includes(String(d.disposition))||typeof d.snapshot_id!=='string'||!/^review-[a-f0-9]{64}$/.test(d.snapshot_id))fail();
  decisionId(d.id);integer(d.sequence,1);ident(d.target_id);hash(d.target_sha256);text(d.reviewer_label,120);text(d.reason,1600);
  const time=text(d.recorded_at,80);if(!/(?:Z|[+-]\d\d:\d\d)$/.test(time)||!Number.isFinite(Date.parse(time)))fail();
  if(current){const t=snapshot.targets.find(t=>t.id===d.target_id);if(d.snapshot_id!==snapshot.snapshot_id||!t||t.availability!=='available'||t.scope_sha256!==d.target_sha256)fail();}
  else if(d.snapshot_id===snapshot.snapshot_id)fail();return d as unknown as Decision;
}

export async function parseDecisionRecord(value:unknown,snapshot:ReviewSnapshot,exact=false):Promise<DecisionRecord>{
  const r=obj(value),q=obj(r.request);
  keys(r,['schema_version','kind','id','ordinal','binding','request','decision','target_title','target_kind','request_key_sha256','request_sha256','financial_approval']);
  keys(q,['schema_version','snapshot_id','target_id','target_sha256','expected_sequence','disposition','reviewer_label','reason','note_ids','correction_ids']);
  if(r.schema_version!==1||r.kind!=='keystone.review-decision-record'||r.financial_approval!==false||canonical(r.binding)!==canonical(snapshot.binding)||q.schema_version!==1)fail();
  const current=q.snapshot_id===snapshot.snapshot_id,d=parseEvent(r.decision,snapshot,current);
  if(exact&&!current)fail();decisionId(r.id);integer(r.ordinal,1);integer(q.expected_sequence);text(r.target_title,240);
  if(r.id!==d.id||r.ordinal!==Number(q.expected_sequence)+1||!reviewKinds.includes(r.target_kind as ReviewTarget['kind']))fail();
  for(const key of ['snapshot_id','target_id','target_sha256','disposition','reviewer_label','reason'] as const)if(d[key]!==q[key])fail();
  refs(q.note_ids,'note',10);refs(q.correction_ids,'correction',5);hash(r.request_key_sha256);hash(r.request_sha256);
  if(r.request_sha256!==await digest({run_id:snapshot.binding.run_id,request:q}))fail();
  if(current){const t=snapshot.targets.find(t=>t.id===d.target_id)!;if(r.target_title!==t.title||r.target_kind!==t.kind)fail();}
  return r as unknown as DecisionRecord;
}

export async function parseJournal(value:unknown,snapshot:ReviewSnapshot,cursor?:JournalCursor):Promise<DecisionJournal>{
  const j=obj(value),p=obj(j.page),progress=obj(j.progress);
  keys(j,['schema_version','kind','protocol_version','snapshot_id','binding','decisions_enabled','last_sequence','current_count','earlier_scope_count','progress','latest_events','records','financial_approval','page']);
  keys(p,['before','before_ordinal','next_cursor','limit','total']);
  if(j.schema_version!==1||j.kind!=='keystone.review-journal'||j.protocol_version!=='dispositions/1.0.0'||j.snapshot_id!==snapshot.snapshot_id
    ||canonical(j.binding)!==canonical(snapshot.binding)||typeof j.decisions_enabled!=='boolean'||j.financial_approval!==false
    ||!Array.isArray(j.latest_events)||!Array.isArray(j.records)||j.latest_events.length>223||j.records.length>25)fail();
  const count=integer(j.last_sequence),current=integer(j.current_count),earlier=integer(j.earlier_scope_count);
  if(current+earlier!==count||p.limit!==25||p.total!==count||p.before!==(cursor?.id??null)
    ||p.before_ordinal!==(cursor?.ordinal??count+1)||cursor&&cursor.revision!==count)fail();
  const before=integer(p.before_ordinal,1,1001);
  if(before>count+1||(j.records as unknown[]).length!==Math.min(25,before-1))fail();
  const records=await Promise.all((j.records as unknown[]).map(r=>parseDecisionRecord(r,snapshot)));
  if(records.some((r,i)=>r.ordinal!==before-1-i)||new Set(records.map(r=>r.id)).size!==records.length
    ||p.next_cursor!==(before-1>25?records[records.length-1]?.id:null))fail();
  const states:Record<string,SubjectState>=Object.fromEntries(snapshot.targets.map(t=>[t.id,t.availability==='available'?'pending':'not_recorded']));
  const latest:LatestEvent[]=[],seen=new Set<string>(),ordinals=new Set<number>(),sequences=new Set<number>();
  for(const raw of j.latest_events as unknown[]){const e=obj(raw),d=parseEvent(e.decision,snapshot,true),ordinal=integer(e.ordinal,1);
    keys(e,['decision','ordinal','target_title','target_kind','note_ids','correction_ids']);
    const target=snapshot.targets.find(t=>t.id===d.target_id)!;
    if(seen.has(d.target_id)||ordinals.has(ordinal)||sequences.has(d.sequence)||ordinal>count||d.sequence>current||e.target_title!==target.title||e.target_kind!==target.kind)fail();
    seen.add(d.target_id);ordinals.add(ordinal);sequences.add(d.sequence);refs(e.note_ids,'note',10);refs(e.correction_ids,'correction',5);
    states[d.target_id]=d.disposition==='reopened'?'pending':d.disposition;
    latest.push(e as unknown as LatestEvent);
  }
  if(current===0?latest.length!==0:!latest.length||Math.max(...sequences)!==current)fail();
  const available=Object.values(states).filter(s=>s!=='not_recorded');
  const overall:ReviewState=current===0?'not_started':available.includes('changes_requested')?'changes_requested':available.length&&available.every(s=>s==='acknowledged')?'reviewed_with_limitations':'in_review';
  const expected={analyst_review:overall,targets:states,decision_count:current,financial_approval:false,evidence_gate:snapshot.evidence_gate};
  if(canonical(progress)!==canonical(expected))fail();
  for(const r of records.filter(r=>r.request.snapshot_id===snapshot.snapshot_id)){
    const e=latest.find(e=>e.decision.target_id===r.decision.target_id)??fail();
    if(r.decision.sequence>e.decision.sequence||r.ordinal>e.ordinal)fail();
    if(r.decision.sequence===e.decision.sequence&&(canonical(r.decision)!==canonical(e.decision)||r.ordinal!==e.ordinal
      ||canonical(r.request.note_ids)!==canonical(e.note_ids)||canonical(r.request.correction_ids)!==canonical(e.correction_ids)))fail();
  }
  return {...j,records,latest_events:latest} as DecisionJournal;
}

export async function decisionJSON(response:Response,signal?:AbortSignal):Promise<unknown>{
  if(!response.ok||!response.headers.get('content-type')?.includes('application/json')||Number(response.headers.get('content-length'))>4_000_000)fail();
  const reader=response.body?.getReader()??fail(),parts:Uint8Array[]=[];let size=0;
  try{for(;;){signal?.throwIfAborted();const chunk=await reader.read();if(chunk.done)break;size+=chunk.value.byteLength;if(size>4_000_000)fail();parts.push(chunk.value);}}
  finally{await reader.cancel();}
  const bytes=new Uint8Array(size);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.byteLength;}signal?.throwIfAborted();
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}

export async function fetchJournal(snapshot:ReviewSnapshot,fetcher:typeof fetch,signal:AbortSignal,cursor?:JournalCursor):Promise<DecisionJournal>{
  const path=`/api/runs/${encodeURIComponent(snapshot.binding.run_id)}/review-decisions`+(cursor?`?before=${encodeURIComponent(cursor.id)}&revision=${cursor.revision}`:'');
  const r=await fetcher(path,{signal,cache:'no-store',redirect:'error'});
  const result=await parseJournal(await decisionJSON(r,signal),snapshot,cursor);signal.throwIfAborted();return result;
}
