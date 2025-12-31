import React from 'react';
import {
  Box,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import type { GenerationRule, TriggerKind } from './ruleTypes';

export type RuleDraft = Omit<GenerationRule, 'id'> & { id?: string };

function ensureTriggerShape(trigger: RuleDraft['trigger']): RuleDraft['trigger'] {
  if (trigger.kind === 'AFTER_N_ISSUES_COMPLETED') {
    return {
      kind: 'AFTER_N_ISSUES_COMPLETED',
      nIssuesCompleted: trigger.nIssuesCompleted ?? 1,
    };
  }
  return { kind: 'MANUAL_ONLY' };
}

export function RuleForm(props: {
  value: RuleDraft;
  onChange: (next: RuleDraft) => void;
  readOnly: boolean;
}): React.JSX.Element {
  const v = props.value;
  const trigger = ensureTriggerShape(v.trigger);

  function set<K extends keyof RuleDraft>(key: K, val: RuleDraft[K]): void {
    props.onChange({ ...v, [key]: val });
  }

  function setTriggerKind(kind: TriggerKind): void {
    if (kind === 'MANUAL_ONLY') {
      set('trigger', { kind: 'MANUAL_ONLY' });
      return;
    }
    set('trigger', { kind: 'AFTER_N_ISSUES_COMPLETED', nIssuesCompleted: trigger.nIssuesCompleted ?? 1 });
  }

  return (
    <Box display="flex" flexDirection="column" gap={2}>
      <TextField
        label="Name"
        value={v.name}
        onChange={(e) => set('name', e.target.value)}
        disabled={props.readOnly}
        fullWidth
      />

      <FormControl fullWidth disabled={props.readOnly}>
        <InputLabel id="rule-category">Category</InputLabel>
        <Select
          labelId="rule-category"
          label="Category"
          value={v.category}
          onChange={(e) => set('category', String(e.target.value) as GenerationRule['category'])}
        >
          <MenuItem value="review">review</MenuItem>
          <MenuItem value="gap">gap</MenuItem>
          <MenuItem value="maintenance">maintenance</MenuItem>
          <MenuItem value="system">system</MenuItem>
        </Select>
      </FormControl>

      <FormControlLabel
        control={
          <Switch
            checked={v.enabled}
            onChange={(e) => set('enabled', e.target.checked)}
            disabled={props.readOnly}
          />
        }
        label="Enabled"
      />

      <TextField
        label="Target folder"
        helperText="Folder path under planning/issue_queue/pending (opaque label)"
        value={v.targetFolder}
        onChange={(e) => set('targetFolder', e.target.value)}
        disabled={props.readOnly}
        fullWidth
      />

      <FormControl fullWidth disabled={props.readOnly}>
        <InputLabel id="rule-trigger-kind">Trigger</InputLabel>
        <Select
          labelId="rule-trigger-kind"
          label="Trigger"
          value={trigger.kind}
          onChange={(e) => setTriggerKind(String(e.target.value) as TriggerKind)}
        >
          <MenuItem value="MANUAL_ONLY">Manual only</MenuItem>
          <MenuItem value="AFTER_N_ISSUES_COMPLETED">After N issues completed</MenuItem>
        </Select>
      </FormControl>

      {trigger.kind === 'AFTER_N_ISSUES_COMPLETED' ? (
        <TextField
          label="N issues completed"
          type="number"
          value={trigger.nIssuesCompleted ?? 1}
          onChange={(e) =>
            set('trigger', {
              kind: 'AFTER_N_ISSUES_COMPLETED',
              nIssuesCompleted: Number(e.target.value || 0),
            })
          }
          disabled={props.readOnly}
          inputProps={{ min: 1 }}
        />
      ) : null}

      <Box>
        <Typography variant="subtitle2" gutterBottom>
          Prompt text
        </Typography>
        <TextField
          value={v.promptText}
          onChange={(e) => set('promptText', e.target.value)}
          disabled={props.readOnly}
          multiline
          minRows={14}
          fullWidth
          InputProps={{
            sx: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace' },
          }}
        />
      </Box>
    </Box>
  );
}
