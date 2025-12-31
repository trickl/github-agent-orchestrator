import React from 'react';
import { Chip } from '@mui/material';
import type { IssueStatus } from '../features/issues/issueTypes';

function colorFor(status: string):
  | 'default'
  | 'primary'
  | 'secondary'
  | 'success'
  | 'warning'
  | 'error' {
  switch (status as IssueStatus) {
    case 'PENDING':
      return 'default';
    case 'OPEN':
      return 'primary';
    case 'ASSIGNED':
      return 'secondary';
    case 'PR_OPEN':
      return 'warning';
    case 'MERGED':
    case 'CLOSED':
      return 'success';
    case 'FAILED':
    case 'BLOCKED':
      return 'error';
    default:
      return 'default';
  }
}

export function StatusChip(props: { status: string | null | undefined }): React.JSX.Element {
  const label = props.status && props.status.trim().length > 0 ? props.status : 'UNKNOWN';
  return <Chip label={label} color={colorFor(label)} />;
}
