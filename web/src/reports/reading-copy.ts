/** Complete presentation data: no pagination, display filters or new calculations. */
import { datasetRows, pointMetric, ReportFailure } from './report-data.ts';
import type { NativeReport } from './report-data';
import { calendarDate, formatMetric } from './format.ts';

export function readingCopy(report: NativeReport) {
  if (report.agent !== 'agent3' || !['events','news'].includes(report.workflow)) throw new ReportFailure('unsupported_report_schema');
  const metrics=new Map(report.metrics.map(m=>[m.id,m]));
  const labels=new Map(report.evidence.map((e,i)=>[e.id,'E'+(i+1)]));
  const references=(refs:string[])=>refs.map(ref=>labels.get(ref) || 'Unresolved reference').join(', ');
  return {
    title:report.workflow==='news'?'Company news':'Past event reactions',
    references,
    metrics:report.metrics.map(m=>({...m,display:formatMetric(m),references:references(m.evidence_refs)})),
    charts:report.charts.map(chart=>({chart,rows:datasetRows(chart).map(row=>({
      id:row.x,label:chart.x_axis.kind==='date'?calendarDate(row.x):row.x===row.label?row.x:row.x+' · '+row.label,
      values:row.points.map(p=>p ? formatMetric(pointMetric(chart,p)) : 'Not retained'),
      references:references([...new Set(row.points.flatMap(p=>p?.evidence_refs || []))]),
    }))})),
    tables:report.tables.map(table=>({...table,rows:table.rows.map(row=>({...row,
      values:table.columns.map(column=>{
        const cell=row.cells.find(c=>c.column_id===column.id)!;
        const metric=cell.kind==='metric_ref'?metrics.get(cell.metric_id)!:null;
        return metric ? formatMetric(metric)+(metric.visibility==='diagnostic'?' · Diagnostic':'') : cell.kind==='text'?cell.text:'';
      }), references:references([...new Set([...row.evidence_refs,...row.cells.flatMap(c=>c.kind==='metric_ref'?metrics.get(c.metric_id)!.evidence_refs:[])])]),
    }))})),
    evidence:report.evidence.map(e=>({...e,label:labels.get(e.id)!,description:e.label,
      artifact:report.artifacts.find(a=>a.id===e.artifact_id)!.name})),
  };
}
