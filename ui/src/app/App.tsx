import React from 'react';
import { RouterProvider, createBrowserRouter } from 'react-router-dom';
import { routes } from './routes';

export function App(): React.JSX.Element {
  const router = createBrowserRouter(routes);
  return <RouterProvider router={router} />;
}
