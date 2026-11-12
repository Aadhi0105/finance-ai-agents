import {useEffect,useState,useSyncExternalStore} from 'react';
import type {ReviewSnapshot,ReviewTarget} from './review-data';
import type {ReviewNote} from './notes-data';
import type {CorrectionHistory} from './corrections-data';
import type {ReviewDecisionClient} from './decision-client';
import {fetchJournal,dispositionLabels,subjectLabels,type DecisionJournal,type DecisionRequest,type DecisionRecord,type Disposition,type JournalState,type JournalCursor} from './decisions-data';
import {savedInstant} from '../reports/format';

type Draft={reason:string;disposition:Disposition;note_ids:string[];correction_ids:string[]};
const fresh=():Draft=>({reason:'',disposition:'acknowledged',note_ids:[],correction_ids:[]});

export function DecisionWorkspace({snapshot,target,fetcher,client,notes,corrections,referencesReady,onJournal,onInspect}:{
  snapshot:ReviewSnapshot;target:ReviewTarget|undefined;fetcher:typeof fetch;client:ReviewDecisionClient;notes:ReviewNote[];
  corrections:CorrectionHistory|null;referencesReady:boolean;onJournal:(state:JournalState)=>void;onInspect:(refs:string[])=>void;
}){
  const status=useSyncExternalStore(client.subscribe,client.getSnapshot);
  const [journal,setJournal]=useState<DecisionJournal|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[revision,setRevision]=useState(0);
  const [cursor,setCursor]=useState<JournalCursor|undefined>(),[drafts,setDrafts]=useState<Record<string,Draft>>({}),[reviewer,setReviewer]=useState(''),[confirmed,setConfirmed]=useState(false),[notice,setNotice]=useState('');
  useEffect(()=>{setConfirmed(false);},[target?.id]);
  const clearSaved=(r:DecisionRecord)=>setDrafts(old=>{const d=old[r.request.target_id];return d?.reason===r.request.reason?{...old,[r.request.target_id]:fresh()}:old;});
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');setJournal(null);setConfirmed(false);onJournal({kind:'checking'});
    fetchJournal(snapshot,fetcher,controller.signal,cursor).then(async j=>{
      const saved=await client.reconcile(j);if(controller.signal.aborted)return;setJournal(j);onJournal({kind:'ready',journal:j});
      if(saved){clearSaved(saved);setNotice('The original review decision is confirmed in saved history.');}
    }).catch(()=>{if(!controller.signal.aborted){setError('Review decisions are unavailable or history changed. Recheck the latest history before continuing.');onJournal({kind:'unavailable'});}})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[snapshot,fetcher,client,cursor,revision,onJournal]);
  const draft=target?(drafts[target.id]||fresh()):fresh(),state=target?journal?.progress.targets[target.id]:undefined;
  const current=journal?.latest_events.find(e=>e.decision.target_id===target?.id),locked=status.phase!=='idle'||status.foreignPending;
  const pending=status.runId===snapshot.binding.run_id?client.pendingRequest(status.snapshotId||''):null;
  const itemNotes=notes.filter(n=>n.request.target_id===target?.id&&n.request.snapshot_id===snapshot.snapshot_id);
  const itemCorrections=(corrections?.outgoing||[]).filter(c=>c.record.binding.run_id===snapshot.binding.run_id&&c.record.request.snapshot_id===snapshot.snapshot_id&&c.record.request.target_id===target?.id);
  const canWrite=!!journal?.decisions_enabled&&!loading&&!error&&!locked&&referencesReady&&target?.availability==='available'&&journal.last_sequence<1000;
  const sameAction=state===draft.disposition||draft.disposition==='reopened'&&state==='pending';
  const update=(patch:Partial<Draft>)=>{if(target&&!locked){setConfirmed(false);setDrafts(old=>({...old,[target.id]:{...(old[target.id]||fresh()),...patch}}));}};
  function recheck(){setCursor(undefined);setRevision(n=>n+1);}
  async function save(){
    if(!canWrite||!target||!journal||!confirmed||sameAction||!reviewer.trim()||!draft.reason.trim())return;
    const request:DecisionRequest={schema_version:1,snapshot_id:snapshot.snapshot_id,target_id:target.id,target_sha256:target.scope_sha256,
      expected_sequence:journal.last_sequence,disposition:draft.disposition,reviewer_label:reviewer,reason:draft.reason,note_ids:draft.note_ids,correction_ids:draft.correction_ids};
    setNotice('');try{const record=await client.submit(snapshot,request);if(record){clearSaved(record);setNotice('Review decision saved. Evidence restrictions and financial approval are unchanged.');recheck();}}
    catch{setNotice('The decision has not been confirmed. Inspect the original submission and saved history below.');}
  }
  async function retry(){try{const record=await client.submit();if(record){clearSaved(record);setNotice('Original review decision confirmed.');recheck();}}catch{setNotice('Preserve the original submission. Recheck saved history before trying again.');}}
  function refused(){if(pending?.snapshot_id===snapshot.snapshot_id){setDrafts(old=>({...old,[pending.target_id]:{reason:pending.reason,disposition:pending.disposition,note_ids:pending.note_ids,correction_ids:pending.correction_ids}}));setReviewer(pending.reviewer_label);}client.acknowledgeRefusal();recheck();}
  const renderRecord=(r:DecisionRecord)=>{const old=r.request.snapshot_id!==snapshot.snapshot_id;return <article className="review-saved-decision" key={r.id}>
    <div><strong>{dispositionLabels[r.decision.disposition]}</strong><span>#{r.ordinal} · {old?'Earlier scope · retained history only':r.target_title}</span></div>
    <p className="review-note-text">{r.decision.reason}</p><p className="review-note-meta">{r.decision.reviewer_label} · {savedInstant(r.decision.recorded_at)} · local attribution, not authenticated financial approval</p>
    {(r.request.note_ids.length>0||r.request.correction_ids.length>0)&&<details><summary>Attached review references</summary><p>{r.request.note_ids.length} note(s) · {r.request.correction_ids.length} correction(s)</p><ul>{[...r.request.note_ids,...r.request.correction_ids].map(id=><li key={id}><code>{id}</code></li>)}</ul><p>Exact references are retained. Current-scope note and correction details appear in their own panels.</p></details>}
  </article>;};
  return <section className="review-decisions" aria-labelledby="review-decision-title">
    <div className="review-workspace-heading"><div><p className="eyebrow">REVIEW THE ITEM, RECORD YOUR REASON</p><h3 id="review-decision-title">Your review decision.</h3></div><button className="nr-secondary-button" disabled={loading} onClick={recheck}>Recheck review decisions</button></div>
    <p>Acknowledge what you reviewed, request changes, or reopen an item. These decisions preserve the evidence restrictions and grant no financial approval.</p>
    {loading&&<p role="status">Checking the exact review history…</p>}{error&&<p role="alert" className="review-alert">{error}</p>}
    {locked&&<div className="review-alert" role="status"><strong>{status.phase==='sending'?'Saving this review decision…':status.phase==='refused'?'The decision was refused.':'The original decision needs confirmation.'}</strong>
      <p>{status.foreignPending?'Reconnect to the original workspace before continuing.':'Keep the original tab open. Recheck history or retry the same submission before recording another. A full reload loses an unconfirmed retry identity.'}</p>
      {status.runId&&status.runId!==snapshot.binding.run_id&&<a href={'#/runs/'+status.runId}>Return to the original decision report</a>}
      {pending&&<details><summary>Inspect the original decision submission</summary><p>{dispositionLabels[pending.disposition]} · {pending.reviewer_label}</p><p>{pending.reason}</p><p>Based on history version {pending.expected_sequence}. It will not be rebound to a newer history automatically.</p></details>}
      {pending&&status.phase==='unconfirmed'&&<button className="nr-secondary-button" onClick={retry}>Retrieve / retry same decision</button>}
      {pending&&status.phase==='refused'&&<button className="nr-secondary-button" onClick={refused}>Acknowledge decision refusal and edit</button>}
    </div>}
    {journal&&!journal.decisions_enabled&&<p className="review-boundary">Decision history is available to read. Recording new decisions is disabled for this workspace.</p>}
    {journal&&target&&<div className="review-decision-item"><p className="eyebrow">SELECTED ITEM</p><h4>{target.title}</h4><p className="review-decision-state" data-testid="decision-subject-state">{state?subjectLabels[state]:'Status unavailable'}</p>
      {current&&<div className="review-decision-latest"><strong>Latest recorded explanation</strong><p>{current.decision.reason}</p><p className="review-note-meta">{current.decision.reviewer_label} · {savedInstant(current.decision.recorded_at)}</p><p>{current.note_ids.length} attached note(s) · {current.correction_ids.length} attached correction(s)</p></div>}
      {target.availability==='available'?<form className="review-note-form" onSubmit={e=>{e.preventDefault();void save();}}>
        <label>Review action<select aria-label="Review action" value={draft.disposition} onChange={e=>update({disposition:e.target.value as Disposition})} disabled={!canWrite}>{Object.entries(dispositionLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <p>{draft.disposition==='acknowledged'?'Acknowledgement records that you reviewed this item and understand its limitations. It does not establish that the source is correct.':draft.disposition==='changes_requested'?'This records a request for changes. Use the correction workflow for revised inputs and a separate calculation.':'Reopening returns this item to awaiting review. Previous decisions remain in its history.'}</p>
        <label>Your name or analyst label<input aria-label="Decision analyst label" value={reviewer} onChange={e=>{setConfirmed(false);setReviewer(e.target.value);}} maxLength={120} disabled={!canWrite}/></label>
        <label>Explain your decision<textarea aria-label="Decision explanation" rows={4} maxLength={1600} value={draft.reason} onChange={e=>update({reason:e.target.value})} disabled={!canWrite}/></label>
        {(itemNotes.length>0||itemCorrections.length>0)&&<details><summary>Attach notes or corrections for this item</summary>
          {itemNotes.map(n=><div className="review-decision-reference" key={n.id}><label className="review-attach"><input type="checkbox" checked={draft.note_ids.includes(n.id)} disabled={!canWrite||!draft.note_ids.includes(n.id)&&draft.note_ids.length>=10} onChange={e=>update({note_ids:e.target.checked?[...draft.note_ids,n.id]:draft.note_ids.filter(id=>id!==n.id)})}/>Note: {n.request.text}</label>{n.request.evidence_refs.length>0&&<button className="nr-source-button" type="button" onClick={()=>onInspect(n.request.evidence_refs)}>Inspect attached note evidence</button>}</div>)}
          {itemCorrections.map(c=><label className="review-attach" key={c.record.id}><input type="checkbox" checked={draft.correction_ids.includes(c.record.id)} disabled={!canWrite||!draft.correction_ids.includes(c.record.id)&&draft.correction_ids.length>=5} onChange={e=>update({correction_ids:e.target.checked?[...draft.correction_ids,c.record.id]:draft.correction_ids.filter(id=>id!==c.record.id)})}/>Correction: {c.record.request.reason}</label>)}
        </details>}
        {!referencesReady&&<p className="review-boundary">Recheck saved notes and correction history before recording a decision.</p>}
        {sameAction&&<p className="review-note-meta">Choose an action that changes the current review state. To retrieve a previously submitted decision, use its original retry controls.</p>}
        <label className="review-attach"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} disabled={!canWrite}/>I am recording a decision for this exact report and item. Financial approval remains separate.</label>
        <button className="nr-secondary-button" type="submit" disabled={!canWrite||!confirmed||sameAction||!reviewer.trim()||!draft.reason.trim()}>Save review decision</button>
      </form>:<p>This subject was not recorded; there is no available item to acknowledge.</p>}
    </div>}
    <p className="review-save-notice" role="status">{notice}</p>
    {journal&&<div className="review-decision-history"><h4>Decision history</h4><p>{journal.current_count} decisions for this scope · {journal.earlier_scope_count} for earlier scopes · {journal.last_sequence} retained in total</p>
      {journal.earlier_scope_count>0&&<p>Earlier-scope decisions remain historical evidence and do not count toward this review.</p>}
      {journal.records.map(renderRecord)}{journal.last_sequence===0&&<p>No review decision has been recorded for this report.</p>}
      <div className="review-pages"><button disabled={!cursor||loading} onClick={recheck}>Latest decisions</button><span>Up to 25 decisions per page · history version {journal.last_sequence}</span><button disabled={!journal.page.next_cursor||loading} onClick={()=>setCursor({id:journal.page.next_cursor!,ordinal:journal.records[journal.records.length-1].ordinal,revision:journal.last_sequence})}>Earlier decisions</button></div>
    </div>}
  </section>;
}
