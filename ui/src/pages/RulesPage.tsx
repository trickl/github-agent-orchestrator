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
import type { GenerationRule, RuleRunResult } from '../features/rules/ruleTypes';
import { RuleEditorDrawer } from '../features/rules/RuleEditorDrawer';
import type { RuleDraft } from '../features/rules/RuleForm';
import { RulesList, type RulesListFilters } from '../features/rules/RulesList';
import { RuleRunDialog } from '../features/rules/RuleRunDialog';
import { defaultDraftFromRule } from '../features/rules/ruleDraft';

function newEmptyDraft(): RuleDraft {
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

export function RulesPage(): React.JSX.Element {
  const navigate = useNavigate();

  const rulesRes = useApiResource(() => apiFetch<GenerationRule[]>(endpoints.rules()), []);

  const [filters, setFilters] = React.useState<RulesListFilters>({ search: '', category: 'all' });

  const [editorOpen, setEditorOpen] = React.useState(false);
  const [editorMode, setEditorMode] = React.useState<'create' | 'edit' | 'duplicate' | 'view'>('create');
  const [editorInitial, setEditorInitial] = React.useState<RuleDraft>(newEmptyDraft());
  const [editorEditable, setEditorEditable] = React.useState(true);

  const [deleteTarget, setDeleteTarget] = React.useState<GenerationRule | null>(null);
  const [runTarget, setRunTarget] = React.useState<GenerationRule | null>(null);

  const [snack, setSnack] = React.useState<null | { message: string; goIssues?: boolean }>(null);

  const rules = React.useMemo(() => {
    const all = rulesRes.data ?? [];
    return all.filter((r) => {
      if (filters.category !== 'all' && r.category !== filters.category) return false;
      if (filters.search && !r.name.toLowerCase().includes(filters.search.toLowerCase())) return false;
      return true;
    });
  }, [filters.category, filters.search, rulesRes.data]);

  function openCreate(): void {
    setEditorMode('create');
    setEditorInitial(newEmptyDraft());
    setEditorEditable(true);
    setEditorOpen(true);
  }

  function openEdit(rule: GenerationRule): void {
    setEditorMode(rule.editable ? 'edit' : 'view');
    setEditorInitial(defaultDraftFromRule(rule));
    setEditorEditable(rule.editable);
    setEditorOpen(true);
  }

  function openDuplicate(rule: GenerationRule): void {
    const d = defaultDraftFromRule(rule);
    delete d.id;
    d.name = `${rule.name} (copy)`;
    setEditorMode('duplicate');
    setEditorInitial(d);
    setEditorEditable(true);
    setEditorOpen(true);
  }

  async function saveDraft(draft: RuleDraft): Promise<void> {
    if (editorMode === 'create' || editorMode === 'duplicate') {
      await apiFetch<GenerationRule>(endpoints.rules(), {
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
      if (!draft.id) throw new Error('Missing rule id');
      await apiFetch<GenerationRule>(endpoints.ruleById(draft.id), {
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
    rulesRes.reload();
  }

  async function toggleEnabled(rule: GenerationRule, enabled: boolean): Promise<void> {
    await apiFetch<GenerationRule>(endpoints.ruleById(rule.id), {
      method: 'PUT',
      body: JSON.stringify({ ...rule, enabled }),
    });
    rulesRes.reload();
  }

  async function deleteRule(rule: GenerationRule): Promise<void> {
    await apiFetch<{ ok: boolean }>(endpoints.ruleById(rule.id), { method: 'DELETE' });
    rulesRes.reload();
  }

  async function runRule(rule: GenerationRule): Promise<void> {
    const result = await apiFetch<RuleRunResult>(endpoints.ruleRun(rule.id), { method: 'POST' });
    if (!result.ok) throw new Error('Run failed');

    setSnack({ message: `Created issue: ${result.createdIssueTitle}`, goIssues: true });
    // Required refreshes after a successful run:
    rulesRes.reload();
    await Promise.all([
      apiFetch(endpoints.issues('open')),
      apiFetch(endpoints.timeline(200)),
    ]);
  }

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Generation Rules
      </Typography>

      {rulesRes.loading ? <LoadingState /> : null}
      {rulesRes.error ? <ErrorState message={rulesRes.error} onRetry={rulesRes.reload} /> : null}

      {!rulesRes.loading && !rulesRes.error ? (
        rulesRes.data && rulesRes.data.length === 0 ? (
          <EmptyState title="No rules" description="Create your first generation rule." />
        ) : (
          <Box>
            <RulesList
              rules={rules}
              filters={filters}
              onFiltersChange={setFilters}
              onCreate={openCreate}
              onEdit={openEdit}
              onDuplicate={openDuplicate}
              onDelete={(r) => setDeleteTarget(r)}
              onRun={(r) => setRunTarget(r)}
              onToggleEnabled={(r, enabled) => void toggleEnabled(r, enabled)}
            />
          </Box>
        )
      ) : null}

      <RuleEditorDrawer
        open={editorOpen}
        mode={editorMode}
        initial={editorInitial}
        editable={editorEditable}
        onCancel={() => setEditorOpen(false)}
        onSave={saveDraft}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete rule?"
        body={`Delete “${deleteTarget?.name ?? ''}”? This cannot be undone.`}
        destructive
        confirmLabel="Delete"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) return;
          const r = deleteTarget;
          setDeleteTarget(null);
          void deleteRule(r);
        }}
      />

      <RuleRunDialog
        open={!!runTarget}
        ruleName={runTarget?.name ?? ''}
        onCancel={() => setRunTarget(null)}
        onConfirm={() => {
          if (!runTarget) return;
          const r = runTarget;
          setRunTarget(null);
          void runRule(r).catch((e: unknown) => {
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
