import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'runtime-4k-visual.spec.ts',
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: process.env.EGYM_E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    viewport: { width: 2560, height: 1440 },
    deviceScaleFactor: 1.5,
    trace: 'retain-on-failure',
  },
})
