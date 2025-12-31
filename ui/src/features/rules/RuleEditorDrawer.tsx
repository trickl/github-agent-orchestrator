import React from 'react';
import {
  Box,
  Button,
  Divider,
  Drawer,
  Stack,
  Typography,
} from '@mui/material';
import { RuleForm, type RuleDraft } from './RuleForm';

export function RuleEditorDrawer(props: {
  open: boolean;
  mode: 'create' | 'edit' | 'duplicate' | 'view';
  initial: RuleDraft;
  editable: boolean;
  onCancel: () => void;
  onSave: (draft: RuleDraft) => Promise<void>;
}): React.JSX.Element {
  const [draft, setDraft] = React.useState<RuleDraft>(props.initial);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    setDraft(props.initial);
  }, [props.initial, props.open]);

  const title =
    props.mode === 'create'
      ? 'Create rule'
      : props.mode === 'duplicate'
        ? 'Duplicate rule'
        : props.mode === 'edit'
          ? 'Edit rule'
          : 'View rule';

  const readOnly = !props.editable || props.mode === 'view';

  async function save(): Promise<void> {
    setSaving(true);
    try {
      await props.onSave(draft);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer anchor="right" open={props.open} onClose={props.onCancel} PaperProps={{ sx: { width: 520 } }}>
      <Box p={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" gap={2}>
          <Typography variant="h6">{title}</Typography>
          <Stack direction="row" gap={1}>
            <Button onClick={props.onCancel}>Cancel</Button>
            {!readOnly ? (
              <Button variant="contained" onClick={() => void save()} disabled={saving}>
                Save
              </Button>
            ) : null}
          </Stack>
        </Stack>
      </Box>
      <Divider />
      <Box p={2} sx={{ overflowY: 'auto' }}>
        <RuleForm value={draft} onChange={setDraft} readOnly={readOnly} />
      </Box>
    </Drawer>
  );
}
