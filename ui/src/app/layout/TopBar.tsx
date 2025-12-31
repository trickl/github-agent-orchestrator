import React from 'react';
import {
  AppBar,
  Box,
  Chip,
  IconButton,
  Toolbar,
  Typography,
  CircularProgress,
  Tooltip,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import MenuIcon from '@mui/icons-material/Menu';
import MenuOpenIcon from '@mui/icons-material/MenuOpen';
import { LightDarkToggle } from 'react-light-dark-toggle';
import { apiFetch } from '../../lib/apiClient';
import { endpoints } from '../../lib/endpoints';
import { ColorModeContext } from '../colorModeContext';

type Health = { ok: boolean; version: string; repoName: string };

type TopBarProps = {
  sidebarWidth: number;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
};

export function TopBar({
  sidebarWidth,
  sidebarCollapsed,
  onToggleSidebar,
}: TopBarProps): React.JSX.Element {
  const theme = useTheme();
  const colorMode = React.useContext(ColorModeContext);
  if (!colorMode) {
    throw new Error('TopBar must be rendered within ColorModeProvider');
  }

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
    <AppBar
      position="fixed"
      elevation={1}
      color="default"
      sx={{
        width: { sm: `calc(100% - ${sidebarWidth}px)` },
        ml: { sm: `${sidebarWidth}px` },
      }}
    >
      <Toolbar>
        <IconButton
          color="inherit"
          edge="start"
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          onClick={onToggleSidebar}
          sx={{ mr: 1 }}
        >
          {sidebarCollapsed ? <MenuIcon /> : <MenuOpenIcon />}
        </IconButton>

        <Typography variant="h6" sx={{ flexGrow: 1 }}>
          GitHub Agent Orchestrator
        </Typography>

        <Box display="flex" alignItems="center" gap={1.5}>
          <LightDarkToggle
            aria-label="Toggle light/dark mode"
            isLight={colorMode.mode === 'light'}
            onToggle={(isLight: boolean) => colorMode.setMode(isLight ? 'light' : 'dark')}
            lightBorderColor={theme.palette.divider}
            darkBorderColor={theme.palette.divider}
            lightBackgroundColor={theme.palette.background.paper}
            darkBackgroundColor={theme.palette.background.paper}
          />

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
