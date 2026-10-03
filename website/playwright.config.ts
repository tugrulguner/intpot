import { defineConfig } from '@playwright/test';

const port = process.env.SITE_TEST_PORT ?? '4387';
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests/browser',
  outputDir: './test-results',
  reporter: 'list',
  use: { baseURL, browserName: 'chromium' },
  webServer: {
    command: `npm run preview -- --host 127.0.0.1 --port ${port}`,
    url: `${baseURL}/playground/`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
