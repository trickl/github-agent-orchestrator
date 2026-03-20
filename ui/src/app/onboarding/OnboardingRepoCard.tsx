import {
  Alert,
  Button,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import React from 'react';

type Props = {
  repos: string[];
  repoSearch: string;
  selectedRepo: string;
  isRefreshingRepos: boolean;
  githubAppInstallUrl: string | null;
  onRepoSearchChange: (value: string) => void;
  onSelectRepo: (value: string) => void;
  onRefreshRepos: () => void;
  onContinueFromRepo: () => void;
};

export function OnboardingRepoCard({
  repos,
  repoSearch,
  selectedRepo,
  isRefreshingRepos,
  githubAppInstallUrl,
  onRepoSearchChange,
  onSelectRepo,
  onRefreshRepos,
  onContinueFromRepo,
}: Props): React.JSX.Element {
  const filteredRepos = React.useMemo(() => {
    const query = repoSearch.trim().toLowerCase();
    if (!query) return repos;
    return repos.filter((repo) => repo.toLowerCase().includes(query));
  }, [repoSearch, repos]);

  return (
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
              You may need to grant access to your repositories during setup. After granting access in
              GitHub, return to this tab and refresh.
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25}>
              {githubAppInstallUrl ? (
                <Button
                  component="a"
                  href={githubAppInstallUrl}
                  target="_blank"
                  rel="noreferrer"
                  variant="contained"
                >
                  Install GitHub App
                </Button>
              ) : null}
              <Button variant="outlined" onClick={onRefreshRepos} disabled={isRefreshingRepos}>
                {isRefreshingRepos ? 'Refreshing…' : "I've granted access — refresh"}
              </Button>
              <Button
                component="a"
                href="https://github.com/settings/installations"
                target="_blank"
                rel="noreferrer"
                variant="outlined"
              >
                Manage access in GitHub
              </Button>
            </Stack>
          </Stack>
        </Alert>
      ) : (
        <Stack spacing={1.25}>
          <List
            dense
            sx={{
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 1,
              maxHeight: 280,
              overflowY: 'auto',
            }}
          >
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

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25}>
            <Button variant="outlined" onClick={onRefreshRepos} disabled={isRefreshingRepos}>
              {isRefreshingRepos ? 'Refreshing…' : 'Refresh repositories'}
            </Button>
            <Button
              component="a"
              href="https://github.com/settings/installations"
              target="_blank"
              rel="noreferrer"
              variant="text"
            >
              Add or remove repository access in GitHub
            </Button>
          </Stack>
        </Stack>
      )}

      <Button variant="contained" size="large" disabled={!selectedRepo} onClick={onContinueFromRepo}>
        Continue
      </Button>
    </Stack>
  );
}
