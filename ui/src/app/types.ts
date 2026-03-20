export type RepoStatusResponse = {
  hasTargetState: boolean;
  status: string;
  currentStep?: string | null;
};

export type DevelopmentPullRequest = {
  title: string;
  url: string;
  createdAt: string;
};

export type RunResponse = {
  status: string;
  repo: string;
  dispatched: boolean;
  workflow: string;
  ref: string;
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
export const ONBOARDING_COMPLETE_KEY = 'gao.onboardingComplete.v1';
export const DASHBOARD_TOUR_DISABLED_KEY = 'gao.dashboardTourDisabled.v1';
export const RUNNING_POLL_MS = 1500;
export const IDLE_POLL_MS = 7000;
