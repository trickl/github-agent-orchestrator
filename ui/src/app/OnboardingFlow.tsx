import React from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  FormControl,
  IconButton,
  InputLabel,
  LinearProgress,
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
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';
import type { OnboardingScene } from './App';

type ColorModeValue = {
  mode: 'light' | 'dark';
  toggle: () => void;
} | null;

type InitProgress = {
  repositoryPrepared: boolean;
  initialAnalysisComplete: boolean;
  planGenerated: boolean;
};

type Props = {
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
  initProgress: InitProgress;
  error: string | null;
  onGoToConnect: () => void;
  onConnectGithub: () => void;
  onContinueAfterConnected: () => void;
  onContinueFromRepo: () => void;
  onStartFirstIteration: () => void;
  onSaveForLater: () => void;
};

const EXAMPLE_TARGET_PROMPTS = [
  'Add a new feature',
  'Fix failing tests',
  'Refactor a module',
  'Improve performance',
];

const WELCOME_STEPS = ['Connect GitHub', 'Choose repository', 'Define target state', 'Run agent'];

export function OnboardingFlow({
  scene,
  colorMode,
  repos,
  repoSearch,
  onRepoSearchChange,
  selectedRepo,
  onSelectRepo,
  targetStateText,
  onTargetStateChange,
  isConnecting,
  isStartingFirstIteration,
  initProgress,
  error,
  onGoToConnect,
  onConnectGithub,
  onContinueAfterConnected,
  onContinueFromRepo,
  onStartFirstIteration,
  onSaveForLater,
}: Props): React.JSX.Element {
  const filteredRepos = React.useMemo(() => {
    const query = repoSearch.trim().toLowerCase();
    if (!query) return repos;
    return repos.filter((repo) => repo.toLowerCase().includes(query));
  }, [repoSearch, repos]);

  const commonShell = (content: React.ReactNode): React.JSX.Element => (
    <Container maxWidth="md" sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', py: 4 }}>
      <Card sx={{ width: '100%', maxWidth: 920 }}>
        <CardContent sx={{ p: { xs: 3, md: 4 } }}>
          <Stack spacing={3}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h5">GitHub Agent Orchestrator</Typography>
              <IconButton aria-label="Toggle color mode" onClick={colorMode?.toggle}>
                {colorMode?.mode === 'dark' ? <LightModeOutlinedIcon /> : <DarkModeOutlinedIcon />}
              </IconButton>
            </Stack>
            {error ? <Alert severity="error">{error}</Alert> : null}
            {content}
          </Stack>
        </CardContent>
      </Card>
    </Container>
  );

  if (scene === 'welcome') {
    return commonShell(
      <Stack spacing={3}>
        <Stack spacing={1}>
          <Typography variant="h4">Engineering that moves toward a goal.</Typography>
          <Typography color="text.secondary">
            Connect your repository, define your goal, and let the agent work toward it step by step.
          </Typography>
        </Stack>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          {WELCOME_STEPS.map((step) => (
            <Chip key={step} label={step} variant="outlined" />
          ))}
        </Stack>

        <Stack direction="row" spacing={2}>
          <Button variant="contained" size="large" onClick={onGoToConnect}>
            Connect GitHub
          </Button>
          <Button
            component="a"
            href="https://github.com/trickl/github-agent-orchestrator#why-this-exists"
            target="_blank"
            rel="noreferrer"
          >
            Learn how it works
          </Button>
        </Stack>
      </Stack>
    );
  }

  if (scene === 'connect') {
    return commonShell(
      <Stack spacing={2.5}>
        <Typography variant="h4">Connect your GitHub account</Typography>
        <Typography color="text.secondary">
          We use a GitHub App to access your repositories securely. You choose which repositories are
          available.
        </Typography>

        <Box>
          <Button variant="contained" size="large" onClick={onConnectGithub} disabled={isConnecting}>
            {isConnecting ? 'Connecting...' : 'Connect with GitHub'}
          </Button>
        </Box>
      </Stack>
    );
  }

  if (scene === 'connected') {
    return commonShell(
      <Stack spacing={2.5}>
        <Alert severity="success" icon={<CheckCircleOutlineIcon fontSize="inherit" />}>
          GitHub connected
        </Alert>
        <Typography color="text.secondary">Your repositories are now available.</Typography>
        <Box>
          <Button variant="contained" size="large" onClick={onContinueAfterConnected}>
            Continue
          </Button>
        </Box>
      </Stack>
    );
  }

  if (scene === 'repo') {
    return commonShell(
      <Stack spacing={2.5}>
        <Typography variant="h4">Select a repository</Typography>
        <TextField
          label="Search repositories"
          value={repoSearch}
          onChange={(event) => onRepoSearchChange(event.target.value)}
          placeholder="Filter by name"
          fullWidth
        />

        {repos.length === 0 ? (
          <Alert severity="info" variant="outlined">
            <Stack spacing={1}>
              <Typography fontWeight={600}>No repositories available yet</Typography>
              <Typography variant="body2">
                You may need to grant access to your repositories during setup.
              </Typography>
              <Box>
                <Button
                  component="a"
                  href="https://github.com/settings/installations"
                  target="_blank"
                  rel="noreferrer"
                  variant="outlined"
                >
                  Manage access in GitHub
                </Button>
              </Box>
            </Stack>
          </Alert>
        ) : (
          <List dense sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, maxHeight: 280, overflowY: 'auto' }}>
            {filteredRepos.map((repoName) => (
              <ListItem key={repoName} disablePadding>
                <ListItemButton selected={selectedRepo === repoName} onClick={() => onSelectRepo(repoName)}>
                  <ListItemText
                    primary={repoName}
                    secondary="Visibility is controlled by your GitHub app installation"
                  />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        )}

        <Box>
          <Button variant="contained" size="large" disabled={!selectedRepo} onClick={onContinueFromRepo}>
            Continue
          </Button>
        </Box>
      </Stack>
    );
  }

  if (scene === 'target') {
    return commonShell(
      <Stack spacing={2.5}>
        <Typography variant="h4">What do you want to build?</Typography>
        <Typography color="text.secondary">
          Describe the desired end state. The agent will work toward this goal iteratively.
        </Typography>

        <TextField
          multiline
          minRows={8}
          value={targetStateText}
          onChange={(event) => onTargetStateChange(event.target.value)}
          placeholder="Implement a REST API for user authentication with login, registration, and tests."
          fullWidth
        />

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {EXAMPLE_TARGET_PROMPTS.map((prompt) => (
            <Chip
              key={prompt}
              label={prompt}
              onClick={() => {
                if (targetStateText.trim()) return;
                onTargetStateChange(prompt);
              }}
              variant="outlined"
            />
          ))}
        </Stack>

        <Accordion>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>Advanced options</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={2}>
              <FormControl fullWidth disabled>
                <InputLabel id="branch-behavior-label">Branch behaviour</InputLabel>
                <Select labelId="branch-behavior-label" label="Branch behaviour" value="default">
                  <MenuItem value="default">Use default branch strategy</MenuItem>
                </Select>
              </FormControl>
              <FormControl fullWidth disabled>
                <InputLabel id="review-preferences-label">Review preferences</InputLabel>
                <Select labelId="review-preferences-label" label="Review preferences" value="standard">
                  <MenuItem value="standard">Standard review cadence</MenuItem>
                </Select>
              </FormControl>
              <TextField disabled label="Iteration constraints" placeholder="Optional limits and constraints" />
            </Stack>
          </AccordionDetails>
        </Accordion>

        <Typography variant="body2" color="text.secondary">
          More specific goals produce better results.
        </Typography>

        <Stack direction="row" spacing={2}>
          <Button variant="contained" size="large" disabled={isStartingFirstIteration} onClick={onStartFirstIteration}>
            Start first iteration
          </Button>
          <Button variant="outlined" disabled={isStartingFirstIteration} onClick={onSaveForLater}>
            Save for later
          </Button>
        </Stack>
      </Stack>
    );
  }

  return commonShell(
    <Stack spacing={2.5}>
      <Typography variant="h4">Setting up your project…</Typography>
      <LinearProgress />

      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1} alignItems="center">
          {initProgress.repositoryPrepared ? (
            <CheckCircleOutlineIcon color="success" fontSize="small" />
          ) : (
            <RadioButtonUncheckedIcon color="disabled" fontSize="small" />
          )}
          <Typography>Repository prepared</Typography>
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center">
          {initProgress.initialAnalysisComplete ? (
            <CheckCircleOutlineIcon color="success" fontSize="small" />
          ) : (
            <RadioButtonUncheckedIcon color="disabled" fontSize="small" />
          )}
          <Typography>Initial analysis complete</Typography>
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center">
          {initProgress.planGenerated ? (
            <CheckCircleOutlineIcon color="success" fontSize="small" />
          ) : (
            <RadioButtonUncheckedIcon color="disabled" fontSize="small" />
          )}
          <Typography>Plan generated</Typography>
        </Stack>
      </Stack>

      {isStartingFirstIteration ? (
        <Stack direction="row" spacing={1.5} alignItems="center">
          <CircularProgress size={20} />
          <Typography color="text.secondary">Running first iteration…</Typography>
        </Stack>
      ) : null}
    </Stack>
  );
}
