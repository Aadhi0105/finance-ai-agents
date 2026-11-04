import { InputFailure, safeError, responseError, obj, id, list, parseCapabilities, parseWorkspace, parseEntity, parseDataset, parsePage, parseVersion, parsePreview, parseReceipt, parseJob, jobRequest, localFormats } from './data.ts';
import type { Capabilities, Entity, Dataset, Version, Preview, Receipt, PrivateJob, JobRequest, Page } from './data.ts';

export function canonicalLocal(v:unknown):string {if(v===null||typeof v!=='object')return JSON.stringify(v);if(Array.isArray(v))return '['+v.map(canonicalLocal).join(',')+']';return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonicalLocal((v as Record<string,unknown>)[k])).join(',')+'}';}

type Workspace=ReturnType<typeof parseWorkspace>;
type PendingImport={preview:Preview;file:Blob;key:string;id:string|null;workspaceId:string};
type PendingJob={request:JobRequest;key:string;workspaceId:string};
export type Snapshot={caps:Capabilities|null;connected:boolean;connecting:boolean;workspace:Workspace|null;entities:Entity[];datasets:Dataset[];error:string;refreshing:boolean;importState:'idle'|'sending'|'unconfirmed'|'held';importReceipt:Receipt|null;importError:string;jobState:'idle'|'sending'|'unconfirmed'|'refused';jobError:string;mutationUnknown:boolean};
const empty:Snapshot={caps:null,connected:false,connecting:false,workspace:null,entities:[],datasets:[],error:'',refreshing:false,importState:'idle',importReceipt:null,importError:'',jobState:'idle',jobError:'',mutationUnknown:false};

/** One tab, one local authority. No credential, package, request key or private
 * response is written to browser storage, a URL, a log or an HTML attribute. */
export class PrivateClient {
  private token='';private epoch=0;private readSequence=0;
  private reads=new Set<AbortController>();private objects=new Set<string>();
  private listeners=new Set<()=>void>();private state:Snapshot={...empty};
  private importing:PendingImport|null=null;private submitting:PendingJob|null=null;private preparing=false;private creating=false;
  private fetcher:typeof fetch;private key:()=>string;private timeout:number;
  constructor(fetcher:typeof fetch=(...args)=>fetch(...args),key=()=> 'ui-'+crypto.randomUUID(),timeout=12000){this.fetcher=fetcher;this.key=key;this.timeout=timeout;}
  getSnapshot=()=>this.state;
  subscribe=(listener:()=>void)=>{this.listeners.add(listener);return()=>{this.listeners.delete(listener);};};
  private update(patch:Partial<Snapshot>){this.state={...this.state,...patch};this.listeners.forEach(f=>f());}
  disconnect=()=>{
    this.epoch++;this.readSequence++;this.token='';this.reads.forEach(c=>c.abort());this.reads.clear();
    this.objects.forEach(url=>URL.revokeObjectURL(url));this.objects.clear();
    this.update({...empty,caps:this.state.caps,mutationUnknown:this.state.mutationUnknown,
      importState:this.importing?'unconfirmed':'idle',jobState:this.submitting?'unconfirmed':'idle'});
  };
  private async raw(path:string,init:RequestInit={},secret=this.token,write=false):Promise<Response>{
    if(!/^\/api\/[A-Za-z0-9_/?=&.%-]+$/.test(path)||path.includes('..')||path.includes('//'))throw new InputFailure('unsupported_response');
    const c=new AbortController(),epoch=this.epoch;
    const abort=()=>c.abort();init.signal?.addEventListener('abort',abort,{once:true});if(init.signal?.aborted)c.abort();
    if(!write)this.reads.add(c);
    const timer=setTimeout(()=>c.abort(),write?75000:this.timeout);
    try{
      const headers=new Headers(init.headers);if(secret)headers.set('Authorization','Bearer '+secret);
      const r=await this.fetcher(path,{...init,headers,signal:c.signal,cache:'no-store',credentials:'omit',redirect:'error',referrerPolicy:'no-referrer'});
      const limit=r.ok?20_000_000:65536;
      if(Number(r.headers.get('content-length'))>limit)throw new InputFailure('unsupported_response');
      const reader=r.body?.getReader();const chunks:Uint8Array[]=[];let length=0;
      if(reader)try{for(;;){const v=await reader.read();if(v.done)break;length+=v.value.byteLength;if(length>limit)throw new InputFailure('unsupported_response');chunks.push(v.value);}}finally{try{await reader.cancel();}catch{/* Closed response. */}}
      c.signal.throwIfAborted();if(!write&&epoch!==this.epoch)throw new InputFailure('access_required');
      const bytes=new Uint8Array(length);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
      const response=new Response(bytes,{status:r.status,headers:r.headers});
      if(!r.ok){const error=await responseError(response);if(error.code==='access_required'&&epoch===this.epoch){this.disconnect();this.update({error:error.message});}throw error;}
      return response;
    }catch(e){throw safeError(e);}finally{clearTimeout(timer);this.reads.delete(c);init.signal?.removeEventListener('abort',abort);}
  }
  private async json(path:string,init:RequestInit={},secret=this.token,write=false):Promise<unknown>{
    const r=await this.raw(path,init,secret,write);if(!r.headers.get('content-type')?.includes('application/json'))throw new InputFailure('unsupported_response');
    try{return JSON.parse(await r.text());}catch{throw new InputFailure('unsupported_response');}
  }
  private async read(path:string){if(!this.state.connected||!this.token)throw new InputFailure('access_required');return this.json(path);}
  private post(path:string,body:unknown,key?:string){return this.json(path,{method:'POST',headers:{'Content-Type':'application/json',...(key?{'Idempotency-Key':key}:{})},body:JSON.stringify(body)},this.token,true);}
  async discover(){const epoch=this.epoch;try{const caps=parseCapabilities(await this.json('/api/execution',{},''));if(epoch===this.epoch)this.update({caps,error:''});}catch(e){if(epoch===this.epoch)this.update({caps:null,error:safeError(e).message});}}
  async connect(value:string){
    this.disconnect();const epoch=this.epoch,secret=value.trim();
    if(!/^[A-Za-z0-9_-]{43}$/.test(secret)){this.update({error:'Use the current local access token from the server’s private control folder.'});return;}
    this.update({connecting:true,error:''});
    try{
      const caps=parseCapabilities(await this.json('/api/execution',{},''));
      const workspace=parseWorkspace(await this.json('/api/workspace',{},secret));
      const [entities,datasets]=await Promise.all([this.json('/api/entities?limit=100',{},secret),this.json('/api/datasets?limit=100',{},secret)]);
      if(epoch!==this.epoch)return;
      this.token=secret;this.update({caps,connected:true,connecting:false,workspace,entities:parsePage(entities,parseEntity).items,datasets:parsePage(datasets,parseDataset).items,error:''});
    }catch(e){if(epoch===this.epoch)this.update({connecting:false,error:safeError(e).message});}
  }
  async refresh(){if(!this.state.connected)return;const epoch=this.epoch,seq=++this.readSequence;this.update({refreshing:true,error:''});
    try{const [w,e,d,c]=await Promise.all([this.read('/api/workspace'),this.read('/api/entities?limit=100'),this.read('/api/datasets?limit=100'),this.json('/api/execution',{},'')]);
      if(epoch===this.epoch&&seq===this.readSequence){const workspace=parseWorkspace(w);if(workspace.id!==this.state.workspace?.id)throw new InputFailure('access_required');this.update({workspace,entities:parsePage(e,parseEntity).items,datasets:parsePage(d,parseDataset).items,caps:parseCapabilities(c),error:''});}
    }catch(e){if(epoch===this.epoch&&seq===this.readSequence){const error=safeError(e);this.update({workspace:null,entities:[],datasets:[],error:error.message});}}
    finally{if(epoch===this.epoch&&seq===this.readSequence)this.update({refreshing:false});}
  }
  private async mutation(path:string,value:unknown){
    if(!this.state.connected||!this.state.caps?.imports||this.state.mutationUnknown||this.creating)throw new InputFailure('input_disabled');const epoch=this.epoch;this.creating=true;
    try{const result=await this.post(path,value);if(epoch!==this.epoch){this.update({mutationUnknown:true});return null;}await this.refresh();return result;}
    catch(e){if(!safeError(e).refused)this.update({mutationUnknown:true});throw safeError(e);}finally{this.creating=false;}
  }
  async createEntity(value:unknown){const result=await this.mutation('/api/entities',value);return result===null?null:parseEntity(result);}
  async createDataset(value:unknown){const result=await this.mutation('/api/datasets',value);return result===null?null:parseDataset(result);}
  acknowledgeMutation(){this.update({mutationUnknown:false});}
  async versions(dataset:string,before:string|null=null):Promise<Page<Version>>{return parsePage(await this.read(`/api/datasets/${id(dataset)}/versions?limit=25${before?'&before='+id(before):''}`),parseVersion);}
  async version(dataset:string,version:string){const v=parseVersion(await this.read(`/api/datasets/${id(dataset)}/versions/${id(version)}`));if(v.id!==version||v.dataset_id!==dataset)throw new InputFailure('unsupported_response');return v;}
  async imports(before:string|null=null):Promise<Page<Receipt>>{return parsePage(await this.read('/api/imports?limit=25'+(before?'&before='+id(before):'')),parseReceipt);}
  async receipt(ident:string){const r=parseReceipt(await this.read('/api/imports/'+id(ident)));if(r.id!==ident)throw new InputFailure('unsupported_response');return r;}
  async inspect(dataset:Dataset,file:File):Promise<Preview>{
    if(!this.state.caps?.imports)throw new InputFailure('input_disabled');
    if(this.importing||!file.name.toLowerCase().endsWith('.json')||file.size<1||file.size>((dataset.payload_format==='agent1.financial-kit/1'||localFormats.includes(dataset.payload_format))?1_000_000:20_000_000))throw new InputFailure(this.importing?'input_busy':'input_too_large');
    const epoch=this.epoch;
    // The server computes Python's exact canonical payload hash. Browsers never
    // reinterpret integers/floats or rewrite the submitted JSON package.
    const response=await this.json(`/api/datasets/${id(dataset.id)}/inspect`,{method:'POST',headers:{'Content-Type':'application/json'},body:file});
    const preview=parsePreview(response,dataset);
    const hash=await this.hash(await file.arrayBuffer());
    if(epoch!==this.epoch)throw new InputFailure('access_required');
    if(preview.bytes!==file.size||preview.package_sha256!==hash)throw new InputFailure('unsupported_response');return preview;
  }
  async importPackage(preview?:Preview,file?:Blob):Promise<Receipt|null>{
    if(!this.state.connected||!this.state.caps?.imports)return null;
    if(this.state.importState==='sending')return null;
    if(!this.importing){if(!preview||!file)return null;this.importing={preview,file,key:this.key(),id:null,workspaceId:this.state.workspace!.id};}
    else if(preview||file)throw new InputFailure('input_conflict');
    const pending=this.importing,epoch=this.epoch,wasUnconfirmed=['unconfirmed','held'].includes(this.state.importState);
    if(pending.workspaceId!==this.state.workspace?.id)throw new InputFailure('input_conflict');
    this.update({importState:'sending',importError:''});
    try{
      let receipt:Receipt;
      if(pending.id===null){const r=obj(await this.post('/api/imports',pending.preview.descriptor,pending.key));if(typeof r.replayed!=='boolean')throw new InputFailure('unsupported_response');receipt=parseReceipt(r.import_attempt);pending.id=receipt.id;}
      else receipt=await this.receipt(pending.id);
      if(receipt.dataset_id!==pending.preview.dataset_id)throw new InputFailure('unsupported_response');
      if(epoch!==this.epoch)throw new InputFailure();
      this.update({importReceipt:receipt});
      if(receipt.state==='reserved'||receipt.state==='interrupted'){
        receipt=parseReceipt(await this.json('/api/imports/'+receipt.id+'/package',{method:'PUT',headers:{'Content-Type':'application/json','Idempotency-Key':pending.key},body:pending.file},this.token,true));
        if(receipt.id!==pending.id||receipt.dataset_id!==pending.preview.dataset_id)throw new InputFailure('unsupported_response');
      }
      if(epoch!==this.epoch)throw new InputFailure();
      if(receipt.state==='accepted'||receipt.state==='rejected'){
        this.importing=null;this.update({importState:'idle',importReceipt:receipt,importError:''});return receipt;
      }
      this.update({importState:'held',importReceipt:receipt,importError:'Inspect this saved receipt. Active validation must finish; prepared delivery recovery is an operator action.'});return receipt;
    }catch(e){const error=safeError(e);if(error.refused&&pending.id===null&&!wasUnconfirmed){this.importing=null;this.update({importState:'idle',importError:error.message});}else this.update({importState:'unconfirmed',importError:error.message});return null;}
  }
  async jobs(before:string|null=null):Promise<Page<PrivateJob>>{const r=obj(await this.read('/api/jobs?limit=25'+(before?'&before='+id(before):'')));return {items:list(r.jobs,25).map(v=>parseJob(v,this.state.workspace!.id)),next:r.next_cursor===null?null:id(r.next_cursor)};}
  async job(ident:string){const r=obj(await this.read('/api/jobs/'+id(ident))),job=parseJob(r.job,this.state.workspace!.id);if(job.id!==ident)throw new InputFailure('unsupported_response');return {job,events:list(r.events,50).map(x=>{const e=obj(x);return {event:String(e.event).slice(0,80),created_at:String(e.created_at).slice(0,80)};})};}
  async submit(version?:Version,timeout=600,selection?:{analysis_plan:Record<string,unknown>;reviewed:boolean}):Promise<PrivateJob|null>{
    if(!this.state.connected||!this.state.caps?.jobs||this.state.jobState==='sending'||this.preparing)return null;
    if(!this.submitting){if(!version)return null;const epoch=this.epoch;this.preparing=true;this.update({jobState:'sending',jobError:''});try{const checked=await this.version(version.dataset_id,version.id);if(epoch!==this.epoch)return null;if(checked.contract_sha256!==version.contract_sha256)throw new InputFailure('input_conflict');let request:JobRequest;if(checked.metadata.payload_format==='agent1.financial-kit/1'){if(!selection||!Number.isInteger(timeout)||timeout<1||timeout>120||selection.analysis_plan.valuation&&!selection.reviewed)throw new InputFailure('input_invalid',true);const source={kind:'dataset_version' as const,dataset_id:checked.dataset_id,version_id:checked.id,contract_sha256:checked.contract_sha256};const hash=async(v:unknown)=>this.hash(new TextEncoder().encode(canonicalLocal(v)).buffer as ArrayBuffer);request={schema_version:3,workflow:'research',source,analysis_plan:selection.analysis_plan,assumption_review:selection.analysis_plan.valuation?{acknowledged:true,source_reference_sha256:await hash(source),analysis_plan_sha256:await hash(selection.analysis_plan)}:null,timeout_seconds:timeout};}else request=jobRequest(checked,timeout);this.submitting={request,key:this.key(),workspaceId:this.state.workspace!.id};}catch(e){if(epoch===this.epoch)this.update({jobState:'idle',jobError:safeError(e).message});throw safeError(e);}finally{this.preparing=false;}}
    else if(version)throw new InputFailure('input_conflict');
    const pending=this.submitting,epoch=this.epoch,wasUnconfirmed=this.state.jobState==='unconfirmed';if(pending.workspaceId!==this.state.workspace?.id)throw new InputFailure('input_conflict');
    this.update({jobState:'sending',jobError:''});
    try{const r=obj(await this.post('/api/jobs',pending.request,pending.key));if(typeof r.replayed!=='boolean')throw new InputFailure('unsupported_response');const job=parseJob(r.job,pending.workspaceId);
      if(canonicalLocal(job.request)!==canonicalLocal(pending.request))throw new InputFailure('unsupported_response');
      if(epoch!==this.epoch)throw new InputFailure();this.submitting=null;this.update({jobState:'idle',jobError:''});return job;
    }catch(e){const error=safeError(e);this.update({jobState:error.refused&&!wasUnconfirmed?'refused':'unconfirmed',jobError:error.message});return null;}
  }
  clearRefusedJob(){if(this.state.jobState==='refused'){this.submitting=null;this.update({jobState:'idle',jobError:''});}}
  private async hash(bytes:ArrayBuffer){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');}
  downloadBytes(bytes:ArrayBuffer,name:string){const url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'}));this.objects.add(url);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>{URL.revokeObjectURL(url);this.objects.delete(url);},1000);}
  async downloadInput(version:Version,name:string){const proof=version.files[name];if(!proof||!['package.json','payload.json','validation.json','context.json','preflight.json','contract.json'].includes(name))throw new InputFailure('unsupported_response');
    const epoch=this.epoch,r=await this.raw(`/api/datasets/${id(version.dataset_id)}/versions/${id(version.id)}/files/${name}`);const bytes=await r.arrayBuffer();if(epoch!==this.epoch)throw new InputFailure('access_required');if(bytes.byteLength!==proof.bytes||await this.hash(bytes)!==proof.sha256)throw new InputFailure('input_unavailable');if(epoch!==this.epoch)throw new InputFailure('access_required');this.downloadBytes(bytes,name);
  }
  authenticatedFetch:typeof fetch=async(input,init)=>{
    if(!this.state.connected||!this.token)throw new InputFailure('access_required');
    if(typeof input!=='string'||!input.startsWith('/api/runs/'))throw new InputFailure('unsupported_response');
    return this.raw(input,init);
  };
}
