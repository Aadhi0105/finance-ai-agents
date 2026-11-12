import type {ReviewCorrectionClient} from './correction-client';
import {useEffect,useMemo,useState} from 'react';
import type {Run} from '../workspace-types';
import type {NativeReport} from '../reports/report-data';
import {fetchReview,reviewKinds,reviewLabels,type ReviewSnapshot} from './review-data';
import './review.css';
import {ReviewNoteClient} from './note-client';
import {ReviewWorkspace} from './ReviewWorkspace';
import {ReviewDecisionClient} from './decision-client';
import {reviewStateLabels,type JournalState} from './decisions-data';

type State={kind:'loading'}|{kind:'ready';snapshot:ReviewSnapshot}|{kind:'unavailable'};
export function ReviewOverview({run,report,fetcher,notesClient,correctionsClient,decisionsClient,onInspect,onReviews,onSection}:{
  run:Run;report:NativeReport;fetcher:typeof fetch;notesClient?:ReviewNoteClient;correctionsClient?:ReviewCorrectionClient;decisionsClient?:ReviewDecisionClient;
  onInspect:(refs:string[])=>void;onReviews:(refs:string[])=>void;onSection:(id:string)=>void;
}){
  const client=useMemo(()=>notesClient||new ReviewNoteClient(),[notesClient]);
  const decisions=useMemo(()=>decisionsClient||new ReviewDecisionClient(),[decisionsClient]);
  const [decisionState,setDecisionState]=useState<JournalState>({kind:'checking'});
  const [activity,setActivity]=useState<'checking'|'not_started'|'in_review'|'unavailable'>('checking');
  const [state,setState]=useState<State>({kind:'loading'}),[attempt,setAttempt]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();setState({kind:'loading'});setActivity('checking');setDecisionState({kind:'checking'});
    fetchReview(run,report,controller.signal,fetcher).then(snapshot=>{if(!controller.signal.aborted)setState({kind:'ready',snapshot});})
      .catch(()=>{if(!controller.signal.aborted)setState({kind:'unavailable'});});
    return()=>controller.abort();
  },[run,report,fetcher,attempt]);
  useEffect(()=>{if(!notesClient&&state.kind==='ready')client.activate(state.snapshot.binding.workspace_id);},[notesClient,client,state]);
  useEffect(()=>{if(!decisionsClient&&state.kind==='ready')decisions.activate(state.snapshot.binding.workspace_id);},[decisionsClient,decisions,state]);
  if(state.kind==='loading')return <div className="review-overview" role="status">Checking the review scope for this report…</div>;
  if(state.kind==='unavailable')return <div className="review-overview" role="status"><h3>Review overview unavailable</h3><p>The review scope could not be matched to this report. Existing financial restrictions remain in force.</p><button className="nr-secondary-button" onClick={()=>setAttempt(n=>n+1)}>Recheck review overview</button></div>;
  const s=state.snapshot;
  const label=decisionState.kind==='checking'||activity==='checking'?'Checking review activity…':decisionState.kind!=='ready'||activity==='unavailable'?'Review activity unavailable':
    decisionState.journal.current_count?reviewStateLabels[decisionState.journal.progress.analyst_review]:activity==='in_review'?'In progress · notes recorded':'Not started';
  return <div className="review-overview" aria-labelledby="review-overview-title">
    <p className="eyebrow">YOUR REVIEW SCOPE</p><h3 id="review-overview-title">Where this report stands.</h3>
    <button className="nr-secondary-button" onClick={()=>{const target=document.getElementById('review-workspace-title');target?.scrollIntoView({block:'start',behavior:'instant'});target?.focus({preventScroll:true});}}>Open review workspace</button>
    <dl className="review-state-grid">
      <div><dt>Input evidence</dt><dd>{s.input_acceptance==='accepted_for_processing'?'Accepted for processing':'Retained saved evidence'}</dd></div>
      <div><dt>Technical execution</dt><dd>{s.execution==='completed'?'Completed':s.execution==='held'?'Held for review':s.execution.replaceAll('_',' ')}</dd></div>
      <div><dt>Analyst review</dt><dd>{label}</dd></div>
      <div><dt>Financial approval</dt><dd>Not granted</dd></div>
    </dl>
    <p>These are separate states. Accepted inputs and completed calculations still need financial review. An acknowledgement cannot clear a source restriction or release a withheld figure.</p>
    <ul className="review-area-list">{reviewKinds.map(kind=>{
      const targets=s.targets.filter(t=>t.kind===kind),available=targets.filter(t=>t.availability==='available').length;
      const states=decisionState.kind==='ready'?targets.map(t=>decisionState.journal.progress.targets[t.id]):null;
      const summary=!available?'Not recorded for this report':!states?'Review status unavailable':`${states.filter(s=>s==='acknowledged').length} acknowledged · ${states.filter(s=>s==='changes_requested').length} changes requested · ${states.filter(s=>s==='pending').length} awaiting review`;
      return <li key={kind}><div><strong>{reviewLabels[kind]}</strong><span>{summary}</span></div>{kind==='financial_mappings'&&<p>Saved source fields and transformations. Document extraction has not been performed.</p>}</li>;
    })}</ul>
    <p className="review-boundary">Saved decisions record analyst review. Notes, input corrections and financial approval retain their separate meanings.</p>
    <ReviewWorkspace snapshot={s} report={report} fetcher={fetcher} client={client} correctionsClient={correctionsClient} decisionsClient={decisions} decisionState={decisionState} onDecisions={setDecisionState} onActivity={setActivity} onInspect={onInspect} onReviews={onReviews} onSection={onSection}/>
    <details className="nr-technical-record"><summary>Exact review version</summary><dl><dt>Snapshot</dt><dd><code>{s.snapshot_id}</code></dd><dt>Input version</dt><dd>{s.binding.version_id||'Retained saved evidence'}</dd><dt>Binding</dt><dd>Run, registered files, input version, request and presentation. Changes require a new review scope.</dd></dl></details>
  </div>;
}
