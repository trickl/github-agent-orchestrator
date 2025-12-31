import React from 'react';
import {
  Box,
  Link,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import type { Theme } from '@mui/material/styles';
import type { Issue } from './issueTypes';
import { StatusChip } from '../../components/StatusChip';
import { TypeChip } from '../../components/TypeChip';
import { Timestamp } from '../../components/Timestamp';

export function IssueTable(props: { issues: Issue[] }): React.JSX.Element {
  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Title</TableCell>
            <TableCell>Type</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Age</TableCell>
            <TableCell>Updated</TableCell>
            <TableCell>Links</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {props.issues.map((i) => (
            <TableRow
              key={i.id}
              hover
              data-testid="issue-row"
              data-issue-id={i.id}
              data-active={i.isActive ? 'true' : 'false'}
              sx={
                i.isActive
                  ? {
                      backgroundColor: (theme: Theme) => theme.palette.action.selected,
                      '&:hover': {
                        backgroundColor: (theme: Theme) => theme.palette.action.selected,
                      },
                    }
                  : undefined
              }
            >
              <TableCell>
                <Typography variant="body2" fontWeight={600}>
                  {i.title || '—'}
                </Typography>
              </TableCell>
              <TableCell>
                <TypeChip typePath={i.typePath} />
              </TableCell>
              <TableCell>
                <StatusChip status={i.status} />
              </TableCell>
              <TableCell>
                <Typography variant="body2" color="text.secondary">
                  {Math.max(0, Math.round(i.ageSeconds / 60))}m
                </Typography>
              </TableCell>
              <TableCell>
                <Timestamp iso={i.lastUpdatedIso} />
              </TableCell>
              <TableCell>
                <Box display="flex" gap={1.5} flexWrap="wrap">
                  {i.githubIssueUrl ? (
                    <Link href={i.githubIssueUrl} target="_blank" rel="noreferrer">
                      GitHub Issue
                    </Link>
                  ) : null}
                  {i.prUrl ? (
                    <Link href={i.prUrl} target="_blank" rel="noreferrer">
                      PR
                    </Link>
                  ) : null}
                </Box>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
