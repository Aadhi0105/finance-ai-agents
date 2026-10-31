export type IconName = 'overview' | 'research' | 'monitoring' | 'events' | 'close' | 'history' | 'evidence' | 'arrow' | 'search' | 'check' | 'download' | 'info' | 'back' | 'external';
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
export function Icon({ name, size = 19 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
