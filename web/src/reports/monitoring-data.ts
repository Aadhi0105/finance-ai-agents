/** Presentation selectors over the validated view. No detection or correction. */
import type { NativeReport } from './report-data';
import type { TableData } from './analysis-types';
import { savedInstant } from './format.ts';

const statusNames:Record<string,string>={NEW_BREACH:'New breach',WIDENING:'Breach widening',IMPROVING:'Breach improving',KNOWN_STABLE:'Stable breach',RESOLVED:'Breach resolved',OK:'Within saved policy',BASELINE:'Baseline observation'};
export function monitoringClassification(state:string) {
  const [code,...qualifiers]=state.split(' · ');
  return [statusNames[code]||code,...qualifiers].join(' · ');
}
export function monitoringPeriod(period:string) {
  return period.startsWith('Snapshot export: ')?'Snapshot export: '+savedInstant(period.slice('Snapshot export: '.length)):period;
}

export function monitoringBasis(report: NativeReport, field: string) {
  const row=report.tables.find(t=>t.id==='monitor-basis')?.rows.find(r=>r.id==='basis-'+field);
  const cell=row?.cells.find(c=>c.column_id==='value');
  return cell?.kind==='text'?cell.text:'Not retained';
}

export function monitoringItems(report: NativeReport, scope: 'cycle'|'effective') {
  const table=report.tables.find(t=>t.id===scope+'-observations');
  return (table?.rows||[]).map(row=>{
    const text=(key:string)=>{const cell=row.cells.find(c=>c.column_id===key);return cell?.kind==='text'?cell.text:'Not retained';};
    const metric=(key:string)=>{const cell=row.cells.find(c=>c.column_id===key);return cell?.kind==='metric_ref'?report.metrics.find(m=>m.id===cell.metric_id):undefined;};
    return {id:row.id,item:text('item'),entity:text('entity'),metric:text('metric'),observed:text('observed'),
      direction:text('direction'),state:text('state'),breach:text('breach'),signals:text('signals'),attention:text('attention'),
      value:metric('value'),threshold:metric('threshold'),refs:row.evidence_refs};
  });
}
export type MonitoringItem=ReturnType<typeof monitoringItems>[number];
export function filterMonitoringItems(items:MonitoringItem[],query:string,filter:string) {
  const q=query.trim().toLocaleLowerCase();
  return items.filter(item=>(!q||[item.item,item.entity,item.metric,item.state].join(' ').toLocaleLowerCase().includes(q))
    && (filter==='all'||filter==='surfaced'&&item.attention==='Surfaced for attention'||filter==='breaches'&&item.breach==='Recorded breach'
      ||filter==='signals'&& !['No flags recorded','Not retained'].includes(item.signals)
      ||filter==='pending'&&item.state.includes('correction review pending')));
}
export function historyForItem(report:NativeReport,item:string) {
  return report.charts.find(c=>c.series.some(s=>s.label===item) || c.title==='Selected-cycle history · '+item);
}
export function textValue(table:TableData|undefined,column:string,index=0) {
  const cell=table?.rows[index]?.cells.find(c=>c.column_id===column);return cell?.kind==='text'?cell.text:'Not retained';
}
export const monitoringMetricNames:Record<string,string>={net_debt_to_ebitda:'Net debt / EBITDA',interest_coverage:'Interest coverage',current_ratio:'Current ratio',
  operating_interest_coverage:'Operating interest coverage',net_debt_to_operating_ebitda_proxy:'Net debt / operating EBITDA proxy'};
