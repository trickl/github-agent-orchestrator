import '@testing-library/jest-dom/vitest';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { server } from '../src/mocks/server';
import { resetMockState } from '../src/mocks/handlers';

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});

afterEach(() => {
  server.resetHandlers();
  resetMockState();
});

afterAll(() => {
  server.close();
});
