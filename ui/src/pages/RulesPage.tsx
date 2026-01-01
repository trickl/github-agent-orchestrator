import type React from 'react';
import { Navigate } from 'react-router-dom';

export function RulesPage(): React.JSX.Element {
  // Legacy page retained for compatibility with older deep links.
  // The canonical UI surface is now /cognitive-tasks.
  return <Navigate to="/cognitive-tasks" replace />;
}
