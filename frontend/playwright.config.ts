import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:8000',
    headless: true,
  },
  webServer: {
    command: 'cd .. && python run.py',
    port: 8000,
    timeout: 15000,
    reuseExistingServer: true,
  },
})
