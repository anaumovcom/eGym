import { expect, type Page, type Route } from '@playwright/test'
import { getExerciseDetails } from '../src/mocks/stage2-data'
import { test } from './fixtures/navigation'

async function openApp(page: Page) {
  await page.route('**/api/scales/status', (route) => route.fulfill({ json: { connected: false } }))
  await page.route('**/api/scales/activity', (route) => route.fulfill({ json: {} }))
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Выбрать профиль Алексей', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

async function expectFitsKiosk(page: Page) {
  const main = page.getByRole('main')
  expect(await page.evaluate(() => ({ width: innerWidth, height: innerHeight, dpr: devicePixelRatio }))).toEqual({ width: 2560, height: 1440, dpr: 1.5 })
  expect(await main.evaluate((node) => node.scrollHeight - node.clientHeight), 'main must not scroll vertically').toBeLessThanOrEqual(2)
  expect(await main.evaluate((node) => node.scrollWidth - node.clientWidth), 'main must not scroll horizontally').toBeLessThanOrEqual(2)
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(1440)
  await expect(page.getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeInViewport()
}

async function installLocalRuntimeApi(page: Page) {
  let setId = 0
  await page.route('**/api/runtime/**', async (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const body = (request.postDataJSON() ?? {}) as Record<string, unknown>
    if (path === '/api/runtime/exercises/settings') {
      await route.fulfill({ json: request.method() === 'GET' ? null : {} })
      return
    }
    if (path === '/api/runtime/sets') {
      await route.fulfill({ json: { setId: ++setId, exerciseSessionId: 7 } })
      return
    }
    if (path === '/api/runtime/exercises') {
      const sets = (body.sets as Array<Record<string, unknown>> | undefined) ?? []
      await route.fulfill({ json: {
        exerciseSessionId: 7,
        outcome: body.status === 'in_progress' ? 'completed' : body.status,
        exerciseId: body.exerciseSlug,
        exerciseSlug: body.exerciseSlug,
        title: body.exerciseName,
        subtitle: '3 подхода · результат сохранён',
        kind: body.kind,
        currentLoad: 'собственный вес',
        nextLoad: 'собственный вес',
        setResults: sets,
        totals: { setsCompleted: String(sets.length), repsOrTime: '31 повтор', volume: 'собственный вес', tempo: 'стабильный', bestSet: '12 повторов' },
        planVsFact: [],
        recommendation: 'Темп стабильный. В следующий раз сохраните тот же объём и постарайтесь повторить результат.',
        nextStepLabel: 'Открыть итог тренировки',
      } })
      return
    }
    if (path === '/api/runtime/workouts') {
      await route.fulfill({ json: {
        workoutSessionId: 42,
        outcome: body.status,
        title: 'Тренировка завершена',
        subtitle: 'Результат сохранён локально в визуальном тесте',
        metrics: [],
        exercises: [],
        muscleLoad: [],
        recommendation: 'Отдохните перед следующей тренировкой.',
        nextWorkout: 'По самочувствию',
      } })
      return
    }
    await route.fulfill({ status: 404, json: { detail: `Unexpected runtime call ${path}` } })
  })
}

test.describe('4K at Windows scale 150%', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/runtime/**', async (route) => {
      if (new URL(route.request().url()).pathname === '/api/runtime/exercises/settings') {
        await route.fulfill({ json: route.request().method() === 'GET' ? null : {} })
      } else {
        await route.fallback()
      }
    })
  })

  test('exercise setup is balanced and all controls fit', async ({ page }, testInfo) => {
    await openApp(page)
    await page.getByRole('navigation', { name: 'Основная навигация', exact: true }).getByRole('link', { name: 'Каталог', exact: true }).click()
    await page.getByPlaceholder('Найти упражнение...').fill('machine-pulldown')
    const card = page.getByRole('article', { name: 'Тяга верхнего блока в тренажёре' })
    await card.getByRole('button', { name: /^Открыть/ }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Начать упражнение', exact: true }).click()

    await expect(page.getByRole('region', { name: 'Настройка грифа', exact: true })).toBeInViewport()
    await expect(page.getByRole('region', { name: 'Параметры упражнения', exact: true })).toBeInViewport()
    await expect(page.locator('.rt-media-frame').first()).toBeInViewport()
    for (const group of ['Вес', 'Подходы', 'Повторы', 'Отдых']) {
      await expect(page.getByRole('group', { name: group, exact: true })).toBeInViewport()
    }
    await expect(page.getByRole('button', { name: 'Старт недоступен', exact: true })).toBeDisabled()
    await expectFitsKiosk(page)

    const screenshot = testInfo.outputPath('exercise-setup.png')
    await page.screenshot({ path: screenshot })
    await testInfo.attach('exercise-setup', { path: screenshot, contentType: 'image/png' })
  })

  test('exercise summary has a clear result and next step', async ({ page }, testInfo) => {
    await openApp(page)
    await page.route('**/api/exercises/push-up?*', (route) => route.fulfill({ json: getExerciseDetails('push-up') }))
    await installLocalRuntimeApi(page)
    await page.goto('/exercise-setup?source=catalog&slug=push-up', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Запустить упражнение', exact: true }).click()
    await page.waitForURL(/\/exercise-session\?/)

    for (let step = 0; step < 12 && !/\/exercise-summary/.test(page.url()); step++) {
      if (/\/exercise-session/.test(page.url())) {
        await page.getByRole('button', { name: 'Завершить подход', exact: true }).click()
        await page.waitForURL(/\/(rest|exercise-summary)\?/)
      } else {
        await page.getByRole('group', { name: 'Действия во время отдыха' }).getByRole('button', { name: 'Начать подход сейчас', exact: true }).click()
        await page.waitForURL(/\/exercise-session\?/)
      }
    }

    await expect(page).toHaveURL(/\/exercise-summary\?/)
    await expect(page.getByRole('list', { name: 'Итоги упражнения' })).toBeInViewport()
    await expect(page.getByRole('button', { name: 'Открыть итог тренировки', exact: true })).toBeInViewport()
    await expectFitsKiosk(page)

    const screenshot = testInfo.outputPath('exercise-summary.png')
    await page.screenshot({ path: screenshot })
    await testInfo.attach('exercise-summary', { path: screenshot, contentType: 'image/png' })
  })
})
