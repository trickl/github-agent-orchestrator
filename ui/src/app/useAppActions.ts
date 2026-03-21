import React from 'react';
import { apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import { DASHBOARD_TOUR_DISABLED_KEY, ONBOARDING_COMPLETE_KEY, REPO_STORAGE_KEY } from './types';
import type {
  AuthStartResponse,
  DevelopmentPullRequest,
  OrchestratorMode,
  RepoInitializeResponse,
  RepoRunResponse,
} from './types';
import type { AppDataResult } from './useAppData';

function isRepoRunResponse(value: unknown): value is RepoRunResponse {
  if (typeof value !== 'object' || value === null) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.status === 'string' &&
    typeof candidate.repo === 'string' &&
    typeof candidate.dispatched === 'boolean' &&
    typeof candidate.workflow === 'string' &&
    typeof candidate.ref === 'string'
  );
}

export function useAppActions(data: AppDataResult) {
  const {
    selectedRepoParts,
    selectedMode,
    targetStateText,
    running,
    loadRepoData,
    markOnboardingCompleted,
    setError,
    setRunToast,
    setRunning,
    setDevelopmentPrs,
    setIsConnecting,
    setAuthLogin,
    setRepos,
    setSelectedRepo,
    setStatus,
    setScene,
    setIsStartingFirstIteration,
    setInitProgress,
    setShowTour,
  } = data;

  const resolveBackendMode = React.useCallback((mode: OrchestratorMode): 'manual' | 'auto' => {
    return mode === 'auto' ? 'auto' : 'manual';
  }, []);

  const handleTargetStateSubmit = React.useCallback(async () => {
    if (!selectedRepoParts) return;
    const content = targetStateText.trim();
    if (!content) {
      setError('Please describe the system you want to build before starting.');
      return;
    }
    setError(null);
    setRunToast(null);
    const { owner, repo } = selectedRepoParts;
    await apiFetch(String(endpoints.repoTargetState(owner, repo)), {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
    setRunToast({ severity: 'success', message: '✅ Target state saved. You can now start building.' });
    await loadRepoData();
  }, [loadRepoData, selectedRepoParts, setError, setRunToast, targetStateText]);

  const handleRun = React.useCallback(async () => {
    if (!selectedRepoParts || running) return;
    setRunning(true);
    setError(null);
    setRunToast(null);
    const { owner, repo } = selectedRepoParts;
    const backendMode = resolveBackendMode(selectedMode);
    try {
      await apiFetch(String(endpoints.repoOrchestratorMode(owner, repo)), {
        method: 'POST',
        body: JSON.stringify({ mode: backendMode }),
      });

      const runResultRaw = await apiFetch<unknown>(String(endpoints.repoRun(owner, repo)), {
        method: 'POST',
        body: JSON.stringify({}),
      });
      if (!isRepoRunResponse(runResultRaw)) {
        throw new Error('Control plane returned an invalid workflow dispatch response.');
      }
      const runResult = runResultRaw;
      const prs = await apiFetch<DevelopmentPullRequest[]>(String(endpoints.developmentPrs(owner, repo)));
      const latestPrTitle = prs[0]?.title;
      setDevelopmentPrs(prs);
      if (runResult.dispatched) {
        setRunToast({
          severity: 'success',
          message: latestPrTitle
            ? `✅ Workflow dispatched. Latest dev PR: ${latestPrTitle}`
            : `✅ Workflow dispatched (${runResult.workflow} on ${runResult.ref}).`,
        });
      } else {
        setRunToast({ severity: 'error', message: 'Workflow dispatch was not acknowledged by the backend.' });
      }
      await loadRepoData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setRunToast({ severity: 'error', message: 'Run failed to start from control plane.' });
      await loadRepoData();
    } finally {
      setRunning(false);
    }
  }, [
    loadRepoData,
    resolveBackendMode,
    running,
    selectedMode,
    selectedRepoParts,
    setDevelopmentPrs,
    setError,
    setRunToast,
    setRunning,
  ]);

  const handleConnectGithub = React.useCallback(async () => {
    setIsConnecting(true);
    setError(null);
    try {
      const payload = await apiFetch<AuthStartResponse>('/auth/github/start', {
        method: 'POST',
        body: JSON.stringify({}),
      });
      window.location.assign(payload.authorizationUrl);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsConnecting(false);
    }
  }, [setError, setIsConnecting]);

  const handleLogout = React.useCallback(async () => {
    try {
      await apiFetch('/auth/logout', { method: 'POST', body: JSON.stringify({}) });
    } finally {
      window.localStorage.removeItem(REPO_STORAGE_KEY);
      window.localStorage.removeItem(ONBOARDING_COMPLETE_KEY);
      setAuthLogin(null);
      setRepos([]);
      setSelectedRepo('');
      setStatus(null);
      setDevelopmentPrs([]);
      setScene('connect');
    }
  }, [setAuthLogin, setDevelopmentPrs, setRepos, setScene, setSelectedRepo, setStatus]);

  const handleContinueFromRepoSelection = React.useCallback(async () => {
    if (!selectedRepoParts) {
      setError('Please select a repository to continue.');
      return;
    }
    setError(null);
    try {
      const latestStatus = await loadRepoData();
      if (latestStatus?.hasTargetState) {
        markOnboardingCompleted();
        setScene('dashboard');
        return;
      }
      setScene('target');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [loadRepoData, markOnboardingCompleted, selectedRepoParts, setError, setScene]);

  const runInitializationStep = React.useCallback(async () => {
    if (!selectedRepoParts) return;
    const content = targetStateText.trim();
    if (!content) {
      setError('Please describe the system you want to build before starting.');
      return;
    }

    setScene('initializing');
    setIsStartingFirstIteration(true);
    setInitProgress({ repositoryPrepared: false, initialAnalysisComplete: false, planGenerated: false });
    const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));
    try {
      const { owner, repo } = selectedRepoParts;
      await apiFetch<RepoInitializeResponse>(String(endpoints.repoInitialize(owner, repo)), {
        method: 'POST',
        body: JSON.stringify({
          target_state: content,
          orchestrator_config: `mode: ${resolveBackendMode(selectedMode)}\n`,
          open_pr: false,
          apply_directly: true,
        }),
      });
      setInitProgress((prev) => ({ ...prev, repositoryPrepared: true }));
      await wait(700);
      setInitProgress((prev) => ({ ...prev, initialAnalysisComplete: true }));
      await wait(700);
      setInitProgress((prev) => ({ ...prev, planGenerated: true }));
      await wait(500);
      await handleRun();
      markOnboardingCompleted();
      setScene('dashboard');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setScene('target');
    } finally {
      setIsStartingFirstIteration(false);
    }
  }, [
    handleRun,
    markOnboardingCompleted,
    selectedRepoParts,
    setError,
    setInitProgress,
    setIsStartingFirstIteration,
    setScene,
    selectedMode,
    targetStateText,
    resolveBackendMode,
  ]);

  const handleSaveForLater = React.useCallback(async () => {
    try {
      await handleTargetStateSubmit();
      markOnboardingCompleted();
      setRunToast({ severity: 'success', message: 'Target state saved. Continue whenever you are ready.' });
      setScene('dashboard');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [handleTargetStateSubmit, markOnboardingCompleted, setError, setRunToast, setScene]);

  const handleDisableTour = React.useCallback(() => {
    window.localStorage.setItem(DASHBOARD_TOUR_DISABLED_KEY, 'true');
    setShowTour(false);
  }, [setShowTour]);

  const handleRefreshStatus = React.useCallback(async () => {
    try {
      await loadRepoData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [loadRepoData, setError]);

  return {
    handleTargetStateSubmit,
    handleRun,
    handleRefreshStatus,
    handleConnectGithub,
    handleLogout,
    handleContinueFromRepoSelection,
    runInitializationStep,
    handleSaveForLater,
    handleDisableTour,
  };
}
