import React from 'react';
import { CssBaseline } from '@mui/material';
import type { PaletteMode } from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import { ColorModeContext } from './colorModeContext';
import { createAppTheme } from './theme';

import type { ColorModeContextValue } from './colorModeContext';

const STORAGE_KEY = 'gao.colorMode';

function getInitialMode(): PaletteMode {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw === 'light' || raw === 'dark') return raw;
  const prefersDark =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
  return prefersDark ? 'dark' : 'light';
}

export function ColorModeProvider({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  const [mode, setMode] = React.useState<PaletteMode>(() => getInitialMode());

  React.useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, mode);
  }, [mode]);

  const value = React.useMemo<ColorModeContextValue>(
    () => ({
      mode,
      setMode,
      toggle: () => setMode((m) => (m === 'light' ? 'dark' : 'light')),
    }),
    [mode]
  );

  const theme = React.useMemo(() => createAppTheme(mode), [mode]);

  return (
    <ColorModeContext.Provider value={value}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ColorModeContext.Provider>
  );
}
