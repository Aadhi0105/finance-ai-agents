import { useState } from 'react';
import type { NativeReport } from './report-data';
import { DatasetTable, LocalReviews, SavedTable } from './AnalysisSections';
import { MetricCard, ReportSection } from './ReportFrame';
import { savedInstant } from './format';
import { filterNewsStories, newsBasis, newsCoverage, newsStories, scorerName } from './news-data';
import './news-report.css';

type Props={report:NativeReport;onInspect:(refs:string[])=>void;onReviews:(refs:string[])=>void};
const PAGE_SIZE=10;

export function NewsSections({report,onInspect,onReviews}:Props) {
  const [query,setQuery]=useState(''),[page,setPage]=useState(0);
  const stories=newsStories(report), filtered=filterNewsStories(stories,query), coverage=newsCoverage(report);
  const table=(id:string)=>report.tables.find(t=>t.id===id);
  const local=(section:string)=><LocalReviews refs={report.sections.find(s=>s.id===section)?.review_refs || []} report={report} onReviews={onReviews}/>;
  const plot=(id:string)=>report.charts.filter(c=>c.id===id).map(c=><DatasetTable key={c.id} chart={c} onInspect={onInspect} review={<LocalReviews refs={c.review_refs} report={report} onReviews={onReviews}/>}/>);
  return <>
    <ReportSection id="summary" eyebrow="01 / COVERAGE BEFORE CONCLUSIONS" title="News summary">
      <p className="nr-summary-text">{report.summary.text}</p>
      <div className="nr-news-cutoff"><div><span>Saved cutoff</span><strong>{newsBasis(report,'cutoff')==='Not retained' ? 'Not retained in this presentation' : savedInstant(newsBasis(report,'cutoff'))}</strong></div><div><span>Maximum publication age</span><strong>{newsBasis(report,'max-age')==='Not retained' ? 'Not retained' : newsBasis(report,'max-age')+' days'}</strong></div></div>
      <p className="nr-analysis-note">This is a saved synthetic snapshot. Opening the report does not fetch current headlines. Publication time, retrieval time and report preparation time have separate meanings.</p>
      <div className="nr-news-metrics">{['coverage-raw','coverage-after-relevance','coverage-after-dedup'].flatMap(id=>{const m=report.metrics.find(m=>m.id===id);return m?[<MetricCard key={id} metric={m} onInspect={()=>onInspect(m.evidence_refs)}/>]:[];})}</div>
      <div className="nr-news-held"><p className="eyebrow">PUBLISHED DOCUMENT TONE</p><h3>Tone withheld</h3><p>These illustrative inputs do not support a published tone conclusion. A saved diagnostic value of zero does not make the published result neutral. No investment recommendation or future-return estimate is supplied.</p><button className="nr-source-button" onClick={()=>onReviews(report.sections.find(s=>s.id==='tone')?.review_refs || [])}>Understand the tone restrictions →</button></div>
    </ReportSection>

    <ReportSection id="stories" eyebrow="02 / THE RETAINED TEXT" title="Retained stories">
      <p className="nr-section-intro">Read each retained cluster representative with its own publisher, publication time and text scope. These are fictional demonstration records. Grouping does not verify a source or establish independent stories.</p>
      {local('retained-news')}
      {stories.length>0 ? <>
        <div className="nr-news-search"><label htmlFor="news-story-search">Search saved headlines or publishers</label><input id="news-story-search" type="search" value={query} onChange={e=>{setQuery(e.target.value);setPage(0);}} placeholder="Filter retained records…"/><p role="status">{filtered.length} of {stories.length} retained representatives shown by this filter. Filtering changes only this list.</p></div>
        {filtered.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE).map(story=><article className="nr-news-story" key={story.id}>
          <div className="nr-news-story-meta"><span>Story {story.index+1} · synthetic evidence</span><span>{story.publisher}</span></div><h3>{story.headline}</h3>
          <dl className="nr-news-story-basis"><div><dt>Published</dt><dd>{savedInstant(story.published)}</dd></div><div><dt>Retained scope</dt><dd>{story.scope}</dd></div></dl>
          <button className="nr-source-button" onClick={()=>onInspect(story.refs)}>Inspect story evidence →</button>
          <details className="nr-news-story-detail"><summary>Text, relevance and grouping details</summary>
            {story.hasDetail ? <><dl><div><dt>Retrieved</dt><dd>{savedInstant(story.retrieved)}</dd></div><div><dt>Original publication timestamp</dt><dd>{story.published}</dd></div><div><dt>Language</dt><dd>{story.language}</dd></div><div><dt>Relevance method</dt><dd>{story.relevance==='headline_alias_or_cashtag' ? 'Recorded headline alias or cashtag match' : story.relevance}</dd></div><div><dt>Recorded matches</dt><dd>{story.matches}</dd></div><div><dt>Cluster size</dt><dd>{story.size} recorded member(s); independence not established</dd></div><div><dt>Scorer</dt><dd>{scorerName(story.scorer)}</dd></div></dl>
              <p className="nr-analysis-note">Saved text excerpt · full-article text is not implied</p><blockquote>{story.excerpt}</blockquote><p className="nr-analysis-note">Recorded address (unverified demonstration reference): <code>{story.url}</code></p><p className="nr-analysis-note">Cluster identity: <code>{story.cluster}</code></p></>
              : <p className="nr-analysis-note">This older presentation did not retain these display details. Inspect its original registered evidence; no text scope, cluster members or scorer metadata have been reconstructed here.</p>}
          </details>
        </article>)}
        {!filtered.length && <div className="nr-empty"><h3>No matching retained headlines</h3><p>The filter matched no saved headline or publisher. This does not change the study’s coverage or publication state.</p><button className="nr-source-button" onClick={()=>setQuery('')}>Clear headline filter</button></div>}
        {filtered.length>PAGE_SIZE && <nav className="nr-table-pager" aria-label="Retained stories pages"><span>Page {page+1} of {Math.ceil(filtered.length/PAGE_SIZE)}</span><div><button className="nr-page-button" onClick={()=>setPage(p=>p-1)} disabled={!page}>Previous</button><button className="nr-page-button" onClick={()=>setPage(p=>p+1)} disabled={(page+1)*PAGE_SIZE>=filtered.length}>Next</button></div></nav>}
      </> : <div className="nr-empty"><h3>No retained representatives</h3><p>{coverage.description} No substitute headlines or neutral tone have been supplied.</p></div>}
      {table('news-cluster-members') && <details className="nr-method-glossary"><summary>Inspect retained cluster members</summary><p className="nr-analysis-note">These are the recorded members, including duplicates. Their inclusion does not demonstrate independent reporting.</p><SavedTable table={table('news-cluster-members')!} report={report} onInspect={onInspect}/></details>}
    </ReportSection>

    <ReportSection id="coverage" eyebrow="03 / INPUTS, SELECTION AND EXCLUSIONS" title="Coverage and exclusions">
      <div className="nr-empty"><h3>{coverage.title}</h3><p>{coverage.description}</p></div>
      {plot('news-coverage')}
      {table('news-basis') ? <details className="nr-method-glossary"><summary>Saved cutoff and coverage basis</summary><SavedTable table={table('news-basis')!} report={report} onInspect={onInspect}/></details> : <p className="nr-analysis-note">This older presentation contains no coverage-state table.</p>}
      {table('news-exclusions') ? table('news-exclusions')!.rows.length ? <><h3>Excluded input records</h3><p className="nr-analysis-note">Original reasons and stage references are retained below. Exclusion does not establish that a story was unimportant.</p><SavedTable table={table('news-exclusions')!} report={report} onInspect={onInspect}/></> : <p className="nr-analysis-note">No excluded input records were retained in this projection. This does not prove complete coverage.</p> : <p className="nr-analysis-note">Exclusion detail is not retained in this older presentation; inspect the original bundle.</p>}
    </ReportSection>

    <ReportSection id="tone" eyebrow="04 / DOCUMENT TEXT, NOT A MARKET SIGNAL" title="Tone evidence">
      <p className="nr-section-intro">Published tone remains withheld. Headline relevance links a document to a company; it does not isolate sentiment toward that company. Clusters are heuristic text groups. Scorer probabilities are not calibrated reliability or return probabilities.</p>
      {local('tone')}
      <details className="nr-news-diagnostics"><summary>Inspect saved diagnostics · review required</summary>
        <p className="nr-analysis-note">The values below describe the retained text only. They do not replace the withheld published result. Zero is a possible numerical diagnostic; it is not a published “neutral” conclusion.</p>
        {plot('news-story-tone')}
        {table('news-tone-records') ? <SavedTable table={table('news-tone-records')!} report={report} onInspect={onInspect}/> : <div className="nr-news-legacy-tone">{report.metrics.filter(m=>m.id.startsWith('diagnostic-tone-')).map(m=><MetricCard key={m.id} metric={m} diagnosticLabel="Text diagnostic · review required" onInspect={()=>onInspect(m.evidence_refs)}/>)}<p className="nr-analysis-note">This older presentation has no supported story-score plot or detailed scorer table.</p></div>}
        {table('news-scorer-details') && <details className="nr-method-glossary"><summary>Saved scorer metadata and text limits</summary><SavedTable table={table('news-scorer-details')!} report={report} onInspect={onInspect}/></details>}
      </details>
    </ReportSection>
  </>;
}

export function NewsReviewDetails({report,onInspect}:Pick<Props,'report'|'onInspect'>) {
  const table=report.tables.find(t=>t.id==='news-review-reasons');
  return table ? <details className="nr-method-glossary"><summary>Original news review identifiers</summary><SavedTable table={table} report={report} onInspect={onInspect}/></details> : null;
}
