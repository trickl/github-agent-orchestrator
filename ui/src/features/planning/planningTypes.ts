export type PlanningDocKey = 'goal' | 'capabilities';

export type PlanningDoc = {
  key: PlanningDocKey;
  title: string;
  path: string;
  lastUpdatedIso?: string;
  content: string;
};
