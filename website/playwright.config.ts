import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  outputDir: './test-results',
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:4341', browserName: 'chromium' },
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4341',
    url: 'http://127.0.0.1:4341/playground/',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
