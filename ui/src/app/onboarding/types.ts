import type { OnboardingScene } from '../types';

export type ColorModeValue = {
  mode: 'light' | 'dark';
  toggle: () => void;
} | null;

export type InitProgress = {
  repositoryPrepared: boolean;
  initialAnalysisComplete: boolean;
  planGenerated: boolean;
};

export type OnboardingFlowProps = {
  scene: OnboardingScene;
  colorMode: ColorModeValue;
  repos: string[];
  repoSearch: string;
  onRepoSearchChange: (value: string) => void;
  selectedRepo: string;
  onSelectRepo: (value: string) => void;
  targetStateText: string;
  onTargetStateChange: (value: string) => void;
  isConnecting: boolean;
  isStartingFirstIteration: boolean;
  isRefreshingRepos: boolean;
  githubAppInstallUrl: string | null;
  initProgress: InitProgress;
  error: string | null;
  onGoToConnect: () => void;
  onConnectGithub: () => void;
  onContinueAfterConnected: () => void;
  onRefreshRepos: () => void;
  onContinueFromRepo: () => void;
  onStartFirstIteration: () => void;
  onSaveForLater: () => void;
};
