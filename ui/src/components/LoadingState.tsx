import React from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';

export function LoadingState(props: { label?: string }): React.JSX.Element {
  return (
    <Box display="flex" alignItems="center" gap={2} py={2}>
      <CircularProgress size={22} />
      <Typography variant="body2" color="text.secondary">
        {props.label ?? 'Loading…'}
      </Typography>
    </Box>
  );
}
