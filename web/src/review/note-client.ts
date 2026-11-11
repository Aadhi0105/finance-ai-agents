import {digest,shaText,type ReviewSnapshot} from './review-data.ts';
import {parseNote,type NoteRequest,type Notebook,type ReviewNote} from './notes-data.ts';

export type NoteWriter=(path:string,body:NoteRequest,key:string,workspaceId:string)=>Promise<unknown>;
type Pending={snapshot:ReviewSnapshot;body:NoteRequest;key:string};
type Phase='idle'|'sending'|'unconfirmed'|'refused';
export type NoteStatus={phase:Phase;runId:string|null;snapshotId:string|null;foreignPending:boolean;lastSavedId:string|null};

/** One in-memory submission per local connection, retained across navigation.
 * Disconnect hides its metadata. An uncertain outcome keeps the exact key/body.
 */
export class ReviewNoteClient{
  private workspace:string|null=null;private epoch=0;private pending:Pending|null=null;
  private phase:Phase='idle';private lastSavedId:string|null=null;private listeners=new Set<()=>void>();
  private state:NoteStatus={phase:'idle',runId:null,snapshotId:null,foreignPending:false,lastSavedId:null};
  private writer:NoteWriter|undefined;private key:()=>string;
  constructor(writer?:NoteWriter,key=()=> 'note-'+crypto.randomUUID()){this.writer=writer;this.key=key;}
  getSnapshot=()=>this.state;
  subscribe=(listener:()=>void)=>{this.listeners.add(listener);return()=>{this.listeners.delete(listener);};};
  private publish(){
    const same=this.pending?.snapshot.binding.workspace_id===this.workspace;
    this.state={phase:this.workspace?this.phase:'idle',runId:same?this.pending!.snapshot.binding.run_id:null,
      snapshotId:same?this.pending!.snapshot.snapshot_id:null,foreignPending:!!this.workspace&&!!this.pending&&!same,lastSavedId:this.workspace?this.lastSavedId:null};
    this.listeners.forEach(f=>f());
  }
  activate(workspace:string){this.workspace=workspace;this.epoch++;this.lastSavedId=null;this.publish();}
  clearAccess(){this.workspace=null;this.epoch++;this.lastSavedId=null;if(this.pending)this.phase='unconfirmed';this.publish();}
  pendingRequest(snapshotId:string):NoteRequest|null{return this.workspace&&this.pending?.snapshot.binding.workspace_id===this.workspace&&this.pending.snapshot.snapshot_id===snapshotId?structuredClone(this.pending.body):null;}
  acknowledgeRefusal(){if(this.phase!=='refused')return;this.pending=null;this.phase='idle';this.publish();}
  async reconcile(notebook:Notebook):Promise<ReviewNote|null>{
    const p=this.pending,epoch=this.epoch;
    if(!p||this.workspace!==notebook.workspace_id||p.snapshot.binding.workspace_id!==notebook.workspace_id||p.snapshot.binding.run_id!==notebook.run_id)return null;
    const kh=await shaText(p.key),fp=await digest({run_id:notebook.run_id,request:p.body});
    if(epoch!==this.epoch||this.pending!==p)return null;
    const note=[...notebook.notes,...notebook.earlier_scope_notes].find(n=>n.request_key_sha256===kh);
    if(!note)return null;
    if(note.request_sha256!==fp)throw new Error('Submission receipt mismatch.');
    this.pending=null;this.phase='idle';this.lastSavedId=note.id;this.publish();return note;
  }
  async submit(snapshot?:ReviewSnapshot,body?:NoteRequest):Promise<ReviewNote|null>{
    if(this.phase==='sending')return null;
    if(!this.writer||!this.workspace)throw new Error('Local note access required.');
    if(snapshot||body){
      if(!snapshot||!body||this.pending||snapshot.binding.workspace_id!==this.workspace)throw new Error('Preserve the existing note request.');
      this.pending={snapshot:structuredClone(snapshot),body:structuredClone(body),key:this.key()};
    }
    const p=this.pending;if(!p||p.snapshot.binding.workspace_id!==this.workspace)throw new Error('Reconnect to the original note workspace.');
    const epoch=this.epoch,wasUnconfirmed=this.phase==='unconfirmed';this.phase='sending';this.publish();
    try{
      const raw=await this.writer(`/api/runs/${encodeURIComponent(p.snapshot.binding.run_id)}/review-notes`,p.body,p.key,this.workspace);
      if(!raw||typeof raw!=='object')throw new Error('Unconfirmed response.');
      const result=raw as Record<string,unknown>;
      if(typeof result.replayed!=='boolean'||result.financial_approval!==false)throw new Error('Unconfirmed response.');
      const note=await parseNote(result.note,p.snapshot);
      if(note.request_key_sha256!==await shaText(p.key)||note.request_sha256!==await digest({run_id:p.snapshot.binding.run_id,request:p.body}))throw new Error('Submission receipt mismatch.');
      if(epoch!==this.epoch)throw new Error('Access changed during submission.');
      if(this.pending===p){this.pending=null;this.phase='idle';this.lastSavedId=note.id;this.publish();}
      return note;
    }catch(error){
      if(this.pending===p){this.phase=!wasUnconfirmed&&epoch===this.epoch&&!!(error as {refused?:boolean})?.refused?'refused':'unconfirmed';this.publish();}
      throw new Error(this.phase==='refused'?'The note was refused. Review the scope before retrying.':'The note outcome is unconfirmed. Retrieve or retry this same note.');
    }
  }
}
