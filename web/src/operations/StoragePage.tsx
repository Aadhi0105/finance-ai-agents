import {useEffect,useState,useSyncExternalStore} from 'react';
import type {PrivateClient} from '../onboarding/client';
import {Heading} from '../onboarding/ui';
import {storageAreas,storageBytes,type StorageView} from './storage';
import './operations.css';

export function StoragePage({client}:{client:PrivateClient}){
 const session=useSyncExternalStore(client.subscribe,client.getSnapshot);
 const [view,setView]=useState<StorageView|null>(null),[busy,setBusy]=useState(true),[error,setError]=useState(false),[attempt,setAttempt]=useState(0),[stale,setStale]=useState(false);
 useEffect(()=>{const controller=new AbortController();setBusy(true);setError(false);
  client.storage(controller.signal).then(v=>{if(!controller.signal.aborted){setView(v);setStale(false);}}).catch(()=>{if(!controller.signal.aborted){setView(null);setError(true);}}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
  return()=>controller.abort();
 },[client,session.workspaceId,attempt]);
 useEffect(()=>{if(!view)return;const timer=setTimeout(()=>setStale(true),60_000);return()=>clearTimeout(timer);},[view]);
 return <>
  <Heading eyebrow="THE EVIDENCE YOU KEEP" title="Storage, accounted for.">See the full local workspace footprint and understand what stays with each analysis.</Heading>
  <div className="ops-toolbar"><button className="primary-button" disabled={busy} onClick={()=>setAttempt(n=>n+1)}>{busy?'Checking storage…':'Recheck storage'}</button><a className="text-button" href="#/operations">View operating limits</a></div>
  {busy&&<p role="status">{view?'Rechecking. The previous inventory remains below until this check finishes.':'Reading the local file inventory…'}</p>}
  {error&&<div className="private-alert" role="alert"><h2>Storage could not be checked.</h2><p>Check local access and recheck. Preserve the workspace; unavailable evidence is never treated as zero.</p></div>}
  {view&&<>
   <section className={'private-card ops-summary ops-'+(view.state==='observed'?'ok':view.state)}>
    <p className="eyebrow">{busy?'PREVIOUS INVENTORY · RECHECKING':'LOCAL FILE INVENTORY'}</p>
    <h2>{view.state==='observed'?'Your evidence footprint':view.state==='attention'?'Storage needs inspection':'Some storage is unavailable'}</h2>
    <dl className="ops-counts"><div><dt>Retained file bytes</dt><dd>{storageBytes(view.total_bytes)}</dd></div><div><dt>Files observed</dt><dd>{view.total_files??'Unavailable'}</dd></div><div><dt>Free on this volume</dt><dd>{storageBytes(view.disk_free_bytes)}</dd></div></dl>
    <p>Observed <time dateTime={view.observed_at}>{new Date(view.observed_at).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'medium'})}</time>. {stale?'Older than one minute; recheck before acting.':'A point-in-time file inventory.'}</p>
    <p>File bytes describe logical size, including runtime files. They exclude admission reservations and are separate from free disk space. This is not a verification of every evidence link or a consistent backup.</p>
   </section>
   <section className="private-card"><p className="eyebrow">THE COMPLETE WORKSPACE ROOT</p><h2>What is taking space?</h2><div className="ops-table-wrap"><table><caption>All local workspace files, grouped by purpose</caption><thead><tr><th>Evidence area</th><th>Files</th><th>Size</th><th>Observation</th></tr></thead><tbody>{view.areas.map(a=><tr key={a.key}><th scope="row">{storageAreas[a.key][0]}<small className="storage-area-description">{storageAreas[a.key][1]}</small></th><td>{a.files??'Unavailable'}</td><td>{storageBytes(a.bytes)}</td><td>{a.state==='observed'?'Counted':a.state==='attention'?'Inspect':'Unavailable'}</td></tr>)}</tbody></table></div><p>Unrecognised files and unsafe or unreadable members require inspection. File names, paths, contents and access keys stay outside this response. Files elsewhere on this computer and external snapshots are outside this inventory.</p></section>
   <section className="private-card storage-policy"><p className="eyebrow">PRESERVE UNTIL REVIEWED</p><h2>History stays connected.</h2><p>Inputs, versions, reports, review records and accounting evidence are kept together. Replacing an input or recording a new decision adds history; it does not erase the earlier evidence.</p><ul><li>No automatic expiry, pruning or deletion.</li><li>Interrupted and rejected work remains available for inspection.</li><li>A source permission expiry or withdrawal holds further use; it does not silently erase evidence or settle any deletion obligation.</li><li>Document and PDF intake is planned separately. Original PDFs are not yet a supported intake type.</li></ul><p>Keystone has no workspace deletion control in this pilot. Do not clear folders to resolve a capacity refusal. Stop new work, inspect the limit and arrange authorised retention, recovery and disposal before changing saved files.</p></section>
   <details className="private-card ops-scope"><summary>Check the saved evidence more deeply</summary><p>The stopped-workspace audit checks retained input versions, review bindings, original job records, saved deliveries, registered artifacts and accounting state. It also checks snapshot permissions and compares evidence hashes before and after the check.</p><p>Stop this workspace’s server and worker first. From the repository, run:</p><pre className="storage-command">.venv/bin/python -m keystone.workspace audit-private --workspace YOUR_WORKSPACE</pre><p>Use the workspace folder supplied to Open Keystone. A verified result checks saved integrity and links; it does not authenticate sources or approve financial conclusions. Held or unavailable results need operator inspection. The audit never repairs, executes or deletes saved work.</p></details>
   <section className="private-card"><p className="eyebrow">RECOVERY IS A SEPARATE COMMITMENT</p><h2>Local files are one copy.</h2><p>A file inventory does not establish backup protection. Use the existing permission-checked snapshot and new-directory restore procedure. Independent encrypted backup, key recovery and a clean-machine drill remain pending.</p></section>
  </>}
 </>;
}
