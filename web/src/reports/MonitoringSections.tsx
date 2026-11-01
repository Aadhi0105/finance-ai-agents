import { useId, useState } from 'react';
import type { NativeReport } from './report-data';
import { calendarDate, formatMetric, savedInstant } from './format';
import { DatasetTable, LocalReviews, SavedTable } from './AnalysisSections';
import { MetricCard, ReportSection } from './ReportFrame';
import { filterMonitoringItems, historyForItem, monitoringBasis, monitoringClassification, monitoringItems, monitoringMetricNames, monitoringPeriod } from './monitoring-data';

type Context={report:NativeReport;onInspect:(refs:string[])=>void;onReviews:(refs:string[])=>void};

function ObservationCards({report,scope,onInspect,onHistory}:{report:NativeReport;scope:'cycle'|'effective';onInspect:Context['onInspect'];onHistory:(item:string)=>void}) {
  const [query,setQuery]=useState(''),[filter,setFilter]=useState('all'),id=useId();
  const all=monitoringItems(report,scope),items=filterMonitoringItems(all,query,filter);
  return <><div className="nr-monitor-tools"><label htmlFor={id}>Find an item<input id={id} type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Entity, metric or item ID"/></label>
    <label htmlFor={id+'-filter'}>Show<select id={id+'-filter'} value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All observations</option>{scope==='cycle'&&<option value="surfaced">Surfaced for attention</option>}<option value="breaches">Recorded breaches</option><option value="signals">Early-warning flags</option><option value="pending">Correction pending</option></select></label></div>
    <p className="nr-table-note" role="status">Showing {items.length} of {all.length} saved {scope==='cycle'?'selected-cycle':'effective-state'} observations. Filters do not change the saved result.</p>
    {items.length?<div className="nr-monitor-cards">{items.map(item=><article className="nr-monitor-card" key={item.id}>
      <div className="nr-monitor-card-top"><p className="eyebrow">{item.entity}</p><span className={item.breach==='Recorded breach'?'nr-monitor-breach':'nr-monitor-flag'}>{item.breach}</span></div>
      <h3>{monitoringMetricNames[item.metric]||item.metric}</h3><p className="nr-monitor-item">{item.item} · Observed {calendarDate(item.observed)}</p>
      <div className="nr-monitor-policy"><div><small>Saved value</small><strong>{item.value?formatMetric(item.value):'Unavailable'}</strong></div><div><small>Allowed analyst policy</small><strong>{item.direction} {item.threshold?formatMetric(item.threshold):'Unavailable'}</strong></div></div>
      <p className="nr-monitor-status">Saved classification: {monitoringClassification(item.state)}{item.attention==='Surfaced for attention'&&' · Surfaced for attention'}</p>
      {(item.value?.availability!=='available'||item.threshold?.availability!=='available'||!['Recorded breach','No recorded breach'].includes(item.breach))&&<p className="nr-table-note">Assessment requires review: values, units or the breach flag are unavailable. The saved classification alone does not establish that this policy was met.</p>}
      <p className="nr-table-note">{item.signals==='Not retained'?'Signal details not retained in this presentation.':item.signals==='No flags recorded'?'No early-warning flags recorded.':item.signals+' · diagnostics require review'}</p>
      <div className="nr-monitor-card-actions"><button className="nr-source-button" onClick={()=>onInspect([...new Set([...item.refs,...(item.value?.evidence_refs||[]),...(item.threshold?.evidence_refs||[])])])}>Inspect saved observation</button><button className="nr-source-button" onClick={()=>onHistory(item.item)}>Original-cycle history</button></div>
    </article>)}</div>:<div className="nr-empty"><h3>{all.length?'No observations match these filters':'No observations retained for this scope'}</h3><p>{all.length?'Change the search or show all observations.':'This does not establish that all policies were met or that ongoing breaches were cleared.'}</p>{all.length>0&&<button className="nr-source-button" onClick={()=>{setQuery('');setFilter('all');}}>Reset filters</button>}</div>}</>;
}

export function MonitoringSections({report,onInspect,onReviews}:Context) {
  const allItems=[...new Set([...monitoringItems(report,'cycle'),...monitoringItems(report,'effective')].map(i=>i.item).filter(i=>i!=='Not retained'))];
  const [item,setItem]=useState(allItems.find(i=>historyForItem(report,i))||allItems[0]||'');
  const chart=historyForItem(report,item),isBaseline=monitoringBasis(report,'baseline')==='True';
  const metrics=(ids:string[])=>ids.flatMap(id=>report.metrics.filter(m=>m.id===id));
  const cards=(ids:string[])=><div className="nr-metric-grid">{metrics(ids).map(m=><MetricCard key={m.id} metric={{...m,period_label:monitoringPeriod(m.period_label)}} onInspect={()=>onInspect(m.evidence_refs)}/>)}</div>;
  const table=(id:string)=>{const t=report.tables.find(t=>t.id===id);return t?<SavedTable key={id} table={t} report={report} onInspect={onInspect}/>:<p className="nr-table-note">This presentation does not retain this detail. Inspect the original saved evidence.</p>;};
  const reviews=(ids:string[])=><LocalReviews refs={[...new Set(report.sections.filter(s=>ids.includes(s.id)).flatMap(s=>s.review_refs))]} report={report} onReviews={onReviews}/>;
  function selectHistory(next:string){setItem(next);const section=document.getElementById('report-history');section?.scrollIntoView({block:'start'});section?.focus({preventScroll:true});}
  return <>
    <ReportSection id="summary" eyebrow="01 / WHAT NEEDS ATTENTION" title="Monitoring summary">
      <p className="nr-summary-text">{report.summary.text}</p>
      <div className="nr-scope-note"><strong>Selected cycle {monitoringBasis(report,'cycle')}</strong><p>Cycle observation date: {calendarDate(monitoringBasis(report,'date'))}. {isBaseline?'Baseline: alerting suppressed.':'A surfaced item may be a breach or an early warning.'}</p></div>
      {cards(['cycle-items','cycle-breaches','surfaced-items'])}
      <p className="nr-analysis-note">A quiet cycle is not an all-clear. Retained effective state appears separately below, including older observations and any saved correction attribution.</p>
      <details className="nr-data-disclosure"><summary>Cycle and export basis<span>Dates, baseline, replay and audit coverage</span></summary>{table('monitor-basis')}</details>
    </ReportSection>
    <ReportSection id="observations" eyebrow="02 / ORIGINAL SELECTED CYCLE" title="Observations and policy thresholds">
      <p className="nr-section-intro">Original measurements and classifications saved for this cycle. At or above / at or below describes the allowed analyst policy. These thresholds are not verified contractual covenants.</p>{reviews(['original-cycle','monitor-coverage'])}
      <ObservationCards report={report} scope="cycle" onInspect={onInspect} onHistory={selectHistory}/>
      <details className="nr-data-disclosure"><summary>Original observation table<span>All saved policy values and states</span></summary>{table('cycle-observations')}</details>
      <details className="nr-data-disclosure"><summary>Skipped inputs<span>Duplicates, holds and rejected candidates</span></summary><p className="nr-analysis-note">Skipped inputs do not clear retained breaches. A candidate value is not an accepted observation.</p>{table('skipped-inputs')}</details>
    </ReportSection>
    <ReportSection id="history" eyebrow="03 / ACTUALLY RETAINED OBSERVATIONS" title="Original-cycle observation history">
      <p className="nr-section-intro">Only dated numerical histories retained with the selected cycle can be plotted. These are original-cycle histories; they have not been restated from current state or correction decisions. No policy line is extrapolated across changing definitions.</p>
      <label className="nr-monitor-history">Monitoring item<select value={item} onChange={e=>setItem(e.target.value)} aria-label="History item">{!allItems.length&&<option value="">No item IDs retained</option>}{allItems.map(i=><option key={i} value={i}>{i}</option>)}</select></label>
      {chart?<DatasetTable key={chart.id} chart={chart} onInspect={onInspect} review={<LocalReviews refs={chart.review_refs} report={report} onReviews={onReviews}/>}/>:<div className="nr-empty"><h3>No usable original-cycle history retained for this item</h3><p>A current value or list of cycle IDs does not establish a numerical history. No points have been inferred.</p></div>}
      {!allItems.length&&report.charts.map(c=><DatasetTable key={c.id} chart={c} onInspect={onInspect} review={<LocalReviews refs={c.review_refs} report={report} onReviews={onReviews}/>}/>)}
    </ReportSection>
    <ReportSection id="effective" eyebrow="04 / RETAINED STATE AT EXPORT" title="Effective state at export">
      <p className="nr-section-intro">The retained state spans observation dates and cycles. Snapshot exported {savedInstant(monitoringBasis(report,'export'))}. Export time is not the date of a new measurement. Retired series remain visible as evidence; the breach total excludes rows marked with a replacement series.</p>{reviews(['effective-state'])}
      {cards(['effective-items','effective-breaches'])}
      <ObservationCards report={report} scope="effective" onInspect={onInspect} onHistory={selectHistory}/>
      <details className="nr-data-disclosure"><summary>Effective-state table<span>Original cycle above remains unchanged</span></summary>{table('effective-observations')}</details>
    </ReportSection>
    <ReportSection id="corrections" eyebrow="05 / READ-ONLY DECISION EVIDENCE" title="Corrections and recovery">
      <p className="nr-section-intro">Pending proposals have not been applied. Saved decisions can restate effective history or establish a replacement series; the original selected cycle remains unchanged. Reviewer names record local attribution, not authenticated approval.</p>{reviews(['monitor-corrections'])}
      {cards(['reviews-count','decisions-count'])}
      {table('pending-corrections')}
      {table('correction-decisions')}
      <details className="nr-data-disclosure"><summary>Before / after decision evidence<span>Separate saved histories; never joined into a new chart</span></summary>{table('decision-observations')}</details>
      <details className="nr-data-disclosure"><summary>Triage process evidence<span>Saved attempts and incomplete-audit coverage</span></summary><p className="nr-analysis-note">Unreadable audits: {monitoringBasis(report,'audit')}. No retained attempt rows does not prove that no attempt occurred. Model commentary is not an approved financial action.</p>{table('triage-attempts')}{reviews(['monitor-triage'])}</details>
    </ReportSection>
  </>;
}
