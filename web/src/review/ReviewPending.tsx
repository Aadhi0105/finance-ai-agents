import {useSyncExternalStore} from 'react';
import type {ReviewNoteClient} from './note-client';

export function ReviewPending({client}:{client:ReviewNoteClient}){
  const state=useSyncExternalStore(client.subscribe,client.getSnapshot);
  if(state.phase==='idle')return null;
  return <div className="private-pending" role="status"><strong>{state.phase==='sending'?'Saving the selected review note':state.phase==='refused'?'Review note refused':'Review note confirmation needs attention'}</strong>
    <p>{state.foreignPending?'An earlier workspace has a pending note. Reconnect there before submitting another note.':state.phase==='sending'?'The note is bound to its exact report and review item.':'Return to the original report to retrieve its saved note or retry the same submission.'}</p>
    {state.runId&&<a className="text-button" href={'#/runs/'+state.runId}>Open the original report</a>}
  </div>;
}
