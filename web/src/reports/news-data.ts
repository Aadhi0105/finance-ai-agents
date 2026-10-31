/** Display-only extraction from the validated news projection. Never infer relevance or tone. */
import type { NativeReport } from './report-data';
import { displaySourceText } from './report-data.ts';
import type { TableData } from './analysis-types';

export function newsCell(row: TableData['rows'][number] | undefined, column: string): string {
  const cell = row?.cells.find(c=>c.column_id===column);
  return cell?.kind==='text' ? cell.text : 'Not retained';
}
export function newsBasis(report: NativeReport, field: string) {
  return newsCell(report.tables.find(t=>t.id==='news-basis')?.rows.find(r=>r.id===field),'value');
}
export const coverageStates: Record<string,{title:string;description:string}> = {
  retained_records: {title:'Retained news evidence',description:'Read the saved representatives below. Retained clusters do not establish independent stories or comprehensive news coverage.'},
  empty_saved_input: {title:'No saved input records',description:'The saved synthetic input was empty. This is not proof that no news existed or that a live feed returned no stories.'},
  recorded_empty_response: {title:'An empty response was recorded',description:'The saved evidence records an empty response. It does not establish that no company news existed or that coverage was comprehensive.'},
  no_relevant_records: {title:'No relevant records retained',description:'The saved processing record retained no headline matches for this company. Inspect the input and exclusions; this is not a statement that no news existed.'},
  retrieval_failed: {title:'Retrieval or execution failed',description:'This saved run cannot establish news coverage. A failed retrieval is not a valid empty feed; any retained text remains incomplete evidence.'},
  coverage_unknown: {title:'Coverage cannot be established',description:'The saved counts or processing evidence do not establish a consistent coverage record. Inspect the original evidence before interpreting the result.'},
};
export function newsCoverage(report: NativeReport) {
  return coverageStates[newsBasis(report,'coverage-state')] || {title:'Coverage detail not retained',description:'This older presentation has saved counts but no supported coverage-state detail. No retrieval outcome has been reconstructed in the browser.'};
}
export function newsStories(report: NativeReport) {
  const details=report.tables.find(t=>t.id==='news-story-details');
  return (report.tables.find(t=>t.id==='retained-headlines')?.rows || []).map((row,index)=>{
    const detail=details?.rows.find(r=>r.id==='story-'+index);
    return {id:row.id,index,headline:newsCell(row,'headline'),publisher:newsCell(row,'publisher'),published:newsCell(row,'published'),
      scope:displaySourceText(detail ? newsCell(detail,'scope') : newsCell(row,'scope')),retrieved:newsCell(detail,'retrieved'),language:newsCell(detail,'language'),
      relevance:newsCell(detail,'relevance'),matches:newsCell(detail,'matches'),cluster:newsCell(detail,'cluster'),size:newsCell(detail,'size'),
      scorer:newsCell(detail,'scorer'),url:newsCell(detail,'url'),excerpt:newsCell(detail,'excerpt'),hasDetail:!!detail,
      refs:[...new Set([...row.evidence_refs,...(detail?.evidence_refs || [])])]};
  });
}
export function filterNewsStories(stories: ReturnType<typeof newsStories>, query: string) {
  const term=query.trim().toLocaleLowerCase();
  return stories.filter(s=>!term || (s.headline+' '+s.publisher).toLocaleLowerCase().includes(term));
}
export function scorerName(value: string) {
  return ({stub:'Synthetic fixture scorer',lm:'Loughran–McDonald lexical tone',finbert:'FinBERT document tone','finbert+lm':'FinBERT and lexical comparison'} as Record<string,string>)[value] || value;
}
