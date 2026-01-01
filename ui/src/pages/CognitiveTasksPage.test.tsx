import React from 'react';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CognitiveTasksPage } from './CognitiveTasksPage';
import { renderWithAppProviders } from '../../tests/testUtils';

async function waitForTasksToLoad(): Promise<void> {
  await screen.findByText('Complexity review');
}

test('Cognitive tasks list renders and filter works', async () => {
  const user = userEvent.setup();
  renderWithAppProviders(<CognitiveTasksPage />, { route: '/cognitive-tasks' });
  await waitForTasksToLoad();

  // Read-only notice
  expect(screen.getByText(/intentionally read-only/i)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /new task/i })).not.toBeInTheDocument();

  // Filter by search
  const search = screen.getByLabelText('Search');
  await user.type(search, 'gap');

  expect(screen.getByText('Gap analysis: observability')).toBeInTheDocument();
  expect(screen.queryByText('Complexity review')).not.toBeInTheDocument();
});
