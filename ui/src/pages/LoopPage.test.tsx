import React from 'react';
import { screen } from '@testing-library/react';

import { LoopPage } from './LoopPage';
import { renderWithAppProviders } from '../../tests/testUtils';

test('Loop page renders the loop visualization', async () => {
  renderWithAppProviders(<LoopPage />, { route: '/loop' });

  await screen.findByText('Loop');
  await screen.findByText(/Current stage:/i);

  // Spot-check some step titles.
  await screen.findByText(/Step 1a — Gap analysis issue/i);
  await screen.findByText(/Step 2a — Development issue creation/i);
  await screen.findByText(/Step 3a — Capability update issue/i);
});
