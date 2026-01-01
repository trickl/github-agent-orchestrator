import React from 'react';
import { Alert, Box, Button, Snackbar, Typography } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import { useApiResource } from '../lib/useApiResource';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { EmptyState } from '../components/EmptyState';
import { ConfirmDialog } from '../components/ConfirmDialog';
import type { CognitiveTask, CognitiveTaskRunResult } from '../features/cognitiveTasks/cognitiveTaskTypes';
import { CognitiveTaskEditorDrawer } from '../features/cognitiveTasks/CognitiveTaskEditorDrawer';
import type { CognitiveTaskDraft } from '../features/cognitiveTasks/CognitiveTaskForm';
import {
  CognitiveTasksList,
  type CognitiveTasksListFilters,
} from '../features/cognitiveTasks/CognitiveTasksList';
import { CognitiveTaskRunDialog } from '../features/cognitiveTasks/CognitiveTaskRunDialog';
import { defaultDraftFromCognitiveTask } from '../features/cognitiveTasks/cognitiveTaskDraft';

function newEmptyDraft(): CognitiveTaskDraft {
  return {
    name: '',
    category: 'review',
    enabled: true,
    promptText: '',
    targetFolder: 'reviews/',
    trigger: { kind: 'MANUAL_ONLY' },
    editable: true,
  };
}

export function CognitiveTasksPage(): React.JSX.Element {
  const navigate = useNavigate();

  const tasksRes = useApiResource(() => apiFetch<CognitiveTask[]>(endpoints.cognitiveTasks()), []);

  const [filters, setFilters] = React.useState<CognitiveTasksListFilters>({ search: '', category: 'all' });

  const [editorOpen, setEditorOpen] = React.useState(false);
  const [editorMode, setEditorMode] = React.useState<'create' | 'edit' | 'duplicate' | 'view'>('create');
  const [editorInitial, setEditorInitial] = React.useState<CognitiveTaskDraft>(newEmptyDraft());
  const [editorEditable, setEditorEditable] = React.useState(true);

  const [deleteTarget, setDeleteTarget] = React.useState<CognitiveTask | null>(null);
  const [runTarget, setRunTarget] = React.useState<CognitiveTask | null>(null);

  const [snack, setSnack] = React.useState<null | { message: string; goIssues?: boolean }>(null);

  const tasks = React.useMemo(() => {
    const all = tasksRes.data ?? [];
    return all.filter((t) => {
      if (filters.category !== 'all' && t.category !== filters.category) return false;
      if (filters.search && !t.name.toLowerCase().includes(filters.search.toLowerCase())) return false;
      return true;
    });
  }, [filters.category, filters.search, tasksRes.data]);

  function openCreate(): void {
    setEditorMode('create');
    setEditorInitial(newEmptyDraft());
    setEditorEditable(true);
    setEditorOpen(true);
  }

  function openEdit(task: CognitiveTask): void {
    setEditorMode(task.editable ? 'edit' : 'view');
    setEditorInitial(defaultDraftFromCognitiveTask(task));
    setEditorEditable(task.editable);
    setEditorOpen(true);
  }

  function openDuplicate(task: CognitiveTask): void {
    const d = defaultDraftFromCognitiveTask(task);
    delete d.id;
    d.name = `${task.name} (copy)`;
    setEditorMode('duplicate');
    setEditorInitial(d);
    setEditorEditable(true);
    setEditorOpen(true);
  }

  async function saveDraft(draft: CognitiveTaskDraft): Promise<void> {
    if (editorMode === 'create' || editorMode === 'duplicate') {
      await apiFetch<CognitiveTask>(endpoints.cognitiveTasks(), {
        method: 'POST',
        body: JSON.stringify({
          name: draft.name,
          category: draft.category,
          enabled: draft.enabled,
          promptText: draft.promptText,
          targetFolder: draft.targetFolder,
          trigger: draft.trigger,
        }),
      });
    } else {
      if (!draft.id) throw new Error('Missing cognitive task id');
      await apiFetch<CognitiveTask>(endpoints.cognitiveTaskById(draft.id), {
        method: 'PUT',
        body: JSON.stringify({
          id: draft.id,
          name: draft.name,
          category: draft.category,
          enabled: draft.enabled,
          promptText: draft.promptText,
          targetFolder: draft.targetFolder,
          trigger: draft.trigger,
          lastRunIso: draft.lastRunIso,
          nextEligibleIso: draft.nextEligibleIso,
          editable: draft.editable,
        }),
      });
    }

    setEditorOpen(false);
    tasksRes.reload();
  }

  async function toggleEnabled(task: CognitiveTask, enabled: boolean): Promise<void> {
    await apiFetch<CognitiveTask>(endpoints.cognitiveTaskById(task.id), {
      method: 'PUT',
      body: JSON.stringify({ ...task, enabled }),
    });
    tasksRes.reload();
  }

  async function deleteTask(task: CognitiveTask): Promise<void> {
    await apiFetch<{ ok: boolean }>(endpoints.cognitiveTaskById(task.id), { method: 'DELETE' });
    tasksRes.reload();
  }

  async function runTask(task: CognitiveTask): Promise<void> {
    const result = await apiFetch<CognitiveTaskRunResult>(endpoints.cognitiveTaskRun(task.id), { method: 'POST' });
    if (!result.ok) throw new Error('Run failed');

    setSnack({ message: `Created issue: ${result.createdIssueTitle}`, goIssues: true });
    // Required refreshes after a successful run:
    tasksRes.reload();
    await Promise.all([
      apiFetch(endpoints.issues('open')),
      apiFetch(endpoints.timeline(200)),
    ]);
  }

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Cognitive Tasks
      </Typography>

      {tasksRes.loading ? <LoadingState /> : null}
      {tasksRes.error ? <ErrorState message={tasksRes.error} onRetry={tasksRes.reload} /> : null}

      {!tasksRes.loading && !tasksRes.error ? (
        tasksRes.data && tasksRes.data.length === 0 ? (
          <EmptyState title="No cognitive tasks" description="Create your first cognitive task." />
        ) : (
          <Box>
            <CognitiveTasksList
              tasks={tasks}
              filters={filters}
              onFiltersChange={setFilters}
              onCreate={openCreate}
              onEdit={openEdit}
              onDuplicate={openDuplicate}
              onDelete={(t) => setDeleteTarget(t)}
              onRun={(t) => setRunTarget(t)}
              onToggleEnabled={(t, enabled) => void toggleEnabled(t, enabled)}
            />
          </Box>
        )
      ) : null}

      <CognitiveTaskEditorDrawer
        open={editorOpen}
        mode={editorMode}
        initial={editorInitial}
        editable={editorEditable}
        onCancel={() => setEditorOpen(false)}
        onSave={saveDraft}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete cognitive task?"
        body={`Delete “${deleteTarget?.name ?? ''}”? This cannot be undone.`}
        destructive
        confirmLabel="Delete"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) return;
          const t = deleteTarget;
          setDeleteTarget(null);
          void deleteTask(t);
        }}
      />

      <CognitiveTaskRunDialog
        open={!!runTarget}
        taskName={runTarget?.name ?? ''}
        onCancel={() => setRunTarget(null)}
        onConfirm={() => {
          if (!runTarget) return;
          const t = runTarget;
          setRunTarget(null);
          void runTask(t).catch((e: unknown) => {
            setSnack({ message: e instanceof Error ? e.message : String(e) });
          });
        }}
      />

      <Snackbar
        open={!!snack}
        autoHideDuration={3500}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          severity="success"
          onClose={() => setSnack(null)}
          action={
            snack?.goIssues ? (
              <Button
                color="inherit"
                size="small"
                onClick={() => {
                  setSnack(null);
                  navigate('/issues');
                }}
              >
                View
              </Button>
            ) : undefined
          }
        >
          {snack?.message ?? ''}
        </Alert>
      </Snackbar>
    </div>
  );
}
