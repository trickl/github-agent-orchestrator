import { Box, Button, Stack, Typography } from '@mui/material';

type Props = {
  isConnecting: boolean;
  githubAppInstallUrl: string | null;
  onConnectGithub: () => void;
};

export function OnboardingConnectCard({
  isConnecting,
  githubAppInstallUrl,
  onConnectGithub,
}: Props): React.JSX.Element {
  return (
    <Stack spacing={2.5}>
      <Typography variant="h4">Connect your GitHub account</Typography>
      <Typography color="text.secondary">
        We use a GitHub App to access your repositories securely. You choose which repositories are
        available.
      </Typography>

      <Box>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          <Button variant="contained" size="large" onClick={onConnectGithub} disabled={isConnecting}>
            {isConnecting ? 'Connecting...' : 'Connect with GitHub'}
          </Button>
          {githubAppInstallUrl ? (
            <Button
              component="a"
              href={githubAppInstallUrl}
              target="_blank"
              rel="noreferrer"
              variant="outlined"
            >
              Install GitHub App
            </Button>
          ) : null}
        </Stack>
      </Box>
    </Stack>
  );
}
