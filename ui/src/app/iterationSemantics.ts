import type { DevelopmentPullRequest, OrchestratorMode, RepoStatusResponse } from './types';

const MERGE_APPROVAL_STAGES = new Set(['1c', '2c', '3c']);

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

export function isAwaitingManualApproval(status: RepoStatusResponse | null, mode: OrchestratorMode): boolean {
  if (mode !== 'manual') return false;
  const stage = normalizeStage(status?.status_artifact?.stage);
  return MERGE_APPROVAL_STAGES.has(stage);
}

export function getCanonicalIterationState(
  status: RepoStatusResponse | null,
  mode: OrchestratorMode
): CanonicalIterationState {
  const backendStatus = normalizeBackendStatus(status?.status);
  if (backendStatus === 'error') return 'error';
  if (backendStatus === 'running') return 'running';

  if (isAwaitingManualApproval(status, mode)) {
    return 'awaiting_user_approval';
  }

  const currentStep = (status?.currentStep ?? '').trim().toLowerCase();
  if (currentStep.includes('no actionable stage')) {
    return 'complete_noop';
  }

  if (currentStep.includes('current state') || currentStep.includes('capability')) {
    return 'awaiting_state_refresh';
  }

  return 'idle';
}

export function getCompletedWorkCount(developmentPrs: DevelopmentPullRequest[]): number {
  return developmentPrs.filter((pr) => Boolean(pr.mergedAt)).length;
}
