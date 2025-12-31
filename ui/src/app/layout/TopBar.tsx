import React from 'react';
import {
  AppBar,
  Box,
  Chip,
  Toolbar,
  Typography,
  CircularProgress,
  Tooltip,
} from '@mui/material';
import { apiFetch } from '../../lib/apiClient';
import { endpoints } from '../../lib/endpoints';

type Health = { ok: boolean; version: string; repoName: string };

export function TopBar(): React.JSX.Element {
  const [health, setHealth] = React.useState<Health | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [down, setDown] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      setLoading(true);
      try {
        const h = await apiFetch<Health>(endpoints.health());
        if (cancelled) return;
        setHealth(h);
        setDown(!h.ok);
      } catch {
        if (cancelled) return;
        setHealth(null);
        setDown(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    const t = window.setInterval(() => void load(), 10_000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  return (
    <AppBar position="fixed" elevation={1} color="default">
      <Toolbar>
        <Typography variant="h6" sx={{ flexGrow: 1 }}>
          Orchestrator Dashboard
        </Typography>

        <Box display="flex" alignItems="center" gap={1.5}>
          {health?.repoName ? (
            <Typography variant="body2" color="text.secondary">
              {health.repoName}
            </Typography>
          ) : null}

          {loading ? <CircularProgress size={18} /> : null}

          <Tooltip title={down ? 'Backend unreachable' : 'Backend connected'} arrow>
            <Chip
              label={down ? 'Offline' : 'Online'}
              color={down ? 'error' : 'success'}
              variant="outlined"
              size="small"
            />
          </Tooltip>
        </Box>
      </Toolbar>
    </AppBar>
  );
}
