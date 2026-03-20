import { useAppActions } from './useAppActions';
import { useAppData } from './useAppData';

export function useAppController() {
  const data = useAppData();
  const actions = useAppActions(data);
  return { ...data, ...actions };
}
