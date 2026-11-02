import type { Run } from '../workspace-types';

export const profiles = {
  research: { name: 'Equity research', action: 'Rebuild saved research', profile: 'rebuild-saved-research', agent: 'agent1' },
  monitoring: { name: 'Financial monitoring', action: 'Render saved monitoring', profile: 'render-saved-monitoring', agent: 'agent2' },
  events: { name: 'Past event reactions', action: 'Replay saved events', profile: 'replay-saved-events', agent: 'agent3' },
  news: { name: 'Company news', action: 'Replay saved news', profile: 'replay-saved-news', agent: 'agent3' },
  close: { name: 'Financial close', action: 'Render saved close', profile: 'render-saved-close', agent: 'agent4' },
} as const;
export type Workflow = keyof typeof profiles;
export type JobRequest = { schema_version: 1; workflow: Workflow; source_run_id: string; timeout_seconds: number };
export type Capabilities = { admission_enabled: boolean; worker_enabled: boolean; worker_status: 'running' | 'stopped' | 'not_enabled'; timeout_seconds_max: number };
export type JobState = 'queued' | 'running' | 'completed' | 'review_required' | 'source_changed' | 'failed' | 'outcome_unknown' | 'delivery_failed';
export type Job = {
  id: string; operationId: string; request: JobRequest; createdAt: string; status: JobState;
  startedAt: string | null; verifiedAt: string | null; finishedAt: string | null;
  workerEnabled: boolean; recoveryRequired: boolean; resultUrl: string | null;
};
export const eventNames = {
  admitted: 'Request saved', claimed: 'Worker started', inputs_verified: 'Saved inputs checked; processing started',
  prepared: 'Output checked; registration pending', registered: 'Report registered', recovered: 'Saved delivery recovered',
  failed: 'Processing or validation failed', source_changed: 'Source changed', interrupted: 'Outcome requires inspection', delivery_failed: 'Report delivery failed',
} as const;
export type JobEvent = { event: keyof typeof eventNames; created_at: string };
export type JobDetail = { job: Job; events: JobEvent[] };
export const stateNames: Record<JobState, string> = {
  queued: 'Queued', running: 'Running', completed: 'Report registered', review_required: 'Report ready · review required',
  source_changed: 'Source changed', failed: 'Failed · inspect evidence', outcome_unknown: 'Outcome uncertain', delivery_failed: 'Delivery needs recovery',
};
export const jobId = /^job-[a-f0-9]{32}$/;
const runId = /^[a-z0-9][a-z0-9_-]{0,79}$/;
const hash = /^[a-f0-9]{64}$/;
const states = Object.keys(stateNames);
type ObjectValue = Record<string, unknown>;
function object(v: unknown): ObjectValue { if (!v || typeof v !== 'object' || Array.isArray(v)) throw new JobFailure('unsupported_response'); return v as ObjectValue; }
function requireValue(ok: unknown): asserts ok { if (!ok) throw new JobFailure('unsupported_response'); }
function instant(v: unknown): v is string { return typeof v === 'string' && v.length <= 80 && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v)); }
const optionalInstant = (v: unknown) => v === null || instant(v);
export function workflow(v: unknown): v is Workflow { return typeof v === 'string' && Object.hasOwn(profiles, v); }

export function parseCapabilities(value: unknown): Capabilities {
  const v = object(value), p = object(v.profiles);
  requireValue(v.schema_version === 1 && v.classification === 'synthetic' && v.live_data_enabled === false && v.paid_models_enabled === false && v.financial_approval === false);
  requireValue(typeof v.admission_enabled === 'boolean' && typeof v.worker_enabled === 'boolean' && v.local_token_required === v.admission_enabled);
  requireValue(['running','stopped','not_enabled'].includes(String(v.worker_status)) && (v.worker_status === 'running') === v.worker_enabled);
  requireValue(!v.worker_enabled || v.admission_enabled);
  requireValue(v.timeout_seconds_max === 600 && v.max_requests === 12 && v.max_output_tokens === 48000 && v.max_pending_jobs === 20 && v.max_retained_jobs === 1000);
  const names = Object.keys(profiles);
  requireValue(Array.isArray(v.workflows) && v.workflows.length === (v.admission_enabled ? 5 : 0));
  requireValue(Object.keys(p).length === (v.admission_enabled ? 5 : 0));
  if (v.admission_enabled) requireValue(names.every(k => (v.workflows as unknown[]).includes(k) && p[k] === profiles[k as Workflow].profile));
  return { admission_enabled: v.admission_enabled, worker_enabled: v.worker_enabled, worker_status: v.worker_status as Capabilities['worker_status'], timeout_seconds_max: 600 };
}
export function parseRequest(value: unknown): JobRequest {
  const v = object(value);
  requireValue(Object.keys(v).sort().join(',') === 'schema_version,source_run_id,timeout_seconds,workflow');
  requireValue(v.schema_version === 1 && workflow(v.workflow) && typeof v.source_run_id === 'string' && runId.test(v.source_run_id));
  requireValue(Number.isInteger(v.timeout_seconds) && Number(v.timeout_seconds) >= 1 && Number(v.timeout_seconds) <= 600);
  return { schema_version: 1, workflow: v.workflow, source_run_id: v.source_run_id, timeout_seconds: Number(v.timeout_seconds) };
}
export function parseJob(value: unknown): Job {
  const v = object(value), request = parseRequest(v.request), x = object(v.execution), source = object(v.source);
  requireValue(v.schema_version === 2 && v.admission_schema_version === 1 && v.profile_version === 1 && x.schema_version === 1);
  requireValue(typeof v.job_id === 'string' && jobId.test(v.job_id) && v.operation_id === 'web-' + v.job_id.slice(4));
  requireValue(v.profile === profiles[request.workflow].profile && source.run_id === request.source_run_id && source.workflow === request.workflow);
  requireValue(v.live_data_enabled === false && v.paid_models_enabled === false && v.financial_approval === false && v.max_requests === 12 && v.max_output_tokens === 48000);
  requireValue(states.includes(String(v.status)) && x.status === v.status && instant(v.created_at));
  requireValue(typeof v.worker_enabled === 'boolean' && typeof v.recovery_required === 'boolean');
  requireValue(optionalInstant(x.started_at) && optionalInstant(x.inputs_verified_at) && optionalInstant(x.finished_at));
  const ready = v.status === 'completed' || v.status === 'review_required', queued = v.status === 'queued', running = v.status === 'running';
  requireValue(x.attempt === (queued ? 0 : 1) && (queued ? x.started_at === null : instant(x.started_at)));
  requireValue(queued || running ? x.finished_at === null : instant(x.finished_at));
  requireValue(running ? !v.recovery_required || !v.worker_enabled : v.recovery_required === ['outcome_unknown','delivery_failed'].includes(String(v.status)));
  const reasons: Record<string, string[]> = { queued:['waiting'], running:['processing'], completed:['registered','recovered'], review_required:['registered','recovered'], source_changed:['source_changed'], failed:['execution_failed'], outcome_unknown:['interrupted'], delivery_failed:['delivery_failed'] };
  requireValue(reasons[String(v.status)].includes(String(x.reason)));
  requireValue(['not_started','running','completed','review_required','failed_inspect_state','outcome_unknown'].includes(String(x.operation_status)));
  if (queued) requireValue(x.inputs_verified_at === null && x.result === null && x.operation_status === 'not_started');
  if (x.result !== null) {
    const result = object(x.result);
    requireValue(result.run_id === 'result-' + v.job_id.slice(4) && instant(x.inputs_verified_at));
    requireValue([result.manifest_sha256,result.run_sha256,result.operation_receipt_sha256].every(h => typeof h === 'string' && hash.test(h)));
  }
  if (ready || v.status === 'delivery_failed') requireValue(x.result !== null && ['completed','review_required'].includes(String(x.operation_status)));
  const resultUrl = ready ? '#/runs/result-' + v.job_id.slice(4) : null;
  requireValue(v.result_url === resultUrl);
  return { id: v.job_id, operationId: String(v.operation_id), request, createdAt: v.created_at, status: v.status as JobState,
    startedAt: x.started_at as string | null, verifiedAt: x.inputs_verified_at as string | null, finishedAt: x.finished_at as string | null,
    workerEnabled: v.worker_enabled, recoveryRequired: v.recovery_required, resultUrl };
}
export function parseList(value: unknown): { jobs: Job[]; next: string | null } {
  const v = object(value);
  requireValue(Array.isArray(v.jobs) && v.jobs.length <= 25 && typeof v.worker_enabled === 'boolean');
  const jobs = v.jobs.map(parseJob);
  requireValue(new Set(jobs.map(j => j.id)).size === jobs.length && jobs.every(j => j.workerEnabled === v.worker_enabled));
  requireValue(v.next_cursor === null || typeof v.next_cursor === 'string' && jobId.test(v.next_cursor) && v.next_cursor === jobs.at(-1)?.id);
  return { jobs, next: v.next_cursor as string | null };
}
export function parseDetail(value: unknown, id: string): JobDetail {
  const v = object(value), job = parseJob(v.job);
  requireValue(job.id === id && Array.isArray(v.events) && v.events.length >= 1 && v.events.length <= 50);
  const events = v.events.map(e => { const row = object(e); requireValue(typeof row.event === 'string' && Object.hasOwn(eventNames,row.event) && instant(row.created_at)); return { event: row.event as JobEvent['event'], created_at: row.created_at }; });
  requireValue(events[0].event === 'admitted' && events[0].created_at === job.createdAt);
  const last: Record<JobState, string[]> = { queued:['admitted'],running:['claimed','inputs_verified','prepared'],completed:['registered','recovered'],review_required:['registered','recovered'],source_changed:['source_changed'],failed:['failed'],outcome_unknown:['interrupted'],delivery_failed:['delivery_failed'] };
  requireValue(last[job.status].includes(events.at(-1)!.event));
  return { job, events };
}
export function eligibleRuns(runs: Run[]): Run[] {
  return runs.filter(r => runId.test(r.id) && workflow(r.workflow) && profiles[r.workflow].agent === r.agent && r.native_view?.view_schema_version === 1);
}
export function nextAction(job: Job): string {
  if (job.resultUrl) return 'Open the registered report and review its limitations. Financial approval has not been granted.';
  if (job.recoveryRequired || job.status === 'running' && !job.workerEnabled) return 'Preserve this job. The local operator must inspect saved evidence and, when verified, recover delivery without rerunning the processing.';
  if (job.status === 'queued') return job.workerEnabled ? 'Waiting for the worker. No processing attempt has started.' : 'Saved in the queue. Ask the local operator to enable the worker; leaving this page does not cancel the request.';
  if (job.status === 'running') return 'The worker is preparing inputs, processing saved evidence or registering output. Recorded events below show confirmed stages.';
  if (job.status === 'source_changed') return 'The saved source changed before processing. Inspect the source and its registration before deciding on a new request.';
  return 'The local operator must inspect private processing evidence before deciding on new work. This page cannot approve, cancel or retry the processing.';
}
const failures = {
  connection_unavailable: 'The local server could not be reached. Saved jobs may still be running. Refresh their status when the connection returns.',
  unsupported_response: 'The execution response could not be validated. Preserve existing jobs and check the local server.',
  job_access_required: 'Local access was refused or expired. Enter the current job-access token from the server’s private token file.',
  job_origin_refused: 'Open this workspace at the exact local address used to start its execution server.',
  job_request_invalid: 'The request was refused. Check the selected saved report and the processing limit.',
  job_request_too_large: 'The request exceeds the supported size.', job_media_type_refused: 'The request format was refused.',
  job_source_unavailable: 'The saved source is unavailable or unsupported. Recheck the workspace before requesting new work.',
  job_request_conflict: 'This request identity conflicts with saved history. Preserve it and ask the local operator to inspect.',
  job_capacity_reached: 'The job ledger or queue is full. Review existing jobs with the local operator.',
  job_control_busy: 'Local control is busy. You can resend the same request identity when it is available.',
  job_not_found: 'This job was not found in the selected local ledger.',
  job_store_unavailable: 'Local job history is unavailable. Preserve the ledger and ask the local operator to inspect.',
  execution_disabled: 'Job requests are disabled. The workspace remains available for reading saved reports.',
  request_pending: 'Resolve the existing submission before starting another request.',
} as const;
export class JobFailure extends Error {
  readonly code: keyof typeof failures;
  readonly admissionRefused: boolean;
  constructor(code: string, admissionRefused = false) { const known = Object.hasOwn(failures,code) ? code as keyof typeof failures : 'unsupported_response'; super(failures[known]); this.code = known; this.admissionRefused = admissionRefused; }
}
export async function responseError(response: Response): Promise<JobFailure> {
  try {
    const v = object(await response.json()), e = object(v.error), code = typeof e.code === 'string' ? e.code : 'unsupported_response';
    const refusals: Record<string,number> = { job_request_invalid:422,job_request_too_large:413,job_media_type_refused:415,job_source_unavailable:503,job_capacity_reached:409 };
    return new JobFailure(code,refusals[code] === response.status);
  }
  catch { return new JobFailure('unsupported_response'); }
}
