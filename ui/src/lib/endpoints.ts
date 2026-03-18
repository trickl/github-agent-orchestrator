export const endpoints = {
  // Legacy dashboard endpoints (kept for existing pages/components compile safety)
  health: (): string => `/health`,
  overview: (): string => `/overview`,
  loop: (): string => `/loop`,
  loopGapAnalysisEnsure: (): string => `/loop/gap-analysis/ensure`,
  loopReviewEnsure: (): string => `/loop/review/ensure`,
  loopPromote: (): string => `/loop/promote`,
  loopMerge: (): string => `/loop/merge`,
  issues: (status: 'open' | 'all'): string => `/issues?status=${encodeURIComponent(status)}`,
  active: (): string => `/active`,
  timeline: (limit = 200): string => `/timeline?limit=${encodeURIComponent(String(limit))}`,
  docTargetState: (): string => `/docs/target-state`,
  docCurrentState: (): string => `/docs/current-state`,
  cognitiveTasks: (): string => `/cognitive-tasks`,

  // Local backend control-plane endpoints
  repos: (): string => `/repos`,
  repoStatus: (owner: string, repo: string): string =>
    `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/status`,
  repoTargetState: (owner: string, repo: string): string =>
    `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/target-state`,
  repoRun: (owner: string, repo: string): string =>
    `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/run`,
  developmentPrs: (owner: string, repo: string): string =>
    `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/development-prs`,
} as const;
