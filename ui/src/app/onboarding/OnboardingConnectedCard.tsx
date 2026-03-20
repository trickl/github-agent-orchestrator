import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';

type Props = {
  onContinueAfterConnected: () => void;
};

export function OnboardingConnectedCard({ onContinueAfterConnected }: Props): React.JSX.Element {
  return (
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
