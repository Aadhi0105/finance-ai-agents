/** Decimal-string display only. Never infer a financial result from another field. */
import type { Metric } from './report-data';

function shifted(value: string, places: number) {
  const negative = value.startsWith('-');
  const [whole, fraction = ''] = value.replace(/^-/, '').split('.');
  const digits = whole + fraction, position = whole.length + places;
  const left = position <= 0 ? '0' : (digits.slice(0, position) + '0'.repeat(Math.max(0, position - digits.length)));
  const right = position < 0 ? '0'.repeat(-position) + digits : digits.slice(Math.max(0, position));
  return { negative, whole: left.replace(/^0+(?=\d)/, ''), fraction: right };
}
function grouped(whole: string) { return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
function display(value: string, shift = 0, decimals?: number) {
  const parts = shifted(value, shift);
  let whole = parts.whole, fraction = parts.fraction;
  if (decimals !== undefined) {
    const padded = fraction.padEnd(decimals + 1, '0');
    let scaled = BigInt(whole) * 10n ** BigInt(decimals) + BigInt(padded.slice(0, decimals) || '0');
    if (padded[decimals] >= '5') scaled += 1n;
    const digits = scaled.toString().padStart(decimals + 1, '0');
    whole = digits.slice(0, digits.length - decimals);
    fraction = decimals ? digits.slice(-decimals) : '';
  }
  const nonzero = /[1-9]/.test(whole + fraction);
  return (parts.negative && nonzero ? '−' : '') + grouped(whole) + (fraction ? '.' + fraction : '');
}

export function formatMetric(metric: Metric, compact = false): string {
  if (metric.availability !== 'available' || metric.value === null) {
    return metric.availability === 'withheld' ? 'Withheld' : metric.availability === 'not_applicable' ? 'Not applicable' : 'Unavailable';
  }
  const value = metric.value;
  if (!/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(value)) return 'Unavailable';
  const decimalPlaces = value.split('.')[1]?.length || 0;
  if (metric.unit === 'currency' || metric.unit === 'currency_per_share') {
    if (!/^[A-Z]{3}$/.test(metric.currency || '')) return 'Unavailable';
    const length = value.replace(/^-/, '').split('.')[0].length;
    const scale = compact && metric.unit === 'currency' ? length > 9 ? 9 : length > 6 ? 6 : 0 : 0;
    return `${metric.currency} ${display(value, -scale, compact ? 2 : Math.max(2, decimalPlaces))}${scale === 9 ? 'bn' : scale === 6 ? 'm' : ''}${metric.unit === 'currency_per_share' ? ' / share' : ''}`;
  }
  if (metric.unit === 'fraction') return display(value, 2, compact ? 2 : Math.max(2, decimalPlaces - 2)) + '%';
  if (metric.unit === 'multiple') return display(value, 0, compact ? 2 : undefined) + '×';
  return display(value);
}

export function calendarDate(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const day = new Date(value + 'T12:00:00Z');
  if (Number.isNaN(day.getTime()) || day.toISOString().slice(0, 10) !== value) return value;
  return day.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
}

export function savedInstant(value: string): string {
  const instant = new Date(value);
  return Number.isNaN(instant.getTime()) ? value : instant.toLocaleString('en-GB', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
  }) + ' UTC';
}
