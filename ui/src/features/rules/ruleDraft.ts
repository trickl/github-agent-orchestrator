import type { GenerationRule } from './ruleTypes';
import type { RuleDraft } from './RuleForm';

export function defaultDraftFromRule(rule: GenerationRule): RuleDraft {
  // Drop backend managed fields when editing.
  return {
    id: rule.id,
    name: rule.name,
    category: rule.category,
    enabled: rule.enabled,
    promptText: rule.promptText,
    targetFolder: rule.targetFolder,
    trigger: rule.trigger,
    lastRunIso: rule.lastRunIso,
    nextEligibleIso: rule.nextEligibleIso,
    editable: rule.editable,
  };
}
