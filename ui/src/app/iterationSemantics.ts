import type { DevelopmentPullRequest, OrchestratorMode, RepoStatusResponse } from './types';

const MERGE_APPROVAL_STAGES = new Set(['1c', '2c', '3c']);
const STATE_REFRESH_STAGES = new Set(['3a', '3b']);

export type CanonicalIterationState =
  | 'idle'
  | 'running'
  | 'awaiting_user_approval'
  | 'awaiting_state_refresh'
  | 'complete_noop'
  | 'error';

export function normalizeBackendStatus(status: string | null | undefined): 'idle' | 'running' | 'error' {
  const normalized = (status ?? '').trim().toLowerCase();
  if (normalized === 'running') return 'running';
  if (normalized === 'error') return 'error';
  return 'idle';
}

function normalizeStage(stage: string | null | undefined): string {
  return (stage ?? '').trim().toLowerCase();
}

function hasActiveQueueWork(status: RepoStatusResponse | null): boolean {
  const activeIssues = status?.status_artifact?.active_issue_ids?.length ?? status?.active_issue_ids?.length ?? 0;
  const activePrs = status?.status_artifact?.active_pr_ids?.length ?? status?.active_pr_ids?.length ?? 0;
  return activeIssues > 0 || activePrs > 0;
}

function hasMergedCapabilityOrStatePr(developmentPrs: DevelopmentPullRequest[]): boolean {
  return developmentPrs.some((pr) => {
    if (!pr.mergedAt) return false;
    const title = pr.title.trim().toLowerCase();
    return title.includes('capability') || title.includes('current state');
  });
}

export function isAwaitingManualApproval(status: RepoStatusResponse | null, mode: OrchestratorMode): boolean {
  if (mode !== 'manual') return false;
  const stage = normalizeStage(status?.status_artifact?.stage);
  return MERGE_APPROVAL_STAGES.has(stage);
}

export function getCanonicalIterationState(
  status: RepoStatusResponse | null,
  mode: OrchestratorMode,
  developmentPrs: DevelopmentPullRequest[]
): CanonicalIterationState {
  const backendStatus = normalizeBackendStatus(status?.status);
  if (backendStatus === 'error') return 'error';
  if (backendStatus === 'running') return 'running';

  if (isAwaitingManualApproval(status, mode)) {
    return 'awaiting_user_approval';
  }

  const stage = normalizeStage(status?.status_artifact?.stage);
  const hasPendingStateRefreshSignal =
    STATE_REFRESH_STAGES.has(stage) ||
    (stage === '3c' && mode === 'auto') ||
    hasMergedCapabilityOrStatePr(developmentPrs);

  const currentStep = (status?.currentStep ?? '').trim().toLowerCase();
  if (
    hasPendingStateRefreshSignal &&
    (currentStep.includes('current state') || currentStep.includes('capability') || hasActiveQueueWork(status))
  ) {
    return 'awaiting_state_refresh';
  }

  if (currentStep.includes('no actionable stage')) {
    return 'complete_noop';
  }

  return 'idle';
}

export function getCompletedWorkCount(developmentPrs: DevelopmentPullRequest[]): number {
  return developmentPrs.filter((pr) => Boolean(pr.mergedAt)).length;
}
