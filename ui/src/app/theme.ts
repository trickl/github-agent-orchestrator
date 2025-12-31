import type { PaletteMode } from '@mui/material';
import { createTheme } from '@mui/material/styles';
import type { Theme } from '@mui/material/styles';

export function createAppTheme(mode: PaletteMode): Theme {
  return createTheme({
    palette: {
      mode,
    },
    typography: {
      fontFamily:
        'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, "Apple Color Emoji", "Segoe UI Emoji"',
    },
    components: {
      MuiChip: {
        defaultProps: {
          size: 'small',
        },
      },
    },
  });
}
