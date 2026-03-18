import React from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Container,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  MenuItem,
  Snackbar,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';
import { apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
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

const REPO_STORAGE_KEY = 'gao.selectedRepo';
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

export function App(): React.JSX.Element {
  const colorMode = React.useContext(ColorModeContext);
  const [repos, setRepos] = React.useState<string[]>([]);
  const [selectedRepo, setSelectedRepo] = React.useState<string>('');
  const [status, setStatus] = React.useState<RepoStatusResponse | null>(null);
  const [developmentPrs, setDevelopmentPrs] = React.useState<DevelopmentPullRequest[]>([]);
  const [targetStateText, setTargetStateText] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [runToast, setRunToast] = React.useState<{ severity: 'success' | 'error'; message: string } | null>(null);

  const selectedRepoParts = React.useMemo(() => parseRepoFullName(selectedRepo), [selectedRepo]);

  const loadRepos = React.useCallback(async () => {
    const data = await apiFetch<string[]>(endpoints.repos());
    setRepos(data);
    if (data.length === 0) {
      setSelectedRepo('');
      return;
    }
    const persisted = window.localStorage.getItem(REPO_STORAGE_KEY);
    if (persisted && data.includes(persisted)) {
      setSelectedRepo(persisted);
      return;
    }
    setSelectedRepo(data[0]);
  }, []);

  const loadRepoData = React.useCallback(async () => {
    if (!selectedRepoParts) return;
    const { owner, repo } = selectedRepoParts;
    const [statusPayload, prsPayload] = await Promise.all([
      apiFetch<RepoStatusResponse>(endpoints.repoStatus(owner, repo)),
      apiFetch<DevelopmentPullRequest[]>(endpoints.developmentPrs(owner, repo)),
    ]);
    setStatus(statusPayload);
    setDevelopmentPrs(prsPayload);
  }, [selectedRepoParts]);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void loadRepos()
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadRepos]);

  React.useEffect(() => {
    if (!selectedRepo) return;
    window.localStorage.setItem(REPO_STORAGE_KEY, selectedRepo);
    setError(null);
    void loadRepoData().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  }, [loadRepoData, selectedRepo]);

  React.useEffect(() => {
    if (!selectedRepoParts) return;

    const pollMs = normalizeStatus(status?.status) === 'running' ? RUNNING_POLL_MS : IDLE_POLL_MS;
    const id = window.setInterval(() => {
      void loadRepoData().catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      });
    }, pollMs);

    return () => window.clearInterval(id);
  }, [loadRepoData, selectedRepoParts, status?.status]);

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
    setTargetStateText('');
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

  if (repos.length === 0) {
    return (
      <Container maxWidth="md" sx={{ py: 8 }}>
        <Alert severity="info">No repositories found for this token.</Alert>
      </Container>
    );
  }

  if (!status?.hasTargetState) {
    return (
      <Container maxWidth="md" sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', py: 4 }}>
        <Card sx={{ width: '100%', maxWidth: 860 }}>
          <CardContent sx={{ p: { xs: 3, md: 4 } }}>
            <Stack spacing={3}>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="h5">Welcome to GitHub Agent Orchestrator</Typography>
                <IconButton aria-label="Toggle color mode" onClick={colorMode?.toggle}>
                  {colorMode?.mode === 'dark' ? <LightModeOutlinedIcon /> : <DarkModeOutlinedIcon />}
                </IconButton>
              </Stack>

              <Typography color="text.secondary">
                Welcome 👋 Start by selecting a repository and describing your target state. The agent will
                then iteratively work towards that goal.
              </Typography>

              <Alert severity="info" variant="outlined">
                Tip: include architecture goals, key capabilities, and any non-negotiable constraints.
              </Alert>

              <FormControl fullWidth>
                <InputLabel id="repo-select-label">Repository</InputLabel>
                <Select
                  labelId="repo-select-label"
                  label="Repository"
                  value={selectedRepo}
                  onChange={(event) => setSelectedRepo(event.target.value)}
                >
                  {repos.map((repoName) => (
                    <MenuItem key={repoName} value={repoName}>
                      {repoName}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <TextField
                multiline
                minRows={8}
                fullWidth
                placeholder="Target State Input"
                value={targetStateText}
                onChange={(event) => setTargetStateText(event.target.value)}
              />

              {error ? <Alert severity="error">{error}</Alert> : null}

              <Box>
                <Button variant="contained" size="large" onClick={() => void handleTargetStateSubmit()}>
                  Start Building
                </Button>
              </Box>
            </Stack>
          </CardContent>
        </Card>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Stack spacing={3}>
        <Card variant="outlined">
          <CardContent>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between">
              <Stack spacing={1}>
                <Typography variant="h6">Repo: {selectedRepo}</Typography>
                <Typography color="text.secondary">Simple control panel for long-running autonomous work</Typography>
              </Stack>

              <Stack direction="row" spacing={1} alignItems="center">
                <FormControl sx={{ minWidth: 280 }}>
                  <InputLabel id="repo-switch-label">Select repository</InputLabel>
                  <Select
                    labelId="repo-switch-label"
                    label="Select repository"
                    value={selectedRepo}
                    onChange={(event) => setSelectedRepo(event.target.value)}
                  >
                    {repos.map((repoName) => (
                      <MenuItem key={repoName} value={repoName}>
                        {repoName}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <IconButton aria-label="Toggle color mode" onClick={colorMode?.toggle}>
                  {colorMode?.mode === 'dark' ? <LightModeOutlinedIcon /> : <DarkModeOutlinedIcon />}
                </IconButton>
              </Stack>
            </Stack>
          </CardContent>
        </Card>

        <Grid container spacing={2}>
          <Grid item xs={12} md={4} sx={{ display: 'flex' }}>
            <Card variant="outlined" sx={{ width: '100%', display: 'flex' }}>
              <CardContent sx={{ width: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Control
                </Typography>
                <Box sx={{ pt: 1 }}>
                  <Button
                    variant="contained"
                    size="large"
                    disabled={running || normalizeStatus(status?.status) === 'running'}
                    onClick={() => void handleRun()}
                  >
                    ▶ Run
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={8} sx={{ display: 'flex' }}>
            <Card variant="outlined" sx={{ width: '100%' }}>
              <CardContent>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Current State
                </Typography>
                <Typography variant="h6">Status: {normalizeStatus(status?.status)}</Typography>
                <Typography color="text.secondary">
                  Current Step: {status?.currentStep?.trim() ? status.currentStep : '—'}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {error ? <Alert severity="error">{error}</Alert> : null}

        <Card variant="outlined">
          <CardContent>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              Development Timeline
            </Typography>
            {developmentPrs.length === 0 ? (
              <Typography color="text.secondary">No development pull requests yet.</Typography>
            ) : (
              <List disablePadding>
                {developmentPrs.map((pr) => (
                  <ListItem
                    key={`${pr.url}-${pr.createdAt}`}
                    disablePadding
                    secondaryAction={<Typography color="text.secondary">{formatTimestamp(pr.createdAt)}</Typography>}
                  >
                    <ListItemButton component="a" href={pr.url} target="_blank" rel="noreferrer">
                      <ListItemText primary={pr.title} />
                    </ListItemButton>
                  </ListItem>
                ))}
              </List>
            )}
          </CardContent>
        </Card>
      </Stack>

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
    </Container>
  );
}
