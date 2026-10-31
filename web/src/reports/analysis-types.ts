import type { Availability, Unit } from './report-data';

export type ChartPoint = { id: string; x: string; label: string; y: string | null; evidence_refs: string[]; reason_codes: string[] };
export type ChartData = {
  id: string; title: string; purpose: string; type: string; availability: Availability;
  visibility: 'main' | 'supporting' | 'diagnostic'; reason_codes: string[]; review_refs: string[];
  x_axis: { kind: 'category' | 'date' | 'relative_session'; label: string };
  y_axis: { unit: Unit; currency: string | null; label: string };
  series: { id: string; label: string; points: ChartPoint[] }[];
};
export type TableCell = { column_id: string; kind: 'text'; text: string } | { column_id: string; kind: 'metric_ref'; metric_id: string };
export type TableData = { id: string; title: string; columns: { id: string; label: string }[];
  rows: { id: string; cells: TableCell[]; evidence_refs: string[] }[]; review_refs: string[] };
export type SavedSection = { id: string; title: string; purpose: string; availability: Availability; reason_codes: string[];
  metric_refs: string[]; finding_refs: string[]; chart_refs: string[]; table_refs: string[]; review_refs: string[] };
export type AnalystArea = { availability: Availability; reason_codes: string[]; metric_refs: string[]; evidence_refs: string[] };
