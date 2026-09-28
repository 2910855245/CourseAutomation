import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:17017',
    headless: true,
  },
  webServer: {
    command: 'cd ../rust_worker && cargo run --release',
    port: 17017,
    timeout: 120000,
    reuseExistingServer: true,
  },
})
