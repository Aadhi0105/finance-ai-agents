import { useEffect, useMemo, useRef } from 'react';
import type { NativeReport } from './report-data';
import { datasetRows, pointMetric } from './report-data';
import type { ChartData } from './analysis-types';
import type { Run } from '../workspace-types';
import { formatMetric, savedInstant } from './format';
import { plotGeometry, tickIndices } from './chart-layout';
import { readingCopy } from './reading-copy';
import { ReportStates } from './ReportFrame';
import './reading-copy.css';

function StaticPlot({chart}:{chart:ChartData}) {
  const rows=datasetRows(chart),g=plotGeometry(chart,rows,900);
  const barWidth=Math.min(40,(g.right-g.left)/Math.max(1,rows.length)*.6);
  if(g.reason || !rows.length) return <p>{chart.availability==='withheld'?'Values withheld':'No graphical values available'}. {chart.reason_codes.join(', ')}</p>;
  return <div className="nr-copy-plot-scroll" role="region" aria-label={chart.title+' static plot'} tabIndex={0}><svg className="nr-copy-plot" viewBox={`0 0 ${g.width} ${g.height}`} role="img" aria-label={chart.title+' · complete saved series; exact values follow'}>
    <title>{chart.title}</title>
    {g.ticks.map(t=><g key={t.value}><line x1={g.left} x2={g.right} y1={t.y} y2={t.y} stroke="#d8dfd5"/><text x={g.left-8} y={t.y+4} textAnchor="end">{formatMetric(pointMetric(chart,{id:'axis',x:'',label:'',y:t.value,evidence_refs:[],reason_codes:[]} ),true)}</text></g>)}
    <line x1={g.left} x2={g.right} y1={g.zero} y2={g.zero} stroke="#385d49"/>
    {g.series.flatMap(s=>s.segments.flat().map(p=><g key={s.index+'-'+p.row}><rect x={p.x-barWidth/2} width={barWidth} y={Math.min(p.y,g.zero)} height={Math.abs(p.y-g.zero)} fill="#315f4c"/>{p.y===g.zero&&<line x1={p.x-barWidth/2} x2={p.x+barWidth/2} y1={p.y} y2={p.y} stroke="#315f4c"/>}</g>))}
    {tickIndices(g.xs,900).map(i=><text key={i} x={g.xs[i]} y={g.bottom+20} textAnchor="middle">{rows[i].x.length>18?rows[i].x.slice(0,17)+'…':rows[i].x}</text>)}
    <text x={(g.left+g.right)/2} y={g.height-4} textAnchor="middle">{chart.x_axis.label}</text>
  </svg></div>;
}

function FullTable({title,columns,rows}:{title:string;columns:string[];rows:{id:string;values:string[];references:string}[]}) {
  return <div className="nr-copy-table-scroll" role="region" aria-label={title} tabIndex={0}><table><caption>{title} · {rows.length} saved rows</caption><thead><tr>{columns.map((c,i)=><th key={i} scope="col">{c}</th>)}<th scope="col">Evidence</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}>{row.values.map((v,i)=>i===0?<th key={i} scope="row">{v}</th>:<td key={i}>{v}</td>)}<td>{row.references}</td></tr>)}</tbody></table>{!rows.length&&<p>No rows retained.</p>}</div>;
}

export function ReadingCopy({report,run,busy,onClose,onPrint}:{report:NativeReport;run:Run;busy:boolean;onClose:()=>void;onPrint:()=>void}) {
  const copy=useMemo(()=>readingCopy(report),[report]),heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{
    document.body.classList.add('reading-copy-open');heading.current?.focus();window.scrollTo(0,0);
    return()=>document.body.classList.remove('reading-copy-open');
  },[]);
  return <article className="nr-reading-copy">
    <div className="nr-copy-actions"><button className="nr-secondary-button" onClick={onClose} disabled={busy}>Return to interactive report</button><button className="nr-secondary-button" onClick={onPrint} disabled={busy}>{busy?'Checking saved evidence…':'Print reading copy'}</button></div>
    <header><p className="eyebrow">KEYSTONE / COMPLETE READING COPY / SYNTHETIC EVIDENCE</p><h1 ref={heading} tabIndex={-1}>{copy.title} — reading copy</h1><p>{report.identity.entity} · {report.identity.period_label}</p><p>Prepared {savedInstant(report.identity.prepared_at)}</p></header>
    <ReportStates execution={report.state.execution} evidenceGate={report.state.evidence_gate}/>
    <div className="nr-copy-notice"><strong>Review required · financial approval not granted</strong><p>{report.workflow==='news'?'Published document tone remains withheld. Diagnostic zero is not a published neutral conclusion.':'Historical diagnostics do not predict the next event or establish causality. The event-relative path remains withheld.'}</p><p>Includes every retained row, series and review note from this presentation, independently of screen filters and pagination. Saved display excerpts remain excerpts; full originals remain in their registered files. File consistency does not authenticate a source.</p></div>
    <section><h2>Summary</h2><p>{report.summary.text}</p><p className="nr-copy-reference">Evidence: {copy.references(report.summary.evidence_refs)}</p></section>
    <section><h2>Review requirements</h2>{report.review_items.map(item=><article key={item.id}><h3>{item.title} · {item.impact==='publication_block'?'Publication restricted':'Section requires review'}</h3><p>{item.explanation}</p><p><strong>Next review:</strong> {item.action}</p><p className="nr-copy-reference">Evidence: {copy.references(item.evidence_refs)}</p><ul>{item.source_check_refs.map(ref=><li key={ref}><code>{ref}</code></li>)}</ul></article>)}</section>
    <section><h2>All saved measures</h2><FullTable title="Saved measures" columns={['Measure','Value / state','Canonical value','Unit','Period / scope']} rows={copy.metrics.map(m=>({id:m.id,values:[m.label+(m.visibility==='diagnostic'?' · Diagnostic':''),m.display,m.value??'null',m.unit,m.period_label],references:m.references}))}/></section>
    <section><h2>Charts and complete numerical data</h2>{copy.charts.map(({chart,rows})=><article className="nr-copy-dataset" key={chart.id}><h3>{chart.title}{chart.visibility==='diagnostic'?' · Diagnostic; review required':''}</h3><p>{chart.purpose}</p><StaticPlot chart={chart}/><FullTable title={chart.title+' exact data'} columns={[chart.x_axis.label,...chart.series.map(s=>s.label)]} rows={rows.map(r=>({id:r.id,values:[r.label,...r.values],references:r.references}))}/></article>)}</section>
    <section><h2>Complete saved tables</h2>{copy.tables.map(t=><FullTable key={t.id} title={t.title} columns={t.columns.map(c=>c.label)} rows={t.rows}/>)}</section>
    <section><h2>Methodology and definitions</h2><dl>{report.glossary.map(g=><div key={g.term}><dt>{g.term}</dt><dd>{g.definition}</dd></div>)}</dl></section>
    <section><h2>Evidence references and file identities</h2><p>References below point to registered saved artifacts and fields. Unverified URLs in source text remain plain text in this copy.</p><dl className="nr-copy-identity"><dt>Source run</dt><dd>{report.identity.source_run_id}</dd><dt>Presentation</dt><dd>{report.report_id}</dd></dl><FullTable title="Evidence reference index" columns={['Reference','Description','Saved artifact','Saved field','Transformation']} rows={copy.evidence.map(e=>({id:e.id,values:[e.label,e.description,e.artifact,e.pointer||'(complete record)',e.method||e.transform],references:e.label}))}/><ul>{run.artifacts.map(a=><li key={a.id}>{a.name} · SHA-256 <code>{a.sha256}</code></li>)}</ul></section>
  </article>;
}
