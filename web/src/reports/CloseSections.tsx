import { useId, useState } from 'react';
import type { NativeReport } from './report-data';
import { DatasetTable, LocalReviews, SavedTable } from './AnalysisSections';
import { MetricCard, ReportSection } from './ReportFrame';
import { accountTable, closeAccountOverview, closeAccounts, closeBasis, closeText } from './close-data';
import { calendarDate } from './format';

type Context={report:NativeReport;onInspect:(refs:string[])=>void;onReviews:(refs:string[])=>void};
export function CloseSections({report,onInspect,onReviews}:Context) {
  const [query,setQuery]=useState(''),[filter,setFilter]=useState('all'),id=useId();
  const all=closeAccounts(report),filtered=closeAccounts(report,query,filter);
  const [node,setNode]=useState(closeText(all?.rows[0],'node'));
  const closedYear=closeText(report.tables.find(t=>t.id==='account-forecasts')?.rows[0],'state')==='deterministic';
  const metrics=(ids:string[])=>ids.flatMap(id=>report.metrics.filter(m=>m.id===id));
  const cards=(ids:string[])=><div className="nr-metric-grid">{metrics(ids).map(m=><MetricCard key={m.id} metric={m} diagnosticLabel={closedYear?'Saved closed-year result':'Conditional year-end scenario'} onInspect={()=>onInspect(m.evidence_refs)}/>)}</div>;
  const table=(id:string,selected?:string)=>{const t=selected?accountTable(report,id,selected):report.tables.find(t=>t.id===id);return t?<SavedTable key={id+'-'+(selected||'all')} table={t} report={report} onInspect={onInspect}/>:<div className="nr-empty"><p>This saved presentation does not retain this detail. Inspect the registered original evidence.</p></div>;};
  const reviews=(ids:string[])=><LocalReviews refs={[...new Set(report.sections.filter(s=>ids.includes(s.id)).flatMap(s=>s.review_refs))]} report={report} onReviews={onReviews}/>;
  const chart=(id:string)=>{const c=report.charts.find(c=>c.id===id);return c?<DatasetTable chart={c} onInspect={onInspect} review={<LocalReviews refs={c.review_refs} report={report} onReviews={onReviews}/>}/>:<p className="nr-table-note">No eligible saved chart is retained here.</p>;};
  return <>
    <ReportSection id="summary" eyebrow="01 / THE SELECTED FINANCIAL CLOSE" title="Close summary">
      <p className="nr-summary-text">{report.summary.text}</p>
      <div className="nr-scope-note"><strong>{closeBasis(report,'name')} · {calendarDate(report.identity.period_end||report.identity.period_label)}</strong><p>One selected reporting period. Source versions and any caller-supplied approval assertion are shown below.</p></div>
      {cards(['close-budget-cents','close-actual-cents','close-total-variance-cents'])}
      <p className="nr-analysis-note">Actual less budget is an account amount. Whether an increase is favourable depends on the account and its sign toward profit. The source’s saved assessment remains attached to every account.</p>
    </ReportSection>
    <ReportSection id="bridge" eyebrow="02 / FROM BUDGET TO ACTUAL" title="Variance bridge">
      <p className="nr-section-intro">Start with budget, apply the retained account or driver movements, and finish at actual. Internal accounting checks verify the reconciliation; this chart displays the saved values.</p>
      {chart('close-bridge')}
    </ReportSection>
    <ReportSection id="accounts" eyebrow="03 / WHERE REVIEW IS NEEDED" title="Account review">
      <p className="nr-section-intro">Account variance and saved profit impact have separate columns. Material amounts remain review priorities even when significance cannot be computed. Saved diagnostics do not establish business causes.</p>{reviews(['accounts','close-diagnostics'])}
      <div className="nr-monitor-tools"><label htmlFor={id}>Find an account<input id={id} type="search" placeholder="Account name or ID" value={query} onChange={e=>setQuery(e.target.value)}/></label><label htmlFor={id+'-filter'}>Show<select id={id+'-filter'} value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All accounts</option><option value="material">Material accounts</option><option value="unavailable">Significance not computable</option></select></label></div>
      <p className="nr-table-note" role="status">Showing {filtered?.rows.length||0} of {all?.rows.length||0} retained accounts. Search and filters do not change the result.</p>
      {filtered&&<SavedTable key={query+'-'+filter} table={closeAccountOverview(filtered)} report={report} onInspect={onInspect}/>}
      <details className="nr-data-disclosure"><summary>Full account hierarchy and saved review classes<span>All metadata for the current account filter</span></summary>{filtered&&<SavedTable key={'full-'+query+'-'+filter} table={filtered} report={report} onInspect={onInspect}/>}</details>
      <label className="nr-monitor-history">Inspect account evidence<select aria-label="Account evidence" value={node} onChange={e=>setNode(e.target.value)}>{all?.rows.map(row=><option key={row.id} value={closeText(row,'node')}>{closeText(row,'account')} · {closeText(row,'node')}</option>)}</select></label>
      {table('account-diagnostics',node)}
      <details className="nr-data-disclosure"><summary>Selected account’s dated prior variances<span>Account amounts, with their original periods</span></summary>{table('account-prior-observations',node)}</details>
      <details className="nr-data-disclosure"><summary>Root account variance history<span>Saved observations, separate from year-end scenarios</span></summary>{chart('close-variance-history')}</details>
    </ReportSection>
    <ReportSection id="forecast" eyebrow="04 / YEAR-END BASIS AND LIMITATIONS" title={closedYear?'Closed-year result':'Forecast and limitations'}>
      <p className="nr-section-intro">{closedYear?'The saved year is closed: no periods remain. The landing and equal bounds represent the saved full-year actual amount; the target outcome is realised, rather than a forecast probability.':'These saved year-end projections have a different horizon and basis from the selected-period close. A point estimate does not establish an uncertainty interval; unavailable probability does not mean zero probability.'}</p>{reviews(['forecast','close-forecast-context'])}
      {cards(['forecast-projected-landing-cents','forecast-target-cents','forecast-prob-hit-target'])}
      {cards(['forecast-band-0','forecast-band-1'])}
      <p className="nr-analysis-note">{closedYear?'Equal closed-year bounds describe the saved actual amount, with no remaining horizon.':'A model interval is conditional on its stated assumptions and coverage level. Model probabilities are uncalibrated. No future monthly path has been invented from a single year-end landing.'}</p>
      {table('account-forecasts')}
      <label className="nr-monitor-history">Forecast assumptions for<select aria-label="Forecast account" value={node} onChange={e=>setNode(e.target.value)}>{all?.rows.map(row=><option key={row.id} value={closeText(row,'node')}>{closeText(row,'account')}</option>)}</select></label>
      {table('forecast-basis',node)}
    </ReportSection>
    <ReportSection id="versions" eyebrow="05 / SOURCE AND CORRECTION BASIS" title="Source versions and close history">
      <p className="nr-section-intro">The original submitted actuals delta and the effective actuals used by this close answer different questions. Effective rows retain their winning version identifiers. Budget approval is a saved caller assertion.</p>{reviews(['close-basis','close-sources'])}
      {table('close-basis')}
      <div className="nr-scope-note"><strong>History coverage</strong><p>This bundle retains prior variance observations and any superseded-run identifier. A complete related-close inventory is not retained here. Open the workspace’s financial-close reports to inspect other registered runs.</p><a className="nr-source-button" href="#/agent/agent4">Browse saved financial closes</a></div>
      <details className="nr-data-disclosure"><summary>Original submitted actuals delta<span>What this run submitted</span></summary>{table('submitted-actuals')}</details>
      <details className="nr-data-disclosure"><summary>Effective actuals used<span>Frozen observations and winning source versions</span></summary>{table('effective-actuals')}</details>
      <details className="nr-data-disclosure"><summary>Selected budget panel<span>Canonical cents and exact EUR amounts</span></summary>{table('budget-panel')}</details>
      <details className="nr-data-disclosure"><summary>Excluded historical periods<span>Saved incompleteness evidence</span></summary>{table('history-exclusions')}</details>
    </ReportSection>
  </>;
}
