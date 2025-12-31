import React from 'react';
import { Typography } from '@mui/material';
import { apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import { useApiResource } from '../lib/useApiResource';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { EmptyState } from '../components/EmptyState';
import type { TimelineEvent } from '../features/timeline/timelineTypes';
import { TimelineFeed } from '../features/timeline/TimelineFeed';

export function TimelinePage(): React.JSX.Element {
  const res = useApiResource(
    () => apiFetch<TimelineEvent[]>(endpoints.timeline(200)),
    []
  );

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Timeline
      </Typography>

      {res.loading ? <LoadingState /> : null}
      {res.error ? <ErrorState message={res.error} onRetry={res.reload} /> : null}

      {!res.loading && !res.error && res.data ? (
        res.data.length === 0 ? (
          <EmptyState title="No timeline events" description="Nothing has happened yet." />
        ) : (
          <TimelineFeed events={res.data} />
        )
      ) : null}
    </div>
  );
}
