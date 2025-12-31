import React from 'react';
import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { TimelinePage } from './TimelinePage';
import { renderWithAppProviders } from '../../tests/testUtils';

test('Timeline renders events', async () => {
  renderWithAppProviders(<TimelinePage />, { route: '/timeline' });
  await screen.findByText('Timeline');
  await screen.findByText(/Rule triggered:/i);
});

test('Timeline handles empty list', async () => {
  server.use(
    http.get('*/timeline', () => {
      return HttpResponse.json([]);
    })
  );

  renderWithAppProviders(<TimelinePage />, { route: '/timeline' });
  await screen.findByText('No timeline events');
});
