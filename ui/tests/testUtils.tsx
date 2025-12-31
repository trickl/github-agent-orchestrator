import React from 'react';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import { render, type RenderOptions } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { createAppTheme } from '../src/app/theme';

const theme = createAppTheme('light');

export function renderWithAppProviders(
  ui: React.ReactElement,
  opts?: { route?: string } & Omit<RenderOptions, 'wrapper'>
) {
  const route = opts?.route ?? '/';
  return render(ui, {
    ...opts,
    wrapper: ({ children }) => (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
      </ThemeProvider>
    ),
  });
}
