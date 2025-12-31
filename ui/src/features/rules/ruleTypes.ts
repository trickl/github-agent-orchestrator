export type TriggerKind = 'MANUAL_ONLY' | 'AFTER_N_ISSUES_COMPLETED';

export type GenerationRuleCategory = 'review' | 'gap' | 'maintenance' | 'system' | 'unknown';

export type GenerationRule = {
  id: string;
  name: string;
  category: GenerationRuleCategory;
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

export type RuleRunResult = {
  ok: boolean;
  createdIssueId: string;
  createdIssueTitle: string;
  timelineEventId: string;
};
