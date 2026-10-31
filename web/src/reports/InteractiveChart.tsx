import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { PointerEvent } from 'react';
import { Icon } from '../icons';
import type { ChartData } from './analysis-types';
import type { ChartRow } from './chart-layout';
import { nearestObservation, plotGeometry, tickIndices } from './chart-layout';
import { calendarDate, formatMetric } from './format';
import { pointMetric } from './report-data';
import './interactive-chart.css';

const styles = [
  { color: '#315f4c', dash: '', shape: 'circle' }, { color: '#977039', dash: '8 5', shape: 'square' },
  { color: '#476b91', dash: '2 4', shape: 'diamond' }, { color: '#855c78', dash: '9 3 2 3', shape: 'triangle' },
] as const;
function Mark({ index, x, y, size = 4 }: { index: number; x: number; y: number; size?: number }) {
  const style = styles[index % styles.length];
  const props = {fill: '#fff', stroke: style.color, strokeWidth: 2};
  return style.shape === 'square' ? <rect x={x-size} y={y-size} width={size*2} height={size*2} {...props} />
    : style.shape === 'diamond' ? <path d={`M${x},${y-size-1}l${size+1},${size+1}l${-size-1},${size+1}l${-size-1},${-size-1}Z`} {...props} />
    : style.shape === 'triangle' ? <path d={`M${x},${y-size-1}l${size+1},${size*2+1}h${-size*2-2}Z`} {...props} />
    : <circle cx={x} cy={y} r={size} {...props} />;
}

function rowLabel(chart: ChartData, row: ChartRow) {
  return chart.x_axis.kind === 'date' ? calendarDate(row.x) : row.label === row.x ? row.label : row.x + ' · ' + row.label;
}
function axisLabel(chart: ChartData, value: string) {
  const formatted = formatMetric(pointMetric(chart, {id: 'axis', label: '', x: '', y: value, evidence_refs: [], reason_codes: []}), true);
  const label = chart.y_axis.currency ? formatted.replace(chart.y_axis.currency + ' ', '').replace(' / share', '') : formatted;
  const number = Number(value) * (chart.y_axis.unit === 'fraction' ? 100 : 1);
  return label.length > 11 || number !== 0 && /^−?0\.00[%×]?$/.test(label)
    ? number.toExponential(1) + (chart.y_axis.unit === 'fraction' ? '%' : chart.y_axis.unit === 'multiple' ? '×' : '') : label;
}
function shortDate(x: string) {
  return new Date(x + 'T12:00:00Z').toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: '2-digit', timeZone: 'UTC'});
}

export function InteractiveChart({ chart, rows, onInspect }: {
  chart: ChartData; rows: ChartRow[]; onInspect: (refs: string[]) => void;
}) {
  const container = useRef<HTMLDivElement>(null), id = useId();
  const [width, setWidth] = useState(700), [selected, setSelected] = useState(0);
  const [hidden, setHidden] = useState<string[]>([]), [floating, setFloating] = useState(false);
  const [announce, setAnnounce] = useState(false);
  useEffect(() => {
    const node = container.current;
    if (!node) return;
    const observer = new ResizeObserver(entries => setWidth(Math.max(220, entries[0].contentRect.width)));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!floating) return;
    const dismiss = (event: KeyboardEvent) => { if (event.key === 'Escape') setFloating(false); };
    window.addEventListener('keydown', dismiss);
    return () => window.removeEventListener('keydown', dismiss);
  }, [floating]);
  const geometry = useMemo(() => plotGeometry(chart, rows, width, hidden), [chart, rows, width, hidden]);
  if (chart.availability !== 'available' || !rows.length) return null;
  const row = rows[Math.min(selected, rows.length-1)];
  const unit = chart.y_axis.currency ? chart.y_axis.currency + (chart.y_axis.unit === 'currency_per_share' ? ' per share' : '')
    : ({fraction: 'Percent', index: 'Rebased index', multiple: 'P/E multiple'} as Record<string,string>)[chart.y_axis.unit] || chart.y_axis.label;
  const value = (i: number) => {
    const point = row.points[i];
    if (!point) return 'Not retained';
    return formatMetric(pointMetric(chart, point)) + (point.y !== null && chart.y_axis.unit === 'index' ? ' index points' : '');
  };
  const selectedText = rowLabel(chart, row) + '. ' + chart.series.map((s, i) => s.label + ': ' + value(i) + (hidden.includes(s.id) ? ' (hidden in plot)' : '')).join('. ')
    + (chart.visibility === 'diagnostic' ? '. Diagnostic; review required.' : '');
  function choose(index: number, keyboard = false) {
    setSelected(Math.max(0, Math.min(rows.length-1, index))); setAnnounce(keyboard);
  }
  function pointer(event: PointerEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const next = nearestObservation(geometry.xs, (event.clientX-box.left)/box.width*geometry.width);
    choose(next);
    if (event.pointerType !== 'touch' && next !== selected) setFloating(true);
  }
  const x = geometry.xs[selected];
  return <div className="nr-chart" ref={container} role="group" aria-label={chart.title + ' interactive chart'}>
    <div className="nr-chart-basis" id={id+'-basis'}><span>Saved synthetic evidence</span><span>{rows.length} observations · {unit}</span></div>
    <div className="nr-chart-legend" aria-label="Chart series">
      {chart.series.map((series, i) => <button key={series.id} type="button" aria-pressed={!hidden.includes(series.id)}
        aria-label={(hidden.includes(series.id) ? 'Show ' : 'Hide ') + series.label}
        onClick={() => { setHidden(h => h.includes(series.id) ? h.filter(s=>s!==series.id) : [...h,series.id]); setFloating(false); }}>
        <svg width="29" height="15" viewBox="0 0 29 15" aria-hidden="true"><path d="M1 7.5h27" stroke={styles[i%styles.length].color} strokeWidth="2" strokeDasharray={styles[i%styles.length].dash}/><Mark index={i} x={14} y={7.5} size={3}/></svg>
        {series.label}<small>{hidden.includes(series.id) ? 'Hidden' : 'Shown'}</small>
      </button>)}
    </div>
    {geometry.reason ? <p className="nr-chart-unavailable" role="status">{geometry.reason}</p> : <div className="nr-plot">
      <svg className="nr-plot-svg" viewBox={`0 0 ${geometry.width} ${geometry.height}`} role="img"
        aria-label={`${chart.title}. ${rows.length} saved observations; inspect exact values with the controls or table below.`}
        onPointerMove={event => { if (event.pointerType !== 'touch') pointer(event); }}
        onPointerDown={event => { pointer(event); if (event.pointerType === 'touch') setFloating(false); }}
        onPointerEnter={event => { if (event.pointerType !== 'touch') setFloating(true); }} onPointerLeave={() => setFloating(false)}>
        <title>{chart.title}</title>
        {geometry.ticks.map(tick => <g key={tick.value}><line x1={geometry.left} x2={geometry.right} y1={tick.y} y2={tick.y} className="nr-grid-line"/><text x={geometry.left-10} y={tick.y+4} textAnchor="end" className="nr-axis-text">{axisLabel(chart,tick.value)}</text></g>)}
        <line x1={geometry.left} x2={geometry.right} y1={geometry.bottom} y2={geometry.bottom} className="nr-axis-line"/>
        {geometry.kind === 'bar' && <line x1={geometry.left} x2={geometry.right} y1={geometry.zero} y2={geometry.zero} className="nr-zero-line"/>}
        {tickIndices(geometry.xs, width).map(i => <g key={i}><line x1={geometry.xs[i]} x2={geometry.xs[i]} y1={geometry.bottom} y2={geometry.bottom+5} className="nr-axis-line"/><text x={geometry.xs[i]} y={geometry.bottom+20} textAnchor={i===0 && chart.x_axis.kind==='date' ? 'start' : i===rows.length-1 && chart.x_axis.kind==='date' ? 'end' : 'middle'} className="nr-axis-text">{chart.x_axis.kind==='date' ? shortDate(rows[i].x) : rows[i].x.length>12 ? rows[i].x.slice(0,11)+'…' : rows[i].x}</text></g>)}
        <text x={(geometry.left+geometry.right)/2} y={geometry.height-4} textAnchor="middle" className="nr-axis-title">{chart.x_axis.label}</text>
        {geometry.series.map(({index,segments}, visibleIndex) => <g key={chart.series[index].id}>
          {geometry.kind === 'line' ? segments.map((segment, n) => <g key={n}>
            <path d={segment.map((p,i)=>(i?'L':'M')+p.x.toFixed(3)+','+p.y.toFixed(3)).join(' ')} fill="none" stroke={styles[index%styles.length].color} strokeWidth="2" strokeDasharray={styles[index%styles.length].dash} strokeLinejoin="round"/>
            {segment.length===1 && <Mark index={index} x={segment[0].x} y={segment[0].y} size={3}/>}
          </g>) : segments.flat().map(p => {
            const band = (geometry.right-geometry.left)/Math.max(1,rows.length), barWidth = Math.min(56,band*.6/geometry.series.length);
            const center = p.x + (visibleIndex-(geometry.series.length-1)/2)*barWidth;
            return geometry.kind === 'bar' ? <g key={p.row}><rect x={center-barWidth*.43} y={Math.min(p.y,geometry.zero)} width={barWidth*.86} height={Math.abs(p.y-geometry.zero)} fill={styles[index%styles.length].color} opacity={p.row===selected ? 1 : .77}/>{p.y===geometry.zero && <line x1={center-barWidth*.43} x2={center+barWidth*.43} y1={p.y} y2={p.y} stroke={styles[index%styles.length].color} strokeWidth="2"/>}</g>
              : <Mark key={p.row} index={index} x={p.x} y={p.y} size={p.row===selected ? 6 : 4}/>;
          })}
        </g>)}
        <line x1={x} x2={x} y1={geometry.top} y2={geometry.bottom} className="nr-chart-crosshair"/>
        {geometry.series.flatMap(({index,segments})=>segments.flat().filter(p=>p.row===selected).map(p=><Mark key={index} index={index} x={p.x} y={p.y} size={5}/>))}
      </svg>
      {floating && <div className="nr-chart-tooltip" aria-hidden="true" style={{left: Math.max(26,Math.min(74,x/geometry.width*100))+'%'}}>
        <strong>{rowLabel(chart,row)}</strong>{chart.visibility==='diagnostic' && <small>Diagnostic · review required</small>}
        {chart.series.map((s,i)=>!hidden.includes(s.id) && <div key={s.id}><span>{s.label}</span><b>{value(i)}</b></div>)}
      </div>}
    </div>}
    <p className="nr-chart-instructions" id={id+'-help'}>Hover or tap a point. Use arrows, Home/End on the slider, or Previous/Next. Escape closes the floating label. Saved gaps stay missing.</p>
    <div className="nr-chart-controls"><label htmlFor={id+'-point'}>Inspect saved observation</label><div>
      <button type="button" className="nr-page-button" aria-label="Previous observation" disabled={selected===0} onClick={()=>choose(selected-1,true)}>Previous</button>
      <input id={id+'-point'} type="range" min={0} max={rows.length-1} step={1} value={selected}
        aria-label={'Inspect '+chart.title} aria-valuetext={selectedText} aria-describedby={id+'-help '+id+'-basis'}
        onChange={event=>{choose(Number(event.target.value));setFloating(true);}}
        onFocus={()=>setFloating(true)} onBlur={()=>setFloating(false)} onKeyDown={event=>{if(event.key==='Escape')setFloating(false);}}/>
      <button type="button" className="nr-page-button" aria-label="Next observation" disabled={selected===rows.length-1} onClick={()=>choose(selected+1,true)}>Next</button>
    </div></div>
    <div className="nr-chart-selection" aria-live={announce?'polite':'off'} aria-atomic="true">
      <div className="nr-chart-selection-heading"><strong>{rowLabel(chart,row)}</strong><span>Observation {selected+1} of {rows.length}</span>{chart.visibility==='diagnostic' && <span className="nr-diagnostic-label">Diagnostic · review required</span>}</div>
      <dl>{chart.series.map((series,i)=><div key={series.id}><dt>{series.label}{hidden.includes(series.id) && <small>Hidden in plot</small>}</dt><dd>{value(i)}</dd><button className="nr-source-button" disabled={!row.points[i]?.evidence_refs.length} onClick={()=>onInspect(row.points[i]!.evidence_refs)} aria-label={'Inspect source for '+series.label}><Icon name="evidence" size={13}/>Source</button></div>)}</dl>
    </div>
    <p className="nr-chart-scale-note">Axes use compact display labels; selection and the exact table retain saved precision. {chart.type==='bar' ? 'Bars start at zero.' : 'The vertical scale follows the visible saved values.'} {chart.id==='news-story-tone' ? 'Text scores use the fixed −1 to +1 range.' : ''} {chart.type==='scenario_range' ? 'Each point is a separate conditional scenario, not a probability interval.' : chart.type==='dot_plot' ? 'Companies are separate screening observations, not a trend.' : ''}</p>
  </div>;
}
