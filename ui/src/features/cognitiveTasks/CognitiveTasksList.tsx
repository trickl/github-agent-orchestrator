import React from 'react';
import {
  Box,
  Button,
  Chip,
  IconButton,
  Link,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import EditIcon from '@mui/icons-material/Edit';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import type { CognitiveTask } from './cognitiveTaskTypes';
import { Timestamp } from '../../components/Timestamp';
import { humanTriggerSummary } from '../../lib/format';

export type CognitiveTasksListFilters = {
  search: string;
  category: 'all' | CognitiveTask['category'];
};

type ReadOnlyProps = {
  readOnly: true;
  tasks: CognitiveTask[];
  filters: CognitiveTasksListFilters;
  onFiltersChange: (next: CognitiveTasksListFilters) => void;
};

type EditableProps = {
  readOnly?: false;
  tasks: CognitiveTask[];
  filters: CognitiveTasksListFilters;
  onFiltersChange: (next: CognitiveTasksListFilters) => void;
  onCreate: () => void;
  onEdit: (task: CognitiveTask) => void;
  onDuplicate: (task: CognitiveTask) => void;
  onDelete: (task: CognitiveTask) => void;
  onRun: (task: CognitiveTask) => void;
  onToggleEnabled: (task: CognitiveTask, enabled: boolean) => void;
};

export function CognitiveTasksList(props: ReadOnlyProps | EditableProps): React.JSX.Element {
  const { filters } = props;

  return (
    <Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} gap={2} alignItems={{ sm: 'center' }} mb={2}>
        <TextField
          label="Search"
          value={filters.search}
          onChange={(e) => props.onFiltersChange({ ...filters, search: e.target.value })}
          size="small"
        />
        <TextField
          label="Category"
          select
          value={filters.category}
          onChange={(e) =>
            props.onFiltersChange({
              ...filters,
              category: String(e.target.value) as CognitiveTasksListFilters['category'],
            })
          }
          size="small"
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="all">all</MenuItem>
          <MenuItem value="review">review</MenuItem>
          <MenuItem value="gap">gap</MenuItem>
          <MenuItem value="maintenance">maintenance</MenuItem>
          <MenuItem value="system">system</MenuItem>
        </TextField>

        <Box flex={1} />

        {props.readOnly === true ? null : (
          <Button startIcon={<AddIcon />} variant="contained" onClick={props.onCreate}>
            New task
          </Button>
        )}
      </Stack>

      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Name</TableCell>
            <TableCell>Category</TableCell>
            <TableCell>Enabled</TableCell>
            <TableCell>Trigger</TableCell>
            <TableCell>Target folder</TableCell>
            <TableCell>Last run</TableCell>
            <TableCell>Next eligible</TableCell>
            {props.readOnly === true ? null : <TableCell align="right">Actions</TableCell>}
          </TableRow>
        </TableHead>
        <TableBody>
          {props.tasks.map((t) => (
            <TableRow key={t.id} hover>
              <TableCell>
                <Typography variant="body2" fontWeight={600}>
                  {t.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {t.id}
                </Typography>
              </TableCell>
              <TableCell>
                <Chip label={t.category} variant="outlined" />
              </TableCell>
              <TableCell>
                {props.readOnly === true ? (
                  <Typography variant="body2" color="text.secondary">
                    {t.enabled ? 'Enabled' : 'Disabled'}
                  </Typography>
                ) : (
                  <Link
                    component="button"
                    onClick={() => props.onToggleEnabled(t, !t.enabled)}
                    underline="hover"
                  >
                    {t.enabled ? 'Enabled' : 'Disabled'}
                  </Link>
                )}
              </TableCell>
              <TableCell>{humanTriggerSummary(t.trigger)}</TableCell>
              <TableCell>
                <Typography variant="body2" color="text.secondary">
                  {t.targetFolder}
                </Typography>
              </TableCell>
              <TableCell>
                <Timestamp iso={t.lastRunIso} />
              </TableCell>
              <TableCell>
                <Timestamp iso={t.nextEligibleIso} />
              </TableCell>
              {props.readOnly === true ? null : (
                <TableCell align="right">
                  <Stack direction="row" justifyContent="flex-end" gap={0.5}>
                    <Tooltip title="Run now" arrow>
                      <span>
                        <IconButton
                          aria-label="Run now"
                          onClick={() => props.onRun(t)}
                          size="small"
                        >
                          <PlayArrowIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title={t.editable ? 'Edit' : 'View (read-only)'} arrow>
                      <IconButton aria-label="Edit" onClick={() => props.onEdit(t)} size="small">
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Duplicate" arrow>
                      <IconButton
                        aria-label="Duplicate"
                        onClick={() => props.onDuplicate(t)}
                        size="small"
                      >
                        <ContentCopyIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete" arrow>
                      <span>
                        <IconButton
                          aria-label="Delete"
                          onClick={() => props.onDelete(t)}
                          size="small"
                          disabled={!t.editable}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </Stack>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
