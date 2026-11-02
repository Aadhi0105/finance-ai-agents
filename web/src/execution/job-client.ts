import { JobFailure, jobId, parseCapabilities, parseDetail, parseJob, parseList, parseRequest, responseError } from './job-data.ts';
import type { Capabilities, Job, JobDetail, JobRequest } from './job-data.ts';

type Pending = { request: JobRequest; state: 'sending' | 'unconfirmed' | 'refused'; error: string | null };
export type ExecutionSnapshot = {
  capabilities: Capabilities | null; capabilityError: string; connected: boolean; connecting: boolean;
  jobs: Job[]; next: string | null; cursor: string | null; listError: string; checkedAt: string | null; listing: boolean;
  detail: JobDetail | null; detailError: string; detailCheckedAt: string | null;
  pending: Pending | null; refreshing: boolean;
};
// One in-memory session for this application tab. Neither tokens nor submission
// keys enter browser storage, URLs, DOM attributes or error strings.
export class JobClient {
  private token = '';
  private epoch = 0;
  private listeners = new Set<() => void>();
  private activeReads = new Set<AbortController>();
  private pendingKey: string | null = null;
  private selected: string | null = null;
  private detailSequence = 0;
  private listSequence = 0;
  private capabilitySequence = 0;
  private refreshLock = false;
  private state: ExecutionSnapshot = { capabilities: null, capabilityError: '', connected: false, connecting: false,
    jobs: [], next: null, cursor: null, listError: '', checkedAt: null, listing: false, detail: null, detailError: '', detailCheckedAt: null, pending: null, refreshing: false };
  private fetcher: typeof fetch;
  private makeKey: () => string;
  private requestTimeout: number;
  constructor(fetcher: typeof fetch = (...args) => fetch(...args), makeKey = () => 'ui-' + crypto.randomUUID(), requestTimeout = 12000) {
    this.fetcher = fetcher; this.makeKey = makeKey; this.requestTimeout = requestTimeout;
  }
  getSnapshot = (): ExecutionSnapshot => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(values: Partial<ExecutionSnapshot>) { this.state = { ...this.state, ...values }; this.listeners.forEach(f => f()); }
  private resetAccess() {
    this.epoch++; this.capabilitySequence++; this.token = ''; this.activeReads.forEach(c => c.abort()); this.activeReads.clear();
    this.update({ connected: false, connecting: false, jobs: [], next: null, cursor: null, checkedAt: null, listing: false,
      detail: null, detailCheckedAt: null, detailError: '', listError: '' });
  }
  disconnect = () => { this.resetAccess(); };
  private failure(error: unknown): JobFailure { return error instanceof JobFailure ? error : new JobFailure('connection_unavailable'); }
  private async request(path: string, init: RequestInit = {}, secret = '', read = true): Promise<{ status: number; data: unknown }> {
    const controller = new AbortController();
    if (read) this.activeReads.add(controller);
    const timer = setTimeout(() => controller.abort(), this.requestTimeout);
    try {
      const response = await this.fetcher(path, { ...init, signal: controller.signal, cache: 'no-store', credentials: 'omit',
        redirect: 'error', referrerPolicy: 'no-referrer', headers: { ...init.headers, ...(secret ? { Authorization: 'Bearer ' + secret } : {}) } });
      if (!response.ok) throw await responseError(response);
      // Consume while the request deadline still applies, including response bodies.
      let data: unknown;
      try { data = await response.json(); } catch { throw new JobFailure('unsupported_response'); }
      return { status: response.status, data };
    } catch (e) { throw this.failure(e); }
    finally { clearTimeout(timer); this.activeReads.delete(controller); }
  }
  async discover(): Promise<void> {
    const seq = ++this.capabilitySequence;
    try {
      const caps = parseCapabilities((await this.request('/api/execution')).data);
      if (seq !== this.capabilitySequence) return;
      if (!caps.admission_enabled && this.token) this.resetAccess();
      this.update({ capabilities: caps, capabilityError: '' });
    } catch (e) { if (seq === this.capabilitySequence) this.update({ capabilities: null, capabilityError: this.failure(e).message }); }
  }
  async connect(raw: string): Promise<void> {
    this.resetAccess();
    const secret = raw.trim(), epoch = this.epoch;
    if (!/^[A-Za-z0-9_-]{43}$/.test(secret)) { this.update({ listError: 'Use the current local job-access token from the private server file.' }); return; }
    if (!this.state.capabilities?.admission_enabled) { this.update({ listError: new JobFailure('execution_disabled').message }); return; }
    this.update({ connecting: true });
    try {
      const list = parseList((await this.request('/api/jobs?limit=25', {}, secret)).data);
      if (epoch !== this.epoch) return;
      this.token = secret;
      this.update({ connected: true, connecting: false, jobs: list.jobs, next: list.next, checkedAt: new Date().toISOString(), listError: '' });
      if (this.selected) await this.loadDetail();
    } catch (e) { if (epoch === this.epoch) this.update({ connecting: false, listError: this.failure(e).message }); }
  }
  private readError(e: unknown, epoch: number): JobFailure {
    const error = this.failure(e);
    if (epoch === this.epoch && error.code === 'job_access_required') this.resetAccess();
    return error;
  }
  async loadList(cursor: string | null = this.state.cursor): Promise<void> {
    if (!this.token || cursor !== null && !jobId.test(cursor)) return;
    const epoch = this.epoch, seq = ++this.listSequence;
    this.update({ cursor, listError: '', listing: true,
      ...(cursor !== this.state.cursor ? { jobs: [], next: null, checkedAt: null } : {}) });
    try {
      const list = parseList((await this.request('/api/jobs?limit=25' + (cursor ? '&before=' + cursor : ''), {}, this.token)).data);
      if (epoch === this.epoch && seq === this.listSequence) this.update({ jobs: list.jobs, next: list.next, checkedAt: new Date().toISOString() });
    } catch (e) {
      if (epoch !== this.epoch || seq !== this.listSequence) return;
      const error = this.readError(e,epoch); this.update({ jobs: [], next: null, checkedAt: null, listError: error.message });
    }
    finally { if (epoch === this.epoch && seq === this.listSequence) this.update({ listing: false }); }
  }
  select(id: string | null) {
    if (id === this.selected) return;
    this.selected = id; this.detailSequence++;
    this.update({ detail: null, detailError: '', detailCheckedAt: null });
    if (id !== null) void this.loadDetail();
  }
  async loadDetail(): Promise<void> {
    const id = this.selected;
    if (!this.token || id === null) return;
    if (!jobId.test(id)) { this.update({ detailError: new JobFailure('job_not_found').message }); return; }
    const epoch = this.epoch, seq = ++this.detailSequence;
    try {
      const detail = parseDetail((await this.request('/api/jobs/' + id, {}, this.token)).data,id);
      if (epoch === this.epoch && seq === this.detailSequence) this.update({ detail, detailError: '', detailCheckedAt: new Date().toISOString() });
    } catch (e) {
      if (epoch !== this.epoch || seq !== this.detailSequence) return;
      const error = this.readError(e,epoch); this.update({ detail: null, detailCheckedAt: null, detailError: error.message });
    }
  }
  async refresh(): Promise<void> {
    if (this.refreshLock) return;
    this.refreshLock = true; this.update({ refreshing: true });
    try { await this.discover(); if (this.token) await Promise.all([this.loadList(),this.loadDetail()]); }
    finally { this.refreshLock = false; this.update({ refreshing: false }); }
  }
  editRefused() {
    if (this.state.pending?.state !== 'refused') return;
    this.pendingKey = null; this.update({ pending: null });
  }
  async submit(value?: JobRequest): Promise<Job | null> {
    if (this.state.pending?.state === 'sending') return null;
    if (!this.token || !this.state.connected || !this.state.capabilities?.admission_enabled || this.state.capabilityError) return null;
    if (!this.state.pending) {
      if (!value) return null;
      const request = parseRequest(value), key = this.makeKey();
      if (!/^[A-Za-z0-9][A-Za-z0-9_-]{7,95}$/.test(key)) throw new JobFailure('unsupported_response');
      this.pendingKey = key;
      this.update({ pending: { request, state: 'sending', error: null } });
    } else {
      // Retry only this frozen request with its original identity.
      if (value) throw new JobFailure('request_pending');
      this.update({ pending: { ...this.state.pending, state: 'sending', error: null } });
    }
    const epoch = this.epoch, request = this.state.pending!.request, key = this.pendingKey!;
    try {
      const response = await this.request('/api/jobs', { method: 'POST', headers: { 'Content-Type':'application/json', 'Idempotency-Key':key }, body: JSON.stringify(request) }, this.token, false);
      const body = response.data as Record<string,unknown>;
      if (!body || typeof body !== 'object' || typeof body.replayed !== 'boolean' || response.status !== (body.replayed ? 200 : 202)) throw new JobFailure('unsupported_response');
      const job = parseJob(body.job);
      if (JSON.stringify(job.request) !== JSON.stringify(request)) throw new JobFailure('unsupported_response');
      if (epoch !== this.epoch) { this.update({ pending: { request, state:'unconfirmed', error: 'Access was cleared before confirmation. Reconnect and resend this same request to retrieve its saved identity.' } }); return null; }
      this.pendingKey = null; this.update({ pending: null });
      return job;
    } catch (e) {
      const error = this.readError(e,epoch);
      this.update({ pending: { request, state: error.admissionRefused ? 'refused' : 'unconfirmed', error: error.message } });
      return null;
    }
  }
}
