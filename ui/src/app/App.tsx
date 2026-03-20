import React from 'react';
import { Alert, Box, CircularProgress, Container, Snackbar, Stack, Typography } from '@mui/material';
import { ApiError, apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import { DashboardView } from './DashboardView';
import { OnboardingFlow } from './OnboardingFlow';
import { ColorModeContext } from './colorModeContext';

type RepoStatusResponse = {
  hasTargetState: boolean;
  status: 'idle' | 'running' | 'error' | string;
  currentStep?: string | null;
};

type DevelopmentPullRequest = {
  title: string;
  url: string;
  createdAt: string;
};

type RunResponse = {
  status: string;
  repo: string;
  stdout: string;
  stderr: string;
  exit_code: number;
};

type AuthMeResponse = {
  authenticated: boolean;
  login: string;
  id: number;
};

type AuthStartResponse = {
  authorizationUrl: string;
};

type GithubAppInstallUrlResponse = {
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

const REPO_STORAGE_KEY = 'gao.selectedRepo';
const TARGET_DRAFT_STORAGE_KEY = 'gao.targetStateDraft';
const ONBOARDING_COMPLETE_KEY = 'gao.onboardingComplete.v1';
const DASHBOARD_TOUR_DISABLED_KEY = 'gao.dashboardTourDisabled.v1';
const RUNNING_POLL_MS = 1500;
const IDLE_POLL_MS = 7000;

function parseRepoFullName(fullName: string): { owner: string; repo: string } | null {
  const [owner, repo] = fullName.split('/');
  if (!owner || !repo) return null;
  return { owner, repo };
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString();
}

function normalizeStatus(status: string | null | undefined): 'idle' | 'running' | 'error' {
  const normalized = (status ?? '').trim().toLowerCase();
  if (normalized === 'running') return 'running';
  if (normalized === 'error') return 'error';
  return 'idle';
}

function isNoInstallationsError(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;

  const combined = `${err.message}\n${err.bodyText ?? ''}`.toLowerCase();
  return (
    err.status === 502 &&
    (combined.includes('no installations found for this github app') ||
      combined.includes('no github app installations available'))
  );
}

export function App(): React.JSX.Element {
  const colorMode = React.useContext(ColorModeContext);
  const [repos, setRepos] = React.useState<string[]>([]);
  const [authLogin, setAuthLogin] = React.useState<string | null>(null);
  const [githubAppInstallUrl, setGithubAppInstallUrl] = React.useState<string | null>(null);
  const [selectedRepo, setSelectedRepo] = React.useState<string>('');
  const [status, setStatus] = React.useState<RepoStatusResponse | null>(null);
  const [developmentPrs, setDevelopmentPrs] = React.useState<DevelopmentPullRequest[]>([]);
  const [targetStateText, setTargetStateText] = React.useState(
    () => window.localStorage.getItem(TARGET_DRAFT_STORAGE_KEY) ?? ''
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
  const [runToast, setRunToast] = React.useState<{ severity: 'success' | 'error'; message: string } | null>(null);
  const lastRepoRefreshAtRef = React.useRef<number>(0);

  const selectedRepoParts = React.useMemo(() => parseRepoFullName(selectedRepo), [selectedRepo]);

  const loadRepos = React.useCallback(async () => {
    const data = await apiFetch<string[]>(endpoints.repos());
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
      const me = await apiFetch<AuthMeResponse>(endpoints.authMe());
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
      const payload = await apiFetch<GithubAppInstallUrlResponse>(endpoints.authGithubAppInstallUrl());
      setGithubAppInstallUrl(payload.installUrl);
    } catch {
      setGithubAppInstallUrl(null);
    }
  }, []);

  const loadRepoData = React.useCallback(async () => {
    if (!selectedRepoParts) return null;
    const { owner, repo } = selectedRepoParts;
    const [statusPayload, prsPayload] = await Promise.all([
      apiFetch<RepoStatusResponse>(endpoints.repoStatus(owner, repo)),
      apiFetch<DevelopmentPullRequest[]>(endpoints.developmentPrs(owner, repo)),
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
        if (!cancelled) {
          setLoading(false);
        }
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
      if (document.visibilityState === 'visible') {
        maybeRefresh();
      }
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
    if (!authLogin) {
      setScene('welcome');
    } else if (onboardingComplete) {
      setScene(selectedRepo ? 'dashboard' : 'repo');
    } else {
      setScene('repo');
    }

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
    await apiFetch(endpoints.repoTargetState(owner, repo), {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
    setRunToast({ severity: 'success', message: '✅ Target state saved. You can now start building.' });
    await loadRepoData();
  }, [loadRepoData, selectedRepoParts, targetStateText]);

  const handleRun = React.useCallback(async () => {
    if (!selectedRepoParts || running) return;
    setRunning(true);
    setError(null);
    setRunToast(null);
    const { owner, repo } = selectedRepoParts;
    try {
      const runResult = await apiFetch<RunResponse>(endpoints.repoRun(owner, repo), {
        method: 'POST',
        body: JSON.stringify({}),
      });
      const prs = await apiFetch<DevelopmentPullRequest[]>(endpoints.developmentPrs(owner, repo));
      const latestPrTitle = prs[0]?.title;
      setDevelopmentPrs(prs);
      if (runResult.exit_code === 0) {
        setRunToast({
          severity: 'success',
          message: latestPrTitle
            ? `✅ Run completed. Created PR: ${latestPrTitle}`
            : '✅ Run completed.',
        });
      } else {
        setRunToast({
          severity: 'error',
          message: 'Run finished with errors. Check repository activity for details.',
        });
      }
      await loadRepoData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setRunToast({ severity: 'error', message: 'Run failed to start from control plane.' });
      await loadRepoData();
    } finally {
      setRunning(false);
    }
  }, [loadRepoData, running, selectedRepoParts]);

  const markOnboardingCompleted = React.useCallback(() => {
    window.localStorage.setItem(ONBOARDING_COMPLETE_KEY, 'true');
    if (window.localStorage.getItem(DASHBOARD_TOUR_DISABLED_KEY) !== 'true') {
      setShowTour(true);
    }
  }, []);

  const handleConnectGithub = React.useCallback(async () => {
    setIsConnecting(true);
    setError(null);
    try {
      const payload = await apiFetch<AuthStartResponse>(endpoints.authGithubStart(), {
        method: 'POST',
        body: JSON.stringify({}),
      });
      window.location.assign(payload.authorizationUrl);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsConnecting(false);
    }
  }, []);

  const handleLogout = React.useCallback(async () => {
    try {
      await apiFetch(endpoints.authLogout(), {
        method: 'POST',
        body: JSON.stringify({}),
      });
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
  }, []);

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
  }, [loadRepoData, markOnboardingCompleted, selectedRepoParts]);

  const runInitializationStep = React.useCallback(async () => {
    if (!selectedRepoParts) return;
    setScene('initializing');
    setIsStartingFirstIteration(true);
    setInitProgress({
      repositoryPrepared: false,
      initialAnalysisComplete: false,
      planGenerated: false,
    });

    const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

    try {
      await handleTargetStateSubmit();
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
  }, [handleRun, handleTargetStateSubmit, markOnboardingCompleted, selectedRepoParts]);

  const handleSaveForLater = React.useCallback(async () => {
    try {
      await handleTargetStateSubmit();
      markOnboardingCompleted();
      setRunToast({ severity: 'success', message: 'Target state saved. Continue whenever you are ready.' });
      setScene('dashboard');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [handleTargetStateSubmit, markOnboardingCompleted]);

  const handleDisableTour = React.useCallback(() => {
    window.localStorage.setItem(DASHBOARD_TOUR_DISABLED_KEY, 'true');
    setShowTour(false);
  }, []);

  if (loading) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <Stack spacing={2} alignItems="center">
          <CircularProgress />
          <Typography color="text.secondary">Loading repositories...</Typography>
        </Stack>
      </Box>
    );
  }

  if (scene !== 'dashboard') {
    return (
      <OnboardingFlow
        scene={scene}
        colorMode={colorMode}
        repos={repos}
        repoSearch={repoSearch}
        onRepoSearchChange={setRepoSearch}
        selectedRepo={selectedRepo}
        onSelectRepo={setSelectedRepo}
        targetStateText={targetStateText}
        onTargetStateChange={setTargetStateText}
        isConnecting={isConnecting}
        isStartingFirstIteration={isStartingFirstIteration}
        isRefreshingRepos={isRefreshingRepos}
        githubAppInstallUrl={githubAppInstallUrl}
        initProgress={initProgress}
        error={error}
        onGoToConnect={() => setScene('connect')}
        onConnectGithub={() => void handleConnectGithub()}
        onContinueAfterConnected={() => setScene('repo')}
        onRefreshRepos={() => void refreshRepos()}
        onContinueFromRepo={() => void handleContinueFromRepoSelection()}
        onStartFirstIteration={() => void runInitializationStep()}
        onSaveForLater={() => void handleSaveForLater()}
      />
    );
  }

  return (
    <>
      <DashboardView
        colorMode={colorMode}
        authLogin={authLogin}
        repos={repos}
        selectedRepo={selectedRepo}
        onSelectRepo={setSelectedRepo}
        status={status}
        running={running}
        developmentPrs={developmentPrs}
        targetStateText={targetStateText}
        onTargetStateChange={setTargetStateText}
        onSaveTargetState={() => void handleTargetStateSubmit()}
        onRunNextIteration={() => void handleRun()}
        onLogout={() => void handleLogout()}
        showTour={showTour}
        onCloseTour={() => setShowTour(false)}
        onDisableTour={handleDisableTour}
      />

      {error ? (
        <Container maxWidth="lg" sx={{ pb: 2 }}>
          <Alert severity="error">{error}</Alert>
        </Container>
      ) : null}

      <Snackbar
        open={Boolean(runToast)}
        autoHideDuration={4500}
        onClose={() => setRunToast(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        {runToast ? (
          <Alert onClose={() => setRunToast(null)} severity={runToast.severity} variant="filled" sx={{ width: '100%' }}>
            {runToast.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </>
  );
}
