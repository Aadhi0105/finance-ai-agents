import type { NativeReport } from './report-data';
import { formatMetric } from './format';
import { DatasetTable, LocalReviews, SavedTable } from './AnalysisSections';
import { MetricCard, ReportSection } from './ReportFrame';
import './event-report.css';

type Props = { report: NativeReport; onInspect: (refs: string[]) => void; onReviews: (refs: string[]) => void };
function basis(report: NativeReport, field: string) {
  const cell = report.tables.find(t=>t.id==='event-basis')?.rows.find(r=>r.id===field)?.cells.find(c=>c.column_id==='value');
  return cell?.kind==='text' ? cell.text : 'Not retained in this presentation';
}
function DetailMissing({ children }: { children: React.ReactNode }) {
  return <div className="nr-empty"><h3>Saved detail unavailable</h3><p>{children}</p></div>;
}

export function EventSections({report,onInspect,onReviews}:Props) {
  const metric = (id: string) => report.metrics.find(m=>m.id===id);
  const table = (id: string) => report.tables.find(t=>t.id===id);
  const inference = metric('p-value');
  const sample = table('event-case-metadata'), peers=table('event-peer-selection'), exclusions=table('event-exclusions');
  const reviews = report.review_items.filter(r=>r.category==='statistical_eligibility').map(r=>r.id);
  return <>
    <ReportSection id="summary" eyebrow="01 / WHAT THE SAVED STUDY SHOWS" title="Study summary">
      <p className="nr-summary-text">{report.summary.text}</p>
      <div className="nr-event-metrics">{['event-count','issuer-count','mean-car'].flatMap(id=>{const m=metric(id);return m?[<MetricCard key={id} metric={m} diagnosticLabel="Historical diagnostic · review required" onInspect={()=>onInspect(m.evidence_refs)}/>]:[];})}</div>
      <div className="nr-inference-state"><h3>{inference?.availability==='available' ? 'Saved statistical test available for review' : 'Statistical inference unavailable'}</h3>
        <p>{inference?.availability==='available' ? 'The saved test can be inspected. Its assumptions, study-design checks and publication restrictions still apply; it is not a probability of a future return.' : 'The saved record does not support an eligible statistical conclusion. A positive historical mean does not resolve the sample, timing, comparison or study-design requirements.'}</p>
        {inference?.availability==='available' && <p>Recorded p-value: <strong>{formatMetric(inference)}</strong> <span className="nr-diagnostic-label">Diagnostic</span></p>}
        {reviews.length>0 && <button className="nr-source-button" onClick={()=>onReviews(reviews)}>Understand the review requirements →</button>}
        {inference && <button className="nr-source-button" onClick={()=>onInspect(inference.evidence_refs)}>Inspect saved inference evidence</button>}
      </div>
    </ReportSection>

    <ReportSection id="sample" eyebrow="02 / THE STUDY AND ITS COVERAGE" title="What was examined">
      <p className="nr-section-intro">Inspect the retained cases and their own measurement basis. A case count is different from a count of independent issuers.</p>
      <dl className="nr-event-basis"><div><dt>Event category</dt><dd>{basis(report,'category')}</dd></div><div><dt>Recorded method</dt><dd>{basis(report,'method')}</dd></div><div><dt>Recorded weighting</dt><dd>{basis(report,'weighting')}</dd></div></dl>
      <p className="nr-analysis-note">A recorded event date is not proof of an issuer-confirmed release time. The table distinguishes the recorded date, its saved review status, actual measurement dates and benchmark basis. Preparation time is not an event date.</p>
      {sample ? <SavedTable table={sample} report={report} onInspect={onInspect}/> : <DetailMissing>This older presentation has no case metadata table. The numerical observations below and original bundle remain available; timing and benchmark details have not been reconstructed in the browser.</DetailMissing>}
      {peers && <details className="nr-method-glossary"><summary>Requested, contributing and excluded companies</summary><p className="nr-analysis-note">One company can have more than one recorded role. A pinned/requested company is not automatically a contributing or economically comparable peer.</p><SavedTable table={peers} report={report} onInspect={onInspect}/></details>}
      {exclusions && <details className="nr-method-glossary"><summary>Rejected and unresolved records</summary>{exclusions.rows.length ? <SavedTable table={exclusions} report={report} onInspect={onInspect}/> : <p className="nr-analysis-note">No rejected study inputs or unresolved assembly rows were retained in this presentation. Recorded peer exclusions, where supplied, appear in the selection table. This is not a guarantee of complete coverage.</p>}</details>}
      {table('event-basis') && <details className="nr-method-glossary"><summary>Full saved method and scope</summary><SavedTable table={table('event-basis')!} report={report} onInspect={onInspect}/></details>}
    </ReportSection>

    <ReportSection id="observations" eyebrow="03 / HISTORICAL OBSERVATIONS ONLY" title="Historical observations">
      <p className="nr-section-intro">Each bar is a saved case’s accumulated abnormal return (CAR): the sum of its returns relative to the saved market model over the measurement window. A positive bar is not a forecast or proof of an event’s effect.</p>
      {report.charts.filter(c=>c.id==='event-cases').map(c=><DatasetTable key={c.id} chart={c} onInspect={onInspect} review={<LocalReviews refs={c.review_refs} report={report} onReviews={onReviews}/>}/>)}
      <div className="nr-event-path"><h3>Event-relative path withheld</h3><p>This presentation does not project a verified before/after-event path. Recorded date strings and array positions do not establish release/session alignment. No path, intermediate return or confidence band has been filled in.</p>
        <p>Per-case totals remain separate historical diagnostics.</p>
        {report.charts.find(c=>c.id==='event-path') && <LocalReviews refs={report.charts.find(c=>c.id==='event-path')!.review_refs} report={report} onReviews={onReviews}/>}
      </div>
      {table('event-spread') && <details className="nr-method-glossary"><summary>Descriptive spread of retained cases</summary><p className="nr-analysis-note">These saved percentiles describe the historical sample. They are not a range for the next event or an interval for the mean. No future positive-return probability is supplied here.</p><SavedTable table={table('event-spread')!} report={report} onInspect={onInspect}/></details>}
    </ReportSection>

    <ReportSection id="interpretation" eyebrow="04 / READING THE RESULT" title="What this means">
      <div className="nr-event-explain"><article><h3>Return relative to a model</h3><p>The market model estimates how a stock would normally move with its benchmark. Abnormal return is the difference from that estimate; CAR adds those differences across the retained window. It is distinct from the stock’s raw total return.</p></article>
        <article><h3>A sample description</h3><p>The saved mean and percentiles describe the accepted cases under their recorded weighting. Repeated issuers and overlapping windows can share influences. More cases do not automatically provide more independent evidence or resolve other failed checks.</p></article>
        <article><h3>No next-event prediction</h3><p>Past observations do not establish a likely future return. Unavailable inference stays unavailable, and a held study stays held. Source review, study eligibility and financial approval have separate meanings.</p></article></div>
    </ReportSection>
  </>;
}

export function EventGateDetails({report,onInspect}:Pick<Props,'report'|'onInspect'>) {
  const table=report.tables.find(t=>t.id==='event-gates');
  return table ? <details className="nr-method-glossary"><summary>Original check results and identifiers</summary><p className="nr-analysis-note">The readable topics above preserve the original findings. These are the saved check statuses and details; they are not a new approval.</p><SavedTable table={table} report={report} onInspect={onInspect}/></details> : null;
}
