import {
  getCanonicalIterationState,
  getCompletedWorkCount,
  isAwaitingManualApproval,
} from './iterationSemantics';
import type { RepoStatusResponse } from './types';

function statusWith(overrides: Partial<RepoStatusResponse>): RepoStatusResponse {
  return {
    hasTargetState: true,
    status: 'idle',
    currentStep: null,
    ...overrides,
  };
}

test('manual mode reports awaiting approval on merge stage', () => {
  const status = statusWith({
    status_artifact: { stage: '2c' },
  });

  expect(isAwaitingManualApproval(status, 'manual')).toBe(true);
  expect(getCanonicalIterationState(status, 'manual')).toBe('awaiting_user_approval');
});

test('auto mode does not block on merge stage', () => {
  const status = statusWith({
    status_artifact: { stage: '2c' },
  });

  expect(isAwaitingManualApproval(status, 'auto')).toBe(false);
  expect(getCanonicalIterationState(status, 'auto')).toBe('idle');
});

test('complete_noop is derived from current step text', () => {
  const status = statusWith({
    currentStep: 'No actionable stage detected; treating as successful no-op.',
  });

  expect(getCanonicalIterationState(status, 'manual')).toBe('complete_noop');
});

test('completed work counts only merged PRs', () => {
  const count = getCompletedWorkCount([
    {
      title: 'Open PR',
      url: 'https://example/pr/1',
      createdAt: '2026-03-21T00:00:00Z',
      state: 'open',
      mergedAt: null,
    },
    {
      title: 'Merged PR',
      url: 'https://example/pr/2',
      createdAt: '2026-03-21T01:00:00Z',
      state: 'closed',
      mergedAt: '2026-03-21T02:00:00Z',
    },
  ]);

  expect(count).toBe(1);
});
