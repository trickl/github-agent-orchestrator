import React from 'react';
import { Alert, Box, Typography } from '@mui/material';
import { apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import { useApiResource } from '../lib/useApiResource';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { EmptyState } from '../components/EmptyState';
import type { CognitiveTask } from '../features/cognitiveTasks/cognitiveTaskTypes';
import {
  CognitiveTasksList,
  type CognitiveTasksListFilters,
} from '../features/cognitiveTasks/CognitiveTasksList';

export function CognitiveTasksPage(): React.JSX.Element {
  const tasksRes = useApiResource(() => apiFetch<CognitiveTask[]>(endpoints.cognitiveTasks()), []);

  const [filters, setFilters] = React.useState<CognitiveTasksListFilters>({
    search: '',
    category: 'all',
  });

  const tasks = React.useMemo(() => {
    const all = tasksRes.data ?? [];
    return all.filter((t) => {
      if (filters.category !== 'all' && t.category !== filters.category) return false;
      if (filters.search && !t.name.toLowerCase().includes(filters.search.toLowerCase())) return false;
      return true;
    });
  }, [filters.category, filters.search, tasksRes.data]);

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Cognitive Tasks
      </Typography>

      <Alert severity="info" sx={{ mb: 2 }}>
        Cognitive Tasks are read from <code>planning/issue_templates/</code> in the target GitHub repo.
        This dashboard view is intentionally read-only.
      </Alert>

      {tasksRes.loading ? <LoadingState /> : null}
      {tasksRes.error ? <ErrorState message={tasksRes.error} onRetry={tasksRes.reload} /> : null}

      {!tasksRes.loading && !tasksRes.error ? (
        tasksRes.data && tasksRes.data.length === 0 ? (
          <EmptyState title="No cognitive tasks" description="Create your first cognitive task." />
        ) : (
          <Box>
            <CognitiveTasksList
              tasks={tasks}
              filters={filters}
              onFiltersChange={setFilters}
              readOnly
            />
          </Box>
        )
      ) : null}
    </div>
  );
}
