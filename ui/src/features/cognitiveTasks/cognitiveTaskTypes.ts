export type TriggerKind = 'MANUAL_ONLY' | 'AFTER_N_ISSUES_COMPLETED';

export type CognitiveTaskCategory = 'review' | 'gap' | 'maintenance' | 'system' | 'unknown';

export type CognitiveTask = {
  id: string;
  name: string;
  category: CognitiveTaskCategory;
  enabled: boolean;
  promptText: string;
  targetFolder: string;
  trigger: {
    kind: TriggerKind;
    nIssuesCompleted?: number;
  };
  lastRunIso?: string;
  nextEligibleIso?: string;
  editable: boolean;
};

export type CognitiveTaskRunResult = {
  ok: boolean;
  createdIssueId: string;
  createdIssueTitle: string;
  timelineEventId: string;
};
