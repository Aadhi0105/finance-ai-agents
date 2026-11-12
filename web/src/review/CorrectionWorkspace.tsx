import {useEffect,useState,useSyncExternalStore} from 'react';
import type {ReviewSnapshot,ReviewTarget} from './review-data';
import {fetchCorrections,type CorrectionHistory,type CorrectionRequest,type CorrectionLink,type ChangeCell} from './corrections-data';
import type {ReviewCorrectionClient} from './correction-client';
import {savedInstant} from '../reports/format';

export function CorrectionWorkspace({snapshot,target,fetcher,client,onHistory}:{snapshot:ReviewSnapshot;target:ReviewTarget|undefined;fetcher:typeof fetch;client:ReviewCorrectionClient;onHistory?:(value:CorrectionHistory|null)=>void}){
  const status=useSyncExternalStore(client.subscribe,client.getSnapshot);
  const [history,setHistory]=useState<CorrectionHistory|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[revision,setRevision]=useState(0);
  const [replacement,setReplacement]=useState(''),[reviewer,setReviewer]=useState(''),[reason,setReason]=useState(''),[checked,setChecked]=useState(false),[notice,setNotice]=useState(''),[page,setPage]=useState(0);
  useEffect(()=>{setChecked(false);},[target?.id]);
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');setHistory(null);onHistory?.(null);setChecked(false);setPage(0);
    fetchCorrections(snapshot,fetcher,controller.signal,replacement||undefined).then(async h=>{
      const saved=await client.reconcile(h);if(controller.signal.aborted)return;setHistory(h);onHistory?.(h);
      if(saved){setReason('');setNotice('The original correction is confirmed in saved history. No job was started by recording it.');}
    }).catch(()=>{if(!controller.signal.aborted)setError('Correction history or the selected comparison is unavailable. Recheck the input, validation and current source permissions.');})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[snapshot,fetcher,client,replacement,revision,onHistory]);
  const locked=status.phase!=='idle'||status.foreignPending;
  const pending=status.runId===snapshot.binding.run_id?client.pendingRequest(status.snapshotId||''):null;
  const comparison=history?.comparison;
  const canSave=!!history?.corrections_enabled&&!history.outgoing.length&&!loading&&!error&&!locked&&target?.availability==='available'&&comparison&&checked&&reviewer.trim()&&reason.trim();
  async function save(){
    if(!canSave||!target||!comparison)return;
    const body:CorrectionRequest={schema_version:1,snapshot_id:snapshot.snapshot_id,target_id:target.id,target_sha256:target.scope_sha256,
      replacement:comparison.replacement,change_sha256:comparison.change_sha256,reviewer_label:reviewer,reason};
    setNotice('');try{const saved=await client.submit(snapshot,body);if(saved){setReason('');setReplacement('');setNotice('Correction recorded. The original report is retained. Inspect the replacement input to request processing.');setRevision(n=>n+1);}}
    catch{setNotice('The correction has not been confirmed. Preserve the original submission and inspect its saved history.');}
  }
  async function retry(){try{if(await client.submit()){setReplacement('');setNotice('Original correction confirmed.');setRevision(n=>n+1);}}catch{setNotice('The original submission still needs confirmation. Recheck saved history before trying again.');}}
  function refused(){if(pending?.snapshot_id===snapshot.snapshot_id){setReason(pending.reason);setReviewer(pending.reviewer_label);setReplacement(pending.replacement.version_id);}client.acknowledgeRefusal();}
  const inputHref=(version:string)=>`#/inputs/${snapshot.binding.dataset_id}/versions/${version}`;
  const cell=(c:ChangeCell)=>c.present?<span className="review-change-value">{c.text}{c.truncated&&<em>… preview truncated; inspect the complete package</em>}</span>:<em>Not present</em>;
  const links=(link:CorrectionLink,incoming:boolean)=><article className="review-correction-record" key={link.record.id}>
    <p className="eyebrow">{incoming?'THIS REPORT USES A CORRECTED INPUT':'THIS INPUT HAS A RECORDED CORRECTION'}</p>
    <h4>{incoming?'Follow the evidence back.':'Continue from the replacement.'}</h4><p>{link.record.request.reason}</p>
    <p className="review-note-meta">{link.record.request.reviewer_label} · {savedInstant(link.record.recorded_at)} · local attribution, not authenticated approval</p>
    <p>{link.record.change_count} changed input/source fields. The earlier reports and their review records remain separate.</p>
    <div className="review-context-actions"><a className="nr-secondary-button" href={inputHref(link.record.request.replacement.version_id)}>Inspect corrected input & choose processing</a><a className="nr-source-button" href={inputHref(link.record.binding.version_id!)}>Inspect original input</a></div>
    <details><summary>Affected reports ({link.affected_reports.length})</summary><p>These reports retain the original input. They have not been rewritten or invalidated automatically.</p><ul>{link.affected_reports.map(r=><li key={r.id}><a href={'#/runs/'+r.id}>{r.title}</a><span className="review-note-meta"> · {r.id.slice(-8)} · {r.execution}</span></li>)}</ul></details>
    <details open={link.replacement_reports.length>0}><summary>Reports using the replacement ({link.replacement_reports.length})</summary>{link.replacement_reports.length?<ul>{link.replacement_reports.map(r=><li key={r.id}><a href={'#/runs/'+r.id}>{r.title}</a><span className="review-note-meta"> · {r.id.slice(-8)} · {r.execution}</span></li>)}</ul>:<p>No report has been saved for this replacement. Processing requires a separate request.</p>}</details>
  </article>;
  return <section className="review-corrections" aria-labelledby="review-correction-title">
    <div className="review-workspace-heading"><div><p className="eyebrow">CORRECT THE INPUT, KEEP THE TRAIL</p><h3 id="review-correction-title">A new version. A clear reason.</h3></div><button className="nr-secondary-button" disabled={loading} onClick={()=>setRevision(n=>n+1)}>Recheck correction history</button></div>
    <p>Use a separately imported, validated replacement package. Compare its changes and record why it replaces this input. Calculations, financial review and approval remain separate.</p>
    {loading&&<p role="status">Checking correction history and current source permissions…</p>}{error&&<div className="review-alert" role="alert"><p>{error}</p>{replacement&&<button className="nr-secondary-button" onClick={()=>setReplacement('')}>Clear selected comparison and recheck history</button>}</div>}
    {locked&&<div className="review-alert" role="status"><strong>{status.phase==='sending'?'Recording this correction…':status.phase==='refused'?'The correction was refused.':'The original correction needs confirmation.'}</strong><p>{status.foreignPending?'Reconnect to the original workspace before continuing.':'Keep this tab open. Retrieve saved history or retry the same submission before creating another. A full reload loses an unconfirmed retry identity.'}</p>
      {status.runId&&status.runId!==snapshot.binding.run_id&&<a href={'#/runs/'+status.runId}>Return to the original report</a>}
      {pending&&<details><summary>Inspect the original correction submission</summary><p>{pending.reviewer_label}</p><p>{pending.reason}</p><p>Replacement input: {pending.replacement.version_id}</p></details>}
      {pending&&status.phase==='unconfirmed'&&<button className="nr-secondary-button" onClick={retry}>Retrieve / retry same correction</button>}
      {pending&&status.phase==='refused'&&<button className="nr-secondary-button" onClick={refused}>Acknowledge correction refusal and edit</button>}
    </div>}
    {history?.incoming.map(link=>links(link,true))}{history?.outgoing.map(link=>links(link,false))}
    {history&&!history.outgoing.length&&<>
      {!history.corrections_enabled&&<p className="review-boundary">Correction recording is disabled. Retained lineage remains available to inspect.</p>}
      <details className="review-correction-guide"><summary>1 · Prepare and import the corrected package</summary><p>Download the original package from its input page. Correct the supported JSON fields and source references, and set <code>dataset.supersedes_version_id</code> to <code>{snapshot.binding.version_id}</code>.</p><p>The local operator must register valid permission for the replacement contents. Editing a figure does not extend the original source permission. Importing validates a new version and starts no calculation. PDF and document extraction are a later feature.</p><div className="review-context-actions"><a className="nr-source-button" href={inputHref(snapshot.binding.version_id!)}>Inspect / download original input</a><a className="nr-secondary-button" href={`#/inputs/${snapshot.binding.dataset_id}?corrects=${snapshot.binding.version_id}&report=${snapshot.binding.run_id}`}>Import a corrected package</a></div></details>
      <label className="review-correction-select">2 · Select a validated replacement<select aria-label="Validated replacement input" disabled={locked||loading} value={replacement} onChange={e=>setReplacement(e.target.value)}><option value="">Choose a successor version</option>{history.candidates.map(c=><option value={c.pin.version_id} key={c.pin.version_id}>{c.period} · {c.pin.version_id.slice(-8)} · {savedInstant(c.created_at)}</option>)}</select></label>
      {!history.candidates.length&&<p>No eligible successor is available. Import it into this same dataset with the original version’s lineage pointer, then recheck this history.</p>}
      {comparison&&<div className="review-change-comparison"><h4>What changes in the input?</h4><p>{comparison.change_count} changed fields · source/package changes, not a forecast of their effect on report results.</p>
        <div className="review-change-table"><table><thead><tr><th>Saved field</th><th>Original input</th><th>Replacement input</th></tr></thead><tbody>{comparison.changes.slice(page*10,page*10+10).map(d=><tr key={d.path}><th><code>{d.path}</code></th><td>{cell(d.before)}</td><td>{cell(d.after)}</td></tr>)}</tbody></table></div>
        <div className="review-pages"><button disabled={page===0} onClick={()=>setPage(p=>p-1)}>Previous changes</button><span>Page {page+1} of {Math.ceil(comparison.change_count/10)}</span><button disabled={(page+1)*10>=comparison.change_count} onClick={()=>setPage(p=>p+1)}>Next changes</button></div>
        <form className="review-note-form" onSubmit={e=>{e.preventDefault();void save();}}><h4>3 · Record the correction</h4><p>Review item: <strong>{target?.title||'Select an available review item above'}</strong>. Recording the link does not resolve that item or carry its notes into another report.</p>
          <label>Your name or analyst label<input aria-label="Correction analyst label" value={reviewer} onChange={e=>setReviewer(e.target.value)} maxLength={120} disabled={locked||!history.corrections_enabled}/></label>
          <label>Why is this correction needed?<textarea aria-label="Correction reason" rows={4} value={reason} onChange={e=>setReason(e.target.value)} maxLength={2000} disabled={locked||!history.corrections_enabled}/></label>
          <label className="review-attach"><input type="checkbox" checked={checked} onChange={e=>setChecked(e.target.checked)} disabled={locked||!history.corrections_enabled}/>I checked the replacement and its changes. Linking starts no job and grants no financial approval.</label>
          <button className="nr-secondary-button" type="submit" disabled={!canSave}>Record correction link</button>
        </form>
      </div>}
    </>}
    <p role="status" className="review-save-notice">{notice}</p>
  </section>;
}
