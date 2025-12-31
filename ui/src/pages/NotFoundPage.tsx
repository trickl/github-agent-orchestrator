import React from 'react';
import { Button, Stack, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

export function NotFoundPage(): React.JSX.Element {
  return (
    <Stack spacing={2}>
      <Typography variant="h4">Not found</Typography>
      <Typography variant="body2" color="text.secondary">
        The page you requested doesn’t exist.
      </Typography>
      <Button component={RouterLink} to="/" variant="contained">
        Go to overview
      </Button>
    </Stack>
  );
}
