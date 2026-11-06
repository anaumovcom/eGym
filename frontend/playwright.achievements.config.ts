import { defineConfig, devices } from '@playwright/test'

// Achievement QA must never start the backend, bootstrap a DB or contact hardware.
// The navigation fixture intercepts all /api/ HTTP and WebSocket traffic.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'achievements.spec.ts',
  workers: 1,
  fullyParallel: false,
  use: { baseURL: 'http://127.0.0.1:4186', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev -- --host=127.0.0.1 --port=4186 --strictPort',
    url: 'http://127.0.0.1:4186',
    reuseExistingServer: false,
    env: { VITE_ENABLE_MSW: 'false' },
  },
})