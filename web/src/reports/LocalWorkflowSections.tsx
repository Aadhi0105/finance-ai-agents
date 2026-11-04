import type {NativeReport} from './report-data';
import {DatasetTable,SavedTable} from './AnalysisSections';
import {MetricCard,ReportSection} from './ReportFrame';

export function LocalWorkflowSections({report,onInspect}:{report:NativeReport;onInspect:(refs:string[])=>void}){
 return <>{report.sections.map((section,i)=><ReportSection key={section.id} id={section.id} eyebrow={String(i+1).padStart(2,'0')+' / SUPPLIED LOCAL EVIDENCE'} title={section.title}>
  <p className="nr-summary-text">{section.id==='summary'?report.summary.text:section.purpose}</p>
  {section.id==='summary'&&<div className="nr-metric-grid">{section.metric_refs.map(id=>report.metrics.find(m=>m.id===id)).filter(m=>!!m).map(m=><MetricCard key={m.id} metric={m} onInspect={()=>onInspect(m.evidence_refs)}/>)}</div>}
  {section.id==='observations'&&report.workflow==='events'&&<div className="nr-metric-grid">{report.metrics.filter(m=>['mean-car','p-value'].includes(m.id)).map(m=><MetricCard key={m.id} metric={m} onInspect={()=>onInspect(m.evidence_refs)}/>)}</div>}
  {section.chart_refs.map(id=>report.charts.find(c=>c.id===id)).filter(c=>!!c).map(c=><DatasetTable key={c.id} chart={c} onInspect={onInspect}/>)}
  {section.table_refs.map(id=>report.tables.find(t=>t.id===id)).filter(t=>!!t).map(t=><SavedTable key={t.id} table={t} report={report} onInspect={onInspect}/>)}
  {section.id==='method'&&<dl>{report.glossary.map(g=><div key={g.term}><dt>{g.term}</dt><dd>{g.definition}</dd></div>)}</dl>}
 </ReportSection>)}</>;
}
