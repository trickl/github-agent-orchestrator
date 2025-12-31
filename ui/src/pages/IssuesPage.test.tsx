import React from 'react';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IssuesPage } from './IssuesPage';
import { renderWithAppProviders } from '../../tests/testUtils';

test('Issues page filter/search works', async () => {
  const user = userEvent.setup();
  renderWithAppProviders(<IssuesPage />, { route: '/issues' });

  // default status=open should include pending issue
  await screen.findByText('Dev: Improve timeline event persistence');

  const search = screen.getByLabelText('Search title');
  await user.type(search, 'rules endpoint');

  // should filter out everything because open status doesn't include merged issue
  expect(screen.queryByText('Dev: Add rules endpoint')).not.toBeInTheDocument();

  // switch to all
  await user.click(screen.getByRole('combobox', { name: 'Status' }));
  await user.click(await screen.findByRole('option', { name: 'all' }));

  await screen.findByText('Dev: Add rules endpoint');
});
