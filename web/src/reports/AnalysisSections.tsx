import { useId, useState } from 'react';
import { Icon } from '../icons';
import { datasetRows, displaySourceText, pointMetric } from './report-data';
import type { Metric, NativeReport } from './report-data';
import type { ChartData, SavedSection, TableData } from './analysis-types';
import { calendarDate, formatMetric } from './format';
import { MetricCard, ReportSection } from './ReportFrame';

type Inspect = (refs: string[]) => void;
type Context = { report: NativeReport; onInspect: Inspect; onReviews: Inspect };
const PAGE_SIZE = 25;
const categories: Record<string, string> = { data_basis: 'source basis', observation_dates: 'dates and recency',
  valuation_assumptions: 'valuation assumptions', peer_comparability: 'peer comparability', narrative_support: 'supported claims',
  statistical_eligibility: 'statistical eligibility', delivery: 'saved files' };
function SourceButton({ refs, onInspect, label = 'Source' }: { refs: string[]; onInspect: Inspect; label?: string }) {
  return <button className="nr-source-button" disabled={!refs.length} onClick={() => onInspect(refs)}><Icon name="evidence" size={13} />{label}</button>;
}

export function LocalReviews({ refs, report, onReviews }: Pick<Context, 'report' | 'onReviews'> & { refs: string[] }) {
  const items = refs.flatMap(id => report.review_items.filter(r => r.id === id));
  if (!items.length) return null;
  const names = [...new Set(items.map(r => categories[r.category] || 'saved restrictions'))];
  return <div className="nr-local-review"><Icon name="info" size={16} /><p><strong>Review required:</strong> {names.join(' · ')}.</p>
    <button className="nr-source-button" onClick={() => onReviews(items.map(i => i.id))}>View {items.length} review notes<Icon name="arrow" size={14} /></button></div>;
}

function Missing({ title = 'Saved detail unavailable', children }: { title?: string; children: React.ReactNode }) {
  return <div className="nr-empty"><h3>{title}</h3><p>{children}</p></div>;
}

function Pager({ page, count, onPage, label }: { page: number; count: number; onPage: (page: number) => void; label: string }) {
  if (count <= PAGE_SIZE) return null;
  const total = Math.ceil(count / PAGE_SIZE);
  return <nav className="nr-table-pager" aria-label={label + ' pages'}><span>Rows {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, count)} of {count}</span>
    <div><button className="nr-page-button" onClick={() => onPage(page - 1)} disabled={page === 0}>Previous</button><span>Page {page + 1} of {total}</span><button className="nr-page-button" onClick={() => onPage(page + 1)} disabled={page + 1 === total}>Next</button></div></nav>;
}

export function MetricTable({ metrics, onInspect, title = 'Saved financial measures' }: { metrics: Metric[]; onInspect: Inspect; title?: string }) {
  if (!metrics.length) return <Missing>No financial measures were retained for this section.</Missing>;
  return <div className="nr-table-scroll" role="region" aria-label={title} tabIndex={0}><table className="nr-data-table"><caption>{title}</caption><thead><tr><th scope="col">Measure</th><th scope="col">Saved value</th><th scope="col">Period / scope</th><th scope="col">Evidence</th></tr></thead><tbody>{metrics.map(m => <tr key={m.id}><th scope="row">{m.label}{m.visibility === 'diagnostic' && <span className="nr-diagnostic-label">Diagnostic</span>}</th><td className={m.availability === 'available' ? 'nr-number' : 'nr-unavailable-cell'}>{formatMetric(m)}</td><td>{displaySourceText(calendarDate(m.period_label))}</td><td><SourceButton refs={m.evidence_refs} onInspect={onInspect} /></td></tr>)}</tbody></table></div>;
}

export function SavedTable({ table, report, onInspect }: Pick<Context, 'report' | 'onInspect'> & { table: TableData }) {
  const [page, setPage] = useState(0);
  const id = useId();
  function go(next: number) { setPage(next); document.getElementById(id)?.focus({ preventScroll: true }); }
  if (!table.rows.length) return <Missing title={table.title}>No rows were retained for this table.</Missing>;
  return <div className="nr-table-block"><div id={id} className="nr-table-scroll" role="region" aria-label={table.title} tabIndex={0}>
    <table className="nr-data-table"><caption>{table.title}</caption><thead><tr>{table.columns.map(c => <th scope="col" key={c.id}>{c.label}</th>)}<th scope="col">Evidence</th></tr></thead><tbody>{table.rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map(row => {
      const refs = [...new Set([...row.evidence_refs, ...row.cells.flatMap(c => c.kind === 'metric_ref' ? report.metrics.find(m => m.id === c.metric_id)!.evidence_refs : [])])];
      return <tr key={row.id}>{table.columns.map((column, i) => {
        const cell = row.cells.find(c => c.column_id === column.id)!;
        const metric = cell.kind === 'metric_ref' ? report.metrics.find(m => m.id === cell.metric_id)! : null;
        const value = metric ? formatMetric(metric) : displaySourceText(calendarDate(cell.kind === 'text' ? cell.text : ''));
        return i === 0 ? <th scope="row" key={column.id}>{value}</th> : <td key={column.id} className={metric?.availability === 'available' ? 'nr-number' : metric ? 'nr-unavailable-cell' : ''} title={cell.kind === 'text' ? cell.text : metric?.period_label}>{value}</td>;
      })}<td><SourceButton refs={refs} onInspect={onInspect} /></td></tr>;
    })}</tbody></table>
  </div><Pager page={page} count={table.rows.length} onPage={go} label={table.title} /></div>;
}

export function DatasetTable({ chart, onInspect, collapsed = false }: { chart: ChartData; onInspect: Inspect; collapsed?: boolean }) {
  const [page, setPage] = useState(0);
  const id = useId(), rows = datasetRows(chart);
  const unit = chart.y_axis.currency || ({ fraction: 'percent', multiple: 'multiple', index: 'index points' } as Record<string, string>)[chart.y_axis.unit] || chart.y_axis.unit;
  const table = rows.length ? <><div id={id} className="nr-table-scroll" role="region" aria-label={chart.title + ' numerical data'} tabIndex={0}><table className="nr-data-table"><caption>{chart.title} · {unit}</caption><thead><tr><th scope="col">{chart.x_axis.label}</th>{chart.series.map(s => <th scope="col" key={s.id}>{s.label}</th>)}<th scope="col">Evidence</th></tr></thead><tbody>{rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map(row => <tr key={row.x}>
    <th scope="row">{chart.x_axis.kind === 'date' ? calendarDate(row.x) : row.label === row.x ? row.label : row.x + ' · ' + row.label}</th>
    {row.points.map((point, i) => <td key={chart.series[i].id} className={point?.y !== null && point ? 'nr-number' : 'nr-unavailable-cell'} title={point?.y === null ? 'Saved point missing or observation window not yet filled' : point?.y ?? 'No point retained for this date'}>{point ? formatMetric(pointMetric(chart, point)) : 'Not retained'}</td>)}
    <td><SourceButton refs={[...new Set(row.points.flatMap(p => p?.evidence_refs || []))]} onInspect={onInspect} /></td></tr>)}</tbody></table></div>
    <Pager page={page} count={rows.length} onPage={next => { setPage(next); document.getElementById(id)?.focus({ preventScroll: true }); }} label={chart.title} />
    {chart.series.some(s => s.points.some(p => p.y === null)) && <p className="nr-table-note">Unavailable points remain missing. A moving-average or volatility window may not yet contain enough observations; no zero or interpolated value is supplied.</p>}</>
    : <Missing title={chart.availability === 'withheld' ? 'Values withheld' : 'Numerical series unavailable'}>The saved evidence does not support displaying this series. Review the linked restrictions before relying on it.</Missing>;
  return <article className="nr-dataset"><div className="nr-dataset-heading"><h3>{chart.title}</h3>{chart.visibility === 'diagnostic' && <span className="nr-diagnostic-label">Diagnostic · review required</span>}</div><p>{chart.purpose}</p>
    {collapsed && rows.length ? <details className="nr-data-disclosure"><summary>Inspect {rows.length} saved observations <span>Numerical table</span></summary>{table}</details> : table}</article>;
}

function sectionMetrics(report: NativeReport, section: SavedSection | undefined) {
  return (section?.metric_refs || []).flatMap(id => report.metrics.filter(m => m.id === id));
}

export function AnalysisSections({ report, onInspect, onReviews }: Context) {
  const section = (id: string) => report.sections.find(s => s.id === id);
  const metrics = (id: string) => sectionMetrics(report, section(id));
  const tables = (id: string) => (section(id)?.table_refs || []).flatMap(ref => report.tables.filter(t => t.id === ref));
  const charts = (id: string) => (section(id)?.chart_refs || []).flatMap(ref => report.charts.filter(c => c.id === ref));
  const reviews = (id: string) => <LocalReviews refs={section(id)?.review_refs || []} report={report} onReviews={onReviews} />;
  const isAvailable = (id: string) => section(id)?.availability === 'available';
  const renderTables = (id: string) => tables(id).map(t => <SavedTable key={t.id} table={t} report={report} onInspect={onInspect} />);
  const valuationMetrics = metrics('valuation').filter(m => ['weighted-valuation', 'fcff-base'].includes(m.id));
  const marketArea = report.analyst_content.market_consensus;
  const brokerArea = report.analyst_content.external_research;
  return <>
    <ReportSection id="performance" eyebrow="03 / THE FINANCIAL RECORD" title="Business performance">
      <p className="nr-section-intro">Saved annual measures and their historical context. Growth describes the retained periods; it does not identify a business cause or forecast the next year.</p>{reviews('performance')}
      {isAvailable('performance') ? <><MetricTable metrics={metrics('performance')} onInspect={onInspect} /><div className="nr-history-grid">{charts('performance').map(c => <DatasetTable key={c.id} chart={c} onInspect={onInspect} />)}</div></> : <Missing>The saved performance section is unavailable or restricted.</Missing>}
    </ReportSection>

    <ReportSection id="valuation" eyebrow="04 / CONDITIONAL MODEL OUTPUT" title="Valuation & assumptions">
      <p className="nr-section-intro">Keystone’s saved valuation is a model result conditional on its inputs and assumptions. External analyst estimates appear separately in Market consensus.</p>{reviews('valuation')}
      {isAvailable('valuation') ? <><div className="nr-valuation-cards">{valuationMetrics.map(m => <MetricCard key={m.id} metric={m} onInspect={() => onInspect(m.evidence_refs)} />)}</div>
        <p className="nr-analysis-note">The reported free-cash-flow measure and the model’s unlevered FCFF input have different definitions. Assigned scenario weights are assumptions, not measured outcome probabilities.</p>
        {charts('valuation').map(c => <DatasetTable key={c.id} chart={c} onInspect={onInspect} />)}
        {renderTables('valuation')}
        {!tables('valuation').some(t => t.id === 'equity-bridge') && <Missing title="Detailed equity bridge not retained">This saved presentation does not include the enterprise, net-debt and equity bridge table. Its original model evidence remains available; no bridge has been reconstructed in the browser.</Missing>}
      </> : <Missing>The saved valuation section cannot be displayed. No price target is inferred.</Missing>}
    </ReportSection>

    <ReportSection id="peers" eyebrow="05 / A COMPARISON TO REVIEW" title="Peer comparison">
      <p className="nr-section-intro">Retained P/E observations are screening diagnostics. Check financial periods, quote dates, exclusions and business comparability before drawing a comparison.</p>{reviews('peers')}
      {isAvailable('peers') ? <>{charts('peers').map(c => <DatasetTable key={c.id} chart={c} onInspect={onInspect} />)}{renderTables('peers')}
        {!tables('peers').some(t => t.id === 'peer-evidence') && <Missing title="Peer dates and exclusions not retained here">The original evidence contains the saved screening record. This presentation does not establish a common fiscal period or an economically approved peer group.</Missing>}
      </> : <Missing>The peer comparison is unavailable or withheld in the saved report.</Missing>}
    </ReportSection>

    <ReportSection id="market" eyebrow="06 / HISTORICAL MARKET CONTEXT" title="Saved market context">
      <p className="nr-section-intro">Saved quotes and historical observations retain their original dates. Opening this report does not refresh the market data.</p>{reviews('market')}
      {isAvailable('market') ? <>{metrics('market').length ? <MetricTable metrics={metrics('market')} title="Saved quote observations" onInspect={onInspect} /> : <Missing title="Separate quote not retained here">The saved historical series below remain available. This presentation does not include a separately dated quote.</Missing>}{renderTables('market')}
        <div className="nr-method-note"><h3>Reading these series</h3><p>Moving averages use saved 50- and 200-observation windows. The benchmark comparison uses common dates rebased to 100. Volatility uses the retained 30-observation annualised definition; drawdown measures decline from a prior peak. All series were prepared in Python from saved evidence.</p></div>
        {charts('market').map(c => <DatasetTable key={c.id} chart={c} onInspect={onInspect} collapsed />)}
      </> : <Missing>No usable saved market context is available.</Missing>}
    </ReportSection>

    <ReportSection id="consensus" eyebrow="07 / EXTERNAL AGGREGATE ESTIMATES" title="Market consensus">
      <p className="nr-section-intro">Provider-supplied analyst estimates remain distinct from Keystone’s valuation and the company’s historical growth.</p>{reviews('consensus')}
      {marketArea.availability === 'available' && isAvailable('consensus') ? <>{tables('consensus').length ? renderTables('consensus') : <MetricTable metrics={marketArea.metric_refs.flatMap(id => report.metrics.filter(m => m.id === id))} title="Saved external estimates" onInspect={onInspect} />}
        <p className="nr-analysis-note">Relative provider labels identify estimate periods, not a confirmed fiscal year or publication date. Review analyst counts, currency and observation-date limitations in the saved evidence.</p></>
        : <Missing title={marketArea.availability === 'withheld' ? 'Analyst estimates withheld' : 'Analyst estimates unavailable'}>Analyst estimates were unavailable or restricted in this saved run. Historical growth and the valuation model have not been substituted for external consensus.</Missing>}
      <SourceButton refs={marketArea.evidence_refs} onInspect={onInspect} label="Inspect saved consensus evidence" />
    </ReportSection>

    <ReportSection id="external-research" eyebrow="08 / ATTRIBUTABLE BROKER RESEARCH" title="External research">
      <Missing title={brokerArea.availability === 'withheld' ? 'External research withheld' : brokerArea.reason_codes.includes('broker_reports_not_collected') ? 'Broker reports and ratings not collected' : 'External research unavailable'}>{brokerArea.reason_codes.includes('broker_reports_not_collected') ? 'Named-broker reports and buy/hold/sell ratings were not collected in this saved run.' : 'This presentation contains no broker documents or ratings eligible for display.'} Keystone’s supported observations and model outputs are shown in the sections above.</Missing>
      <p className="nr-analysis-note">External research means identifiable broker documents and ratings, with their own sources and permitted use. A model-generated draft does not establish a broker recommendation.</p>
    </ReportSection>
  </>;
}
