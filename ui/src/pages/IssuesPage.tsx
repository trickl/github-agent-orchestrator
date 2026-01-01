import React from 'react';
import {
  Box,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import { useApiResource } from '../lib/useApiResource';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { EmptyState } from '../components/EmptyState';
import type { Issue } from '../features/issues/issueTypes';
import { IssueTable } from '../features/issues/IssueTable';

type StatusFilter = 'open' | 'all';

export function IssuesPage(): React.JSX.Element {
  const [status, setStatus] = React.useState<StatusFilter>('open');
  const [typePath, setTypePath] = React.useState('');
  const [search, setSearch] = React.useState('');

  const res = useApiResource(() => apiFetch<Issue[]>(endpoints.issues(status)), [status]);

  const issues = React.useMemo(() => res.data ?? [], [res.data]);

  const typeOptions = React.useMemo(() => {
    const set = new Set<string>();
    for (const i of issues) {
      if (i.typePath) set.add(i.typePath);
    }
    return Array.from(set).sort();
  }, [issues]);

  const filtered = React.useMemo(() => {
    return issues.filter((i) => {
      if (typePath && i.typePath !== typePath) return false;
      if (search && !i.title.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [issues, search, typePath]);

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Issues
      </Typography>

      <Stack direction={{ xs: 'column', sm: 'row' }} gap={2} mb={2}>
        <TextField
          select
          label="Status"
          size="small"
          value={status}
          onChange={(e) => setStatus(String(e.target.value) as StatusFilter)}
          sx={{ minWidth: 140 }}
        >
          <MenuItem value="open">open</MenuItem>
          <MenuItem value="all">all</MenuItem>
        </TextField>

        <TextField
          select
          label="Type"
          size="small"
          value={typePath}
          onChange={(e) => setTypePath(String(e.target.value))}
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">all</MenuItem>
          {typeOptions.map((t) => (
            <MenuItem key={t} value={t}>
              {t}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          label="Search title"
          size="small"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          fullWidth
        />
      </Stack>

      {res.loading ? <LoadingState /> : null}
      {res.error ? <ErrorState message={res.error} onRetry={res.reload} /> : null}

      {!res.loading && !res.error ? (
        filtered.length === 0 ? (
          <EmptyState title="No issues" description="Try changing filters." />
        ) : (
          <Box>
            <IssueTable issues={filtered} />
          </Box>
        )
      ) : null}
    </div>
  );
}
