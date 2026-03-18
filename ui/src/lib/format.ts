export function humanTriggerSummary(trigger: {
  kind: 'MANUAL_ONLY' | 'AFTER_N_ISSUES_COMPLETED';
  nIssuesCompleted?: number;
}): string {
  if (trigger.kind === 'MANUAL_ONLY') return 'Manual only';
  const n = trigger.nIssuesCompleted ?? 0;
  return `After ${n} completed issues`;
}

export function coerceString(v: unknown, fallback = '—'): string {
  if (typeof v === 'string' && v.trim().length > 0) return v;
  return fallback;
}
