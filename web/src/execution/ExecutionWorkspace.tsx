import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { FormEvent } from 'react';
import type { Run } from '../workspace-types';
import { Icon } from '../icons';
import { JobClient } from './job-client';
import type { ExecutionSnapshot } from './job-client';
import { eligibleRuns, eventNames, jobId, nextAction, profiles, stateNames, workflow } from './job-data';
import type { Job, JobRequest, Workflow } from './job-data';
import './execution.css';

const time = (v: string | null) => v ? new Date(v).toLocaleString(undefined,{ dateStyle:'medium',timeStyle:'medium' }) : 'Not recorded';
const jobHref = (id: string) => '#/jobs/' + id;
type SubmitRequest = (request?: JobRequest) => Promise<void>;

export function ExecutionWorkspace({ client, runs, route, inventoryStatus, onRefreshReports, onOpenReport, onSubmit }: {
  client: JobClient; runs: Run[]; route: string; inventoryStatus: 'loading' | 'ready' | 'unavailable'; onRefreshReports: () => Promise<unknown>; onOpenReport: (job: Job) => Promise<void>; onSubmit: SubmitRequest;
}) {
  const state = useSyncExternalStore(client.subscribe,client.getSnapshot);
  const id = route.startsWith('/jobs/new/') ? null : route.startsWith('/jobs/') ? route.slice(6) : null;
  const source = route.startsWith('/jobs/new/') ? route.slice(10) : '';
  const [reportError,setReportError] = useState(''), [opening,setOpening] = useState(false);
  const refreshed = useRef(new Set<string>()), title = useRef<HTMLHeadingElement>(null);
  const openRequest = useRef(0);
  useEffect(() => {
    const poll = () => { if (document.visibilityState !== 'hidden') void client.refresh(); };
    poll(); const timer = window.setInterval(poll,3000);
    document.addEventListener('visibilitychange',poll);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange',poll); };
  },[client]);
  useEffect(() => { openRequest.current++;setOpening(false);client.select(id); setReportError(''); title.current?.focus(); return () => client.select(null); },[client,id]);
  useEffect(() => {
    let current = true;
    const job = state.detail?.job;
    if (job?.resultUrl && !refreshed.current.has(job.id)) {
      refreshed.current.add(job.id);
      void onRefreshReports().catch(() => { if (current) setReportError('The report inventory could not be rechecked. Use Open report to try again.'); });
    }
    return () => { current = false; };
  },[state.detail?.job.id,state.detail?.job.resultUrl,onRefreshReports]);
  async function submitted() {
    await onSubmit();
  }
  async function openReport(job: Job) {
    if (opening) return;
    const request = ++openRequest.current;
    setOpening(true); setReportError('');
    try { await onOpenReport(job); }
    catch { if (request === openRequest.current) setReportError('The registered report could not be rechecked. Preserve the job and refresh the workspace before opening it again.'); }
    finally { if (request === openRequest.current) setOpening(false); }
  }
  return <div className="execution-workspace">
    <div className="page-heading"><div><p className="eyebrow">CONTROLLED LOCAL EXECUTION</p><h1 ref={title} tabIndex={-1}>{id ? 'Saved job' : 'Run from saved evidence.'}</h1><p>Rebuild or replay a registered demonstration. Follow its recorded outcome and open the resulting report.</p></div><a className="text-button" href="#/history">Browse saved reports<Icon name="arrow" size={16}/></a></div>
    <CapabilitiesPanel state={state} refresh={() => void client.refresh()}/>
    <div className="execution-scope"><Icon name="info" size={18}/><p>Offline synthetic inputs · no fresh market data or paid model calls. Successful runs register separate reports. Financial review remains required.</p></div>
    <AccessPanel state={state} client={client}/>
    {state.pending && <section className="execution-pending" aria-labelledby="pending-title">
      <h2 id="pending-title">{state.pending.state === 'sending' ? 'Saving your request…' : state.pending.state === 'refused' ? 'Request refused before admission' : 'Submission needs confirmation'}</h2>
      <p>{profiles[state.pending.request.workflow].action} · source <code>{state.pending.request.source_run_id}</code> · {state.pending.request.timeout_seconds}s processing limit.</p>
      <p role="status">{state.pending.error || 'Keep this request identity while the server confirms it.'}</p>
      <p>{state.pending.state === 'refused' ? 'The server explicitly refused admission. You can edit this request or resend it with its existing identity.' : 'Resending uses the same identity and retrieves any existing job. Repeated submissions with this identity do not create another job. A page reload clears this local identity; reconnect and inspect job history before starting new work.'}</p>
      <button className="primary-button" onClick={() => void submitted()} disabled={!state.connected || state.pending.state === 'sending' || !state.capabilities?.admission_enabled}>{state.pending.state === 'sending' ? 'Waiting for confirmation…' : 'Resend same request'}</button>
      {state.pending.state === 'refused' && <button className="execution-secondary" onClick={() => client.editRefused()}>Edit refused request</button>}
    </section>}
    {id ? <>
      <a className="back-link" href="#/jobs"><Icon name="back" size={16}/>Run & jobs</a>
      {state.connected && !state.detail && !state.detailError && <p role="status">Reading the saved job…</p>}
      {state.detailError && <div className="execution-alert" role="alert"><p>{state.detailError}</p><button className="text-button" onClick={() => void client.loadDetail()}>Recheck job</button></div>}
      {state.detail && <JobDetailPanel state={state} runs={runs} onOpen={() => void openReport(state.detail!.job)} opening={opening}/>}
      {!jobId.test(id) && <p role="alert">This job address is unsupported. Choose a job from the history below.</p>}
      {reportError && <p className="execution-alert" role="alert">{reportError}</p>}
    </> : <RunForm key={source} source={source} runs={runs} state={state} inventoryStatus={inventoryStatus} onSubmit={onSubmit}/>}
    <JobHistory state={state} runs={runs} client={client}/>
  </div>;
}
function CapabilitiesPanel({ state,refresh }: { state: ExecutionSnapshot; refresh: () => void }) {
  const caps = state.capabilities;
  const label = !caps ? 'Execution status unavailable' : !caps.admission_enabled ? 'Requests disabled' : caps.worker_enabled ? 'Worker available' : caps.worker_status === 'stopped' ? 'Worker stopped' : 'Queue only';
  const explanation = !caps ? state.capabilityError || 'Checking the local server…' : !caps.admission_enabled ? 'Saved reports are available for reading. The local operator must explicitly enable execution.' : caps.worker_enabled ? 'The local worker can process queued requests one at a time.' : caps.worker_status === 'stopped' ? 'Requests can be saved, but processing is unavailable. The operator must inspect the worker.' : 'Requests can be saved. Processing starts only when the local operator enables the worker.';
  return <section className="execution-capabilities" aria-label="Execution availability"><div><strong><span className="status-dot"/>{label}</strong><p>{explanation}</p></div><button className="execution-secondary" onClick={refresh} disabled={state.refreshing}>{state.refreshing ? 'Checking…' : 'Refresh status'}</button></section>;
}
function AccessPanel({ state,client }: { state: ExecutionSnapshot; client: JobClient }) {
  const [token,setToken] = useState('');
  const heading = useRef<HTMLHeadingElement>(null), input = useRef<HTMLInputElement>(null), wasConnected = useRef(false);
  useEffect(() => { if (state.connected) heading.current?.focus(); else if (wasConnected.current) input.current?.focus(); wasConnected.current=state.connected; },[state.connected]);
  useEffect(() => { const clear = () => setToken(''); addEventListener('pagehide',clear); return () => removeEventListener('pagehide',clear); },[]);
  async function connect(event: FormEvent) { event.preventDefault(); const value = token; setToken(''); await client.connect(value); }
  return <section className="panel execution-access" aria-labelledby="access-title">
    <div><p className="eyebrow">LOCAL JOB ACCESS</p><h2 id="access-title" tabIndex={-1} ref={heading}>{state.connected ? 'Connected for this tab' : 'Connect to run and inspect jobs'}</h2><p>{state.connected ? 'Access is held in memory. Clearing access or reloading this page does not stop saved jobs.' : 'Use the job-access token from the private file named when the execution server starts. This is separate from your data-provider and AI keys.'}</p></div>
    {state.connected ? <button className="execution-secondary" onClick={() => { setToken('');client.disconnect(); }}>Clear local access</button> : <form onSubmit={event => void connect(event)}>
      <label htmlFor="job-token">Local job-access token</label><div className="execution-access-controls"><input id="job-token" type="password" ref={input} value={token} onChange={e => setToken(e.target.value)} autoComplete="off" autoCapitalize="none" spellCheck={false} maxLength={128} required disabled={state.connecting || !state.capabilities?.admission_enabled} aria-describedby="token-help"/>
        <button className="primary-button" disabled={state.connecting || !state.capabilities?.admission_enabled}>{state.connecting ? 'Connecting…' : 'Connect'}</button></div>
      <p id="token-help">The field is cleared on connection. The application keeps no token in browser storage. After a reload, inspect job history before submitting new work.</p>
    </form>}
    {state.listError && <p className="execution-alert" role="alert">{state.listError}</p>}
  </section>;
}
function RunForm({ source,runs,state,inventoryStatus,onSubmit }: { source: string; runs: Run[]; state: ExecutionSnapshot; inventoryStatus: 'loading' | 'ready' | 'unavailable'; onSubmit: SubmitRequest }) {
  const eligible = eligibleRuns(runs), initial = eligible.find(r => r.id === source);
  const [family,setFamily] = useState<Workflow>(initial && workflow(initial.workflow) ? initial.workflow : 'research');
  const [selected,setSelected] = useState(initial?.id || '');
  const [timeout,setTimeout] = useState('600'), [error,setError] = useState('');
  const submitting = useRef(false);
  const appliedSource = useRef('');
  useEffect(() => { if (initial && workflow(initial.workflow) && appliedSource.current !== source) { appliedSource.current=source;setFamily(initial.workflow);setSelected(initial.id); } },[initial,source]);
  const choices = eligible.filter(r => r.workflow === family), selectedRun = choices.find(r => r.id === selected);
  const disabled = inventoryStatus !== 'ready' || !state.connected || !state.capabilities?.admission_enabled || !!state.pending || !!state.capabilityError;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (disabled || submitting.current) return;
    const limit = Number(timeout);
    if (!selectedRun || !Number.isInteger(limit) || limit < 1 || limit > 600) { setError('Select an eligible saved report and a processing limit from 1 to 600 seconds.'); return; }
    submitting.current = true; setError('');
    try {
      await onSubmit({ schema_version:1, workflow:family, source_run_id:selectedRun.id, timeout_seconds:limit });
    } catch { setError('The request could not be prepared. Check its saved source and processing limit.'); }
    finally { submitting.current = false; }
  }
  return <section className="panel execution-form" aria-labelledby="new-job-title"><div className="execution-section-heading"><div><p className="eyebrow">NEW SAVED RUN</p><h2 id="new-job-title">Choose the evidence to reuse.</h2><p>Original inputs stay unchanged. Research is rebuilt, monitoring and close are rendered, and event/news bundles are replayed.</p></div><span className="execution-label">SAVED INPUTS</span></div>
    {inventoryStatus === 'loading' && <p role="status" className="execution-help">Loading registered sources…</p>}
    {inventoryStatus === 'unavailable' && <p className="execution-alert" role="alert">Registered sources are unavailable. Recheck the workspace before submitting new work.</p>}
    {inventoryStatus === 'ready' && source && !initial && <p className="execution-alert" role="alert">The requested source is not eligible in this workspace. Choose a registered report below.</p>}
    <form onSubmit={event => void submit(event)}>
      <fieldset disabled={disabled}><legend className="sr-only">Saved run request</legend><div className="execution-fields">
        <label>Workflow<select value={family} onChange={e => { const v=e.target.value; if(workflow(v)){setFamily(v);setSelected('');} }}>{Object.entries(profiles).map(([key,p]) => <option key={key} value={key}>{p.name}</option>)}</select></label>
        <label>Saved source report<select value={selectedRun?.id || ''} onChange={e => setSelected(e.target.value)} required><option value="">Select a registered report</option>{choices.map(r => <option key={r.id} value={r.id}>{r.entity} · {r.title} · {r.period} · {r.id}</option>)}</select></label>
        <label>Processing limit (seconds)<input type="number" min="1" max="600" step="1" required value={timeout} onChange={e => setTimeout(e.target.value)} aria-describedby="processing-limit-help"/></label>
      </div></fieldset>
      <p id="processing-limit-help" className="execution-help">Up to 10 minutes for supervised processing. Queue waiting, input preparation and report registration have separate durations.</p>
      {selectedRun && <div className="execution-selected"><strong>{selectedRun.entity}</strong><span>{selectedRun.period}</span><a href={'#/runs/'+selectedRun.id}>Inspect source report<Icon name="arrow" size={14}/></a></div>}
      {inventoryStatus === 'ready' && !choices.length && <p className="execution-alert">No registered native report supports this workflow in the selected workspace.</p>}
      {error && <p role="alert" className="execution-alert">{error}</p>}
      <div className="execution-form-footer"><p>{!state.connected ? 'Connect local access to submit a request.' : state.pending ? 'Resolve the existing submission above.' : state.capabilities?.worker_enabled ? 'The enabled worker will process this saved evidence.' : 'The request will remain queued until the operator enables a worker.'}</p><button className="primary-button" disabled={disabled || !selectedRun}>{state.capabilities?.worker_enabled ? 'Start saved run' : 'Queue saved run'}<Icon name="arrow" size={16}/></button></div>
    </form>
  </section>;
}
function JobStatus({ job }: { job: Job }) {
  return <span className={'execution-job-status '+(job.status === 'running' || job.status === 'queued' ? 'active' : '')}>{stateNames[job.status]}</span>;
}
function JobDetailPanel({ state,runs,onOpen,opening }: { state: ExecutionSnapshot; runs: Run[]; onOpen: () => void; opening: boolean }) {
  const { job,events } = state.detail!, source = runs.find(r => r.id === job.request.source_run_id);
  return <section className="panel execution-detail" aria-labelledby="job-detail-title"><div className="execution-section-heading"><div><p className="eyebrow">{profiles[job.request.workflow].name.toUpperCase()}</p><h2 id="job-detail-title">{profiles[job.request.workflow].action}</h2><p>{source ? source.entity+' · '+source.period : 'Saved source: '+job.request.source_run_id}</p></div><JobStatus job={job}/></div>
    <p className="execution-outcome" role="status">{nextAction(job)}</p>
    <dl className="execution-facts"><div><dt>Request saved</dt><dd>{time(job.createdAt)}</dd></div><div><dt>Worker started</dt><dd>{time(job.startedAt)}</dd></div><div><dt>Finished</dt><dd>{time(job.finishedAt)}</dd></div><div><dt>Processing limit</dt><dd>{job.request.timeout_seconds} {job.request.timeout_seconds === 1 ? 'second' : 'seconds'}</dd></div></dl>
    <div className="execution-detail-actions">{job.resultUrl && <button className="primary-button" onClick={onOpen} disabled={opening}>{opening ? 'Checking registered report…' : 'Open report'}<Icon name="arrow" size={16}/></button>}{source && <a className="text-button" href={'#/runs/'+source.id}>Inspect original source</a>}<a className="text-button" href="#/jobs">New saved request</a></div>
    <div className="execution-events"><h3>Recorded stages</h3><p>Confirmed events from the local ledger. No percentage or completion time is estimated.</p><ol>{events.map((e,i) => <li key={i}><span aria-hidden="true">{String(i+1).padStart(2,'0')}</span><div><strong>{eventNames[e.event]}</strong><time dateTime={e.created_at}>{time(e.created_at)}</time></div></li>)}</ol></div>
    <details className="execution-identities"><summary>Job and operation identities</summary><dl><dt>Job</dt><dd><code>{job.id}</code></dd><dt>Operation</dt><dd><code>{job.operationId}</code></dd><dt>Source report</dt><dd><code>{job.request.source_run_id}</code></dd></dl></details>
    <p className="execution-help">Status checked {time(state.detailCheckedAt)}. Updates pause while this tab is hidden. Leaving this page or clearing access does not cancel processing.</p>
  </section>;
}
function JobHistory({ state,runs,client }: { state: ExecutionSnapshot; runs: Run[]; client: JobClient }) {
  const heading = useRef<HTMLHeadingElement>(null);
  async function page(cursor: string | null) { await client.loadList(cursor); heading.current?.focus(); }
  return <section className="panel execution-history" aria-labelledby="jobs-title" aria-busy={state.listing}><div className="execution-section-heading"><div><p className="eyebrow">DURABLE LOCAL HISTORY</p><h2 id="jobs-title" tabIndex={-1} ref={heading}>Saved jobs</h2><p>{state.cursor ? 'Older requests in the selected ledger.' : 'Newest requests first. Reconnect after a reload to inspect retained jobs.'}</p></div>{state.connected && <button className="execution-secondary" onClick={() => void client.refresh()} disabled={state.refreshing || state.listing}>Refresh jobs</button>}</div>
    {state.connected && state.listing && !state.jobs.length && <p className="execution-history-empty" role="status">Reading this page of saved jobs…</p>}
    {!state.connected ? <p className="execution-history-empty">Connect local access above to inspect job history.</p> : state.jobs.length ? <div className="table-region" role="region" aria-label="Saved job table" tabIndex={0}><table className="execution-jobs-table"><thead><tr><th>WORKFLOW / SOURCE</th><th>REQUEST SAVED</th><th>RECORDED OUTCOME</th><th><span className="sr-only">Open job</span></th></tr></thead><tbody>{state.jobs.map(job => { const source=runs.find(r=>r.id===job.request.source_run_id); return <tr key={job.id}><td><a href={jobHref(job.id)}>{profiles[job.request.workflow].action}</a><span>{source?.entity || job.request.source_run_id}</span><small>{job.id}</small></td><td><time dateTime={job.createdAt}>{time(job.createdAt)}</time></td><td><JobStatus job={job}/></td><td><a href={jobHref(job.id)} className="row-arrow" aria-label={'Open job '+job.id}><Icon name="arrow" size={18}/></a></td></tr>; })}</tbody></table></div> : !state.listError && !state.listing && <p className="execution-history-empty">No saved jobs on this page. Choose registered evidence above to create a request.</p>}
    {state.connected && <div className="execution-history-footer"><p>{state.checkedAt ? 'Status checked '+time(state.checkedAt) : 'History has not been confirmed.'}</p><div>{state.cursor && <button className="text-button" disabled={state.listing} onClick={() => void page(null)}>Back to latest</button>}{state.next && <button className="text-button" disabled={state.listing} onClick={() => void page(state.next)}>Older jobs<Icon name="arrow" size={14}/></button>}</div></div>}
  </section>;
}
