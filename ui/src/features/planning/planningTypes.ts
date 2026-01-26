export type PlanningDocKey = 'targetState' | 'currentState';

export type PlanningDoc = {
  key: PlanningDocKey;
  title: string;
  path: string;
  lastUpdatedIso?: string;
  content: string;
};
