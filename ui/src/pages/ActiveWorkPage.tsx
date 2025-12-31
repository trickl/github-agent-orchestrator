import React from 'react';
import { Box, Button, Card, CardContent, Link, Stack, Typography } from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import { useApiResource } from '../lib/useApiResource';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { EmptyState } from '../components/EmptyState';
import { StatusChip } from '../components/StatusChip';
import { TypeChip } from '../components/TypeChip';
import { Timestamp } from '../components/Timestamp';
import type { Issue } from '../features/issues/issueTypes';

type ActiveResponse = {
  activeIssue: Issue | null;
  lastAction: null | { tsIso: string; summary: string };
};

export function ActiveWorkPage(): React.JSX.Element {
  const res = useApiResource(() => apiFetch<ActiveResponse>(endpoints.active()), []);

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Active Work
      </Typography>

      {res.loading ? <LoadingState /> : null}
      {res.error ? <ErrorState message={res.error} onRetry={res.reload} /> : null}

      {!res.loading && !res.error && res.data ? (
        res.data.activeIssue ? (
          <Card variant="outlined">
            <CardContent>
              <Stack spacing={1.25}>
                <Typography variant="h6">{res.data.activeIssue.title}</Typography>

                <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
                  <StatusChip status={res.data.activeIssue.status} />
                  <TypeChip typePath={res.data.activeIssue.typePath} />
                  <Typography variant="body2" color="text.secondary">
                    Age: {Math.max(0, Math.round(res.data.activeIssue.ageSeconds / 60))}m
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Updated: <Timestamp iso={res.data.activeIssue.lastUpdatedIso} />
                  </Typography>
                </Stack>

                <Box>
                  {res.data.activeIssue.githubIssueUrl ? (
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<OpenInNewIcon />}
                      component={Link}
                      href={res.data.activeIssue.githubIssueUrl}
                      target="_blank"
                      rel="noreferrer"
                      sx={{ mr: 1 }}
                    >
                      Open issue
                    </Button>
                  ) : null}
                  {res.data.activeIssue.prUrl ? (
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<OpenInNewIcon />}
                      component={Link}
                      href={res.data.activeIssue.prUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open PR
                    </Button>
                  ) : null}
                </Box>

                <Box mt={1}>
                  <Typography variant="subtitle2">Last action</Typography>
                  {res.data.lastAction ? (
                    <Typography variant="body2" color="text.secondary">
                      <Timestamp iso={res.data.lastAction.tsIso} /> — {res.data.lastAction.summary}
                    </Typography>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      —
                    </Typography>
                  )}
                </Box>
              </Stack>
            </CardContent>
          </Card>
        ) : (
          <EmptyState title="No active issue" description="The orchestrator is idle." />
        )
      ) : null}
    </div>
  );
}
