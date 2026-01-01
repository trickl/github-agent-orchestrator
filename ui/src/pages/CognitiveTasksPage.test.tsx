import React from 'react';
import { screen, within } from '@testing-library/react';
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

  // Filter by search
  const search = screen.getByLabelText('Search');
  await user.type(search, 'gap');

  expect(screen.getByText('Gap analysis: observability')).toBeInTheDocument();
  expect(screen.queryByText('Complexity review')).not.toBeInTheDocument();
});

test('Edit cognitive task flow: open editor, change name, save updates list', async () => {
  const user = userEvent.setup();
  renderWithAppProviders(<CognitiveTasksPage />, { route: '/cognitive-tasks' });
  await waitForTasksToLoad();

  const row = screen.getByText('Gap analysis: observability').closest('tr');
  expect(row).not.toBeNull();

  const editButton = within(row as HTMLElement).getByLabelText('Edit');
  await user.click(editButton);

  const nameInput = await screen.findByLabelText('Name');
  await user.clear(nameInput);
  await user.type(nameInput, 'Gap analysis: observability (edited)');

  await user.click(screen.getByRole('button', { name: 'Save' }));

  await screen.findByText('Gap analysis: observability (edited)');
});

test('Run now flow: confirm then snackbar shown', async () => {
  const user = userEvent.setup();
  renderWithAppProviders(<CognitiveTasksPage />, { route: '/cognitive-tasks' });
  await waitForTasksToLoad();

  const row = screen.getByText('Gap analysis: observability').closest('tr');
  expect(row).not.toBeNull();

  const runButton = within(row as HTMLElement).getByRole('button', { name: 'Run now' });
  await user.click(runButton);

  await screen.findByText('Run cognitive task now?');
  await user.click(screen.getByRole('button', { name: 'Run now' }));

  await screen.findByText(/Created issue:/i);
});
