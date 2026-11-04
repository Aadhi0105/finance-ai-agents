import {useState,useSyncExternalStore} from 'react';
import type {PrivateClient} from './client';
import type {Version} from './data';
import {actions,safeError} from './data';
import {Alert} from './ui';

const scope={
 monitoring:{title:'Read the changes in your observations.',included:'Evaluate each supplied history against its declared analyst policy. Show the latest value, active breaches and changes after the initial baseline.',boundary:'This is a self-contained history assessment. It does not advance an earlier monitoring job, approve corrections or establish contractual compliance.'},
 events:{title:'Understand the supplied historical reactions.',included:'Fit the existing market model to each supplied estimation window and calculate historical abnormal returns around each event. Retain the exact sample and rejected-window evidence.',boundary:'Event dates, benchmark mapping, sampling and comparability remain unverified. Inference and forward scenarios stay held for review.'},
 news:{title:'Make sense of your supplied news.',included:'Filter articles by date and company mention, group matching text, then calculate diagnostic document tone with the exact supplied positive and negative word lists.',boundary:'Word counts do not understand context or negation. No company sentiment, broker opinion, model analysis or return forecast is implied. No matching words means unavailable tone.'}
};
export function LocalWorkflow({client,version}:{client:PrivateClient;version:Version}){
 const s=useSyncExternalStore(client.subscribe,client.getSnapshot),[confirmed,setConfirmed]=useState(false),[error,setError]=useState('');
 const content=scope[version.metadata.workflow as keyof typeof scope];
 return <section className="private-card private-local-analysis"><p className="eyebrow">03 / NEW LOCAL CALCULATIONS</p><h2>{content.title}</h2><p>{content.included}</p>
 <div className="private-run-summary"><span>Input version <strong>{version.id.slice(-8)}</strong></span><span>External requests <strong>0</strong></span><span>Paid inference <strong>Disabled</strong></span><span>Time limit <strong>120 seconds</strong></span></div>
 <div className="private-panel-note"><p>{content.boundary} Source permission, file integrity and financial review remain separate.</p></div>
 <div className="private-confirm-analysis"><h3>Confirm this exact assessment.</h3><p>The input contains the observations and selected policies, windows or word list. A new job calculates a native report from this version; importing alone has not started it.</p><label className="private-checkbox"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/><span>I reviewed version {version.id.slice(-8)} and its supplied parameters. I confirm this local assessment and understand the report requires review.</span></label></div>
 {!s.caps?.worker&&<Alert>The worker is disabled. The confirmed request will remain queued.</Alert>}
 <button className="primary-button" disabled={!confirmed||!version.eligible||!s.caps?.localWorkflows||!s.caps.jobs||s.jobState!=='idle'} onClick={async()=>{const route=location.hash;setError('');try{const job=await client.submit(version,120);if(job&&client.getSnapshot().connected&&location.hash===route)location.hash='#/jobs/'+job.id;}catch(e){setError(safeError(e).message);}}}>{actions[version.metadata.payload_format]}</button>{error&&<Alert>{error}</Alert>}</section>;
}
