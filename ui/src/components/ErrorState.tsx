import React from 'react';
import { Alert, AlertTitle, Box, Button } from '@mui/material';

export function ErrorState(props: {
  title?: string;
  message: string;
  onRetry?: () => void;
}): React.JSX.Element {
  return (
    <Box py={2}>
      <Alert severity="error">
        <AlertTitle>{props.title ?? 'Something went wrong'}</AlertTitle>
        {props.message}
        {props.onRetry ? (
          <Box mt={2}>
            <Button variant="outlined" onClick={props.onRetry}>
              Retry
            </Button>
          </Box>
        ) : null}
      </Alert>
    </Box>
  );
}
