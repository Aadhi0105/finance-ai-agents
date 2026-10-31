import React, { useEffect, useRef, useState } from 'react';
import { Icon } from '../icons';
import type { Artifact, Run } from '../workspace-types';
import { coreMetricIds, fetchArtifact, fetchReport, pointMetric, ReportFailure, summaryFindings, verifyOriginal } from './report-data';
import type { Evidence, NativeReport } from './report-data';
import { calendarDate, formatMetric, savedInstant } from './format';
import { AnalysisSections } from './AnalysisSections';
import { EventSections, EventGateDetails } from './EventSections';
import { NewsSections, NewsReviewDetails } from './NewsSections';
import { MetricCard, ReportHeader, ReportSection, ReportStates, ReviewNotice, SectionNavigation } from './ReportFrame';
import './report-reader.css';

type LoadState = { kind: 'loading' } | { kind: 'ready'; report: NativeReport } | { kind: 'error'; error: ReportFailure; originalVerified: boolean };
const researchLinks = [ ['summary', 'Research summary'], ['figures', 'Key figures'], ['performance', 'Business performance'],
  ['valuation', 'Valuation & assumptions'], ['peers', 'Peer comparison'], ['market', 'Saved market context'],
  ['consensus', 'Market consensus'], ['external-research', 'External research'], ['review', 'Review priorities'], ['evidence', 'Saved evidence'] ] as const;
const eventLinks = [['summary', 'Study summary'], ['sample', 'What was examined'], ['observations', 'Historical observations'],
  ['interpretation', 'What this means'], ['review', 'Why review is required'], ['evidence', 'Saved evidence']] as const;
const newsLinks = [['summary', 'News summary'], ['stories', 'Retained stories'], ['coverage', 'Coverage and exclusions'],
  ['tone', 'Tone evidence'], ['review', 'Why review is required'], ['evidence', 'Saved evidence']] as const;
type SectionId = typeof researchLinks[number][0] | typeof eventLinks[number][0] | typeof newsLinks[number][0];
const categoryLabel: Record<string, string> = { data_basis: 'Data basis', observation_dates: 'Dates & recency', valuation_assumptions: 'Valuation assumptions',
  peer_comparability: 'Peer comparison', narrative_support: 'Supported narrative', statistical_eligibility: 'Statistical eligibility', delivery: 'Saved files' };

function jumpTo(section: SectionId) {
  const target = document.getElementById('report-' + section);
  target?.scrollIntoView({ block: 'start', behavior: 'instant' });
  target?.focus({ preventScroll: true });
}

export function NativeReportReader({ run, onReloadWorkspace }: { run: Run; onReloadWorkspace: () => void }) {
  const isEvents = run.workflow === 'events';
  const isNews = run.workflow === 'news', isMarket = isEvents || isNews;
  const [state, setState] = useState<LoadState>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadNotice, setDownloadNotice] = useState('');
  const activeRequest = useRef<AbortController | null>(null);
  const downloadRequest = useRef<AbortController | null>(null);
  const errorHeading = useRef<HTMLHeadingElement | null>(null);
  const original = run.artifacts.find(a => a.id === run.report_id && a.kind === 'report');

  useEffect(() => {
    const controller = new AbortController();
    activeRequest.current = controller;
    setState({ kind: 'loading' }); setDownloadNotice(''); setDownloading(null);
    fetchReport(run, controller.signal).then(report => {
      if (!controller.signal.aborted) setState({ kind: 'ready', report });
    }).catch(async reason => {
      if (controller.signal.aborted) return;
      const error = reason instanceof ReportFailure ? reason : new ReportFailure('connection_unavailable');
      const originalVerified = error.code === 'native_view_unavailable' && await verifyOriginal(run, controller.signal);
      if (!controller.signal.aborted) setState({ kind: 'error', error, originalVerified });
    });
    return () => { controller.abort(); downloadRequest.current?.abort(); };
  }, [run, attempt]);
  useEffect(() => {
    if (state.kind === 'error') errorHeading.current?.focus();
    if (state.kind === 'ready') document.getElementById('native-report-title')?.focus();
  }, [state.kind]);

  async function download(artifact: Artifact) {
    if (downloading) return;
    const controller = new AbortController(); downloadRequest.current = controller;
    setDownloading(artifact.id); setDownloadNotice('');
    try {
      const bytes = await fetchArtifact(run, artifact, controller.signal);
      const url = URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }));
      const link = document.createElement('a'); link.href = url; link.download = artifact.name.split('/').pop()!;
      document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setDownloadNotice('Verified download ready: ' + artifact.label);
    } catch (reason) {
      if (controller.signal.aborted) return;
      const error = reason instanceof ReportFailure ? reason : new ReportFailure('connection_unavailable');
      setState({ kind: 'error', error, originalVerified: false });
      window.scrollTo(0, 0);
    } finally { if (!controller.signal.aborted) setDownloading(null); }
  }
  const retry = () => { activeRequest.current?.abort(); downloadRequest.current?.abort(); setState({ kind: 'loading' }); setAttempt(n => n + 1); };
  return <div className="native-reader">
    <a href={isMarket ? '#/agent/agent3' : '#/agent/agent1'} className="back-link"><Icon name="back" size={16} />{isMarket ? 'Market & news reports' : 'Research reports'}</a>
    {state.kind === 'loading' ? <section className="nr-load" aria-busy="true" role="status"><span className="spinner" /><h1>{isNews ? 'Opening saved company news' : isEvents ? 'Opening saved event study' : 'Opening saved research'}</h1><p>Checking the report and its registered evidence…</p><div className="nr-skeleton" aria-hidden="true"><span /><span /><span /></div></section>
      : state.kind === 'error' ? <section className="nr-error" role="alert"><span className="nr-error-icon"><Icon name="info" size={26} /></span><p className="eyebrow">{isNews ? 'SAVED COMPANY NEWS' : isEvents ? 'SAVED EVENT STUDY' : 'SAVED RESEARCH'} / {run.entity}</p><h1 tabIndex={-1} ref={errorHeading}>{state.error.title}</h1><p>{state.error.message}</p>
        <div className="nr-error-actions"><button className="primary-button" onClick={retry}>Try reading again</button><button className="nr-secondary-button" onClick={onReloadWorkspace}>Reload workspace</button></div>
        {state.originalVerified && original && <div className="nr-original-available"><h2>Original saved report</h2><p>The registered original passed the workspace checks. It retains its original restrictions.</p><button className="text-button" onClick={() => download(original)} disabled={!!downloading}><Icon name="download" size={16} />{downloading ? 'Checking download…' : 'Download original HTML'}</button></div>}
      </section>
      : <ReportContent report={state.report} run={run} downloading={downloading} onDownload={download} onRecheck={retry} />}
    <p className="nr-download-notice" role="status">{downloadNotice}</p>
  </div>;
}

function ReportContent({ report, run, downloading, onDownload, onRecheck }: {
  report: NativeReport; run: Run; downloading: string | null; onDownload: (artifact: Artifact) => void; onRecheck: () => void;
}) {
  const isEvents = report.workflow === 'events';
  const isNews = report.workflow === 'news', isMarket = isEvents || isNews;
  const sectionLinks = isNews ? newsLinks : isEvents ? eventLinks : researchLinks;
  const [active, setActive] = useState<SectionId>('summary');
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence[]>([]);
  const returnControl = useRef<HTMLElement | null>(null);
  const reviewPanels = useRef(new Map<string, HTMLDetailsElement>());
  const original = run.artifacts.find(a => a.id === run.report_id)!;
  const findings = summaryFindings(report);
  const metrics = coreMetricIds.flatMap(id => report.metrics.filter(m => m.id === id && m.visibility === 'main'));

  useEffect(() => {
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(e => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (visible) setActive(visible.target.id.slice(7) as SectionId);
    }, { rootMargin: '-5% 0px -65% 0px' });
    sectionLinks.forEach(([id]) => { const node = document.getElementById('report-' + id); if (node) observer.observe(node); });
    return () => observer.disconnect();
  }, []);

  function inspect(refs: string[]) {
    returnControl.current = document.activeElement as HTMLElement;
    setSelectedEvidence(refs.flatMap(id => report.evidence.filter(e => e.id === id)));
    setActive('evidence'); jumpTo('evidence');
  }
  function showReviews(refs: string[]) {
    refs.forEach(id => { const node = reviewPanels.current.get(id); if (node) node.open = true; });
    setActive('review'); jumpTo('review');
    reviewPanels.current.get(refs[0])?.querySelector<HTMLElement>('summary')?.focus({ preventScroll: true });
  }
  function returnToFigure() {
    setSelectedEvidence([]);
    returnControl.current?.scrollIntoView({ block: 'center' }); returnControl.current?.focus({ preventScroll: true });
  }
  return <>
    <ReportHeader title={isNews ? 'Company news' : isEvents ? 'Past event reactions' : report.identity.title} entity={report.identity.entity}
      eyebrow={isMarket ? <>AGENT 03 <span>/</span> {isNews ? 'SAVED COMPANY NEWS' : 'HISTORICAL EVENT RESEARCH'}</> : <>AGENT 01 <span>/</span> COMPANY RESEARCH <span>/</span> {report.identity.ticker || 'SAVED COMPANY'}</>}
      period={<>{isMarket && <>{report.identity.title}<span>·</span></>}{report.identity.period_end ? <>Period ending <time dateTime={report.identity.period_end}>{calendarDate(report.identity.period_end)}</time></> : report.identity.period_label}<span>·</span>Saved synthetic inputs</>}
      action={<button className="nr-secondary-button" onClick={() => onDownload(original)} disabled={!!downloading}><Icon name="download" size={16} />{downloading === original.id ? 'Checking download…' : 'Original HTML'}</button>} />
    <ReportStates execution={report.state.execution} evidenceGate={report.state.evidence_gate} />
    <ReviewNotice title={isNews ? 'Synthetic news — published tone withheld' : isEvents ? 'Historical diagnostics — review required' : 'Read as illustrative research'} action={<button onClick={() => jumpTo('review')}>{isMarket ? 'Why review is required' : 'Review priorities'}<Icon name="arrow" size={15} /></button>}>
      {isNews ? 'Fictional retained text illustrates this workflow. Document scores do not establish company-specific sentiment, market direction or financial approval.' : isEvents ? 'These saved cases describe past observations. They do not predict the next event, establish causality or grant financial approval.' : 'These saved figures require financial review. Matching files do not establish verified company facts or approval.'}
    </ReviewNotice>

    <div className="nr-report-grid">
      <SectionNavigation sections={sectionLinks} active={active} onSelect={id => { setActive(id as SectionId); jumpTo(id as SectionId); }}>
        <div className="nr-reading-note"><Icon name="evidence" size={21} /><h2>A saved snapshot</h2><p>Opening this report does not refresh prices, estimates or sources.</p><button className="text-button" onClick={onRecheck}>Recheck saved report</button></div>
      </SectionNavigation>

      <div className="nr-report-body">
        {isNews ? <NewsSections report={report} onInspect={inspect} onReviews={showReviews} /> : isEvents ? <EventSections report={report} onInspect={inspect} onReviews={showReviews} /> : <>
        <ReportSection id="summary" eyebrow="01 / THE SAVED OBSERVATIONS" title="Research summary">
          <p className="nr-summary-text">{report.summary.text}</p>
          {findings.length ? <ol className="nr-findings">{findings.map((finding, i) => <li key={finding.id}><span className="nr-finding-number">{String(i + 1).padStart(2, '0')}</span><div><p>{finding.content.text}</p><button className="nr-source-button" onClick={() => inspect(finding.content.evidence_refs)}><Icon name="evidence" size={13} />View saved source</button></div></li>)}</ol>
            : <div className="nr-empty"><h3>No supported observations available</h3><p>The saved report contains no available main observations for this summary. Review the evidence before drawing conclusions.</p></div>}
          <div className="nr-scope-note"><strong>Report coverage</strong><p>Read supported observations, conditional valuation, peer screening and dated market context below. External estimates and broker research retain their own availability; every restriction remains linked to the saved evidence.</p></div>
        </ReportSection>

        <ReportSection id="figures" eyebrow="02 / PERIOD AND UNITS RETAINED" title="Key figures">
          <p className="nr-section-intro">Illustrative saved values for the stated period. Open a figure’s source to inspect its exact value and basis.</p>
          {metrics.length ? <div className="nr-metric-grid">{metrics.map(metric => <MetricCard key={metric.id} metric={metric} onInspect={() => inspect(metric.evidence_refs)} />)}</div>
            : <div className="nr-empty"><h3>Key figures unavailable</h3><p>No supported key figures are present in this saved report. Missing values have not been replaced with zero.</p></div>}
        </ReportSection>

        <AnalysisSections report={report} onInspect={inspect} onReviews={showReviews} />
        </>}

        <ReportSection id="review" eyebrow={isMarket ? '05 / UNDERSTAND THE RESTRICTIONS' : '09 / BEFORE RELYING ON THE RESULT'} title={isMarket ? 'Why review is required' : 'Review priorities'}>
          <p className="nr-section-intro">Saved review notes and their source findings remain attached to this report. Completing a process does not approve its financial conclusions.</p>
          {report.review_items.length ? <div className="nr-review-list">{report.review_items.map(item => <details key={item.id} ref={node => { if (node) reviewPanels.current.set(item.id, node); else reviewPanels.current.delete(item.id); }} className="nr-review-item"><summary><Icon name="info" size={17} /><span>{item.title}</span><small>{item.impact === 'publication_block' ? 'Publication restricted' : 'Section requires review'}</small><span className="nr-expand-mark" aria-hidden="true">+</span></summary><div className="nr-review-detail"><p className="eyebrow">{categoryLabel[item.category] || 'Saved review requirement'}</p><p>{item.explanation}</p><p><strong>Next review:</strong> {item.action}</p>{item.section_refs.length > 0 && <p className="nr-affected">Applies to: {item.section_refs.map(id => report.sections.find(s => s.id === id)?.title || id).join(' · ')}</p>}<button className="nr-source-button" onClick={() => inspect(item.evidence_refs)}>Inspect original findings<Icon name="arrow" size={14} /></button><details className="nr-reference-details"><summary>Saved check references ({item.source_check_refs.length})</summary><ul>{item.source_check_refs.map(ref => <li key={ref}><code>{ref}</code></li>)}</ul></details></div></details>)}</div>
            : <div className="nr-empty"><p>No additional review notes were saved. Financial approval remains unavailable in this workspace.</p></div>}
          {isEvents && <EventGateDetails report={report} onInspect={inspect} />}
          {isNews && <NewsReviewDetails report={report} onInspect={inspect} />}
        </ReportSection>

        <ReportSection id="evidence" eyebrow={isMarket ? '06 / TRACE THE SAVED RECORD' : '10 / TRACE THE SAVED RECORD'} title="Saved evidence">
          <p className="nr-section-intro">File checks establish consistency with the saved inventory. They do not authenticate an issuer or establish source truth.</p>
          {selectedEvidence.length > 0 && <div className="nr-selected-source"><div className="nr-source-heading"><h3>Selected source references</h3><button className="text-button" onClick={returnToFigure}><Icon name="back" size={14} />Return to reading</button></div>{selectedEvidence.map(e => {
            const artifact = run.artifacts.find(a => a.id === e.artifact_id)!;
            const source = report.sources.find(s => s.id === e.source_id)!;
            const referencedMetrics = report.metrics.filter(m => m.evidence_refs.includes(e.id));
            const referencedPoints = referencedMetrics.length ? [] : report.charts.flatMap(c => c.series.flatMap(series => series.points.filter(p => p.evidence_refs.includes(e.id)).map(p => ({ key: c.id + '-' + series.id + '-' + p.id, metric: pointMetric(c, p), label: series.label }))));
            return <div className="nr-source-record" key={e.id}><h4>{e.label}</h4>{referencedMetrics.map(m => <p className="nr-exact-value" key={m.id}>{m.label}: <strong>{formatMetric(m)}</strong><span>{calendarDate(m.period_label)}</span><small>Canonical saved value: {m.value ?? 'null'} · {m.unit}{m.visibility === 'diagnostic' ? ' · diagnostic; review required' : ''}</small></p>)}{referencedPoints.map(({key,metric,label}) => <p className="nr-exact-value" key={key}>{label}: <strong>{formatMetric(metric)}</strong><span>{calendarDate(metric.period_label)}</span><small>Canonical saved value: {metric.value ?? 'null'} · {metric.unit}{metric.visibility === 'diagnostic' ? ' · diagnostic; review required' : ''}</small></p>)}<dl><dt>Saved artifact</dt><dd>{artifact.name}</dd><dt>Source basis</dt><dd>{source.label}</dd><dt>Saved field</dt><dd><code>{e.pointer || '(complete saved record)'}</code></dd><dt>Transformation</dt><dd>{e.method || (e.transform === 'identity' ? 'Original saved field' : e.transform)}</dd></dl><button className="nr-source-button" onClick={() => onDownload(artifact)} disabled={!!downloading}><Icon name="download" size={14} />Download {artifact.name}</button></div>;
          })}</div>}
          <dl className="nr-record-meta"><div><dt>Prepared</dt><dd><time dateTime={report.identity.prepared_at}>{savedInstant(report.identity.prepared_at)}</time></dd></div><div><dt>Data basis</dt><dd>Synthetic demonstration</dd></div><div><dt>Observation / estimate dates</dt><dd>Not established by preparation time</dd></div><div><dt>Reader scope</dt><dd>Saved observations; no authenticated financial approval</dd></div></dl>
          <button className="nr-secondary-button nr-mobile-recheck" onClick={onRecheck}><Icon name="history" size={15} />Recheck saved report</button>
          <div className="nr-file-list">{run.artifacts.filter(a => a.kind === 'report' || a.kind === 'evidence' || a.kind === 'report_view').map(artifact => <div className="nr-file" key={artifact.id}><span className="nr-file-icon"><Icon name={artifact.kind === 'report' ? 'research' : 'evidence'} size={19} /></span><div><h3>{artifact.label}</h3><p>{artifact.name}</p></div><button aria-label={`Download ${artifact.label}`} className="nr-file-download" disabled={!!downloading} onClick={() => onDownload(artifact)}><Icon name="download" size={17} />{downloading === artifact.id ? 'Checking…' : 'Download'}</button></div>)}</div>
          {report.glossary.length > 0 && <details className="nr-method-glossary"><summary>Methodology & definitions</summary><dl>{report.glossary.map(g => <div key={g.term}><dt>{g.term}</dt><dd>{g.definition}</dd></div>)}</dl></details>}
          <details className="nr-technical-record"><summary>Record identity & file hashes</summary><dl><dt>Source run</dt><dd><code>{report.identity.source_run_id}</code></dd><dt>Presentation</dt><dd><code>{report.report_id}</code></dd></dl>{run.artifacts.map(a => <p key={a.id}><strong>{a.name}</strong><code>{a.sha256}</code></p>)}</details>
        </ReportSection>
      </div>
    </div>
  </>;
}
