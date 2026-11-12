import {DecisionWorkspace} from './DecisionWorkspace';
import type {ReviewDecisionClient} from './decision-client';
import {subjectLabels,type JournalState} from './decisions-data';
import type {CorrectionHistory} from './corrections-data';
import {CorrectionWorkspace} from './CorrectionWorkspace';
import type {ReviewCorrectionClient} from './correction-client';
import {useEffect,useState,useSyncExternalStore} from 'react';
import type {NativeReport} from '../reports/report-data';
import {formatMetric,savedInstant} from '../reports/format';
import {fetchNotebook,reviewSectionAnchor,type Notebook,type NoteRequest,type ReviewNote} from './notes-data';
import {ReviewNoteClient} from './note-client';
import {reviewKinds,reviewLabels,type ReviewSnapshot} from './review-data';

type Draft={text:string;note_type:NoteRequest['note_type'];evidence_refs:string[]};
const emptyDraft=():Draft=>({text:'',note_type:'question',evidence_refs:[]});
const noteLabels={observation:'Observation',question:'Question',follow_up:'Follow-up work'};

export function ReviewWorkspace({snapshot,report,fetcher,client,correctionsClient,decisionsClient,decisionState,onDecisions,onActivity,onInspect,onReviews,onSection}:{
  snapshot:ReviewSnapshot;report:NativeReport;fetcher:typeof fetch;client:ReviewNoteClient;correctionsClient?:ReviewCorrectionClient;decisionsClient:ReviewDecisionClient;decisionState:JournalState;onDecisions:(state:JournalState)=>void;
  onActivity:(state:'checking'|'not_started'|'in_review'|'unavailable')=>void;
  onInspect:(refs:string[])=>void;onReviews:(refs:string[])=>void;onSection:(id:string)=>void;
}){
  const status=useSyncExternalStore(client.subscribe,client.getSnapshot);
  const [corrections,setCorrections]=useState<CorrectionHistory|null>(null);
  const [book,setBook]=useState<Notebook|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [revision,setRevision]=useState(0),[kind,setKind]=useState('review_issue'),[search,setSearch]=useState(''),[selected,setSelected]=useState('');
  const [drafts,setDrafts]=useState<Record<string,Draft>>({}),[reviewer,setReviewer]=useState(''),[notice,setNotice]=useState('');
  const [sourcePage,setSourcePage]=useState(0),[sourceSearch,setSourceSearch]=useState('');
  const clearSaved=(note:ReviewNote)=>setDrafts(old=>{
    const draft=old[note.request.target_id];
    return draft?.text===note.request.text?{...old,[note.request.target_id]:emptyDraft()}:old;
  });
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');setBook(null);onActivity('checking');
    fetchNotebook(snapshot,fetcher,controller.signal).then(async value=>{
      const confirmed=await client.reconcile(value);if(controller.signal.aborted)return;
      setBook(value);onActivity(value.analyst_review);if(confirmed){clearSaved(confirmed);setNotice('The original note is confirmed in saved history.');}
    }).catch(()=>{if(!controller.signal.aborted){setError('Saved notes are unavailable. Recheck access and the exact report before continuing.');onActivity('unavailable');}})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[snapshot,fetcher,client,revision,onActivity]);
  const query=search.trim().toLowerCase();
  const filtered=snapshot.targets.filter(t=>(kind==='all'||kind===t.kind)&&(!query||(t.title+' '+t.detail).toLowerCase().includes(query)));
  const target=filtered.find(t=>t.id===selected)||filtered[0];
  const [sectionChoice,setSectionChoice]=useState('');
  const linkedSections=(target?.section_refs||[]).flatMap(id=>{const anchor=reviewSectionAnchor(report.workflow,id);return anchor?[{id,anchor,title:report.sections.find(s=>s.id===id)?.title||'Linked section'}]:[];});
  const linkedSection=linkedSections.find(s=>s.id===sectionChoice)||linkedSections[0];
  const draft=target?(drafts[target.id]||emptyDraft()):emptyDraft();
  const locked=status.phase!=='idle'||status.foreignPending;
  const pending=status.runId===snapshot.binding.run_id?client.pendingRequest(status.snapshotId||''):null;
  const capacityReached=!!book&&book.notes.length+book.earlier_scope_notes.length>=100;
  const canWrite=!!book?.notes_enabled&&!loading&&!error&&!locked&&!capacityReached&&target?.availability==='available';
  useEffect(()=>{setSourcePage(0);setSourceSearch('');},[target?.id]);
  const evidence=target?report.evidence.filter(e=>target.evidence_refs.includes(e.id)&&(!sourceSearch.trim()||(e.label+' '+e.pointer).toLowerCase().includes(sourceSearch.toLowerCase()))):[];
  const pageCount=Math.max(1,Math.ceil(evidence.length/10)),page=Math.min(sourcePage,pageCount-1),pageEvidence=evidence.slice(page*10,page*10+10);
  const update=(patch:Partial<Draft>)=>{if(target&&!locked)setDrafts(old=>({...old,[target.id]:{...(old[target.id]||emptyDraft()),...patch}}));};
  async function save(){
    if(!canWrite||!target)return;setNotice('');
    const body:NoteRequest={schema_version:1,snapshot_id:snapshot.snapshot_id,target_id:target.id,target_sha256:target.scope_sha256,
      reviewer_label:reviewer,note_type:draft.note_type,text:draft.text,evidence_refs:draft.evidence_refs};
    try{const note=await client.submit(snapshot,body);if(note){clearSaved(note);setNotice('Note saved to this exact review scope.');setRevision(n=>n+1);}}
    catch{setNotice('The note has not been confirmed. Preserve this submission and use the controls below.');}
  }
  async function retry(){setNotice('');try{const note=await client.submit();if(note){clearSaved(note);setNotice('Original note confirmed.');setRevision(n=>n+1);}}catch{setNotice('The original submission remains held. Recheck saved notes before trying again.');}}
  function acknowledgeRefusal(){
    if(pending?.snapshot_id===snapshot.snapshot_id){
      setDrafts(old=>({...old,[pending.target_id]:{text:pending.text,note_type:pending.note_type,evidence_refs:pending.evidence_refs}}));
      setReviewer(pending.reviewer_label);setKind('all');setSearch('');setSelected(pending.target_id);
    }
    client.acknowledgeRefusal();
  }
  const renderNote=(note:ReviewNote,earlier=false)=><article className="review-saved-note" key={note.id}>
    <div><strong>{noteLabels[note.request.note_type]}</strong><span>{earlier?'Earlier review scope · retained only':note.target_title}</span></div>
    <p className="review-note-text">{note.request.text}</p><p className="review-note-meta">{note.request.reviewer_label} · {savedInstant(note.recorded_at)} · local attribution, not authenticated approval</p>
    {!earlier&&note.request.evidence_refs.length>0&&<button className="nr-source-button" onClick={()=>onInspect(note.request.evidence_refs)}>Inspect attached source evidence</button>}
  </article>;
  return <section className="review-workspace" aria-labelledby="review-workspace-title">
    <div className="review-workspace-heading"><div><p className="eyebrow">READ, QUESTION, KEEP A TRAIL</p><h3 id="review-workspace-title" tabIndex={-1}>Your review workspace.</h3></div><button className="nr-secondary-button" disabled={loading} onClick={()=>setRevision(n=>n+1)}>{loading?'Checking notes…':'Recheck saved notes'}</button></div>
    <p>Keep questions and follow-up work beside the exact evidence. A note does not correct a source, resolve a financial restriction or approve the report.</p>
    {error&&<p className="review-alert" role="alert">{error}</p>}
    {!loading&&book&&!book.notes_enabled&&<p className="review-boundary">Notes are available to read. Recording new notes is disabled for this workspace.</p>}
    {capacityReached&&<p className="review-boundary">This report has reached its limit of 100 saved notes. Existing notes and evidence remain available.</p>}
    {status.phase!=='idle'&&<div className="review-alert" role="status"><strong>{status.phase==='sending'?'Saving this note…':status.phase==='refused'?'The note was refused.':'Confirmation is still needed.'}</strong><p>{status.foreignPending?'Reconnect to the original workspace to inspect the pending note.':'A retry preserves the original report, item, text and submission identity.'}</p>
      {status.runId&&status.runId!==snapshot.binding.run_id&&<a href={'#/runs/'+status.runId}>Return to the original report</a>}
      {pending&&<details><summary>Inspect the original note submission</summary><p>{pending.reviewer_label} · {noteLabels[pending.note_type]}</p><p className="review-note-text">{pending.text}</p><p>{pending.snapshot_id===snapshot.snapshot_id?'Bound to this review scope.':'Bound to an earlier review scope; it will not count as current review activity.'}</p></details>}
      {status.runId===snapshot.binding.run_id&&status.phase==='unconfirmed'&&<button className="nr-secondary-button" onClick={retry}>Retrieve / retry same note</button>}
      {status.phase==='refused'&&!status.foreignPending&&<button className="nr-secondary-button" onClick={acknowledgeRefusal}>Acknowledge refusal and edit</button>}
    </div>}
    <div className="review-workspace-grid"><div className="review-targets">
      <label>Review area<select aria-label="Review area" value={kind} onChange={e=>{setKind(e.target.value);setSelected('');}}><option value="all">All review items</option>{reviewKinds.map(k=><option key={k} value={k}>{reviewLabels[k]}</option>)}</select></label>
      <label>Find a review item<input value={search} onChange={e=>{setSearch(e.target.value);setSelected('');}} placeholder="Search sources, sections or issues" maxLength={160}/></label>
      <p className="review-note-meta">{filtered.length} items · restrictions remain attached</p>
      <div className="review-target-list" role="group" aria-label="Review items">{filtered.map(t=><button className="review-target" data-review-target={t.id} aria-pressed={target?.id===t.id} key={t.id} onClick={()=>setSelected(t.id)}><strong>{t.title}</strong><span>{reviewLabels[t.kind]} · {decisionState.kind==='ready'?subjectLabels[decisionState.journal.progress.targets[t.id]]:'Review status unavailable'}</span></button>)}</div>
    </div><div className="review-item-detail">{target?<>
      <p className="eyebrow">{reviewLabels[target.kind]}</p><h4>{target.title}</h4><p>{target.detail}</p>
      {target.kind==='review_issue'&&<p className="review-alert">{report.review_items.find(i=>target.issue_refs.includes(i.id))?.impact==='publication_block'?'Publication remains restricted.':'The linked section requires financial review.'} Notes do not clear this restriction.</p>}
      <div className="review-context-actions">{linkedSections.length>1&&<label>Read an affected section<select aria-label="Read an affected section" value={linkedSection?.id||''} onChange={e=>setSectionChoice(e.target.value)}>{linkedSections.map(s=><option key={s.id} value={s.id}>{s.title}</option>)}</select></label>}
        {linkedSection&&<button className="nr-source-button" onClick={()=>onSection(linkedSection.anchor)}>Read {linkedSections.length>1?'selected section':linkedSection.title}</button>}
        {target.issue_refs.length>0&&<button className="nr-source-button" onClick={()=>onReviews(target.issue_refs)}>Inspect linked financial restrictions ({target.issue_refs.length})</button>}</div>
      {target.availability==='not_recorded'?<p className="review-boundary">This subject was not recorded. There is no supported item to annotate or confirm.</p>:<>
      <details className="review-evidence"><summary>Inspect source evidence ({target.evidence_refs.length})</summary>
        {target.evidence_refs.length>0?<><label>Find source evidence<input value={sourceSearch} onChange={e=>{setSourceSearch(e.target.value);setSourcePage(0);}} maxLength={160}/></label>
        <ul>{pageEvidence.map(e=><li key={e.id}><strong>{e.label}</strong><code>{e.pointer||'Complete saved record'}</code>
          {report.metrics.filter(m=>m.evidence_refs.includes(e.id)).map(m=><p key={m.id}>{m.label}: {formatMetric(m)}</p>)}
          <button className="nr-source-button" onClick={()=>onInspect([e.id])}>Inspect source in report</button>
          <label className="review-attach"><input type="checkbox" checked={draft.evidence_refs.includes(e.id)} disabled={!canWrite||!draft.evidence_refs.includes(e.id)&&draft.evidence_refs.length>=10} onChange={event=>update({evidence_refs:event.target.checked?[...draft.evidence_refs,e.id]:draft.evidence_refs.filter(id=>id!==e.id)})}/>Attach this source to the note</label>
        </li>)}</ul><div className="review-pages"><button disabled={page===0} onClick={()=>setSourcePage(p=>p-1)}>Previous sources</button><span>Page {page+1} of {pageCount} · {evidence.length} matching references</span><button disabled={page+1>=pageCount} onClick={()=>setSourcePage(p=>p+1)}>Next sources</button></div></>:<p>No direct source field was retained for this item. Inspect the linked section and registered report evidence.</p>}
      </details>
      <form className="review-note-form" onSubmit={e=>{e.preventDefault();void save();}}>
        <h4>Add a review note</h4><label>Your name or analyst label<input value={reviewer} onChange={e=>setReviewer(e.target.value)} maxLength={120} disabled={!canWrite} autoComplete="off"/></label>
        <label>Note type<select aria-label="Note type" value={draft.note_type} onChange={e=>update({note_type:e.target.value as Draft['note_type']})} disabled={!canWrite}>{Object.entries(noteLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <label>Review note<textarea aria-label="Review note" rows={5} value={draft.text} onChange={e=>update({text:e.target.value})} maxLength={2000} disabled={!canWrite} placeholder="What needs attention, and which evidence supports your question?"/></label>
        <p className="review-note-meta">Draft until saved · up to 2,000 characters and 10 attached sources. {draft.evidence_refs.length} sources attached. Saving keeps an immutable note; add another note to clarify it.</p>
        <button className="nr-secondary-button" type="submit" disabled={!canWrite||!reviewer.trim()||!draft.text.trim()}>Save review note</button>
      </form></>}
      <div className="review-note-history"><h4>Saved notes for this item</h4>{book?.notes.filter(n=>n.request.target_id===target.id).map(n=>renderNote(n))}
        {book&&!book.notes.some(n=>n.request.target_id===target.id)&&<p>No note has been recorded for this item.</p>}</div>
    </>:<p>No review items match this search.</p>}</div></div>
    <DecisionWorkspace snapshot={snapshot} target={target} fetcher={fetcher} client={decisionsClient} notes={book?.notes||[]} corrections={corrections} referencesReady={!!book&&!loading&&!error&&(!correctionsClient||!!corrections)} onJournal={onDecisions} onInspect={onInspect}/>
    {correctionsClient&&snapshot.binding.version_id&&<CorrectionWorkspace snapshot={snapshot} target={target} fetcher={fetcher} client={correctionsClient} onHistory={setCorrections}/>}
    <p role="status" className="review-save-notice">{notice}</p>
    {book&&<details className="review-all-notes"><summary>All notes for this review scope ({book.notes.length})</summary>{book.notes.map(n=>renderNote(n))}{book.notes.length===0&&<p>No notes have been recorded for this scope.</p>}</details>}
    {book&&book.earlier_scope_notes.length>0&&<details className="review-all-notes"><summary>Earlier scope notes ({book.earlier_scope_notes.length})</summary><p>Retained history. These notes have not been carried into the current review scope.</p>{book.earlier_scope_notes.map(n=>renderNote(n,true))}</details>}
  </section>;
}
