import React from 'react';
import { screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { renderWithAppProviders } from '../../tests/testUtils';

import { RulesPage } from './RulesPage';

test('Legacy /rules route redirects to /cognitive-tasks', async () => {
  renderWithAppProviders(
    <Routes>
      <Route path="/rules" element={<RulesPage />} />
      <Route path="/cognitive-tasks" element={<h1>Cognitive Tasks</h1>} />
    </Routes>,
    { route: '/rules' }
  );

  await screen.findByRole('heading', { name: 'Cognitive Tasks' });
});
