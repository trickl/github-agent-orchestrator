import type { CognitiveTask } from './cognitiveTaskTypes';
import type { CognitiveTaskDraft } from './CognitiveTaskForm';

export function defaultDraftFromCognitiveTask(task: CognitiveTask): CognitiveTaskDraft {
  // Drop backend managed fields when editing.
  return {
    id: task.id,
    name: task.name,
    category: task.category,
    enabled: task.enabled,
    promptText: task.promptText,
    targetFolder: task.targetFolder,
    trigger: task.trigger,
    lastRunIso: task.lastRunIso,
    nextEligibleIso: task.nextEligibleIso,
    editable: task.editable,
  };
}
