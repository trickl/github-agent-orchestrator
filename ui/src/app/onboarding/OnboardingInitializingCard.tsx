import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import { CircularProgress, LinearProgress, Stack, Typography } from '@mui/material';
import type { InitProgress } from './types';

type Props = {
  isStartingFirstIteration: boolean;
  initProgress: InitProgress;
};

export function OnboardingInitializingCard({
  isStartingFirstIteration,
  initProgress,
}: Props): React.JSX.Element {
  return (
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
