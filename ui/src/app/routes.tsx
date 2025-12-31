import React from 'react';
import { Navigate } from 'react-router-dom';
import type { RouteObject } from 'react-router-dom';
import { AppLayout } from './layout/AppLayout';
import { ActiveWorkPage } from '../pages/ActiveWorkPage';
import { IssuesPage } from '../pages/IssuesPage';
import { NotFoundPage } from '../pages/NotFoundPage';
import { OverviewPage } from '../pages/OverviewPage';
import { PlanningDocsPage } from '../pages/PlanningDocsPage';
import { RulesPage } from '../pages/RulesPage';
import { TimelinePage } from '../pages/TimelinePage';

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <OverviewPage /> },
      { path: '/timeline', element: <TimelinePage /> },
      { path: '/active', element: <ActiveWorkPage /> },
      { path: '/issues', element: <IssuesPage /> },
      { path: '/rules', element: <RulesPage /> },
      { path: '/docs', element: <PlanningDocsPage /> },
      { path: '/index.html', element: <Navigate to="/" replace /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];
