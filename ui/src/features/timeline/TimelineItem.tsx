import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Chip,
  Link,
  Stack,
  Typography,
} from '@mui/material';
import BoltIcon from '@mui/icons-material/Bolt';
import DescriptionIcon from '@mui/icons-material/Description';
import GitHubIcon from '@mui/icons-material/GitHub';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import MergeIcon from '@mui/icons-material/Merge';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import NotesIcon from '@mui/icons-material/Notes';
import { Timestamp } from '../../components/Timestamp';
import { TypeChip } from '../../components/TypeChip';
import type { TimelineEvent, TimelineEventKind } from './timelineTypes';

function iconFor(kind: TimelineEventKind): React.JSX.Element {
  switch (kind) {
    case 'COGNITIVE_TASK_TRIGGERED':
      return <BoltIcon fontSize="small" />;
    case 'ISSUE_FILE_CREATED':
      return <DescriptionIcon fontSize="small" />;
    case 'GITHUB_ISSUE_OPENED':
    case 'COPILOT_ASSIGNED':
    case 'PR_OPENED':
      return <GitHubIcon fontSize="small" />;
    case 'PR_MERGED':
      return <MergeIcon fontSize="small" />;
    case 'ISSUE_CLOSED':
      return <PlayArrowIcon fontSize="small" />;
    case 'RUN_FAILED':
      return <ErrorOutlineIcon fontSize="small" />;
    case 'NOTE':
    default:
      return <NotesIcon fontSize="small" />;
  }
}

export function TimelineItemView(props: { event: TimelineEvent }): React.JSX.Element {
  const e = props.event;

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" alignItems="flex-start" spacing={2}>
          <Box mt={0.2}>{iconFor(e.kind)}</Box>
          <Box flex={1}>
            <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap">
              <Timestamp iso={e.tsIso} />
              <Chip size="small" label={e.kind} variant="outlined" />
              <TypeChip typePath={e.typePath} />
            </Stack>

            <Typography variant="body1" sx={{ mt: 1 }}>
              {e.summary}
            </Typography>

            {e.details ? (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, whiteSpace: 'pre-wrap' }}>
                {e.details}
              </Typography>
            ) : null}

            {e.links?.length ? (
              <Stack direction="row" spacing={1.5} sx={{ mt: 1 }} flexWrap="wrap">
                {e.links.map((l) => (
                  <Link key={l.url} href={l.url} target="_blank" rel="noreferrer">
                    {l.label}
                  </Link>
                ))}
              </Stack>
            ) : null}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
