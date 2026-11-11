import {useSyncExternalStore} from 'react';
import type {ReviewCorrectionClient} from './correction-client';
export function CorrectionPending({client}:{client:ReviewCorrectionClient}){
  const s=useSyncExternalStore(client.subscribe,client.getSnapshot);
  if(s.phase==='idle')return null;
  return <div className="private-pending" role="status"><strong>{s.phase==='sending'?'Recording the correction':'Correction confirmation needs attention'}</strong><p>{s.foreignPending?'Reconnect to the original workspace to inspect the correction.':'Return to the original report. Retrieve saved history or retry the original correction before creating another.'}</p>{s.runId&&<a className="text-button" href={'#/runs/'+s.runId}>Open the original correction report</a>}</div>;
}
