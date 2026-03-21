export type RepoStatusResponse = {
  hasTargetState: boolean;
  status: string;
  defaultBranch?: string | null;
  currentStep?: string | null;
  status_artifact?: {
    stage?: string | null;
    active_issue_ids?: number[];
    active_pr_ids?: number[];
  } | null;
  active_issue_ids?: number[];
  active_pr_ids?: number[];
};

export type DevelopmentPullRequest = {
  title: string;
  url: string;
  createdAt: string;
  state?: 'open' | 'closed';
  mergedAt?: string | null;
};

export type OrchestratorMode = 'manual' | 'auto';

export type RepoRunResponse = {
  status: string;
  repo: string;
  dispatched: boolean;
  workflow: string;
  ref: string;
};

export type RepoInitializeResponse = {
  owner: string;
  repo: string;
  base_branch: string;
  branch: string;
  opened_pull_request: boolean;
  applied_directly: boolean;
  initialized_files: Record<string, 'created' | 'updated' | 'unchanged'>;
};

export type AuthMeResponse = {
  authenticated: boolean;
  login: string;
  id: number;
};

export type AuthStartResponse = {
  authorizationUrl: string;
};

export type GithubAppInstallUrlResponse = {
  installUrl: string;
};

export type OnboardingScene =
  | 'welcome'
  | 'connect'
  | 'connected'
  | 'repo'
  | 'target'
  | 'initializing'
  | 'dashboard';

export type RunToast = { severity: 'success' | 'error'; message: string } | null;

export const REPO_STORAGE_KEY = 'gao.selectedRepo';
export const TARGET_DRAFT_STORAGE_KEY = 'gao.targetStateDraft';
export const MODE_STORAGE_KEY = 'gao.orchestratorMode';
export const ONBOARDING_COMPLETE_KEY = 'gao.onboardingComplete.v1';
export const DASHBOARD_TOUR_DISABLED_KEY = 'gao.dashboardTourDisabled.v1';
export const RUNNING_POLL_MS = 1500;
export const IDLE_POLL_MS = 7000;
