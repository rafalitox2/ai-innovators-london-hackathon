import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:8089',
    trace: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run build && cd .. && SEED_OFFLINE_MODE=1 .venv/bin/python -m uvicorn app.ui_server:app --host 127.0.0.1 --port 8089',
    url: 'http://127.0.0.1:8089/api/health',
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
