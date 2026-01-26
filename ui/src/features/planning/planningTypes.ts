export type PlanningDocKey = 'goal' | 'targetState' | 'currentState';

export type PlanningDoc = {
  key: PlanningDocKey;
  title: string;
  path: string;
  lastUpdatedIso?: string;
  content: string;
};
