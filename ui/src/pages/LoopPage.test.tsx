import React from 'react';
import { screen } from '@testing-library/react';

import { LoopPage } from './LoopPage';
import { renderWithAppProviders } from '../../tests/testUtils';

test('Loop page renders the loop visualization', async () => {
  renderWithAppProviders(<LoopPage />, { route: '/loop' });

  await screen.findByText('Loop');
  await screen.findByText(/Current stage:/i);

  // Spot-check some step titles.
  await screen.findByText(/Step A — Gap analysis/i);
  await screen.findByText(/Step B — Issue creation/i);
  await screen.findByText(/Step C — Development/i);
});
