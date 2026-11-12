import {useSyncExternalStore} from 'react';
import type {ReviewDecisionClient} from './decision-client';
export function DecisionPending({client}:{client:ReviewDecisionClient}){
  const s=useSyncExternalStore(client.subscribe,client.getSnapshot);if(s.phase==='idle')return null;
  return <div className="private-pending" role="status"><strong>{s.phase==='sending'?'Saving the selected review decision':'Review decision confirmation needs attention'}</strong><p>{s.foreignPending?'Reconnect to the original workspace to inspect its pending decision.':'Return to the original report to retrieve saved history or retry this same decision.'}</p>{s.runId&&<a className="text-button" href={'#/runs/'+s.runId}>Open the original decision report</a>}</div>;
}
