import React from 'react';
import { Alert, Card, CardContent, Container, IconButton, Stack, Typography } from '@mui/material';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';
import { OnboardingConnectedCard } from './onboarding/OnboardingConnectedCard';
import { OnboardingConnectCard } from './onboarding/OnboardingConnectCard';
import { OnboardingInitializingCard } from './onboarding/OnboardingInitializingCard';
import { OnboardingRepoCard } from './onboarding/OnboardingRepoCard';
import { OnboardingTargetCard } from './onboarding/OnboardingTargetCard';
import { OnboardingWelcomeCard } from './onboarding/OnboardingWelcomeCard';
import type { OnboardingFlowProps } from './onboarding/types';

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
  isRefreshingRepos,
  githubAppInstallUrl,
  initProgress,
  error,
  onGoToConnect,
  onConnectGithub,
  onContinueAfterConnected,
  onRefreshRepos,
  onContinueFromRepo,
  onStartFirstIteration,
  onSaveForLater,
}: OnboardingFlowProps): React.JSX.Element {
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
    return commonShell(<OnboardingWelcomeCard onGoToConnect={onGoToConnect} />);
  }

  if (scene === 'connect') {
    return commonShell(
      <OnboardingConnectCard
        isConnecting={isConnecting}
        githubAppInstallUrl={githubAppInstallUrl}
        onConnectGithub={onConnectGithub}
      />
    );
  }

  if (scene === 'connected') {
    return commonShell(<OnboardingConnectedCard onContinueAfterConnected={onContinueAfterConnected} />);
  }

  if (scene === 'repo') {
    return commonShell(
      <OnboardingRepoCard
        repos={repos}
        repoSearch={repoSearch}
        selectedRepo={selectedRepo}
        isRefreshingRepos={isRefreshingRepos}
        githubAppInstallUrl={githubAppInstallUrl}
        onRepoSearchChange={onRepoSearchChange}
        onSelectRepo={onSelectRepo}
        onRefreshRepos={onRefreshRepos}
        onContinueFromRepo={onContinueFromRepo}
      />
    );
  }

  if (scene === 'target') {
    return commonShell(
      <OnboardingTargetCard
        targetStateText={targetStateText}
        isStartingFirstIteration={isStartingFirstIteration}
        onTargetStateChange={onTargetStateChange}
        onStartFirstIteration={onStartFirstIteration}
        onSaveForLater={onSaveForLater}
      />
    );
  }

  return commonShell(
    <OnboardingInitializingCard
      isStartingFirstIteration={isStartingFirstIteration}
      initProgress={initProgress}
    />
  );
}
