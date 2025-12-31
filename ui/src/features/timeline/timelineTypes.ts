export type TimelineEventKind =
  | 'RULE_TRIGGERED'
  | 'ISSUE_FILE_CREATED'
  | 'GITHUB_ISSUE_OPENED'
  | 'COPILOT_ASSIGNED'
  | 'PR_OPENED'
  | 'PR_MERGED'
  | 'ISSUE_CLOSED'
  | 'RUN_FAILED'
  | 'NOTE'
  | 'UNKNOWN';

export type TimelineEvent = {
  id: string;
  tsIso: string;
  kind: TimelineEventKind;
  summary: string;
  ruleId?: string;
  issueId?: string;
  issueTitle?: string;
  typePath?: string;
  links?: { label: string; url: string }[];
  details?: string;
};
