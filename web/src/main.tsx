import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Artifact = { id: string; name: string; label: string; kind: string; sha256: string; bytes: number; url: string };
type Run = {
  id: string; agent: string; workflow: string; title: string; entity: string; period: string;
  prepared_at: string; source_run_id: string; execution_status: string; review_status: 'review_required' | 'not_financial_approval';
  summary: string; limitations: string[]; checks: string[];
  metrics: { label: string; value: string; basis: string }[]; artifacts: Artifact[]; report_id: string;
};
type Workspace = { classification: string; prepared_at: string; code_commit: string | null; runs: Run[] };
type IconName = 'overview' | 'research' | 'monitoring' | 'events' | 'close' | 'history' | 'evidence' | 'arrow' | 'search' | 'check' | 'download' | 'info' | 'back' | 'external';
const paths: Record<IconName, string> = {
  overview: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  research: 'M5 3h11l3 3v15H5z M9 8h5 M9 12h6 M9 16h6',
  monitoring: 'M3 12h4l3-7 4 14 3-7h4',
  events: 'M3 17l5-6 4 3 7-9 M15 5h4v4 M3 21h18',
  close: 'M4 4h16v16H4z M4 10h16 M10 10v10 M14 14h2 M14 17h2',
  history: 'M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v6l4 2',
  evidence: 'M12 3l8 4v6c0 4-8 8-8 8s-8-4-8-8V7z M8 12l3 3 5-6',
  arrow: 'M5 12h14 M14 7l5 5-5 5', search: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14 M15 15l6 6',
  check: 'M5 12l4 4L19 6', download: 'M12 3v12 M7 10l5 5 5-5 M4 17v4h16v-4',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 11v6 M12 7v1',
  back: 'M19 12H5 M10 7l-5 5 5 5', external: 'M14 3h7v7 M21 3L10 14 M10 3H3v18h18v-7',
};
function Icon({ name, size = 19 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
const agents = [
  { id: 'agent1', name: 'Research', icon: 'research' as IconName, number: '01' },
  { id: 'agent2', name: 'Financial monitoring', icon: 'monitoring' as IconName, number: '02' },
  { id: 'agent3', name: 'Market & news', icon: 'events' as IconName, number: '03' },
  { id: 'agent4', name: 'Financial close', icon: 'close' as IconName, number: '04' },
];
const workflowName: Record<string, string> = { research: 'Equity research', monitoring: 'Financial monitoring', events: 'Historical events', news: 'News evidence', close: 'Financial close' };
const stateName: Record<string, string> = { completed: 'Completed', held: 'Held for review', failed: 'Failed', refused: 'Refused', unavailable: 'Unavailable' };
const date = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
const runHref = (run: Run) => `#/runs/${encodeURIComponent(run.id)}`;
function Execution({ status }: { status: string }) {
  return <span className={`execution ${status === 'completed' ? 'complete' : 'held'}`}><span className="status-dot" />{stateName[status] || status}</span>;
}
function Review({ status }: { status: Run['review_status'] }) { return <span className="review-tag">{status === 'review_required' ? 'Review required' : 'Not financial approval'}</span>; }

function App() {
  const [route, setRoute] = useState(location.hash.slice(1) || '/');
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [attempt, setAttempt] = useState(0);
  const [about, setAbout] = useState(false);
  useEffect(() => {
    if (!about) return;
    const previous = document.activeElement as HTMLElement | null;
    document.querySelector<HTMLElement>('[role="dialog"] button')?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setAbout(false);
      if (event.key === 'Tab') {
        const controls = Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"] button, [role="dialog"] a[href]'));
        const first = controls[0], last = controls[controls.length - 1];
        if ((event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last)) {
          event.preventDefault(); (event.shiftKey ? last : first)?.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); previous?.focus(); };
  }, [about]);
  useEffect(() => {
    const change = () => { setRoute(location.hash.slice(1) || '/'); setSearch(''); setStatus('all'); window.scrollTo(0, 0); };
    addEventListener('hashchange', change);
    return () => removeEventListener('hashchange', change);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    fetch('/api/workspace', { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error(response.status === 503
        ? 'The saved workspace is unavailable or its evidence has changed. Prepare a fresh synthetic workspace before continuing.'
        : 'The local workspace could not be loaded. Check that the workspace server is running.');
      const data = await response.json();
      if (data.kind !== 'keystone.synthetic-workspace' || data.classification !== 'synthetic'
          || data.production_release_approved !== false || !Array.isArray(data.runs)) {
        throw new Error('The server returned an unsupported workspace.');
      }
      setWorkspace(data);
    }).catch(reason => { if (reason.name !== 'AbortError') setError(reason.message || 'Unable to connect to the workspace.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [attempt]);

  const runs = workspace?.runs || [];
  const selectedId = route.startsWith('/runs/') ? route.slice(6) : null;
  const selected = runs.find(run => run.id === selectedId);
  const agentFilter = route.startsWith('/agent/') ? route.slice(7) : null;
  const activeAgent = selected?.agent || agentFilter;
  const agent = agents.find(item => item.id === agentFilter);
  const isEvidence = route === '/evidence';
  const isHistory = route === '/history';
  const title = selected ? selected.title : isEvidence ? 'Evidence library' : isHistory ? 'Saved run history' : agent ? agent.name : 'Workspace overview';
  const filtered = runs.filter(run => (!agentFilter || run.agent === agentFilter)
    && (status === 'all' || run.execution_status === status)
    && `${run.title} ${run.entity} ${workflowName[run.workflow]} ${run.period}`.toLowerCase().includes(search.toLowerCase()));

  return <div className="app-shell">
    <a className="skip-link" href="#main" onClick={event => { event.preventDefault(); document.getElementById('main')?.focus(); }}>Skip to workspace</a>
    <aside className="sidebar" aria-label="Main navigation">
      <a className="brand" href="#/" aria-label="Keystone workspace home"><span className="brand-symbol">K</span><span>keystone<span className="brand-period">.</span></span></a>
      <div className="workspace-switch"><span className="workspace-avatar">A</span><div><strong>Analyst workspace</strong><small>Personal · local</small></div><span className="workspace-lock"><Icon name="evidence" size={16} /></span></div>
      <p className="nav-label">WORKSPACE</p>
      <nav>
        <Nav href="#/" icon="overview" active={route === '/'}>Overview</Nav>
        <Nav href="#/history" icon="history" active={isHistory}>Run history<span className="nav-count">{runs.length}</span></Nav>
        <Nav href="#/evidence" icon="evidence" active={isEvidence}>Evidence library</Nav>
        <p className="nav-label workflows-label">WORKFLOWS</p>
        {agents.map(item => <Nav key={item.id} href={`#/agent/${item.id}`} icon={item.icon} active={activeAgent === item.id}>{item.name}<span className="nav-number">{item.number}</span></Nav>)}
      </nav>
      <div className="sidebar-bottom"><div className="local-state"><span className="status-dot" />Local environment</div><p>Saved reports. Clear evidence.<br />Every limitation in view.</p><button onClick={() => setAbout(true)}><Icon name="info" size={16} />About this workspace</button></div>
    </aside>

    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb">Workspace<span>/</span><strong>{title}</strong></div><div className="topbar-right"><span className="mode-indicator"><span className="status-dot" />Offline workspace</span><span className="profile-mark" aria-label="Keystone workspace">K</span></div></header>
      <main id="main" tabIndex={-1}>
        <div className="scope-banner"><span className="synthetic-label">SYNTHETIC DATA</span><span>This workspace uses saved demonstration inputs. Results require review and are not verified company facts.</span></div>
        {loading ? <div className="loading-state" role="status"><span className="spinner" />Loading saved workspace…</div>
          : error ? <div className="error-state" role="alert"><Icon name="info" size={28} /><h1>Workspace unavailable</h1><p>{error}</p><button className="primary-button" onClick={() => setAttempt(attempt + 1)}>Try loading again</button></div>
          : selectedId ? selected ? <RunDetail key={selected.id} run={selected} /> : <div className="empty-state"><h1>Saved run not found</h1><p>This run is not registered in the workspace.</p><a className="primary-button" href="#/">Back to overview</a></div>
          : isEvidence ? <EvidenceLibrary runs={runs} />
          : <>
            <div className="page-heading"><div><p className="eyebrow">{agent ? `AGENT ${agent.number} / SAVED WORK` : isHistory ? 'YOUR ANALYTICAL RECORD' : 'THE ANALYST DESK'}</p><h1>{agent ? agent.name : isHistory ? 'Every run, in one place.' : 'A clearer view of your work.'}</h1><p>{agent ? 'Inspect saved results, review restrictions and the evidence behind them.' : 'Research, monitoring, intelligence and close — connected by evidence.'}</p></div><div className="heading-stamp"><span className="stamp-icon"><Icon name="evidence" size={22} /></span><strong>Read-only workspace</strong><small>Browsing never starts an analysis</small></div></div>
            {!agent && !isHistory && <div className="stats-grid"><Stat label="SAVED REPORTS" value={String(runs.length).padStart(2, '0')} note="Generated by the existing engines" icon="research" /><Stat label="AGENT WORKFLOWS" value={String(new Set(runs.map(r => r.agent)).size).padStart(2, '0')} note="One evidence-led workspace" icon="overview" /><Stat label="REQUIRE REVIEW" value={String(runs.filter(r => r.review_status === 'review_required').length).padStart(2, '0')} note="Execution success is not approval" icon="evidence" amber /></div>}
            <div className={`workspace-grid ${isHistory || agent ? 'wide-grid' : ''}`}>
              <section className="panel reports-panel" aria-labelledby="reports-title"><div className="panel-heading"><div><h2 id="reports-title">{isHistory ? 'Saved run history' : agent ? 'Saved reports' : 'Your saved reports'}<span className="count-badge">{filtered.length}</span></h2><p>Frozen inputs. Retained outcomes. Nothing silently refreshed.</p></div></div>
                <div className="filters"><label className="search-box"><Icon name="search" size={17} /><span className="sr-only">Search saved reports</span><input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search company, report or period…" /></label><label className="status-filter"><span className="sr-only">Filter execution status</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="all">All execution states</option><option value="completed">Completed</option><option value="held">Held for review</option><option value="failed">Failed</option><option value="unavailable">Unavailable</option><option value="refused">Refused</option></select></label></div>
                {filtered.length ? <div className="table-region" role="region" aria-label="Saved reports" tabIndex={0}><table className="reports-table"><thead><tr><th>REPORT / COMPANY</th><th>PERIOD / SCOPE</th><th>EXECUTION</th><th>FINANCIAL REVIEW</th><th><span className="sr-only">Open report</span></th></tr></thead><tbody>{filtered.map(run => <tr key={run.id}><td><div className="report-name"><WorkflowIcon run={run} /><div><a className="report-link" href={runHref(run)}>{run.title}</a><span>{run.entity}</span></div></div></td><td><span className="period-text">{run.period}</span><small className="workflow-text">{workflowName[run.workflow]}</small></td><td><Execution status={run.execution_status} /></td><td><Review status={run.review_status} /></td><td><a className="row-arrow" href={runHref(run)} aria-label={`Open ${run.title}`}><Icon name="arrow" size={18} /></a></td></tr>)}</tbody></table></div> : <div className="empty-state"><Icon name="search" size={28} /><h3>No saved reports match</h3><p>Try a different search or execution status.</p><button className="text-button" onClick={() => { setSearch(''); setStatus('all'); }}>Clear filters</button></div>}
                <div className="table-footer"><span><span className="tiny-dot" />{filtered.length} of {runs.length} registered reports</span><span>Source: saved synthetic workspace</span></div>
              </section>
              {!agent && !isHistory && <aside className="right-rail"><section className="panel guide-panel"><div className="guide-icon"><Icon name="evidence" size={23} /></div><p className="eyebrow">BUILT FOR INSPECTION</p><h2>Follow the evidence.</h2><p>A completed run is a starting point for review.</p><ol className="guide-steps"><li><span>01</span><div><strong>Open a saved report</strong><p>See its period and recorded outcome.</p></div></li><li><span>02</span><div><strong>Inspect the limitations</strong><p>Understand what the result supports.</p></div></li><li><span>03</span><div><strong>Trace the source</strong><p>Download the registered evidence.</p></div></li></ol><a href="#/evidence" className="guide-link">Explore evidence library<Icon name="arrow" size={17} /></a></section><section className="boundary-note"><Icon name="info" size={18} /><div><strong>A deliberate boundary</strong><p>No live feeds or paid model calls. Demonstration scores and financial holds remain visible.</p><button className="text-button" onClick={() => setAbout(true)}>Workspace details</button></div></section></aside>}
            </div>
          </>}
        <footer className="workspace-footer"><span>KEYSTONE <span className="footer-divider">/</span> Traceable analysis, thoughtful review.</span><span>{workspace ? `Prepared ${date(workspace.prepared_at)}` : 'Local report workspace'}</span></footer>
      </main>
    </div>
    {about && <div className="modal-backdrop" onClick={() => setAbout(false)}><section className="about-modal" role="dialog" aria-modal="true" aria-labelledby="about-title" onClick={event => event.stopPropagation()}><p className="eyebrow">KEYSTONE / BATCH 1</p><h2 id="about-title">About this workspace</h2><p>A local report browser backed by the existing four agent engines. Every registered run in this workspace was generated offline from synthetic inputs.</p><ul><li>Report browsing makes no provider or model calls.</li><li>Review-required outcomes remain held.</li><li>No financial decisions or corrections can be submitted here.</li><li>File hashes check inventory consistency; they do not establish source truth.</li><li>Independent backup and production acceptance remain pending.</li></ul><button className="primary-button" onClick={() => setAbout(false)}>Return to workspace</button></section></div>}
  </div>;
}

function Nav({ href, icon, active, children }: { href: string; icon: IconName; active: boolean; children: React.ReactNode }) {
  return <a className={`nav-item ${active ? 'active' : ''}`} href={href} aria-current={active ? 'page' : undefined}><Icon name={icon} /><span className="nav-text">{children}</span></a>;
}
function Stat({ label, value, note, icon, amber = false }: { label: string; value: string; note: string; icon: IconName; amber?: boolean }) {
  return <section className={`stat-card ${amber ? 'amber-stat' : ''}`}><div className="stat-top"><span>{label}</span><Icon name={icon} /></div><strong>{value}</strong><p><span className="tiny-dot" />{note}</p></section>;
}
function WorkflowIcon({ run }: { run: Run }) {
  return <span className={`workflow-icon ${run.agent}`}><Icon name={agents.find(a => a.id === run.agent)?.icon || 'research'} size={20} /></span>;
}
function RunDetail({ run }: { run: Run }) {
  const [tab, setTab] = useState('overview');
  const [preview, setPreview] = useState<{ id: string; text: string } | null>(null);
  const report = run.artifacts.find(artifact => artifact.id === run.report_id)!;
  const tabs = ['overview', 'report', 'evidence'];
  async function inspect(artifact: Artifact) {
    setPreview({ id: artifact.id, text: 'Loading saved evidence…' });
    try {
      const response = await fetch(artifact.url);
      if (!response.ok) throw new Error('Evidence is missing or changed. Reload the workspace to inspect its status.');
      const text = JSON.stringify(await response.json(), null, 2);
      setPreview({ id: artifact.id, text: text.length > 100_000 ? text.slice(0, 100_000) + '\n… Preview truncated. Download the complete evidence file.' : text });
    } catch (error) { setPreview({ id: artifact.id, text: error instanceof Error ? error.message : 'Unable to read evidence.' }); }
  }
  return <>
    <a href="#/" className="back-link"><Icon name="back" size={16} />All saved reports</a>
    <div className="page-heading detail-heading"><div><p className="eyebrow">{workflowName[run.workflow].toUpperCase()} / SAVED RESULT</p><h1>{run.title}</h1><p>{run.entity}<span className="inline-separator">·</span>{run.period}</p></div><a href={report.url} target="_blank" rel="noreferrer" className="primary-button">Open report<Icon name="external" size={16} /></a></div>
    <div className="detail-status"><span>Execution <Execution status={run.execution_status} /></span><span>Financial review <Review status={run.review_status} /></span><span className="synthetic-detail">Synthetic inputs · no live refresh</span></div>
    <div className="metrics-grid">{run.metrics.map(item => <section className="metric-card" key={item.label}><h2>{item.label}</h2><strong>{item.value}</strong><p>{item.basis}</p></section>)}</div>
    <div className="detail-tabs" role="tablist" aria-label="Report details">{tabs.map((key, index) => <button id={`tab-${key}`} key={key} role="tab" aria-selected={tab === key} aria-controls="detail-content" tabIndex={tab === key ? 0 : -1} onClick={() => setTab(key)} onKeyDown={event => { const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1; if (next >= 0) { event.preventDefault(); setTab(tabs[next]); document.getElementById(`tab-${tabs[next]}`)?.focus(); } }}>{key === 'overview' ? 'Overview' : key === 'report' ? 'Saved report' : 'Evidence & provenance'}</button>)}</div>
    <div id="detail-content" role="tabpanel" aria-labelledby={`tab-${tab}`}>
      {tab === 'overview' ? <div className="detail-grid"><div><section className="panel detail-panel"><p className="eyebrow">ANALYST CONTEXT</p><h2>What this run contains</h2><p>{run.summary}</p><div className="record-checks">{run.checks.map(check => <div key={check}><Icon name="check" size={17} /><span>{check}</span></div>)}</div><button className="text-button" onClick={() => setTab('report')}>Inspect the saved report<Icon name="arrow" size={16} /></button></section><section className="panel detail-panel"><h2>Saved record</h2><dl className="record-meta"><dt>Prepared</dt><dd>{date(run.prepared_at)}</dd><dt>Financial period / scope</dt><dd>{run.period}</dd><dt>Source run identifier</dt><dd className="monospace">{run.source_run_id}</dd><dt>Data classification</dt><dd>Synthetic demonstration</dd></dl></section></div><section className="limitations-panel"><span className="limitations-icon"><Icon name="info" size={22} /></span><p className="eyebrow">READ BEFORE USING</p><h2>Boundaries & limitations</h2><ul>{run.limitations.map(value => <li key={value}>{value}</li>)}</ul><p className="limitations-footer">A completed process is not a financial approval.</p></section></div>
        : tab === 'report' ? <section className="panel report-frame-panel"><div className="frame-heading"><span>Original saved report · synthetic inputs</span><a href={report.url} target="_blank" rel="noreferrer">Open separately<Icon name="external" size={15} /></a></div><iframe sandbox="allow-same-origin allow-downloads" title={`${run.title} saved report`} src={report.url} /></section>
        : <section className="panel detail-panel"><div className="panel-heading evidence-heading"><div><h2>Evidence & provenance</h2><p>Only files explicitly registered for this run are accessible. Hash matches verify consistency, not financial truth.</p></div><span className="inventory-label"><Icon name="check" size={15} />Matched on load</span></div><div className="artifact-list">{run.artifacts.map(artifact => <div className="artifact-row" key={artifact.id}><span className="artifact-icon"><Icon name={artifact.kind === 'report' ? 'research' : 'evidence'} /></span><div className="artifact-info"><strong>{artifact.label}</strong><span>{artifact.name} · {(artifact.bytes / 1024).toFixed(1)} KB</span><code title={artifact.sha256}>SHA-256 {artifact.sha256.slice(0, 20)}…</code></div><div className="artifact-actions">{artifact.name.endsWith('.json') && <button className="text-button" onClick={() => inspect(artifact)}>Inspect<span className="sr-only"> {artifact.label}</span></button>}<a href={artifact.url} download className="download-link" aria-label={`Download ${artifact.label}`}><Icon name="download" size={17} /></a></div>{preview?.id === artifact.id && <pre className="json-preview" tabIndex={0} aria-label={`${artifact.label} preview`}>{preview.text}</pre>}</div>)}</div></section>}
    </div>
  </>;
}
function EvidenceLibrary({ runs }: { runs: Run[] }) {
  const count = runs.reduce((n, r) => n + r.artifacts.length, 0);
  return <><div className="page-heading"><div><p className="eyebrow">THE SOURCE BEHIND THE RESULT</p><h1>Evidence, within reach.</h1><p>{count} registered artifacts across {runs.length} saved reports. Original evidence remains separate from interpretation.</p></div></div><div className="evidence-grid">{runs.map(run => <a className="panel evidence-card" key={run.id} href={runHref(run)}><WorkflowIcon run={run} /><span className="eyebrow">{workflowName[run.workflow]}</span><h2>{run.title}</h2><p>{run.entity}</p><div><span>{run.artifacts.length} registered files</span><Icon name="arrow" size={18} /></div></a>)}</div><div className="evidence-note"><Icon name="info" /><p>Files are checked against the saved inventory before delivery. Matching hashes do not authenticate an issuer, approve financial conclusions or replace an independent backup.</p></div></>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
