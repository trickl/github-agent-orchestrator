import React from 'react';
import { Alert, Box, Button, Tab, Tabs, TextField, Typography } from '@mui/material';
import { ApiError, apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import { useApiResource } from '../lib/useApiResource';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import type { PlanningDoc } from '../features/planning/planningTypes';
import { DocViewer } from '../features/planning/DocViewer';

type TabKey = 'targetState' | 'currentState';

export function PlanningDocsPage(): React.JSX.Element {
  const [tab, setTab] = React.useState<TabKey>('targetState');

  const targetState = useApiResource(() => apiFetch<PlanningDoc>(endpoints.docTargetState()), []);
  const currentState = useApiResource(
    () =>
      apiFetch<PlanningDoc>(endpoints.docCurrentState()).catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 404) {
          return {
            key: 'currentState',
            title: 'Current',
            path: '.agent-orchestrator/state/current_state.md',
            content: '',
          };
        }
        throw e;
      }),
    []
  );

  const selected = tab === 'targetState' ? targetState : currentState;
  const [targetStateDraft, setTargetStateDraft] = React.useState<string>('');
  const [targetStateTouched, setTargetStateTouched] = React.useState(false);
  const [saveBusy, setSaveBusy] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [saveNotice, setSaveNotice] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (targetStateTouched) return;
    if (targetState.data?.content) {
      setTargetStateDraft(targetState.data.content);
      return;
    }
    if (targetState.error) {
      setTargetStateDraft('# Target State\n\n');
    }
  }, [targetState.data?.content, targetState.error, targetStateTouched]);

  const onSaveTargetState = (): void => {
    setSaveBusy(true);
    setSaveError(null);
    setSaveNotice(null);

    void apiFetch<{ ok: boolean; message?: string }>(endpoints.docTargetState(), {
      method: 'POST',
      body: JSON.stringify({ content: targetStateDraft }),
    })
      .then((resp) => {
        setSaveNotice(resp.message ?? 'Target saved to the repository.');
        targetState.reload();
      })
      .catch((e: unknown) => {
        setSaveError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        setSaveBusy(false);
      });
  };

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Planning Docs
      </Typography>

      <Tabs value={tab} onChange={(_, v) => setTab(v as TabKey)} sx={{ mb: 2 }}>
        <Tab value="targetState" label="Target" />
        <Tab value="currentState" label="Current" />
      </Tabs>

      {selected.loading ? <LoadingState /> : null}
      {selected.error ? (
        <ErrorState
          message={selected.error}
          onRetry={() => {
            targetState.reload();
            currentState.reload();
          }}
        />
      ) : null}

      {!selected.loading && !selected.error && selected.data ? (
        <Box>
          <DocViewer doc={selected.data} />
        </Box>
      ) : null}

      {tab === 'currentState' && selected.data && !selected.data.content.trim() ? (
        <Alert severity="info" sx={{ mt: 2 }}>
          Current state has not been captured yet. It will be created by capability update issues
          after merges.
        </Alert>
      ) : null}

      {tab === 'targetState' ? (
        <Box mt={3} display="flex" flexDirection="column" gap={2}>
          <Typography variant="subtitle1">Write target</Typography>
          <Typography variant="body2" color="text.secondary">
            Paste Markdown content here to create or update <code>.agent-orchestrator/state/target_state.md</code>.
          </Typography>
          <TextField
            value={targetStateDraft}
            onChange={(e) => {
              setTargetStateDraft(e.target.value);
              setTargetStateTouched(true);
            }}
            multiline
            minRows={10}
            fullWidth
            placeholder="# Target State\n\nDescribe the desired target state..."
            InputProps={{
              sx: {
                fontFamily:
                  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
              },
            }}
          />
          <Box display="flex" alignItems="center" gap={2}>
            <Button variant="contained" onClick={onSaveTargetState} disabled={saveBusy}>
              {saveBusy ? 'Saving…' : 'Save target to repo'}
            </Button>
            <Typography variant="caption" color="text.secondary">
              Requires <code>ORCHESTRATOR_GITHUB_TOKEN</code>.
            </Typography>
          </Box>
          {saveError ? <Alert severity="error">{saveError}</Alert> : null}
          {saveNotice ? <Alert severity="success">{saveNotice}</Alert> : null}
        </Box>
      ) : null}
    </div>
  );
}
