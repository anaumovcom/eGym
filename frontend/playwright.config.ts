import { defineConfig, devices } from '@playwright/test'

const backendCorsOrigins = JSON.stringify([
  'http://127.0.0.1:4174',
  'http://localhost:4174',
  'http://127.0.0.1:5173',
  'http://localhost:5173',
])

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:4174',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: 'd:/eGym/.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
      cwd: '../backend',
      env: {
        CORS_ORIGINS: backendCorsOrigins,
      },
      url: 'http://127.0.0.1:8000/api/openapi.json',
      reuseExistingServer: false,
      timeout: 120000,
    },
    {
      command: 'npm run dev -- --host=127.0.0.1 --port=4174',
      cwd: '.',
      env: {
        VITE_API_BASE_URL: 'http://127.0.0.1:8000',
        VITE_ENABLE_MSW: 'false',
      },
      url: 'http://127.0.0.1:4174',
      reuseExistingServer: false,
      timeout: 120000,
    },
  ],
})