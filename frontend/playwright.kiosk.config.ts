import { defineConfig } from '@playwright/test'
import { kioskDisplay } from './e2e/kiosk-display.mjs'

export default defineConfig({
  testDir: './e2e',
  testMatch: ['runtime-4k-visual.spec.ts', 'tv-framework.spec.ts', 'drive-transport.spec.ts'],
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: process.env.EGYM_E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    ...kioskDisplay,
    trace: 'retain-on-failure',
  },
})
