/** Display geometry only. Original decimal strings remain the inspection values. */
import type { ChartData, ChartPoint } from './analysis-types';

export type ChartRow = { x: string; label: string; points: (ChartPoint | null)[] };
export type PlotPoint = { row: number; x: number; y: number };
export type PlotGeometry = {
  width: number; height: number; left: number; right: number; top: number; bottom: number;
  xs: number[]; ticks: { value: string; y: number }[]; zero: number;
  series: { index: number; segments: PlotPoint[][] }[];
  kind: 'line' | 'bar' | 'dot'; reason: string | null;
};

function decimalParts(value: string) {
  const [whole, fraction = ''] = value.replace(/^-/, '').split('.');
  return { whole, fraction, sign: value.startsWith('-') ? -1n : 1n };
}
function scaled(value: string, places: number) {
  const p = decimalParts(value);
  return p.sign * BigInt(p.whole + p.fraction.padEnd(places, '0'));
}
function decimal(value: bigint, places: number) {
  const negative = value < 0n, digits = (negative ? -value : value).toString().padStart(places + 1, '0');
  const fraction = digits.slice(-places).replace(/0+$/, '');
  return (negative ? '-' : '') + digits.slice(0, -places) + (fraction ? '.' + fraction : '');
}

export function plotGeometry(chart: ChartData, rows: ChartRow[], width: number, hidden: readonly string[] = []): PlotGeometry {
  const geometry: PlotGeometry = { width: Math.max(220, width), height: width < 480 ? 250 : 290,
    left: 66, right: Math.max(220, width) - 17, top: 20, bottom: width < 480 ? 199 : 239,
    xs: [], ticks: [], zero: 0, series: [], kind: chart.type === 'bar' ? 'bar' : chart.type === 'line' ? 'line' : 'dot', reason: null };
  if (chart.availability !== 'available') return { ...geometry, reason: 'This saved series is unavailable or withheld.' };
  if (!['line', 'bar', 'dot_plot', 'scenario_range'].includes(chart.type) || !['date', 'category'].includes(chart.x_axis.kind)) {
    return { ...geometry, reason: 'An interactive plot is not supported for this saved chart type. Its exact table remains available.' };
  }
  const visible = chart.series.map((s, index) => ({ s, index })).filter(({s}) => !hidden.includes(s.id));
  if (!visible.length) return { ...geometry, reason: 'All series are hidden. Select a series in the legend to show it again.' };
  const values = rows.flatMap(r => visible.flatMap(({index}) => r.points[index]?.y == null ? [] : [r.points[index]!.y!]));
  if (!values.length) return { ...geometry, reason: 'No usable saved points are available for the selected series.' };

  // Integer decimal alignment avoids losing small differences in large amounts.
  // Only the final unit-interval ratio becomes a Number for SVG coordinates.
  const places = Math.max(2, ...values.map(v => decimalParts(v).fraction.length));
  const numbers = values.map(v => scaled(v, places));
  let low = numbers.reduce((a, b) => a < b ? a : b), high = numbers.reduce((a, b) => a > b ? a : b);
  if (geometry.kind === 'bar') { low = low < 0n ? low : 0n; high = high > 0n ? high : 0n; }
  const span = high - low;
  if (span === 0n) {
    const magnitude = low < 0n ? -low : low;
    const pad = magnitude / 10n || 10n ** BigInt(places - 2);
    low -= pad; high += pad;
  } else {
    const pad = span / 12n || 1n;
    if (geometry.kind !== 'bar' || low < 0n) low -= pad;
    if (geometry.kind !== 'bar' || high > 0n) high += pad;
  }
  if (chart.id === 'news-story-tone' && chart.y_axis.unit === 'score') {
    low = -(10n ** BigInt(places)); high = 10n ** BigInt(places);
  }
  const countAxis = chart.id === 'news-coverage' && chart.y_axis.unit === 'count';
  const unit = 10n ** BigInt(places);
  if (countAxis) { low = 0n; high = ((high + unit - 1n) / unit || 1n) * unit; }
  const y = (value: bigint) => geometry.bottom - Number((value - low) * 1_000_000_000n / (high - low)) / 1_000_000_000 * (geometry.bottom - geometry.top);
  geometry.zero = Math.max(geometry.top, Math.min(geometry.bottom, y(0n)));
  const ticks = Array.from({length: 5}, (_, i) => {
    const raw = low + (high - low) * BigInt(i) / 4n;
    const value = countAxis ? raw / unit * unit : raw;
    return {value: decimal(value, places), y: y(value)};
  });
  geometry.ticks = [...new Map(ticks.map(t => [t.value, t])).values()];
  if (geometry.kind === 'bar' && !geometry.ticks.some(t => t.value === '0')) {
    geometry.ticks = [...geometry.ticks.filter(t => Math.abs(t.y - geometry.zero) >= 16), {value: '0', y: geometry.zero}]
      .sort((a, b) => b.y - a.y);
  }
  const start = chart.x_axis.kind === 'date' ? Date.parse(rows[0].x + 'T12:00:00Z') : 0;
  const end = chart.x_axis.kind === 'date' ? Date.parse(rows[rows.length - 1].x + 'T12:00:00Z') : rows.length - 1;
  geometry.xs = rows.map((r, i) => {
    if (rows.length === 1) return (geometry.left + geometry.right) / 2;
    const fraction = chart.x_axis.kind === 'date' ? (Date.parse(r.x + 'T12:00:00Z') - start) / (end - start)
      : geometry.kind === 'line' ? i / (rows.length - 1) : (i + 0.5) / rows.length;
    return geometry.left + fraction * (geometry.right - geometry.left);
  });
  geometry.series = visible.map(({index}) => {
    const segments: PlotPoint[][] = [];
    let segment: PlotPoint[] = [];
    rows.forEach((r, i) => {
      const point = r.points[index];
      if (!point || point.y === null) {
        if (segment.length) segments.push(segment);
        segment = [];
      } else segment.push({row: i, x: geometry.xs[i], y: y(scaled(point.y, places))});
    });
    if (segment.length) segments.push(segment);
    return {index, segments};
  });
  return geometry;
}

export function nearestObservation(xs: readonly number[], position: number) {
  let low = 0, high = xs.length - 1;
  while (low < high) { const mid = Math.floor((low + high) / 2); if (xs[mid] < position) low = mid + 1; else high = mid; }
  return low > 0 && position - xs[low - 1] <= xs[low] - position ? low - 1 : low;
}

export function tickIndices(xs: readonly number[], width: number) {
  if (xs.length <= (width < 480 ? 4 : 7)) return xs.map((_, i) => i);
  const count = width < 480 ? 3 : 5;
  return [...new Set(Array.from({length: count}, (_, i) => nearestObservation(xs, xs[0] + (xs[xs.length - 1] - xs[0]) * i / (count - 1))))];
}
