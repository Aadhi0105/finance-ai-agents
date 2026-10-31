import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import test from 'node:test';
import { artifactUrl, datasetRows, displaySourceText, fetchArtifact, fetchReport, parseReport, pointMetric, ReportFailure, responseFailure, summaryFindings, verifyOriginal } from '../src/reports/report-data.ts';
import { calendarDate, formatMetric } from '../src/reports/format.ts';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/research-snapshot.json', import.meta.url), 'utf8'));
const snapshot = () => structuredClone(fixture);
const signal = () => new AbortController().signal;
const jsonResponse = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const failure = (code) => (error) => error instanceof ReportFailure && error.code === code;

test('a captured synthetic view keeps its typed values, approval boundary and evidence links', () => {
  const { run, report } = snapshot();
  const parsed = parseReport(report, run);
  assert.equal(parsed.metrics.find(m => m.id === 'revenue').value, '32667300000');
  assert.equal(parsed.state.financial_approval, false);
  assert.equal(parsed.state.evidence_gate, 'held_for_review');
  assert.equal(parsed.evidence.find(e => e.id === parsed.metrics[0].evidence_refs[0]).pointer, '/analysis/get_financials/financials/revenue');
});

for (const [name, edit, code = 'saved_evidence_invalid'] of [
  ['schema version', (v) => { v.schema_version = 2; }, 'unsupported_report_schema'],
  ['approval upgrade', (v) => { v.state.financial_approval = true; }],
  ['wrong run', (v) => { v.identity.source_run_id = 'different'; }],
  ['stale source revision', (v) => { v.artifacts[0].sha256 = '0'.repeat(64); }],
  ['missing source', (v) => { v.artifacts.pop(); }],
  ['broken metric reference', (v) => { v.findings[0].content.metric_refs = ['missing']; }],
  ['broken evidence reference', (v) => { v.metrics[0].evidence_refs = ['missing']; }],
  ['duplicate identifiers', (v) => { v.metrics.push(v.metrics[0]); }],
  ['unknown template', (v) => { v.summary.template_id = 'unreviewed-model-prose'; }, 'unsupported_report_schema'],
  ['unrepresented broker research', (v) => { v.analyst_content.external_research.availability = 'available'; }, 'unsupported_report_schema'],
  ['withheld numeric value', (v) => { v.metrics[0].availability = 'withheld'; v.metrics[0].reason_codes = ['test_hold']; }],
  ['unknown currency', (v) => { v.metrics[0].currency = null; }],
  ['formatted value as data', (v) => { v.metrics[0].value = 'EUR 32.67bn'; }],
]) test(`refuses ${name} instead of presenting a partially trusted report`, () => {
  const { run, report } = snapshot(); edit(report);
  assert.throws(() => parseReport(report, run), failure(code));
});

test('summary observations exclude withheld metrics and diagnostic valuation', () => {
  const { run, report } = snapshot();
  const parsed = parseReport(report, run);
  parsed.metrics.find(m => m.id === 'revenue').availability = 'withheld';
  parsed.findings.unshift({ id: 'diagnostic', kind: 'observed_fact', visibility: 'main', content: {
    text: 'An illustrative valuation', metric_refs: ['weighted-valuation'], evidence_refs: [], review_refs: [], template_id: 'metric-observation-v1',
  } });
  const selected = summaryFindings(parsed);
  assert(selected.length > 0 && selected.length <= 3);
  assert(!selected.some(f => f.content.metric_refs.includes('revenue') || f.content.metric_refs.includes('weighted-valuation')));
});

test('an empty supported projection stays empty without inheriting catalogue display numbers', () => {
  const { run, report } = snapshot();
  report.metrics = []; report.findings = []; report.summary.metric_refs = [];
  report.tables = [];
  for (const section of report.sections) { section.metric_refs = []; section.finding_refs = []; section.table_refs = []; }
  report.analyst_content.market_consensus.metric_refs = [];
  const parsed = parseReport(report, run);
  assert.equal(parsed.metrics.length, 0);
  assert.equal(summaryFindings(parsed).length, 0);
  assert(run.metrics.length > 0); // The reader must not borrow these legacy formatted figures.
});

test('the expanded report exposes saved bridge, peer dates and explicit consensus availability', () => {
  const { run, report } = snapshot(); const parsed = parseReport(report, run);
  assert.equal(run.native_view.adapter_version, '1.1.0');
  assert(parsed.tables.some(t => t.id === 'equity-bridge'));
  assert(parsed.tables.some(t => t.id === 'peer-evidence'));
  assert.equal(parsed.metrics.find(m => m.id === 'dcf-net-debt').value, '-7500000000');
  assert.equal(parsed.analyst_content.market_consensus.availability, 'unavailable');
  assert.equal(parsed.analyst_content.external_research.availability, 'unavailable');
});

test('the original 1.0 saved presentation remains readable with explicit missing detail', () => {
  const old = JSON.parse(readFileSync(new URL('./fixtures/research-legacy.json', import.meta.url), 'utf8'));
  const parsed = parseReport(old.report, old.run);
  assert.equal(old.run.native_view.adapter_version, '1.0.0');
  assert(!parsed.tables.some(t => t.id === 'equity-bridge'));
  assert.equal(parsed.charts.find(c => c.id === 'valuation-scenarios').series[0].points[0].y, '530.89');
});

for (const [name, edit] of [
  ['chart evidence', r => { r.charts[0].series[0].points[0].evidence_refs = ['missing']; }],
  ['chart decimal', r => { r.charts[0].series[0].points[0].y = 'NaN'; }],
  ['withheld series', r => { r.charts[0].availability = 'withheld'; r.charts[0].reason_codes = ['test_hold']; }],
  ['diagnostic valuation label', r => { r.charts.find(c => c.id === 'valuation-scenarios').visibility = 'main'; }],
  ['table metric', r => { r.tables[0].rows[0].cells.find(c => c.kind === 'metric_ref').metric_id = 'missing'; }],
  ['table columns', r => { r.tables[0].rows[0].cells.pop(); }],
  ['section references', r => { r.sections[0].chart_refs = ['missing']; }],
  ['consensus references', r => { r.analyst_content.market_consensus.metric_refs = ['missing']; }],
]) test(`full analysis refuses invalid ${name}`, () => {
  const {run,report}=snapshot(); edit(report);
  assert.throws(() => parseReport(report,run),failure('saved_evidence_invalid'));
});

test('market tables retain warm-up gaps, genuine zero values and every supplied date', () => {
  const {run,report}=snapshot(), parsed=parseReport(report,run);
  const chart=parsed.charts.find(c => c.id==='prices');
  const rows=datasetRows(chart);
  assert.equal(rows[0].points[1].y,null);
  assert.equal(formatMetric(pointMetric(chart,rows[0].points[1])),'Unavailable');
  assert.equal(rows.length,new Set(chart.series.flatMap(s=>s.points.map(p=>p.x))).size);
  const drawdown=parsed.charts.find(c=>c.id==='drawdown');
  assert.equal(formatMetric(pointMetric(drawdown,drawdown.series[0].points[0])),'0.00%');
  chart.availability='withheld';
  assert.deepEqual(datasetRows(chart),[]);
});

test('saved provider periods and assumption codes are explained without inventing a fiscal year', () => {
  assert.equal(displaySourceText('model_default'),'Saved model default; analyst review required');
  assert.equal(displaySourceText('Provider estimate period: +1y'),'Next annual provider period (+1y)');
  assert.equal(displaySourceText('a source-specific description'),'a source-specific description');
});

test('formatting retains exact high-precision values and currency while compact labels can round', () => {
  const m = snapshot().report.metrics[0];
  assert.equal(formatMetric(m, true), 'EUR 32.67bn');
  assert.equal(formatMetric(m), 'EUR 32,667,300,000.00');
  m.value = '123456789012345678901234567890.12';
  assert.equal(formatMetric(m), 'EUR 123,456,789,012,345,678,901,234,567,890.12');
  m.value = '-12.345';
  assert.equal(formatMetric(m), 'EUR −12.345');
});

test('percentages, missing values and withholding never turn into a zero result', () => {
  const m = snapshot().report.metrics.find(m => m.id === 'operating-margin');
  assert.equal(formatMetric(m, true), '34.60%');
  m.value = '0.123456789';
  assert.equal(formatMetric(m), '12.3456789%');
  m.availability = 'withheld'; m.value = null;
  assert.equal(formatMetric(m, true), 'Withheld');
  m.availability = 'unavailable';
  assert.equal(formatMetric(m, true), 'Unavailable');
  m.availability = 'available'; m.value = '0';
  assert.equal(formatMetric(m, true), '0.00%');
});

test('calendar periods preserve their date and never use preparation time as a substitute', () => {
  assert.equal(calendarDate('2025-12-31'), '31 December 2025');
  assert.equal(calendarDate('2022–2025'), '2022–2025');
  assert.equal(calendarDate('2025-02-31'), '2025-02-31');
});

test('report requests stay read-only, uncached, abortable and bound to the saved run', async t => {
  const { run, report } = snapshot(); const controller = new AbortController();
  const mock = t.mock.method(globalThis, 'fetch', async () => jsonResponse(report));
  const parsed = await fetchReport(run, controller.signal);
  const [url, options] = mock.mock.calls[0].arguments;
  assert.equal(url, '/api/runs/research-example/report-view');
  assert.equal(options.method, undefined);
  assert.equal(options.cache, 'no-store'); assert.equal(options.redirect, 'error');
  assert.equal(options.signal, controller.signal);
  assert.equal(parsed.identity.source_run_id, run.source_run_id);
});

test('legacy and missing/invalid states remain distinct and raw server messages are withheld', async t => {
  const { run } = snapshot();
  const mock = t.mock.method(globalThis, 'fetch', async () => jsonResponse({ error: { code: 'native_view_unavailable', message: '/private/SECRET' } }, 409));
  await assert.rejects(fetchReport(run, signal()), failure('native_view_unavailable'));
  mock.mock.mockImplementation(async () => jsonResponse({ error: { code: 'saved_run_not_found' } }, 404));
  await assert.rejects(fetchReport(run, signal()), failure('saved_run_not_found'));
  const safe = await responseFailure(new Response('<p>/private/SECRET</p>', { status: 503 }));
  assert.equal(safe.code, 'saved_evidence_invalid'); assert(!safe.message.includes('SECRET'));
});

test('a malformed, oversized or HTML success response cannot become a report', async t => {
  const { run } = snapshot();
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response('{', { headers: { 'Content-Type': 'application/json' } }));
  await assert.rejects(fetchReport(run, signal()), failure('saved_evidence_invalid'));
  mock.mock.mockImplementation(async () => new Response('<p>not a report</p>', { headers: { 'Content-Type': 'text/html' } }));
  await assert.rejects(fetchReport(run, signal()), failure('saved_evidence_invalid'));
  mock.mock.mockImplementation(async () => new Response('{}', { headers: { 'Content-Type': 'application/json', 'Content-Length': String(8 * 1024 * 1024 + 1) } }));
  await assert.rejects(fetchReport(run, signal()), failure('saved_evidence_invalid'));
});

test('aborted navigation stays cancelled rather than surfacing a report error', async t => {
  const controller = new AbortController(); controller.abort();
  t.mock.method(globalThis, 'fetch', async () => { throw controller.signal.reason; });
  await assert.rejects(fetchReport(snapshot().run, controller.signal), { name: 'AbortError' });
});

test('a legacy original is offered only after the registered URL passes a fresh HEAD', async t => {
  const { run } = snapshot();
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response(null, { status: 200 }));
  assert.equal(await verifyOriginal(run, signal()), true);
  assert.equal(mock.mock.calls[0].arguments[1].method, 'HEAD');
  mock.mock.mockImplementation(async () => new Response(null, { status: 503 }));
  assert.equal(await verifyOriginal(run, signal()), false);
});

test('evidence controls refuse external, traversing and unregistered paths', () => {
  const { run } = snapshot(); const original = run.artifacts[0];
  assert.equal(artifactUrl(run, original), original.url);
  assert.throws(() => artifactUrl(run, { ...original, url: 'https://external.example/model.json' }), failure('saved_evidence_invalid'));
  assert.throws(() => artifactUrl(run, { ...original, name: '../.env', url: '/api/runs/research-example/files/../.env' }), failure('saved_evidence_invalid'));
  assert.throws(() => artifactUrl(run, { ...original, id: 'unregistered' }), failure('saved_evidence_invalid'));
});

test('download bytes must match the loaded inventory even after server checks succeed', async t => {
  const { run } = snapshot(); const bytes = Buffer.from('saved synthetic evidence\n');
  const artifact = { ...run.artifacts[0], bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
  run.artifacts[0] = artifact;
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response(bytes));
  assert.deepEqual(Buffer.from(await fetchArtifact(run, artifact, signal())), bytes);
  mock.mock.mockImplementation(async () => new Response('changed synthetic evidence'));
  await assert.rejects(fetchArtifact(run, artifact, signal()), failure('saved_evidence_invalid'));
});
