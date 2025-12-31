import React from 'react';
import { Stack } from '@mui/material';
import type { TimelineEvent } from './timelineTypes';
import { TimelineItemView } from './TimelineItem';

export function TimelineFeed(props: { events: TimelineEvent[] }): React.JSX.Element {
  return (
    <Stack spacing={2}>
      {props.events.map((e) => (
        <TimelineItemView key={e.id} event={e} />
      ))}
    </Stack>
  );
}
