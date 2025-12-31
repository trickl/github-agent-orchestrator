import React from 'react';
import { Box, Typography } from '@mui/material';

export function EmptyState(props: {
  title: string;
  description?: string;
}): React.JSX.Element {
  return (
    <Box py={4}>
      <Typography variant="h6" gutterBottom>
        {props.title}
      </Typography>
      {props.description ? (
        <Typography variant="body2" color="text.secondary">
          {props.description}
        </Typography>
      ) : null}
    </Box>
  );
}
