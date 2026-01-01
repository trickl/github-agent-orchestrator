import React from 'react';
import { Box, Button, Card, CardContent, Stack, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import { apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import { useApiResource } from '../lib/useApiResource';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { StatusChip } from '../components/StatusChip';
import { Timestamp } from '../components/Timestamp';
import type { Issue } from '../features/issues/issueTypes';

type Overview = {
  activeIssueId: string | null;
  openIssueCount: number;
  lastEventIso: string;
};

type ActiveResponse = {
  activeIssue: Issue | null;
  lastAction: null | { tsIso: string; summary: string };
};

export function OverviewPage(): React.JSX.Element {
  const overview = useApiResource(() => apiFetch<Overview>(endpoints.overview()), []);
  const active = useApiResource(() => apiFetch<ActiveResponse>(endpoints.active()), []);

  const anyLoading = overview.loading || active.loading;
  const anyError = overview.error || active.error;

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Overview
      </Typography>

      {anyLoading ? <LoadingState /> : null}
      {anyError ? (
        <ErrorState
          message={anyError}
          onRetry={() => {
            overview.reload();
            active.reload();
          }}
        />
      ) : null}

      {!anyLoading && !anyError && overview.data && active.data ? (
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <Card variant="outlined" sx={{ flex: 2 }}>
              <CardContent>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Active issue
                </Typography>
                {active.data.activeIssue ? (
                  <>
                    <Typography variant="h6" gutterBottom>
                      {active.data.activeIssue.title}
                    </Typography>
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                      <StatusChip status={active.data.activeIssue.status} />
                      <Typography variant="body2" color="text.secondary">
                        Age: {Math.max(0, Math.round(active.data.activeIssue.ageSeconds / 60))}m
                      </Typography>
                    </Stack>
                  </>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    None
                  </Typography>
                )}
              </CardContent>
            </Card>

            <Card variant="outlined" sx={{ flex: 1 }}>
              <CardContent>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Open issues
                </Typography>
                <Typography variant="h4">{overview.data.openIssueCount}</Typography>
              </CardContent>
            </Card>

            <Card variant="outlined" sx={{ flex: 1 }}>
              <CardContent>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Last event
                </Typography>
                <Typography variant="body1">
                  <Timestamp iso={overview.data.lastEventIso} />
                </Typography>
              </CardContent>
            </Card>
          </Stack>

          <Box>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              Quick links
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap">
              <Button component={RouterLink} to="/timeline" variant="outlined">
                Timeline
              </Button>
              <Button component={RouterLink} to="/cognitive-tasks" variant="outlined">
                Cognitive Tasks
              </Button>
              <Button component={RouterLink} to="/docs" variant="outlined">
                Docs
              </Button>
            </Stack>
          </Box>
        </Stack>
      ) : null}
    </div>
  );
}
