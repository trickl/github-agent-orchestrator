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
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import {
  getCanonicalIterationState,
  getCompletedWorkCount,
  isAwaitingManualApproval,
} from './iterationSemantics';
import type { DevelopmentPullRequest, OrchestratorMode, RepoStatusResponse } from './types';

type ColorModeValue = {
  mode: 'light' | 'dark';
  toggle: () => void;
} | null;

type Props = {
  colorMode: ColorModeValue;
  authLogin: string | null;
  repos: string[];
  selectedRepo: string;
  onSelectRepo: (repo: string) => void;
  status: RepoStatusResponse | null;
  running: boolean;
  selectedMode: OrchestratorMode;
  onModeChange: (mode: OrchestratorMode) => void;
  developmentPrs: DevelopmentPullRequest[];
  targetStateText: string;
  onTargetStateChange: (value: string) => void;
  onSaveTargetState: () => void;
  onRunNextIteration: () => void;
  onRefreshStatus: () => void;
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

export function DashboardView({
  colorMode,
  authLogin,
  repos,
  selectedRepo,
  onSelectRepo,
  status,
  running,
  selectedMode,
  onModeChange,
  developmentPrs,
  targetStateText,
  onTargetStateChange,
  onSaveTargetState,
  onRunNextIteration,
  onRefreshStatus,
  onLogout,
  showTour,
  onCloseTour,
  onDisableTour,
}: Props): React.JSX.Element {
  const canonicalStatus = getCanonicalIterationState(status, selectedMode, developmentPrs);
  const [tourStep, setTourStep] = React.useState(0);
  const [dontShowAgain, setDontShowAgain] = React.useState(false);
  const [isEditingTargetState, setIsEditingTargetState] = React.useState(false);
  const [targetStateDraft, setTargetStateDraft] = React.useState(targetStateText);
  const targetStateInputRef = React.useRef<HTMLTextAreaElement | null>(null);

  const completedWork = getCompletedWorkCount(developmentPrs);
  const remainingWork = status?.status_artifact?.active_issue_ids?.length ?? status?.active_issue_ids?.length ?? 0;
  const iterationCount = completedWork + (canonicalStatus === 'running' ? 1 : 0);
  const awaitingApproval = isAwaitingManualApproval(status, selectedMode);
  const isTargetStateDirty = targetStateDraft.trim() !== targetStateText.trim();

  React.useEffect(() => {
    if (isEditingTargetState) return;
    setTargetStateDraft(targetStateText);
  }, [isEditingTargetState, targetStateText]);

  React.useEffect(() => {
    if (!isEditingTargetState) return;
    targetStateInputRef.current?.focus();
  }, [isEditingTargetState]);

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

  const handleTargetStateSave = () => {
    onTargetStateChange(targetStateDraft);
    onSaveTargetState();
    setIsEditingTargetState(false);
  };

  const handleTargetStateCancel = () => {
    setTargetStateDraft(targetStateText);
    setIsEditingTargetState(false);
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4, minHeight: '100vh' }}>
      <Stack spacing={3}>
        <Card variant="outlined">
          <CardContent>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between">
              <Stack spacing={1}>
                <Typography variant="h6">GitHub Agent Orchestrator</Typography>
                <Typography color="text.secondary">Repository: {selectedRepo}</Typography>
                <Typography color="text.secondary">
                  Signed in as: {authLogin ?? 'unknown'}
                </Typography>
                <Typography color="text.secondary">Branch: {status?.defaultBranch?.trim() || '—'}</Typography>
                <Typography color="text.secondary">Status: {canonicalStatus}</Typography>
              </Stack>

              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1}
                alignItems={{ xs: 'stretch', sm: 'center' }}
                justifyContent={{ xs: 'flex-start', md: 'flex-end' }}
              >
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
                    inputProps={{ 'aria-label': 'Select repository' }}
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

        {awaitingApproval ? (
          <Alert
            severity="warning"
            action={
              <Stack direction="row" spacing={1}>
                {firstPrUrl ? (
                  <Button color="inherit" size="small" component="a" href={firstPrUrl} target="_blank" rel="noreferrer">
                    Open PR
                  </Button>
                ) : null}
                <Button color="inherit" size="small" onClick={onRefreshStatus}>
                  Refresh status
                </Button>
              </Stack>
            }
          >
            Action required: manual approval is needed to merge the current PR before this iteration can complete.
          </Alert>
        ) : null}

        <Grid container spacing={2}>
          <Grid item xs={12} md={8}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Target State
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  {isEditingTargetState ? 'Editing enabled. Save to persist changes.' : 'Read-only mode. Select Edit to modify.'}
                </Typography>
                <TextField
                  multiline
                  rows={8}
                  fullWidth
                  inputRef={targetStateInputRef}
                  value={targetStateDraft}
                  onChange={(event) => setTargetStateDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape' && isEditingTargetState) {
                      event.preventDefault();
                      handleTargetStateCancel();
                    }
                  }}
                  aria-label="Target state editor"
                  InputProps={{ readOnly: !isEditingTargetState }}
                  sx={{
                    '& textarea': {
                      overflowY: 'scroll',
                      resize: 'none',
                    },
                  }}
                />
                <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                  {isEditingTargetState ? (
                    <>
                      <Button variant="contained" onClick={handleTargetStateSave} disabled={!isTargetStateDirty}>
                        Save changes
                      </Button>
                      <Button variant="outlined" onClick={handleTargetStateCancel}>
                        Cancel
                      </Button>
                      <Typography variant="body2" color={isTargetStateDirty ? 'warning.main' : 'text.secondary'} sx={{ alignSelf: 'center' }}>
                        {isTargetStateDirty ? 'Unsaved changes' : 'No changes'}
                      </Typography>
                    </>
                  ) : (
                    <Button variant="outlined" onClick={() => setIsEditingTargetState(true)}>
                      Edit target state
                    </Button>
                  )}
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

              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <FormControl size="small" sx={{ minWidth: 250 }}>
                  <InputLabel id="mode-select-label">Run mode</InputLabel>
                  <Select
                    labelId="mode-select-label"
                    label="Run mode"
                    value={selectedMode}
                    onChange={(event) => onModeChange(event.target.value as OrchestratorMode)}
                    disabled={running || canonicalStatus === 'running'}
                    inputProps={{ 'aria-label': 'Run mode' }}
                  >
                    <MenuItem value="manual">Manual Approve</MenuItem>
                    <MenuItem value="auto">Auto-Approve (Continuous)</MenuItem>
                  </Select>
                </FormControl>
                <Button
                  variant="contained"
                  disabled={running || canonicalStatus === 'running'}
                  onClick={onRunNextIteration}
                  aria-label="Run iteration"
                >
                  Run iteration
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
                    secondaryAction={
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ pr: 1 }}>
                        <Typography color="text.secondary">{formatTimestamp(pr.createdAt)}</Typography>
                        <IconButton size="small" component="a" href={pr.url} target="_blank" rel="noreferrer" aria-label={`Open PR: ${pr.title}`}>
                          <OpenInNewIcon fontSize="inherit" />
                        </IconButton>
                      </Stack>
                    }
                  >
                    <ListItemButton component="a" href={pr.url} target="_blank" rel="noreferrer">
                      <ListItemText primary={pr.title} secondary="Open pull request in GitHub" />
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
