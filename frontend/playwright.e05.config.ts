import { defineConfig, devices, chromium } from '@playwright/test'
import { existsSync } from 'node:fs'

// Deliberately separate from playwright.config.ts: that config starts a backend.
export default defineConfig({
  testDir: './e2e/e05',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  outputDir: './test-results/e05',
  reporter: [['list'], ['json', { outputFile: 'test-results/e05-results.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:5179',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: {
    ...devices['Desktop Chrome'],
    launchOptions: {
      executablePath: process.env.E05_CHROMIUM_PATH ??
        (existsSync(chromium.executablePath()) ? undefined : '/snap/bin/chromium'),
      args: ['--autoplay-policy=user-gesture-required'],
    },
  } }],
  webServer: {
    command: 'npx vite --config vite.e05.config.ts --host 127.0.0.1 --port 5179 --strictPort',
    url: 'http://127.0.0.1:5179/e05-harness/index.html',
    reuseExistingServer: false,
    timeout: 60_000,
  },
})