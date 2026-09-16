import { expect, test as base, type Page } from '@playwright/test'
import type { HardwareSnapshot } from '../../src/features/hardware/model/types'
import { FALLBACK_STRENGTH_MODES } from '../../src/features/strength/lib/strength-plan'
import { buildDashboardScenario, machineScenarios, mockUsers } from '../../src/mocks/data'
import { getExerciseDetails, getWorkoutBuilderData, getWorkoutCalendarData } from '../../src/mocks/stage2-data'
import { buildFatigueData, buildProgressData, buildSystemSettingsData, defaultStage4DevFlags, getProfileSeed } from '../../src/mocks/stage4-data'

export const primaryNavigation = [
  ['Главная', '/dashboard'],
  ['Мои тренировки', '/builder'],
  ['Каталог', '/catalog'],
  ['Календарь', '/calendar'],
  ['Прогресс', '/progress'],
  ['Modbus', '/modbus'],
] as const

async function installNavigationApi(page: Page) {
  const violations: string[] = []
  const cameraRequests: string[] = []
  const requests: Array<{ method: string; path: string; search: string }> = []
  const exercise = getExerciseDetails('machine-pulldown')
  const excludedExercise = getExerciseDetails('smith-machine-bench-press')
  const builder = structuredClone(getWorkoutBuilderData())
  builder.selectedProgramId = 'e2e-saved-workout'
  builder.info.name = 'Сохранённая тренировка e2e'
  builder.programs = [{ ...builder.programs[0], id: builder.selectedProgramId, name: builder.info.name }]
  const settings = buildSystemSettingsData(defaultStage4DevFlags)
  const snapshot: HardwareSnapshot = {
    eventType: 'snapshot', emittedAt: '2026-09-15T10:00:00Z', machine: machineScenarios.ready,
    safety: { state: 'enabled', label: 'Безопасность включена', message: '', requiresService: false, activeEventId: null },
    emulatorMode: true, serviceMode: false, selectedUserId: 'alexey', userSelected: true,
    drives: [],
    motion: {
      moving: false, motionProfile: 'idle', barPositionMm: 0, leftPositionMm: 0, rightPositionMm: 0,
      syncDeltaMm: 0, amplitudePercent: 0, tempoLabel: 'Покой', repetitionCount: 0,
      currentSet: 0, targetSet: 0, targetReps: 0, direction: 'stopped',
    },
    calibrationRequired: true, calibrationActual: false, activeCalibrationId: null,
    commandQueueDepth: 0, lastCommand: null, diagnosticsStatus: 'idle', lastDiagnosticsAt: null, alerts: [],
  }

  await page.exposeFunction('__navigationCameraRequested', () => { cameraRequests.push('getUserMedia') })
  await page.addInitScript(() => {
    if (!localStorage.getItem('egym-app-store')) {
      localStorage.setItem('egym-app-store', JSON.stringify({ state: { selectedProgramId: 'e2e-saved-workout' }, version: 0 }))
    }
    const mediaDevices = navigator.mediaDevices ?? {}
    Object.defineProperty(mediaDevices, 'getUserMedia', {
      configurable: true,
      value: async () => {
        await (window as unknown as { __navigationCameraRequested: () => Promise<void> }).__navigationCameraRequested()
        throw new DOMException('Camera is blocked in navigation tests', 'NotAllowedError')
      },
    })
    if (!navigator.mediaDevices) Object.defineProperty(navigator, 'mediaDevices', { value: mediaDevices })
  })

  // Do not connect to a real device, even for the global realtime provider.
  await page.context().routeWebSocket((url) => url.pathname.startsWith('/api/'), (socket) => {
    socket.onMessage(() => { violations.push(`Unexpected WebSocket message: ${socket.url()}`) })
  })
  await page.context().route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const request = route.request()
    const { pathname: path, search, searchParams } = new URL(request.url())
    const method = request.method()
    requests.push({ method, path, search })

    // Both selection-screen and persisted-selection sync are fulfilled locally.
    if (method === 'POST' && path === '/api/users/select') {
      await route.fulfill({ json: { currentUser: { id: request.postDataJSON().userId } } })
      return
    }
    if (method !== 'GET') {
      violations.push(`${method} ${path}`)
      await route.fulfill({ status: 405, json: { detail: 'Read-only e2e: mutation blocked' } })
      return
    }

    const responses: Record<string, unknown> = {
      '/api/users': { users: mockUsers },
      '/api/users/current': {
        id: 'alexey', name: 'Алексей', role: 'user', readinessPercent: 78, accent: 'gold',
        profile: { birthDate: null, heightCm: 183, weightKg: 92.4, photoUrl: null, notes: '' }, goals: [],
      },
      '/api/machine/status': machineScenarios.ready,
      '/api/hardware/status': snapshot,
      '/api/hardware/settings': settings,
      '/api/hardware/calibrations/current': null,
      '/api/dashboard': buildDashboardScenario(),
      '/api/builder': builder,
      '/api/calendar': getWorkoutCalendarData(searchParams.get('month') ?? undefined),
      '/api/exercises': { items: [exercise, excludedExercise], total: 2, availableFilters: { muscles: [...new Set([...exercise.muscles, ...excludedExercise.muscles])], equipment: [...new Set([exercise.equipment, excludedExercise.equipment])], difficulty: ['Beginner', 'Intermediate', 'Advanced'], force: ['Push', 'Pull', 'Static', 'Stretch'], mechanic: ['Compound', 'Isolation', 'Mobility'], grips: [...new Set([exercise.grips, excludedExercise.grips])] } },
      '/api/exercises/machine-pulldown': exercise,
      '/api/exercises/smith-machine-bench-press': excludedExercise,
      '/api/strength-modes': FALLBACK_STRENGTH_MODES,
      '/api/progress': buildProgressData({ user: getProfileSeed('alexey'), period: '30d', blacklistedSlugs: [], dev: defaultStage4DevFlags }),
      '/api/fatigue': buildFatigueData({ dev: defaultStage4DevFlags }),
      '/api/body-measurements': { measurements: [] },
      '/api/photo-progress': { photos: [] },
      '/api/achievements': { achievements: [] },
      // The Modbus page is read-only here: no port list, no connection, simulation flag off.
      '/api/modbus/ports': [],
      '/api/modbus/status': { connected: false, port: null, baud_rate: null, parity: null, slave_id: null, last_success_at: null, ok_count: 0, error_count: 0, error_message: null, simulation_mode: false },
    }
    if (Object.hasOwn(responses, path)) {
      await route.fulfill({ json: responses[path] })
      return
    }
    violations.push(`${method} ${path}`)
    await route.fulfill({ status: 404, json: { detail: 'Read-only e2e: missing fixture' } })
  })
  return { builder, exercise, settings, snapshot, requests, violations, cameraRequests }
}

export const test = base.extend<{ navigationApi: Awaited<ReturnType<typeof installNavigationApi>> }>({
  // Override the URL only for an already-running frontend; no backend is needed.
  baseURL: async ({ baseURL }, use) => { await use(process.env.EGYM_E2E_BASE_URL ?? baseURL ?? 'http://127.0.0.1:4174') },
  serviceWorkers: 'block',
  navigationApi: [async ({ page }, use) => {
    const api = await installNavigationApi(page)
    await use(api)
    expect(api.violations, 'No unmocked API calls, writes or WebSocket commands').toEqual([])
    expect(api.cameraRequests, 'Navigation must not request the camera').toEqual([])
  }, { auto: true }],
})

export async function expectPrimaryNavigation(page: Page) {
  const navigation = page.getByRole('navigation', { name: 'Основная навигация', exact: true })
  await expect(navigation.getByRole('link')).toHaveCount(primaryNavigation.length)
  for (const [name, href] of primaryNavigation) {
    const link = navigation.getByRole('link', { name, exact: true })
    await expect(link).toBeVisible()
    await expect(link).toHaveAttribute('href', href)
  }
}

export async function openAppAsAlexey(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: 'Кто тренируется?' })).toBeVisible()
  await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expectPrimaryNavigation(page)
}

export async function openCatalogExerciseSetup(page: Page) {
  await page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link', { name: 'Каталог', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Каталог упражнений' })).toBeVisible()
  // Pick a weighted machine exercise: bodyweight exercises skip setup automatically.
  await page.getByPlaceholder('Найти упражнение...').fill('machine-pulldown')
  const card = page.getByRole('article', { name: 'Тяга верхнего блока в тренажёре' })
  await card.getByRole('button', { name: /^Открыть/ }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Начать упражнение', exact: true }).click()
  await expect(page).toHaveURL(/\/exercise-setup\?source=catalog&slug=machine-pulldown$/)
  await expect(page.getByRole('heading', { name: 'Настройка упражнения' })).toBeVisible()
}

export async function savedBrowserState(page: Page) {
  return page.evaluate(() => ({ ...localStorage }))
}