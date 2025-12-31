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
import type { GenerationRule } from './ruleTypes';
import { Timestamp } from '../../components/Timestamp';
import { humanTriggerSummary } from '../../lib/format';

export type RulesListFilters = {
  search: string;
  category: 'all' | GenerationRule['category'];
};

export function RulesList(props: {
  rules: GenerationRule[];
  filters: RulesListFilters;
  onFiltersChange: (next: RulesListFilters) => void;
  onCreate: () => void;
  onEdit: (rule: GenerationRule) => void;
  onDuplicate: (rule: GenerationRule) => void;
  onDelete: (rule: GenerationRule) => void;
  onRun: (rule: GenerationRule) => void;
  onToggleEnabled: (rule: GenerationRule, enabled: boolean) => void;
}): React.JSX.Element {
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
              category: String(e.target.value) as RulesListFilters['category'],
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

        <Button startIcon={<AddIcon />} variant="contained" onClick={props.onCreate}>
          New rule
        </Button>
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
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {props.rules.map((r) => (
            <TableRow key={r.id} hover>
              <TableCell>
                <Typography variant="body2" fontWeight={600}>
                  {r.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {r.id}
                </Typography>
              </TableCell>
              <TableCell>
                <Chip label={r.category} variant="outlined" />
              </TableCell>
              <TableCell>
                <Link
                  component="button"
                  onClick={() => props.onToggleEnabled(r, !r.enabled)}
                  underline="hover"
                >
                  {r.enabled ? 'Enabled' : 'Disabled'}
                </Link>
              </TableCell>
              <TableCell>{humanTriggerSummary(r.trigger)}</TableCell>
              <TableCell>
                <Typography variant="body2" color="text.secondary">
                  {r.targetFolder}
                </Typography>
              </TableCell>
              <TableCell>
                <Timestamp iso={r.lastRunIso} />
              </TableCell>
              <TableCell>
                <Timestamp iso={r.nextEligibleIso} />
              </TableCell>
              <TableCell align="right">
                <Stack direction="row" justifyContent="flex-end" gap={0.5}>
                  <Tooltip title="Run now" arrow>
                    <span>
                      <IconButton aria-label="Run now" onClick={() => props.onRun(r)} size="small">
                        <PlayArrowIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                  <Tooltip title={r.editable ? 'Edit' : 'View (read-only)'} arrow>
                    <IconButton aria-label="Edit" onClick={() => props.onEdit(r)} size="small">
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Duplicate" arrow>
                    <IconButton aria-label="Duplicate" onClick={() => props.onDuplicate(r)} size="small">
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Delete" arrow>
                    <span>
                      <IconButton
                        aria-label="Delete"
                        onClick={() => props.onDelete(r)}
                        size="small"
                        disabled={!r.editable}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
