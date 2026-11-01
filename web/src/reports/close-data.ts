/** Read-only selectors over the source-validated close presentation. */
import type { NativeReport } from './report-data';
import type { TableData } from './analysis-types';
export function closeText(row:TableData['rows'][number]|undefined,column:string) {
  const c=row?.cells.find(c=>c.column_id===column);return c?.kind==='text'?c.text:'Not retained';
}
export function closeBasis(report:NativeReport,field:string) {
  return closeText(report.tables.find(t=>t.id==='close-basis')?.rows.find(r=>r.id===field),'value');
}
export function closeAccounts(report:NativeReport,query='',filter='all') {
  const table=report.tables.find(t=>t.id==='accounts');if(!table)return undefined;
  const q=query.trim().toLocaleLowerCase();
  return {...table,rows:table.rows.filter(row=>(!q||[closeText(row,'node'),closeText(row,'account')].join(' ').toLocaleLowerCase().includes(q))
    &&(filter==='all'||filter==='material'&&closeText(row,'material')==='Material'
      ||filter==='unavailable'&&closeText(row,'significant')==='Not computable'))};
}
export function accountTable(report:NativeReport,id:string,node:string) {
  const table=report.tables.find(t=>t.id===id);return table?{...table,rows:table.rows.filter(row=>closeText(row,'node')===node)}:undefined;
}

export function closeAccountOverview(table:TableData) {
  const columns=table.columns.filter(c=>!['node','parent','review'].includes(c.id));
  const ids=new Set(columns.map(c=>c.id));
  return {...table,title:'Account amounts and profit effects',columns,rows:table.rows.map(row=>({...row,cells:row.cells.filter(c=>ids.has(c.column_id))}))};
}
