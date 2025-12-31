import React from 'react';
import { Box, Button, Card, CardContent, Stack, Typography } from '@mui/material';
import ReactMarkdown from 'react-markdown';
import type { PlanningDoc } from './planningTypes';
import { Timestamp } from '../../components/Timestamp';

export function DocViewer(props: { doc: PlanningDoc }): React.JSX.Element {
  const [copied, setCopied] = React.useState(false);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(props.doc.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction={{ xs: 'column', sm: 'row' }} gap={2} justifyContent="space-between">
          <Box>
            <Typography variant="h6">{props.doc.title}</Typography>
            <Typography variant="body2" color="text.secondary">
              {props.doc.path}
            </Typography>
            <Box mt={0.5}>
              <Timestamp iso={props.doc.lastUpdatedIso} variant="caption" />
            </Box>
          </Box>

          <Box display="flex" alignItems="center" gap={1}>
            <Button onClick={() => void copy()} variant="outlined">
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </Box>
        </Stack>

        <Box mt={2} sx={{ '& pre': { overflowX: 'auto' } }}>
          <ReactMarkdown>{props.doc.content}</ReactMarkdown>
        </Box>
      </CardContent>
    </Card>
  );
}
