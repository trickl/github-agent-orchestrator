import React from 'react';
import { Box, Tab, Tabs, Typography } from '@mui/material';
import { apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import { useApiResource } from '../lib/useApiResource';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import type { PlanningDoc } from '../features/planning/planningTypes';
import { DocViewer } from '../features/planning/DocViewer';

type TabKey = 'goal' | 'capabilities';

export function PlanningDocsPage(): React.JSX.Element {
  const [tab, setTab] = React.useState<TabKey>('goal');

  const goal = useApiResource(() => apiFetch<PlanningDoc>(endpoints.docGoal()), []);
  const caps = useApiResource(() => apiFetch<PlanningDoc>(endpoints.docCapabilities()), []);

  const selected = tab === 'goal' ? goal : caps;

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Planning Docs
      </Typography>

      <Tabs value={tab} onChange={(_, v) => setTab(v as TabKey)} sx={{ mb: 2 }}>
        <Tab value="goal" label="Goal" />
        <Tab value="capabilities" label="Capabilities" />
      </Tabs>

      {selected.loading ? <LoadingState /> : null}
      {selected.error ? (
        <ErrorState
          message={selected.error}
          onRetry={() => {
            goal.reload();
            caps.reload();
          }}
        />
      ) : null}

      {!selected.loading && !selected.error && selected.data ? (
        <Box>
          <DocViewer doc={selected.data} />
        </Box>
      ) : null}
    </div>
  );
}
