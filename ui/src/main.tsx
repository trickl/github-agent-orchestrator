import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './app/App';
import { ColorModeProvider } from './app/colorMode';

async function maybeStartMsw(): Promise<void> {
  if (import.meta.env.VITE_USE_MSW !== 'true') return;
  const { worker } = await import('./mocks/browser');
  await worker.start({
    onUnhandledRequest: 'bypass',
  });
}

void maybeStartMsw().then(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <ColorModeProvider>
        <App />
      </ColorModeProvider>
    </React.StrictMode>
  );
});
