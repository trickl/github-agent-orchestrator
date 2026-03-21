import React from 'react';
import { ApiError, apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import {
  DASHBOARD_TOUR_DISABLED_KEY,
  IDLE_POLL_MS,
  MODE_STORAGE_KEY,
  ONBOARDING_COMPLETE_KEY,
  REPO_STORAGE_KEY,
  RUNNING_POLL_MS,
  TARGET_DRAFT_STORAGE_KEY,
} from './types';
import type {
  AuthMeResponse,
  DevelopmentPullRequest,
  GithubAppInstallUrlResponse,
  OnboardingScene,
  OrchestratorMode,
  RepoStatusResponse,
  RunToast,
} from './types';

function parseRepoFullName(fullName: string): { owner: string; repo: string } | null {
  const [owner, repo] = fullName.split('/');
  if (!owner || !repo) return null;
  return { owner, repo };
}

function normalizeStatus(status: string | null | undefined): 'idle' | 'running' | 'error' {
  const normalized = (status ?? '').trim().toLowerCase();
  if (normalized === 'running') return 'running';
  if (normalized === 'error') return 'error';
  return 'idle';
}

export function isNoInstallationsError(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  const combined = `${err.message}\n${err.bodyText ?? ''}`.toLowerCase();
  return (
    err.status === 502 &&
    (combined.includes('no installations found for this github app') ||
      combined.includes('no github app installations available'))
  );
}

function normalizeMode(mode: string | null): OrchestratorMode {
  if (mode === 'auto') return 'auto';
  return 'manual';
}

export type AppDataResult = ReturnType<typeof useAppData>;

export function useAppData() {
  const [repos, setRepos] = React.useState<string[]>([]);
  const [authLogin, setAuthLogin] = React.useState<string | null>(null);
  const [githubAppInstallUrl, setGithubAppInstallUrl] = React.useState<string | null>(null);
  const [selectedRepo, setSelectedRepo] = React.useState('');
  const [status, setStatus] = React.useState<RepoStatusResponse | null>(null);
  const [developmentPrs, setDevelopmentPrs] = React.useState<DevelopmentPullRequest[]>([]);
  const [targetStateText, setTargetStateText] = React.useState(
    () => window.localStorage.getItem(TARGET_DRAFT_STORAGE_KEY) ?? ''
  );
  const [selectedMode, setSelectedMode] = React.useState<OrchestratorMode>(() =>
    normalizeMode(window.localStorage.getItem(MODE_STORAGE_KEY))
  );
  const [scene, setScene] = React.useState<OnboardingScene>('welcome');
  const [initialSceneResolved, setInitialSceneResolved] = React.useState(false);
  const [isConnecting, setIsConnecting] = React.useState(false);
  const [isStartingFirstIteration, setIsStartingFirstIteration] = React.useState(false);
  const [showTour, setShowTour] = React.useState(false);
  const [initProgress, setInitProgress] = React.useState({
    repositoryPrepared: false,
    initialAnalysisComplete: false,
    planGenerated: false,
  });
  const [repoSearch, setRepoSearch] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [running, setRunning] = React.useState(false);
  const [isRefreshingRepos, setIsRefreshingRepos] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [runToast, setRunToast] = React.useState<RunToast>(null);

  const lastRepoRefreshAtRef = React.useRef<number>(0);
  const selectedRepoParts = React.useMemo(() => parseRepoFullName(selectedRepo), [selectedRepo]);

  const loadRepos = React.useCallback(async () => {
    const data = await apiFetch<string[]>(String(endpoints.repos()));
    setRepos(data);
    if (data.length === 0) {
      setSelectedRepo('');
      return data;
    }
    const persisted = window.localStorage.getItem(REPO_STORAGE_KEY);
    if (persisted && data.includes(persisted)) {
      setSelectedRepo(persisted);
      return data;
    }
    setSelectedRepo(data[0]);
    return data;
  }, []);

  const loadAuthSession = React.useCallback(async () => {
    try {
      const me = await apiFetch<AuthMeResponse>('/auth/me');
      setAuthLogin(me.login);
      return true;
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 401) {
        setAuthLogin(null);
        return false;
      }
      throw err;
    }
  }, []);

  const loadGithubAppInstallUrl = React.useCallback(async () => {
    try {
      const payload = await apiFetch<GithubAppInstallUrlResponse>('/auth/github-app/install-url');
      setGithubAppInstallUrl(payload.installUrl);
    } catch {
      setGithubAppInstallUrl(null);
    }
  }, []);

  const loadRepoData = React.useCallback(async () => {
    if (!selectedRepoParts) return null;
    const { owner, repo } = selectedRepoParts;
    const [statusPayload, prsPayload] = await Promise.all([
      apiFetch<RepoStatusResponse>(String(endpoints.repoStatus(owner, repo))),
      apiFetch<DevelopmentPullRequest[]>(String(endpoints.developmentPrs(owner, repo))),
    ]);
    setStatus(statusPayload);
    setDevelopmentPrs(prsPayload);
    return statusPayload;
  }, [selectedRepoParts]);

  const refreshRepos = React.useCallback(async () => {
    setIsRefreshingRepos(true);
    lastRepoRefreshAtRef.current = Date.now();
    try {
      return await loadRepos();
    } catch (err: unknown) {
      if (isNoInstallationsError(err)) {
        setRepos([]);
        setSelectedRepo('');
        setError(null);
        return [];
      }
      setError(err instanceof Error ? err.message : String(err));
      return [];
    } finally {
      setIsRefreshingRepos(false);
    }
  }, [loadRepos]);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        await loadGithubAppInstallUrl();
        const isAuthed = await loadAuthSession();
        if (!isAuthed) {
          if (!cancelled) {
            setRepos([]);
            setSelectedRepo('');
            setScene('welcome');
          }
          return;
        }
        await refreshRepos();
      } catch (err: unknown) {
        if (!cancelled) {
          if (isNoInstallationsError(err)) {
            setRepos([]);
            setSelectedRepo('');
            setError(null);
            return;
          }
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadAuthSession, loadGithubAppInstallUrl, refreshRepos]);

  React.useEffect(() => {
    if (scene !== 'repo' || !authLogin || repos.length > 0) return;
    const maybeRefresh = () => {
      const now = Date.now();
      if (now - lastRepoRefreshAtRef.current < 2000) return;
      void refreshRepos();
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') maybeRefresh();
    };
    window.addEventListener('focus', maybeRefresh);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.removeEventListener('focus', maybeRefresh);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [authLogin, refreshRepos, repos.length, scene]);

  React.useEffect(() => {
    if (initialSceneResolved || loading) return;
    const onboardingComplete = window.localStorage.getItem(ONBOARDING_COMPLETE_KEY) === 'true';
    if (!authLogin) setScene('welcome');
    else if (onboardingComplete) setScene(selectedRepo ? 'dashboard' : 'repo');
    else setScene('repo');
    setInitialSceneResolved(true);
  }, [authLogin, initialSceneResolved, loading, selectedRepo]);

  React.useEffect(() => {
    if (!selectedRepo) return;
    window.localStorage.setItem(REPO_STORAGE_KEY, selectedRepo);
    setError(null);
    void loadRepoData().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  }, [loadRepoData, selectedRepo]);

  React.useEffect(() => {
    if (!selectedRepoParts || scene !== 'dashboard') return;
    const pollMs = normalizeStatus(status?.status) === 'running' ? RUNNING_POLL_MS : IDLE_POLL_MS;
    const id = window.setInterval(() => {
      void loadRepoData().catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      });
    }, pollMs);
    return () => window.clearInterval(id);
  }, [loadRepoData, scene, selectedRepoParts, status?.status]);

  React.useEffect(() => {
    window.localStorage.setItem(TARGET_DRAFT_STORAGE_KEY, targetStateText);
  }, [targetStateText]);

  React.useEffect(() => {
    window.localStorage.setItem(MODE_STORAGE_KEY, selectedMode);
  }, [selectedMode]);

  const markOnboardingCompleted = React.useCallback(() => {
    window.localStorage.setItem(ONBOARDING_COMPLETE_KEY, 'true');
    if (window.localStorage.getItem(DASHBOARD_TOUR_DISABLED_KEY) !== 'true') {
      setShowTour(true);
    }
  }, []);

  return {
    repos,
    authLogin,
    githubAppInstallUrl,
    selectedRepo,
    status,
    developmentPrs,
    targetStateText,
    selectedMode,
    scene,
    repoSearch,
    loading,
    running,
    isConnecting,
    isStartingFirstIteration,
    isRefreshingRepos,
    showTour,
    initProgress,
    error,
    runToast,
    selectedRepoParts,
    setRepoSearch,
    setAuthLogin,
    setRepos,
    setSelectedRepo,
    setTargetStateText,
    setSelectedMode,
    setRunToast,
    setScene,
    setShowTour,
    setError,
    setIsConnecting,
    setIsStartingFirstIteration,
    setInitProgress,
    setRunning,
    setStatus,
    setDevelopmentPrs,
    refreshRepos,
    loadRepoData,
    markOnboardingCompleted,
  };
}
