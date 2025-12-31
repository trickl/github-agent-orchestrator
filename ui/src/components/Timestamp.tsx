import React from 'react';
import { Tooltip, Typography } from '@mui/material';
import { formatIso, formatRelativeFromNow } from '../lib/date';

export function Timestamp(props: {
  iso: string | null | undefined;
  variant?: 'body2' | 'caption';
}): React.JSX.Element {
  const label = formatRelativeFromNow(props.iso);
  const full = formatIso(props.iso);
  return (
    <Tooltip title={full} arrow>
      <Typography component="span" variant={props.variant ?? 'body2'} color="text.secondary">
        {label}
      </Typography>
    </Tooltip>
  );
}
