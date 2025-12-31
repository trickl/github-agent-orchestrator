import React from 'react';
import type { PaletteMode } from '@mui/material';

export type ColorModeContextValue = {
  mode: PaletteMode;
  setMode: (mode: PaletteMode) => void;
  toggle: () => void;
};

export const ColorModeContext = React.createContext<ColorModeContextValue | null>(null);
