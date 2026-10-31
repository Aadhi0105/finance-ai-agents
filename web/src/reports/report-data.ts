/** Read boundary for the first native reader; financial validation stays in Python. */
import type { Artifact, Run } from '../workspace-types';
import type { AnalystArea, ChartData, ChartPoint, SavedSection, TableCell, TableData } from './analysis-types';

export type Availability = 'available' | 'unavailable' | 'withheld' | 'not_applicable';
export type Unit = 'currency' | 'currency_per_share' | 'fraction' | 'multiple' | 'count' | 'score' | 'index' | 'p_value' | 'unknown';
export type Metric = {
  id: string; label: string; value: string | null; unit: Unit; currency: string | null;
  period_label: string; as_of: string | null; availability: Availability;
  visibility: 'main' | 'supporting' | 'diagnostic'; reason_codes: string[]; evidence_refs: string[];
};
export type TextBlock = { text: string; template_id: string; metric_refs: string[]; evidence_refs: string[]; review_refs: string[] };
export type Evidence = { id: string; artifact_id: string; source_id: string; pointer: string; label: string; transform: string; method: string | null };
export type ReviewItem = {
  id: string; category: string; impact: string; title: string; explanation: string; action: string;
  section_refs: string[]; source_check_refs: string[]; evidence_refs: string[];
};
export type NativeReport = {
  schema_version: 1; kind: 'keystone.report-view'; report_id: string; agent: 'agent1' | 'agent3'; workflow: 'research' | 'events' | 'news';
  identity: { title: string; entity: string; ticker: string | null; source_run_id: string; period_label: string; period_end: string | null; prepared_at: string };
  state: { execution: string; evidence_gate: string; financial_approval: false; data_classification: 'synthetic'; integrity: 'matched'; review_refs: string[] };
  artifacts: { id: string; name: string; sha256: string; source_schema: string }[];
  sources: { id: string; label: string; source_type: string; observed_at: string | null; published_at: string | null; retrieved_at: string | null; date_reason: string | null }[];
  summary: TextBlock; metrics: Metric[];
  findings: { id: string; kind: string; visibility: string; content: TextBlock }[];
  evidence: Evidence[]; review_items: ReviewItem[]; sections: SavedSection[];
  charts: ChartData[]; tables: TableData[];
  analyst_content: { keystone_scope: string; market_consensus: AnalystArea; external_research: AnalystArea };
  glossary: { term: string; definition: string }[];
};

const failures = {
  native_view_unavailable: ['Native report not available', 'This saved run has no report for the native reader. A verified original may still be available.'],
  unsupported_report_schema: ['Report version not supported', 'This reader cannot display the saved report version. No figures have been substituted.'],
  saved_evidence_invalid: ['Saved evidence needs attention', 'The report could not be verified against its saved evidence. Figures and downloads are unavailable until the workspace is checked.'],
  saved_run_not_found: ['Saved run not found', 'This run is no longer registered in the selected workspace.'],
  local_access_required: ['Local access required', 'Open the report from the same local Keystone address as the workspace.'],
  read_only_workspace: ['Read-only workspace', 'This workspace supports reading saved reports only.'],
  connection_unavailable: ['Cannot reach the saved report', 'Check that the local workspace server is running, then try again.'],
} as const;
export type FailureCode = keyof typeof failures;
export class ReportFailure extends Error {
  readonly title: string;
  readonly code: FailureCode;
  constructor(code: FailureCode) { super(failures[code][1]); this.code = code; this.title = failures[code][0]; }
}
const fail = (): never => { throw new ReportFailure('saved_evidence_invalid'); };
const object = (x: unknown): Record<string, unknown> => x !== null && typeof x === 'object' && !Array.isArray(x) ? x as Record<string, unknown> : fail();
const text = (x: unknown, limit = 1600): string => typeof x === 'string' && x.length <= limit ? x : fail();
const nullable = (x: unknown, limit = 240): string | null => x === null ? null : text(x, limit);
const array = (x: unknown, limit: number): unknown[] => Array.isArray(x) && x.length <= limit ? x : fail();
const strings = (x: unknown, limit = 5000): string[] => array(x, limit).map(v => text(v, 1200));
const member = <T extends string>(x: unknown, allowed: readonly T[]): T => allowed.includes(x as T) ? x as T : fail();
const unique = (rows: { id: string }[]) => { if (new Set(rows.map(r => r.id)).size !== rows.length) fail(); };

/** Validate fields the reader uses and bind them to the selected inventory snapshot.
 * The backend validates the complete report schema and all financial/source transforms.
 */
export function parseReport(value: unknown, run: Run): NativeReport {
  const raw = object(value), reg = run.native_view;
  const events = run.agent === 'agent3' && run.workflow === 'events';
  const news = run.agent === 'agent3' && run.workflow === 'news';
  const family = run.agent === 'agent1' && run.workflow === 'research' ? 'agent1-native-report'
    : events ? 'agent3-event-report' : news ? 'agent3-news-report' : null;
  if (raw.schema_version !== 1 || raw.kind !== 'keystone.report-view'
      || !family || !reg || reg.view_schema_version !== 1 || reg.adapter_id !== family || !['1.0.0', '1.1.0'].includes(reg.adapter_version)) {
    throw new ReportFailure('unsupported_report_schema');
  }
  if (raw.agent !== run.agent || raw.workflow !== run.workflow) fail();
  const identity = object(raw.identity), state = object(raw.state);
  for (const [field, expected] of Object.entries({ title: run.title, entity: run.entity, source_run_id: run.source_run_id,
    period_label: run.period, prepared_at: run.prepared_at })) if (identity[field] !== expected) fail();
  if (state.execution !== run.execution_status || state.financial_approval !== false
      || state.data_classification !== 'synthetic' || state.integrity !== 'matched') fail();
  const artifacts = array(raw.artifacts, 40).map(value => {
    const a = object(value), registered = run.artifacts.find(r => r.id === a.id);
    if (!registered || registered.name !== a.name || registered.sha256 !== a.sha256 || registered.kind !== 'evidence') fail();
    return { id: text(a.id, 80), name: text(a.name, 240), sha256: text(a.sha256, 64), source_schema: text(a.source_schema, 120) };
  });
  if (artifacts.length !== 2 || reg.source_artifact_ids.length !== 2
      || artifacts.some((a, i) => a.id !== reg.source_artifact_ids[i])
      || artifacts[0].source_schema !== (events || news ? 'agent3.run_bundle/1' : 'agent1.model/2') || artifacts[1].source_schema !== 'keystone.report-series/1') fail();
  const native = run.artifacts.find(a => a.id === reg.artifact_id);
  if (!native || native.kind !== 'report_view') fail();
  const sources = array(raw.sources, 40).map(value => {
    const s = object(value);
    return { id: text(s.id, 80), label: text(s.label, 240), source_type: text(s.source_type, 80),
      observed_at: nullable(s.observed_at), published_at: nullable(s.published_at), retrieved_at: nullable(s.retrieved_at), date_reason: nullable(s.date_reason, 1600) };
  });
  const evidence = array(raw.evidence, 5000).map(value => {
    const e = object(value);
    return { id: text(e.id, 80), artifact_id: text(e.artifact_id, 80), source_id: text(e.source_id, 80),
      pointer: text(e.pointer, 1200), label: text(e.label, 240), transform: text(e.transform, 80), method: nullable(e.method, 1600) };
  });
  const metrics = array(raw.metrics, 500).map(value => {
    const m = object(value);
    const metric: Metric = { id: text(m.id, 80), label: text(m.label, 160), value: nullable(m.value, 80),
      unit: member(m.unit, ['currency', 'currency_per_share', 'fraction', 'multiple', 'count', 'score', 'index', 'p_value', 'unknown']),
      currency: nullable(m.currency, 3), period_label: text(m.period_label, 160), as_of: nullable(m.as_of),
      availability: member(m.availability, ['available', 'unavailable', 'withheld', 'not_applicable']),
      visibility: member(m.visibility, ['main', 'supporting', 'diagnostic']),
      reason_codes: strings(m.reason_codes, 30), evidence_refs: strings(m.evidence_refs) };
    if (metric.availability === 'available') {
      if (metric.value === null || !/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(metric.value) || metric.unit === 'unknown') fail();
      if (!metric.evidence_refs.length || metric.unit === 'count' && metric.value !== null && !/^(?:0|[1-9][0-9]*)$/.test(metric.value)) fail();
      if ((metric.unit === 'currency' || metric.unit === 'currency_per_share') && !/^[A-Z]{3}$/.test(metric.currency || '')) fail();
    } else if (metric.value !== null || metric.reason_codes.length === 0) fail();
    return metric;
  });
  const block = (value: unknown): TextBlock => {
    const b = object(value);
    const templates = ['saved-summary-v1', 'metric-observation-v1', ...(events && reg.adapter_version === '1.1.0' ? ['event-study-summary-v1'] : []),
      ...(news && reg.adapter_version === '1.1.0' ? ['news-study-summary-v1'] : [])];
    if (!templates.includes(String(b.template_id))) throw new ReportFailure('unsupported_report_schema');
    return { text: text(b.text, 4000), template_id: text(b.template_id, 80), metric_refs: strings(b.metric_refs), evidence_refs: strings(b.evidence_refs), review_refs: strings(b.review_refs) };
  };
  const summary = block(raw.summary);
  const findings = array(raw.findings, 100).map(value => {
    const f = object(value);
    return { id: text(f.id, 80), kind: text(f.kind, 80), visibility: text(f.visibility, 80), content: block(f.content) };
  });
  const availability = (x: unknown) => member(x, ['available', 'unavailable', 'withheld', 'not_applicable'] as const);
  const visibility = (x: unknown) => member(x, ['main', 'supporting', 'diagnostic'] as const);
  const unit = (x: unknown) => member(x, ['currency', 'currency_per_share', 'fraction', 'multiple', 'count', 'score', 'index', 'p_value', 'unknown'] as const);
  const sections: SavedSection[] = array(raw.sections, 30).map(value => {
    const s = object(value);
    return { id: text(s.id, 80), title: text(s.title, 160), purpose: text(s.purpose, 400), availability: availability(s.availability),
      reason_codes: strings(s.reason_codes, 30), metric_refs: strings(s.metric_refs), finding_refs: strings(s.finding_refs),
      chart_refs: strings(s.chart_refs), table_refs: strings(s.table_refs), review_refs: strings(s.review_refs) };
  });
  const charts: ChartData[] = array(raw.charts, 20).map(value => {
    const c = object(value), x = object(c.x_axis), y = object(c.y_axis);
    const chart: ChartData = { id: text(c.id, 80), title: text(c.title, 160), purpose: text(c.purpose, 1000), type: text(c.type, 80),
      availability: availability(c.availability), visibility: visibility(c.visibility), reason_codes: strings(c.reason_codes, 30), review_refs: strings(c.review_refs),
      x_axis: { kind: member(x.kind, ['category', 'date', 'relative_session']), label: text(x.label, 120) },
      y_axis: { unit: unit(y.unit), currency: nullable(y.currency, 3), label: text(y.label, 120) },
      series: array(c.series, 20).map(value => {
        const s = object(value);
        const points: ChartPoint[] = array(s.points, 5000).map(value => {
          const p = object(value);
          const point = { id: text(p.id, 80), x: text(p.x, 160), label: text(p.label, 240), y: nullable(p.y, 80),
            evidence_refs: strings(p.evidence_refs), reason_codes: strings(p.reason_codes, 30) };
          if (point.y === null ? point.reason_codes.length === 0 : !/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(point.y)) fail();
          if (!point.evidence_refs.length) fail();
          if (x.kind === 'date') {
            const d = new Date(point.x + 'T12:00:00Z');
            if (!/^\d{4}-\d{2}-\d{2}$/.test(point.x) || Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== point.x) fail();
          }
          return point;
        });
        unique(points);
        if (new Set(points.map(p => p.x)).size !== points.length) fail();
        return { id: text(s.id, 80), label: text(s.label, 160), points };
      }) };
    unique(chart.series);
    if (chart.availability !== 'available') {
      if (chart.series.length || !chart.reason_codes.length) fail();
    } else {
      if (!chart.series.some(s => s.points.some(p => p.y !== null)) || chart.y_axis.unit === 'unknown') fail();
      if (['currency', 'currency_per_share'].includes(chart.y_axis.unit) && !/^[A-Z]{3}$/.test(chart.y_axis.currency || '')) fail();
    }
    if (['valuation-scenarios', 'peer-multiples'].includes(chart.id) && chart.visibility !== 'diagnostic') fail();
    return chart;
  });
  const tables: TableData[] = array(raw.tables, 30).map(value => {
    const t = object(value);
    const columns = array(t.columns, 20).map(value => { const c = object(value); return { id: text(c.id, 80), label: text(c.label, 120) }; });
    unique(columns);
    const rows = array(t.rows, 2000).map(value => {
      const r = object(value);
      const cells: TableCell[] = array(r.cells, 20).map(value => {
        const c = object(value), column_id = text(c.column_id, 80);
        if (c.kind === 'text') return { column_id, kind: 'text', text: text(c.text, 1000) };
        if (c.kind === 'metric_ref') return { column_id, kind: 'metric_ref', metric_id: text(c.metric_id, 80) };
        return fail();
      });
      if (cells.length !== columns.length || new Set(cells.map(c => c.column_id)).size !== columns.length
          || cells.some(c => !columns.some(col => col.id === c.column_id))) fail();
      return { id: text(r.id, 80), cells, evidence_refs: strings(r.evidence_refs) };
    });
    unique(rows);
    return { id: text(t.id, 80), title: text(t.title, 160), columns, rows, review_refs: strings(t.review_refs) };
  });
  if (charts.reduce((n, c) => n + c.series.reduce((n, s) => n + s.points.length, 0), 0) > 20_000
      || tables.reduce((n, t) => n + t.rows.reduce((n, r) => n + r.cells.length, 0), 0) > 20_000) fail();
  const analyst = object(raw.analyst_content);
  const area = (value: unknown): AnalystArea => {
    const a = object(value);
    const result = { availability: availability(a.availability), reason_codes: strings(a.reason_codes, 30), metric_refs: strings(a.metric_refs), evidence_refs: strings(a.evidence_refs) };
    if (result.availability !== 'available' && !result.reason_codes.length) fail();
    return result;
  };
  const analyst_content = { keystone_scope: member(analyst.keystone_scope, ['supported_facts_only', 'not_applicable']),
    market_consensus: area(analyst.market_consensus), external_research: area(analyst.external_research) };
  if (analyst_content.external_research.availability === 'available') throw new ReportFailure('unsupported_report_schema');
  const glossary = array(raw.glossary, 50).map(value => { const g = object(value); return { term: text(g.term, 160), definition: text(g.definition, 1600) }; });
  const review_items = array(raw.review_items, 200).map(value => {
    const r = object(value);
    return { id: text(r.id, 80), category: text(r.category, 80), impact: text(r.impact, 80), title: text(r.title, 160),
      explanation: text(r.explanation, 4000), action: text(r.action, 4000), section_refs: strings(r.section_refs),
      source_check_refs: strings(r.source_check_refs), evidence_refs: strings(r.evidence_refs) };
  });
  [artifacts, sources, evidence, metrics, findings, sections, review_items, charts, tables].forEach(unique);
  const ids = { evidence: new Set(evidence.map(e => e.id)), metrics: new Set(metrics.map(m => m.id)),
    reviews: new Set(review_items.map(r => r.id)), sections: new Set(sections.map(s => s.id)) };
  const references = (refs: string[], collection: Set<string>) => { if (refs.some(ref => !collection.has(ref))) fail(); };
  const checkBlock = (b: TextBlock) => { references(b.evidence_refs, ids.evidence); references(b.metric_refs, ids.metrics); references(b.review_refs, ids.reviews); };
  checkBlock(summary); findings.forEach(f => checkBlock(f.content));
  metrics.forEach(m => references(m.evidence_refs, ids.evidence));
  review_items.forEach(r => { references(r.evidence_refs, ids.evidence); references(r.section_refs, ids.sections); });
  charts.forEach(c => { references(c.review_refs, ids.reviews); c.series.forEach(s => s.points.forEach(p => references(p.evidence_refs, ids.evidence))); });
  tables.forEach(t => { references(t.review_refs, ids.reviews); t.rows.forEach(r => {
    references(r.evidence_refs, ids.evidence);
    r.cells.forEach(c => { if (c.kind === 'metric_ref') references([c.metric_id], ids.metrics); });
  }); });
  sections.forEach(s => {
    references(s.metric_refs, ids.metrics); references(s.finding_refs, new Set(findings.map(f => f.id)));
    references(s.chart_refs, new Set(charts.map(c => c.id))); references(s.table_refs, new Set(tables.map(t => t.id))); references(s.review_refs, ids.reviews);
    if (s.availability !== 'available' && !s.reason_codes.length) fail();
  });
  [analyst_content.market_consensus, analyst_content.external_research].forEach(a => {
    references(a.metric_refs, ids.metrics); references(a.evidence_refs, ids.evidence);
  });
  if (analyst_content.market_consensus.availability === 'available'
      && !analyst_content.market_consensus.metric_refs.some(id => metrics.some(m => m.id === id && m.availability === 'available'))) fail();
  if (metrics.some(m => m.id === 'weighted-valuation' && m.visibility !== 'diagnostic')) fail();
  if (events || news) {
    if (analyst_content.keystone_scope !== 'not_applicable'
        || [analyst_content.market_consensus, analyst_content.external_research].some(a => a.availability !== 'not_applicable' || a.metric_refs.length)) fail();
  }
  if (events) {
    if (metrics.some(m => !['event-count', 'issuer-count'].includes(m.id) && m.visibility !== 'diagnostic')) fail();
    for (const c of charts) {
      if (!['event-cases', 'event-path'].includes(c.id) || c.visibility !== 'diagnostic' || c.y_axis.unit !== 'fraction') fail();
      if (c.id === 'event-path' && (c.availability === 'available' || c.series.length)) throw new ReportFailure('unsupported_report_schema');
      if (c.id === 'event-cases' && (c.type !== 'bar' || c.x_axis.kind !== 'category')) fail();
    }
    if (metrics.some(m => m.id === 'p-value' && (m.unit !== 'p_value' || m.value !== null && !/^(?:0(?:\.[0-9]+)?|1(?:\.0+)?)$/.test(m.value)))) fail();
  }
  if (news) {
    const scoreInRange = (value: string) => /^-?(?:0(?:\.[0-9]+)?|1(?:\.0+)?)$/.test(value);
    for (const m of metrics) {
      if (/^coverage-(raw|ingested|after-relevance|after-dedup)$/.test(m.id)) {
        if (m.unit !== 'count') fail();
      } else if (/^published-tone(?:-[0-9]+)?$/.test(m.id)) {
        if (m.unit !== 'score' || m.availability !== 'withheld' || m.value !== null) fail();
      } else if (/^diagnostic-tone-[0-9]+$/.test(m.id)) {
        if (m.unit !== 'score' || m.visibility !== 'diagnostic' || m.value !== null && !scoreInRange(m.value)) fail();
      } else fail();
    }
    for (const c of charts) {
      if (c.type !== 'bar' || c.x_axis.kind !== 'category') fail();
      if (c.id === 'news-coverage') {
        if (c.y_axis.unit !== 'count' || c.series.some(s=>s.points.some(p=>p.y !== null && !/^(?:0|[1-9][0-9]*)$/.test(p.y)))) fail();
      } else if (c.id === 'news-story-tone') {
        if (c.y_axis.unit !== 'score' || c.visibility !== 'diagnostic' || c.series.some(s=>s.points.some(p=>p.y !== null && !scoreInRange(p.y)))) fail();
      } else fail();
    }
  }
  evidence.forEach(e => { if (!artifacts.some(a => a.id === e.artifact_id) || !sources.some(s => s.id === e.source_id)) fail(); });
  const review_refs = strings(state.review_refs); references(review_refs, ids.reviews);
  return { schema_version: 1, kind: 'keystone.report-view', report_id: text(raw.report_id, 80), agent: events || news ? 'agent3' : 'agent1', workflow: events ? 'events' : news ? 'news' : 'research',
    identity: { title: run.title, entity: run.entity, ticker: nullable(identity.ticker, 80), source_run_id: run.source_run_id,
      period_label: run.period, period_end: nullable(identity.period_end, 10), prepared_at: run.prepared_at },
    state: { execution: run.execution_status, evidence_gate: member(state.evidence_gate, ['passed_evidence_checks', 'held_for_review', 'unavailable']),
      financial_approval: false, data_classification: 'synthetic', integrity: 'matched', review_refs },
    artifacts, sources, summary, metrics, findings, evidence, review_items, sections, charts, tables, analyst_content, glossary };
}

export async function responseFailure(response: Response): Promise<ReportFailure> {
  try {
    const data = await response.json();
    if (data?.error && typeof data.error.code === 'string' && Object.hasOwn(failures, data.error.code)) return new ReportFailure(data.error.code as FailureCode);
  } catch { /* Never expose an HTML error page, path or raw server exception. */ }
  return new ReportFailure(response.status === 404 ? 'saved_run_not_found' : response.status === 403 ? 'local_access_required' : 'saved_evidence_invalid');
}

export async function fetchReport(run: Run, signal: AbortSignal): Promise<NativeReport> {
  let response: Response;
  try {
    response = await fetch(`/api/runs/${encodeURIComponent(run.id)}/report-view`, { signal, cache: 'no-store', redirect: 'error' });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new ReportFailure('connection_unavailable');
  }
  if (!response.ok) throw await responseFailure(response);
  try {
    if (!response.headers.get('content-type')?.includes('application/json') || Number(response.headers.get('content-length')) > 8 * 1024 * 1024) fail();
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength > 8 * 1024 * 1024) fail();
    const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
    return parseReport(value, run);
  } catch (error) {
    if (signal.aborted || error instanceof ReportFailure) throw error;
    throw new ReportFailure('saved_evidence_invalid');
  }
}

/** Only registered same-origin URLs are eligible for original/download controls. */
export function artifactUrl(run: Run, artifact: Artifact): string {
  const expected = `/api/runs/${encodeURIComponent(run.id)}/files/${artifact.name}`;
  const registered = run.artifacts.find(a => a.id === artifact.id);
  if (!registered || registered.name !== artifact.name || registered.sha256 !== artifact.sha256
      || registered.bytes !== artifact.bytes || registered.kind !== artifact.kind
      || artifact.url !== expected || !/^[a-z0-9][a-z0-9_-]{0,79}$/.test(run.id)
      || artifact.name.split('/').some(p => !/^[A-Za-z0-9_-][A-Za-z0-9_.-]*$/.test(p))) fail();
  return expected;
}

export async function fetchArtifact(run: Run, artifact: Artifact, signal: AbortSignal): Promise<ArrayBuffer> {
  const url = artifactUrl(run, artifact);
  if (artifact.bytes < 1 || artifact.bytes > 20_000_000) fail();
  let response: Response;
  try { response = await fetch(url, { signal, cache: 'no-store', redirect: 'error' }); }
  catch (error) { if (signal.aborted) throw error; throw new ReportFailure('connection_unavailable'); }
  if (!response.ok) throw await responseFailure(response);
  try {
    if (Number(response.headers.get('content-length')) > artifact.bytes) fail();
    const bytes = await response.arrayBuffer();
    signal.throwIfAborted();
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), n => n.toString(16).padStart(2, '0')).join('');
    signal.throwIfAborted();
    if (bytes.byteLength !== artifact.bytes || hash !== artifact.sha256) fail();
    return bytes;
  } catch (error) { if (signal.aborted || error instanceof ReportFailure) throw error; return fail(); }
}

export async function verifyOriginal(run: Run, signal: AbortSignal): Promise<boolean> {
  const artifact = run.artifacts.find(a => a.id === run.report_id && a.kind === 'report');
  if (!artifact) return false;
  try { return (await fetch(artifactUrl(run, artifact), { method: 'HEAD', signal, cache: 'no-store', redirect: 'error' })).ok; }
  catch { return false; }
}

export const coreMetricIds = ['revenue', 'operating-margin', 'free-cash-flow', 'revenue-growth-yoy'] as const;
export function summaryFindings(report: NativeReport) {
  return report.findings.filter(f => f.kind === 'observed_fact' && f.visibility === 'main'
    && f.content.metric_refs.length > 0 && f.content.metric_refs.every(id => report.metrics.some(m =>
      m.id === id && m.availability === 'available' && m.visibility === 'main'))).slice(0, 3);
}

/** Presentation alignment only: retain every supplied point; never interpolate. */
export function datasetRows(chart: ChartData) {
  if (chart.availability !== 'available') return [];
  const rows = new Map<string, { x: string; label: string; points: (ChartPoint | null)[] }>();
  chart.series.forEach((series, i) => series.points.forEach(point => {
    const row = rows.get(point.x) || { x: point.x, label: point.label, points: chart.series.map(() => null) };
    row.points[i] = point;
    rows.set(point.x, row);
  }));
  const result = [...rows.values()];
  return chart.x_axis.kind === 'date' ? result.sort((a, b) => a.x.localeCompare(b.x)) : result;
}

const labels: Record<string, string> = { model_default: 'Saved model default; analyst review required', equity_value: 'Equity value',
  positive_fcff_model: 'Positive-FCFF model', complete: 'Complete', screening_only: 'Screening diagnostics',
  trim_invalid_trailing_observations_only: 'Only invalid trailing observations may be trimmed',
  unverified: 'Unverified', unavailable: 'Unavailable', available: 'Recorded as available; review still applies',
  human_reviewed: 'Recorded human review; identity is not authenticated here', HELD_FOR_REVIEW: 'Held for review',
  HISTORICAL: 'Historical description only' };

export function displaySourceText(value: string) {
  if (labels[value]) return labels[value];
  const periods: Record<string, string> = { '0q': 'Current quarterly provider period (0q)', '+1q': 'Next quarterly provider period (+1q)',
    '0y': 'Current annual provider period (0y)', '+1y': 'Next annual provider period (+1y)' };
  if (value.startsWith('Provider estimate period: ')) return periods[value.slice('Provider estimate period: '.length)] || value;
  return value;
}

export function pointMetric(chart: ChartData, point: ChartPoint): Metric {
  return { id: point.id, label: point.label, value: point.y, unit: chart.y_axis.unit, currency: chart.y_axis.currency,
    availability: point.y === null ? 'unavailable' : 'available', visibility: chart.visibility, period_label: point.x,
    as_of: null, reason_codes: point.reason_codes, evidence_refs: point.evidence_refs };
}
