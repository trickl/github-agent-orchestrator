import React from 'react';
import { Alert, Box, CircularProgress, Container, Snackbar, Stack, Typography } from '@mui/material';
import { DashboardView } from './DashboardView';
import { OnboardingFlow } from './OnboardingFlow';
import { ColorModeContext } from './colorModeContext';
import { useAppController } from './useAppController';

export function App(): React.JSX.Element {
  const colorMode = React.useContext(ColorModeContext);
  const {
    repos,
    authLogin,
    githubAppInstallUrl,
    selectedRepo,
    status,
    developmentPrs,
    targetStateText,
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
    setRepoSearch,
    setSelectedRepo,
    setTargetStateText,
    setRunToast,
    setScene,
    setShowTour,
    refreshRepos,
    handleConnectGithub,
    handleLogout,
    handleContinueFromRepoSelection,
    runInitializationStep,
    handleSaveForLater,
    handleTargetStateSubmit,
    handleRun,
    handleDisableTour,
  } = useAppController();

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
