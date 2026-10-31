/** Shared native reading elements. The caller selects eligible saved content. */
import { useEffect, useState, type ReactNode } from 'react';
import { Icon } from '../icons';
import type { Metric } from './report-data';
import { calendarDate, formatMetric } from './format';

export function ReportHeader({ eyebrow, title, entity, period, action }: {
  eyebrow: ReactNode; title: string; entity: string; period: ReactNode; action: ReactNode;
}) {
  return <header className="nr-header"><div><p className="eyebrow">{eyebrow}</p><h1 id="native-report-title" tabIndex={-1}>{title}</h1><p className="nr-company">{entity}</p><p className="nr-period">{period}</p></div>{action}</header>;
}

const executionLabel: Record<string, string> = { completed: 'Completed', held: 'Held for review', refused: 'Refused', failed: 'Failed', unavailable: 'Unavailable' };
export function ReportStates({ execution, evidenceGate }: { execution: string; evidenceGate: string }) {
  return <dl className="nr-status-strip" aria-label="Saved report states">
    <div><dt>Execution</dt><dd className={execution === 'completed' ? undefined : execution === 'failed' || execution === 'refused' ? 'nr-error-state' : 'nr-amber'}><span className="nr-state-dot" />{executionLabel[execution] || 'Unknown'}</dd></div>
    <div><dt>Evidence checks</dt><dd className="nr-amber">{evidenceGate === 'held_for_review' ? 'Review required' : evidenceGate === 'passed_evidence_checks' ? 'Checks passed' : 'Unavailable'}</dd></div>
    <div><dt>Financial approval</dt><dd>Not approved</dd></div>
    <div><dt>File consistency</dt><dd>Matched when loaded</dd></div>
  </dl>;
}

export function ReviewNotice({ title, children, action }: { title: string; children: ReactNode; action: ReactNode }) {
  return <div className="nr-review-notice" role="note"><span><Icon name="info" size={21} /></span><div><h2>{title}</h2><p>{children}</p></div>{action}</div>;
}

export function ReportSection({ id, eyebrow, title, children }: { id: string; eyebrow: string; title: string; children: ReactNode }) {
  return <section id={'report-' + id} tabIndex={-1} aria-labelledby={'report-' + id + '-title'} className="nr-section">
    <div className="nr-section-heading"><p className="eyebrow">{eyebrow}</p><h2 id={'report-' + id + '-title'}>{title}</h2></div>{children}
  </section>;
}

export function SectionNavigation({ sections, active, onSelect, children }: {
  sections: readonly (readonly [string, string])[]; active: string; onSelect: (id: string) => void; children?: ReactNode;
}) {
  const [chosen, setChosen] = useState(active);
  useEffect(() => setChosen(active), [active]);
  return <aside className="nr-toc"><nav aria-label="Report sections"><p className="eyebrow">IN THIS REPORT</p><div className="nr-nav-buttons">{sections.map(([id, label], index) => <button key={id} aria-current={active === id ? 'location' : undefined} onClick={() => onSelect(id)}><span>{String(index + 1).padStart(2, '0')}</span>{label}<Icon name="arrow" size={14} /></button>)}</div>
    <form className="nr-section-select" onSubmit={event => { event.preventDefault(); onSelect(chosen); }}><label htmlFor="native-section-select">Jump to a report section</label><div><select id="native-section-select" value={chosen} onChange={event => setChosen(event.target.value)}>{sections.map(([id,label]) => <option key={id} value={id}>{label}</option>)}</select><button className="nr-page-button" type="submit">Go</button></div></form>
  </nav>{children}</aside>;
}

export function MetricCard({ metric, onInspect, diagnosticLabel = 'Diagnostic model output' }: { metric: Metric; onInspect: () => void; diagnosticLabel?: string }) {
  const monetary = metric.unit === 'currency' || metric.unit === 'currency_per_share';
  const formatted = formatMetric(metric, true);
  const available = metric.availability === 'available';
  return <section className={'nr-metric-card' + (available ? '' : ' nr-metric-unavailable')} aria-label={metric.label}>
    {metric.visibility === 'diagnostic' && <span className="nr-diagnostic-label">{diagnosticLabel}</span>}
    <dl><dt>{metric.label}</dt><dd title={formatMetric(metric)}>{monetary && available && <span>{metric.currency}{' '}</span>}{monetary && available ? formatted.slice(4) : formatted}</dd></dl>
    <p className="nr-metric-period">{calendarDate(metric.period_label)}</p>
    {!available && <p className="nr-metric-reason">{metric.availability === 'withheld' ? 'Saved restrictions prevent publication of this figure.' : 'No usable value was saved for this figure.'}</p>}
    <button className="nr-source-button" onClick={onInspect}><Icon name="evidence" size={13} />Exact value & source</button>
  </section>;
}
