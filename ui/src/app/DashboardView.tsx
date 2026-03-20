import React from 'react';
import {
  Alert,
  Button,
  Card,
  CardContent,
  Checkbox,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  Grid,
  IconButton,
  InputLabel,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';

type ColorModeValue = {
  mode: 'light' | 'dark';
  toggle: () => void;
} | null;

type RepoStatusResponse = {
  hasTargetState: boolean;
  status: string;
  currentStep?: string | null;
  active_issue_ids?: number[];
  active_pr_ids?: number[];
};

type DevelopmentPullRequest = {
  title: string;
  url: string;
  createdAt: string;
};

type Props = {
  colorMode: ColorModeValue;
  authLogin: string | null;
  repos: string[];
  selectedRepo: string;
  onSelectRepo: (repo: string) => void;
  status: RepoStatusResponse | null;
  running: boolean;
  developmentPrs: DevelopmentPullRequest[];
  targetStateText: string;
  onTargetStateChange: (value: string) => void;
  onSaveTargetState: () => void;
  onRunNextIteration: () => void;
  onLogout: () => void;
  showTour: boolean;
  onCloseTour: () => void;
  onDisableTour: () => void;
};

const TOUR_STEPS = [
  {
    title: 'Repository area',
    body: 'This is the project you’re working on.',
  },
  {
    title: 'Target state',
    body: 'This defines what the agent is trying to achieve.',
  },
  {
    title: 'Progress section',
    body: 'Here you can see what’s been completed so far.',
  },
  {
    title: 'Run button',
    body: 'Each iteration moves the system closer to your goal.',
  },
] as const;

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

export function DashboardView({
  colorMode,
  authLogin,
  repos,
  selectedRepo,
  onSelectRepo,
  status,
  running,
  developmentPrs,
  targetStateText,
  onTargetStateChange,
  onSaveTargetState,
  onRunNextIteration,
  onLogout,
  showTour,
  onCloseTour,
  onDisableTour,
}: Props): React.JSX.Element {
  const normalizedStatus = normalizeStatus(status?.status);
  const [tourStep, setTourStep] = React.useState(0);
  const [dontShowAgain, setDontShowAgain] = React.useState(false);

  const completedWork = developmentPrs.length;
  const remainingWork = status?.active_issue_ids?.length ?? 0;
  const iterationCount = completedWork + (normalizedStatus === 'running' ? 1 : 0);

  const handleCloseTour = () => {
    if (dontShowAgain) {
      onDisableTour();
      return;
    }
    setTourStep(0);
    onCloseTour();
  };

  const handleNextTour = () => {
    if (tourStep >= TOUR_STEPS.length - 1) {
      handleCloseTour();
      return;
    }
    setTourStep((step) => step + 1);
  };

  const firstPrUrl = developmentPrs[0]?.url;

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Stack spacing={3}>
        <Card variant="outlined">
          <CardContent>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between">
              <Stack spacing={1}>
                <Typography variant="h6">{selectedRepo}</Typography>
                <Typography color="text.secondary">
                  Signed in as: {authLogin ?? 'unknown'}
                </Typography>
                <Typography color="text.secondary">Branch: main</Typography>
                <Typography color="text.secondary">Status: {normalizedStatus}</Typography>
              </Stack>

              <Stack direction="row" spacing={1} alignItems="center">
                <Button variant="outlined" onClick={onLogout}>
                  Log out
                </Button>
                <FormControl sx={{ minWidth: 280 }}>
                  <InputLabel id="repo-switch-label">Select repository</InputLabel>
                  <Select
                    labelId="repo-switch-label"
                    label="Select repository"
                    value={selectedRepo}
                    onChange={(event) => onSelectRepo(event.target.value)}
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
          <Grid item xs={12} md={8}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Target State
                </Typography>
                <TextField
                  multiline
                  minRows={5}
                  fullWidth
                  value={targetStateText}
                  onChange={(event) => onTargetStateChange(event.target.value)}
                />
                <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                  <Button variant="contained" onClick={onSaveTargetState}>
                    Save target state
                  </Button>
                  <Button variant="outlined" disabled>
                    Pause
                  </Button>
                </Stack>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card variant="outlined" sx={{ height: '100%' }}>
              <CardContent>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Progress Overview
                </Typography>
                <Typography>Completed work: {completedWork}</Typography>
                <Typography>Remaining work: {remainingWork}</Typography>
                <Typography>Iterations: {iterationCount}</Typography>
                <Typography color="text.secondary" sx={{ mt: 1 }}>
                  Current step: {status?.currentStep?.trim() ? status.currentStep : '—'}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        <Card variant="outlined">
          <CardContent>
            <Stack
              direction={{ xs: 'column', md: 'row' }}
              spacing={1.5}
              justifyContent="space-between"
              alignItems={{ xs: 'stretch', md: 'center' }}
            >
              <Typography variant="subtitle2" color="text.secondary">
                Recent Activity
              </Typography>

              <Stack direction="row" spacing={1}>
                <Button
                  variant="contained"
                  disabled={running || normalizedStatus === 'running'}
                  onClick={onRunNextIteration}
                >
                  Run next iteration
                </Button>
                <Button variant="outlined" component="a" href={firstPrUrl} target="_blank" rel="noreferrer" disabled={!firstPrUrl}>
                  View pull requests
                </Button>
              </Stack>
            </Stack>

            {developmentPrs.length === 0 ? (
              <Alert severity="info" sx={{ mt: 2 }}>
                No pull requests yet. Run an iteration to generate activity.
              </Alert>
            ) : (
              <List disablePadding sx={{ mt: 1 }}>
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

      <Dialog open={showTour} onClose={handleCloseTour} maxWidth="sm" fullWidth>
        <DialogTitle>{TOUR_STEPS[tourStep].title}</DialogTitle>
        <DialogContent>
          <Typography>{TOUR_STEPS[tourStep].body}</Typography>
          <FormControlLabel
            control={<Checkbox checked={dontShowAgain} onChange={(event) => setDontShowAgain(event.target.checked)} />}
            label="Don’t show again"
            sx={{ mt: 2 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseTour}>Skip tour</Button>
          <Button onClick={handleNextTour} variant="contained">
            {tourStep >= TOUR_STEPS.length - 1 ? 'Finish' : 'Next'}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
