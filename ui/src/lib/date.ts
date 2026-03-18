export function safeDateFromIso(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatIso(iso: string | null | undefined): string {
  const d = safeDateFromIso(iso);
  return d ? d.toISOString() : '—';
}

export function formatRelativeFromNow(iso: string | null | undefined, now = new Date()): string {
  const d = safeDateFromIso(iso);
  if (!d) return '—';
  const diffMs = d.getTime() - now.getTime();
  const abs = Math.abs(diffMs);

  const sec = Math.round(abs / 1000);
  const min = Math.round(sec / 60);
  const hr = Math.round(min / 60);
  const day = Math.round(hr / 24);

  const fmt = (n: number, unit: string) => `${n}${unit}`;

  let body: string;
  if (sec < 60) body = fmt(sec, 's');
  else if (min < 60) body = fmt(min, 'm');
  else if (hr < 48) body = fmt(hr, 'h');
  else body = fmt(day, 'd');

  return diffMs < 0 ? `${body} ago` : `in ${body}`;
}
