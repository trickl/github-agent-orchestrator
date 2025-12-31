import React from 'react';
import { Chip } from '@mui/material';

export function TypeChip(props: { typePath?: string | null }): React.JSX.Element {
  const label = props.typePath && props.typePath.trim().length > 0 ? props.typePath : 'unknown';
  return <Chip variant="outlined" label={label} />;
}
