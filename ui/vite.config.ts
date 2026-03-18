import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const isGithubActions = process.env.GITHUB_ACTIONS === 'true';
const githubRepository = process.env.GITHUB_REPOSITORY;
const repositoryName = githubRepository?.split('/')[1];
const pagesBase = isGithubActions && repositoryName ? `/${repositoryName}/` : '/';

export default defineConfig({
  base: pagesBase,
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setupTests.ts'],
    globals: true,
    exclude: ['playwright/**', 'node_modules/**', 'dist/**'],
    clearMocks: true,
    restoreMocks: true,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
