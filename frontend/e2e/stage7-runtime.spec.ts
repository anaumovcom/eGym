import { expect, type Page, type Route } from '@playwright/test'
import { openAppAsAlexey, openCatalogExerciseSetup, test } from './fixtures/navigation'

async function expectFitsScreen(page: Page, height: number) {
  const main = page.getByRole('main')
  expect(await main.evaluate((node) => node.scrollHeight - node.clientHeight), 'main must not scroll vertically').toBeLessThanOrEqual(2)
  expect(await main.evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(2)
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(height)
  const stop = page.getByRole('button', { name: 'Аварийная остановка', exact: true })
  await expect(stop).toHaveCount(1)
  await expect(stop).toBeInViewport()
  expect((await stop.boundingBox())!.height).toBeGreaterThanOrEqual(64)
}

async function expectLargeControl(page: Page, name: string | RegExp) {
  const control = page.getByRole('button', { name, exact: typeof name === 'string' })
  await expect(control).toBeInViewport()
  expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(64)
}

// Runtime saves are fulfilled locally so no real workout is written by the browser tests.
async function installLocalRuntimeApi(page: Page) {
  const writes: Array<{ path: string; body: Record<string, unknown> }> = []
  let setId = 0
  await page.route('**/api/runtime/**', async (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const body = (request.postDataJSON() ?? {}) as Record<string, unknown>
    writes.push({ path, body })
    if (path === '/api/runtime/sets') {
      await route.fulfill({ json: { setId: ++setId, exerciseSessionId: 7 } })
      return
    }
    if (path === '/api/runtime/exercises') {
      const sets = (body.sets as unknown[] | undefined) ?? []
      await route.fulfill({ json: {
        exerciseSessionId: 7, outcome: body.status === 'in_progress' ? 'completed' : body.status, exerciseId: body.exerciseSlug, exerciseSlug: body.exerciseSlug,
        title: body.exerciseName, subtitle: 'Результат сохранён локально в тесте', kind: body.kind, currentLoad: 'свой вес', nextLoad: 'свой вес',
        setResults: sets, totals: { setsCompleted: String(sets.length), repsOrTime: '—', volume: '—', tempo: 'хорошо' }, planVsFact: [],
        recommendation: 'Нагрузка подобрана верно.', nextStepLabel: 'Открыть итог тренировки',
      } })
      return
    }
    if (path === '/api/runtime/workouts') {
      await route.fulfill({ json: {
        workoutSessionId: 42, outcome: body.status, title: 'Тренировка завершена', subtitle: String(body.subtitle ?? ''),
        metrics: [{ label: 'Упражнения', value: '1', hint: 'выполнено' }, { label: 'Подходы', value: String(setId), hint: 'сохранено' }],
        exercises: [{ exerciseSlug: 'push-up', exerciseId: 'push-up', name: 'Отжимания', result: 'выполнено', status: 'done' }],
        muscleLoad: [], recommendation: 'Отдохните 48 часов перед следующей нагрузкой на грудь.', nextWorkout: 'Следующая тренировка — через 2 дня', feeling: body.feeling, discomfort: body.discomfort,
      } })
      return
    }
    await route.fulfill({ status: 404, json: { detail: `Unexpected runtime call ${path}` } })
  })
  return writes
}

for (const viewport of [{ width: 3840, height: 2160 }, { width: 1920, height: 1080 }]) {
  test.describe(`${viewport.width}x${viewport.height} stage 7 runtime`, () => {
    test.use({ viewport, deviceScaleFactor: 1 })

    test('user selection is a narrow centred block without a dead add-user action', async ({ page }, testInfo) => {
      await page.goto('/', { waitUntil: 'domcontentloaded' })
      await expect(page.getByRole('heading', { name: 'Кто тренируется?' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Добавить пользователя' })).toHaveCount(0)
      await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toHaveCount(0)
      const cards = page.getByRole('region', { name: 'Профили' }).getByRole('article')
      await expect(cards).toHaveCount(2)
      for (const name of ['Алексей', 'Елена']) {
        await expectLargeControl(page, `Выбрать профиль ${name}`)
      }
      const block = await page.locator('.users-screen').boundingBox()
      expect(Math.abs(block!.x + block!.width / 2 - viewport.width / 2)).toBeLessThan(2)
      expect(block!.width).toBeLessThanOrEqual(viewport.width * 0.8)
      await expectLargeControl(page, 'Гость')
      await expectFitsScreen(page, viewport.height)
      const screenshot = testInfo.outputPath('user-selection.png')
      await page.screenshot({ path: screenshot })
      await testInfo.attach('user-selection', { path: screenshot, contentType: 'image/png' })
    })

    test('exercise setup keeps the exercise, parameters and calibration visible without scroll', async ({ page }, testInfo) => {
      await openAppAsAlexey(page)
      await openCatalogExerciseSetup(page)
      // Calibration is missing for this machine exercise: the block is large and the start stays gated.
      const calibration = page.getByRole('region', { name: 'Калибровка амплитуды' })
      await expect(calibration).toBeInViewport()
      await expect(page.getByRole('button', { name: 'Старт недоступен' })).toBeDisabled()
      await expect(page.getByRole('button', { name: 'Зафиксировать нижнюю точку' })).toBeInViewport()
      await expect(page.getByRole('heading', { level: 2, name: 'Тяга верхнего блока в тренажёре' })).toBeInViewport()
      for (const group of ['Вес', 'Подходы', 'Повторы', 'Отдых']) {
        await expect(page.getByRole('group', { name: group })).toBeInViewport()
      }
      await expect(page.locator('.rt-media-frame')).toBeInViewport()
      await expectLargeControl(page, 'Назад')
      await expectLargeControl(page, 'Завершить тренировку')
      await expectFitsScreen(page, viewport.height)

      await page.getByRole('button', { name: 'Режим тренировки' }).click()
      const dialog = page.getByRole('dialog', { name: 'Режим тренировки' })
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeInViewport()
      await expect(page.getByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveCount(1)
      await page.keyboard.press('Escape')
      await expect(dialog).toHaveCount(0)
      const screenshot = testInfo.outputPath('exercise-setup.png')
      await page.screenshot({ path: screenshot })
      await testInfo.attach('exercise-setup', { path: screenshot, contentType: 'image/png' })
    })

    test('bodyweight runtime: session, rest and summaries fit the screen with one primary action', async ({ page }, testInfo) => {
      await openAppAsAlexey(page)
      const writes = await installLocalRuntimeApi(page)
      await page.goto('/exercise-setup?source=catalog&slug=push-up', { waitUntil: 'domcontentloaded' })
      await expect(page).toHaveURL(/\/exercise-session\?source=catalog&slug=push-up$/)

      const finish = page.getByRole('button', { name: 'Завершить подход', exact: true })
      await expect(finish).toHaveAttribute('data-variant', 'primary')
      await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toHaveCount(0)
      await expect(page.getByRole('group', { name: 'Повторы' })).toBeInViewport()
      // Bodyweight exercise: no meaningless weight stepper, the load is shown as a chip instead.
      await expect(page.getByRole('group', { name: 'Вес' })).toHaveCount(0)
      await expect(page.locator('.rt-media-frame')).toBeInViewport()
      await expect(page.getByRole('button', { name: /^(Выполнено|Частично|Пропуск)$/ })).toHaveCount(0)
      await expectLargeControl(page, 'Завершить подход')
      await expectFitsScreen(page, viewport.height)
      const sessionShot = testInfo.outputPath('exercise-session.png')
      await page.screenshot({ path: sessionShot })
      await testInfo.attach('exercise-session', { path: sessionShot, contentType: 'image/png' })

      let restChecked = false
      for (let step = 0; step < 12 && !/\/exercise-summary/.test(page.url()); step++) {
        if (/\/exercise-session/.test(page.url())) {
          await finish.click()
          await expect(page).toHaveURL(/\/(rest|exercise-summary)\?/)
          continue
        }
        await expect(page).toHaveURL(/\/rest\?/)
        const actions = page.getByRole('group', { name: 'Действия во время отдыха' })
        await expect(actions.getByRole('button')).toHaveCount(3)
        await expect(page.getByRole('timer')).toBeInViewport()
        await expect(page.getByText('Дальше')).toBeInViewport()
        if (!restChecked) {
          for (const name of ['+30 сек', 'Пропустить', 'Завершить тренировку']) {
            await expectLargeControl(page, name)
          }
          await expectFitsScreen(page, viewport.height)
          const restShot = testInfo.outputPath('rest.png')
          await page.screenshot({ path: restShot })
          await testInfo.attach('rest', { path: restShot, contentType: 'image/png' })
          restChecked = true
        }
        await actions.getByRole('button', { name: 'Пропустить', exact: true }).click()
        await expect(page).toHaveURL(/\/exercise-session\?/)
      }

      await expect(page).toHaveURL(/\/exercise-summary\?/)
      await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toHaveCount(0)
      await expectLargeControl(page, 'Открыть итог тренировки')
      await expect(page.getByRole('list', { name: 'Итоги упражнения' })).toBeInViewport()
      await expectFitsScreen(page, viewport.height)
      await page.getByRole('button', { name: 'Подробно', exact: true }).click()
      const details = page.getByRole('dialog', { name: /^Подробно:/ })
      await expect(details.getByRole('region', { name: 'Подходы' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveCount(1)
      await page.keyboard.press('Escape')
      await expect(details).toHaveCount(0)
      const exerciseShot = testInfo.outputPath('exercise-summary.png')
      await page.screenshot({ path: exerciseShot })
      await testInfo.attach('exercise-summary', { path: exerciseShot, contentType: 'image/png' })

      await page.getByRole('button', { name: 'Открыть итог тренировки' }).click()
      await expect(page).toHaveURL(/\/workout-summary\?/)
      await expect(page.getByRole('heading', { level: 1, name: 'Тренировка завершена' })).toBeVisible()
      await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible()
      await expectLargeControl(page, 'На главную')
      await expect(page.getByRole('button', { name: /фото|Сделать снимок/i })).toHaveCount(0)
      await expect(page.getByText('Результат сохранён в календаре')).toBeVisible()
      await expectFitsScreen(page, viewport.height)
      await page.getByRole('button', { name: 'Подробно', exact: true }).click()
      const workoutDetails = page.getByRole('dialog', { name: /^Подробно:/ })
      await expect(workoutDetails.getByRole('region', { name: 'Усталость мышц' })).toBeVisible()
      await page.keyboard.press('Escape')
      const workoutShot = testInfo.outputPath('workout-summary.png')
      await page.screenshot({ path: workoutShot })
      await testInfo.attach('workout-summary', { path: workoutShot, contentType: 'image/png' })

      expect(writes.some(({ path }) => path === '/api/runtime/workouts')).toBe(true)
      expect(writes.every(({ path }) => path.startsWith('/api/runtime/'))).toBe(true)
      await page.getByRole('button', { name: 'На главную' }).click()
      await expect(page).toHaveURL(/\/dashboard$/)
    })
  })
}
