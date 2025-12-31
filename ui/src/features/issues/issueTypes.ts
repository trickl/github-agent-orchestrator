export type IssueStatus =
  | 'PENDING'
  | 'OPEN'
  | 'ASSIGNED'
  | 'PR_OPEN'
  | 'MERGED'
  | 'CLOSED'
  | 'FAILED'
  | 'BLOCKED'
  | 'UNKNOWN';

export type Issue = {
  id: string;
  title: string;
  typePath: string;
  status: IssueStatus;
  ageSeconds: number;
  githubIssueUrl?: string;
  prUrl?: string;
  lastUpdatedIso: string;
  isActive: boolean;
};
