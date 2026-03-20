import { Button, Chip, Stack, Typography } from '@mui/material';

type Props = {
  onGoToConnect: () => void;
};

const WELCOME_STEPS = ['Connect GitHub', 'Choose repository', 'Define target state', 'Run agent'];

export function OnboardingWelcomeCard({ onGoToConnect }: Props): React.JSX.Element {
  return (
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
