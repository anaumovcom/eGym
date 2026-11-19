import { expect, type Locator, type Page, type Route } from '@playwright/test'
import type { AchievementAward } from '../src/entities/achievement/model/types'
import { buildDashboardScenario } from '../src/mocks/data'
import { buildRuntimeExercisePlan, createRuntimeSession } from '../src/mocks/stage3-data'
import { getExerciseDetails } from '../src/mocks/stage2-data'
import { generatedExerciseEntries } from '../src/mocks/generated/exercises.generated'
import { test } from './fixtures/navigation'

const dayBExercises = ['cardio-knee-taps', 'smith-machine-incline-bench-press', 'smith-machine-inverted-row',
  'smith-machine-romanian-deadlift', 'smith-machine-drag-curl', 'smith-machine-skullcrusher']

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
  const stop = page.getByRole('button', { name: 'Аварийная остановка', exact: true })
  await expect(stop).toBeInViewport({ ratio: 1 })
  expect((await stop.boundingBox())!.height).toBeGreaterThanOrEqual(64)
}

async function expectWholePanel(panel: Locator) {
  await expect(panel).toBeInViewport({ ratio: 1 })
  expect(await panel.evaluate(node => Math.max(node.scrollHeight - node.clientHeight, node.scrollWidth - node.clientWidth)),
    'All content fits inside its panel').toBeLessThanOrEqual(2)
}

async function expectSetupVideosFillCells(technique: Locator) {
  for (const cell of await technique.locator(':scope > .rt-media').all()) {
    const video = cell.locator('video')
    await expect(video).toBeInViewport({ ratio: 1 })
    await expect(video).toHaveCSS('object-fit', 'contain')
    const [cellBox, videoBox] = await Promise.all([cell.boundingBox(), video.boundingBox()])
    const availableWidth = Math.min(cellBox!.width, cellBox!.height * 16 / 9)
    expect(videoBox!.width, 'The full camera frame uses the available space').toBeGreaterThanOrEqual(availableWidth - 3)
  }
}

async function installLocalRuntimeApi(page: Page) {
  let setId = 0
  const savedSets: Array<{ actualValue: number; setNumber: number; plannedValue: number; tempoLabel: string }> = []
  let exerciseResult: { exerciseSlug: string; name: string; status: string; result: string } | undefined
  await page.route('**/api/runtime/**', async (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const body = (request.postDataJSON() ?? {}) as Record<string, unknown>
    if (path === '/api/runtime/exercises/settings') {
      await route.fulfill({ json: request.method() === 'GET' ? null : {} })
      return
    }
    if (path === '/api/runtime/sets') {
      savedSets.push(request.postDataJSON())
      await route.fulfill({ json: { setId: ++setId, exerciseSessionId: 7 } })
      return
    }
    if (path === '/api/runtime/exercises') {
      exerciseResult = {
        exerciseSlug: String(body.exerciseSlug), name: String(body.exerciseName),
        status: body.status === 'completed' ? 'done' : 'partial',
        result: `${savedSets.length} подхода · ${savedSets.reduce((total, set) => total + set.actualValue, 0)} повторов`,
      }
      await route.fulfill({ json: {
        exerciseSessionId: 7,
        outcome: body.status === 'in_progress' ? 'completed' : body.status,
        exerciseId: body.exerciseSlug,
        exerciseSlug: body.exerciseSlug,
        title: body.exerciseName,
        subtitle: 'Результат сохранён',
        kind: body.kind,
        currentLoad: 'собственный вес',
        nextLoad: 'собственный вес',
        setResults: savedSets,
        totals: { setsCompleted: String(savedSets.length), repsOrTime: String(savedSets.reduce((sum, set) => sum + set.actualValue, 0)), volume: 'собственный вес', tempo: 'стабильный' },
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
        metrics: [{ label: 'длительность', value: '3 минуты', hint: 'за тренировку' }],
        exercises: exerciseResult ? [exerciseResult] : [],
        muscleLoad: [{ name: 'Грудь', status: 'medium', score: 46 }, { name: 'Трицепс', status: 'light', score: 28 }],
        recommendation: 'Отдохните перед следующей тренировкой.',
        nextWorkout: 'По самочувствию',
      } })
      return
    }
    if (path === '/api/runtime/workouts/42/awards') {
      await route.fulfill({ json: { awards: [] } })
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

  test('workspace navigation and catalog windows fit the 4K kiosk', async ({ page }, testInfo) => {
    const dashboard = buildDashboardScenario()
    dashboard.workouts = ['Спина и бицепс', 'Грудь и плечи', 'Ноги', 'Общая тренировка', 'Плечи и кор', 'Растяжка'].map((title, index) => ({
      id: `kiosk-${index}`, title, duration: '≈ 45 минут', lastStatus: 'completed',
      exercises: ['Жим с пола со штангой', 'Тяга верхнего блока в тренажёре', 'Сгибание рук с гантелями', 'Приседания с собственным весом', 'Разгибание ног в тренажёре', 'Горизонтальная тяга к поясу', 'Подъём гантелей через стороны'].map((name, row) => ({ slug: `fixture-${row}`, name })),
    }))
    await page.route((url) => url.pathname === '/api/dashboard', (route) => route.fulfill({ json: dashboard }))
    await openApp(page)
    const nav = page.getByRole('navigation', { name: 'Основная навигация', exact: true })
    const main = page.getByRole('main')
    await expect(nav.getByRole('link', { name: 'Главная', exact: true })).toHaveAttribute('aria-current', 'page')
    for (const link of await nav.getByRole('link').all()) {
      await expect(link).toBeInViewport({ ratio: 1 })
      expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(64)
    }
    const cards = main.getByRole('button', { name: /^Выбрать тренировку «/ })
    await expect(cards).toHaveCount(6)
    for (const card of await cards.all()) {
      await expect(card).toBeInViewport({ ratio: 1 })
      await expect(card.locator('.home-card-exercise').last()).toBeInViewport({ ratio: 1 })
    }
    const [navBox, mainBox] = await Promise.all([nav.boundingBox(), main.boundingBox()])
    expect(navBox!.y + navBox!.height).toBeLessThanOrEqual(mainBox!.y)
    await expectFitsKiosk(page)
    await page.screenshot({ path: testInfo.outputPath('dashboard-4k.png') })

    await cards.first().click()
    const preview = page.getByRole('dialog')
    const previewHeader = preview.locator('header')
    await expect(previewHeader.getByText('Нет сохранённых выполнений', { exact: true })).toBeVisible()
    await expect(previewHeader.getByRole('listitem')).toHaveText(['7 упражнений', '≈ 45 мин'])
    const summaryBoxes = await previewHeader.locator('p, li').evaluateAll(items => items.map(item => item.getBoundingClientRect().toJSON()))
    expect(Math.max(...summaryBoxes.map(box => box.top)), 'workout status and metrics share one row')
      .toBeLessThan(Math.min(...summaryBoxes.map(box => box.bottom)))
    const previewFooter = preview.locator('footer')
    const actions = previewFooter.getByRole('button')
    await expect(actions).toHaveText(['Назад', 'Изменить', 'Начать'])
    const actionRows = await actions.evaluateAll(buttons => new Set(buttons.map(button => (button as HTMLElement).offsetTop)).size)
    expect(actionRows, 'workout preview buttons share one row').toBe(1)
    await previewFooter.getByRole('button', { name: 'Назад', exact: true }).click()

    await nav.getByRole('link', { name: 'Каталог', exact: true }).click()
    await expect(nav.getByRole('link', { name: 'Каталог', exact: true })).toHaveAttribute('aria-current', 'page')
    const card = page.getByRole('article', { name: 'Тяга верхнего блока в тренажёре' })
    const openExercise = card.getByRole('button', { name: /^Открыть/ })
    await openExercise.press('Enter')
    const dialog = page.getByRole('dialog')
    const stop = dialog.getByRole('button', { name: 'Аварийная остановка', exact: true })
    await expect(stop).toBeInViewport({ ratio: 1 })
    await stop.click({ trial: true })
    const [dockBox, panelBox] = await Promise.all([
      dialog.locator('.forma-dialog-dock').boundingBox(),
      dialog.locator('.forma-dialog-panel').boundingBox(),
    ])
    expect(panelBox!.y).toBeGreaterThanOrEqual(dockBox!.y + dockBox!.height)
    expect(panelBox!.y + panelBox!.height).toBeLessThanOrEqual(1440)
    await page.screenshot({ path: testInfo.outputPath('catalog-preview-4k.png') })
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(openExercise).toBeFocused()
    await expect(nav.getByRole('link', { name: 'Каталог', exact: true })).toBeInViewport({ ratio: 1 })

    await nav.getByRole('link', { name: 'Усталость мышц', exact: true }).click()
    await expect(page).toHaveURL(/\/fatigue$/)
    await expect(page.locator('.fatigue-map')).toBeVisible()
    expect(await page.locator('html').getAttribute('data-forma-theme')).toBeNull()
    await nav.getByRole('link', { name: 'Главная', exact: true }).click()
    await expect(page.locator('html')).toHaveAttribute('data-forma-theme', 'broadcast-blue')
  })

  test('exercise details keep the video, tabs and start action in reach', async ({ page, navigationApi }, testInfo) => {
    await openApp(page)
    await page.goto(`/catalog/${navigationApi.exercise.slug}`)
    const tabs = page.getByRole('group', { name: 'Разделы упражнения' })
    const start = page.getByRole('button', { name: 'Начать упражнение', exact: true })
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(navigationApi.exercise.name)
    const video = page.locator('.exercise-detail-video video')
    await expect.poll(() => video.evaluate(node => (node as HTMLVideoElement).videoWidth)).toBeGreaterThan(0)
    await page.screenshot({ path: testInfo.outputPath('catalog-exercise-4k.png') })
    const firstSource = await video.locator('source').getAttribute('src')
    await page.getByRole('group', { name: 'Варианты видео' }).getByRole('button', { name: 'Сбоку' }).click()
    await expect(video.locator('source')).not.toHaveAttribute('src', firstSource!)
    for (const tab of await tabs.getByRole('button').all()) {
      await tab.click()
      await expectWholePanel(tabs)
      await expect(start).toBeInViewport({ ratio: 1 })
      await expect(page.locator('.exercise-detail-video')).toBeInViewport({ ratio: 1 })
      await expectFitsKiosk(page)
    }
    await page.goto(`/catalog/${navigationApi.exercise.slug}?tab=technique&scenario=no-video`)
    await expect(page.getByText('Видео для этого упражнения пока нет')).toBeInViewport({ ratio: 1 })
    await expect(page.getByRole('group', { name: 'Варианты видео' })).toHaveCount(0)
    await expect(start).toBeInViewport({ ratio: 1 })
    await expectFitsKiosk(page)
  })

  test('machine session keeps the video, set plan, rail and finish visible', async ({ page, navigationApi }, testInfo) => {
    const slug = navigationApi.exercise.slug
    await page.route((url) => url.pathname === '/api/hardware/status', (route) => route.fulfill({ json: {
      ...navigationApi.snapshot,
      motion: {
        ...navigationApi.snapshot.motion, barPositionMm: 980, leftPositionMm: 980, rightPositionMm: 979,
        lowerBoundMm: 640, upperBoundMm: 1320, repetitionCount: 9, amplitudePercent: 92, syncDeltaMm: 1,
      },
    } }))
    await openApp(page)
    // Set only the visual runtime state. The read-only fixture rejects all motor commands.
    await page.evaluate(async (slug) => {
      const storeModule = '/src/stores/runtime-store.ts'
      const { useRuntimeStore } = await import(storeModule)
      const store = useRuntimeStore.getState()
      store.initializeSession({ source: 'catalog', slug, calibrationState: 'saved' })
      store.startExercise()
    }, slug)
    await page.goto(`/exercise-session?source=catalog&slug=${encodeURIComponent(slug)}&calibration=saved`)
    const video = page.locator('.rt-media-frame')
    const counter = page.locator('.rt-counter')
    const plan = page.getByRole('complementary', { name: 'План упражнения' })
    const rail = page.getByRole('region', { name: 'Положение грифа' })
    const finish = page.getByRole('button', { name: 'Завершить подход', exact: true })
    const weight = page.getByRole('group', { name: 'Вес', exact: true })
    await expect(rail.getByLabel('Гриф · 980 мм', { exact: true })).toBeVisible()
    for (const element of [video, counter, plan, rail, finish, weight]) {
      await expect(element).toBeInViewport({ ratio: 1 })
    }
    const boxes = await Promise.all([video, counter, plan, rail].map((element) => element.boundingBox()))
    for (let index = 1; index < boxes.length; index++) {
      expect(boxes[index - 1]!.x + boxes[index - 1]!.width).toBeLessThanOrEqual(boxes[index]!.x + 1)
    }
    await expectFitsKiosk(page)
    await page.screenshot({ path: testInfo.outputPath('machine-session-4k.png') })
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
    const technique = page.getByRole('region', { name: 'Техника движения' })
    await expectWholePanel(technique)
    await expectSetupVideosFillCells(technique)
    for (const name of ['Настройка грифа', 'Параметры упражнения']) {
      await expectWholePanel(page.getByRole('region', { name, exact: true }))
    }
    for (const group of ['Вес', 'Подходы', 'Повторы', 'Отдых']) {
      await expect(page.getByRole('group', { name: group, exact: true })).toBeInViewport()
    }
    await expect(page.getByRole('button', { name: 'Старт недоступен', exact: true })).toBeDisabled()
    await expectFitsKiosk(page)

    const screenshot = testInfo.outputPath('exercise-setup.png')
    await page.screenshot({ path: screenshot })
    await testInfo.attach('exercise-setup', { path: screenshot, contentType: 'image/png' })
  })

  test('timed workout setup fits both knee-tap angles, instructions and editable targets', async ({ page, navigationApi }, testInfo) => {
    const slugs = dayBExercises
    const builder = navigationApi.builder
    builder.info.name = 'День B – Верх груди · Широчайшие · Задняя поверхность бедра'
    builder.groups = [{ id: 'day-b', kind: 'single', title: builder.info.name, items: slugs.map((slug, index) => ({
      id: slug, slug, name: getExerciseDetails(slug).name, muscleGroup: '', rest: '60 сек',
      load: index === 0 ? 'Вес тела' : '20 кг', loadType: index === 0 ? 'timed' : 'weighted', sets: index === 0 ? '1 × 60 сек' : '3 × 12',
    })) }]
    const cameras = generatedExerciseEntries.find(entry => entry.slug === slugs[0])!.videos.filter(video => video.gender === 'male')
    let videoCount = 2
    await page.route(url => url.pathname.startsWith('/api/exercises/'), route => {
      const details = getExerciseDetails(new URL(route.request().url()).pathname.split('/').at(-1)!)
      if (details.slug === slugs[0]) {
        details.videos = cameras.slice(0, videoCount).map(video => ({ ...video, label: video.view === 'side' ? 'Мужчина · Сбоку' : 'Мужчина · Спереди' }))
        details.previewVideoUrl = details.videos[0]?.url
      }
      return route.fulfill({ json: details })
    })
    await openApp(page)
    for (const count of [2, 1, 0]) {
      videoCount = count
      await page.goto(`/exercise-setup?source=builder&programId=${builder.selectedProgramId}&runId=cameras-${count}`, { waitUntil: 'domcontentloaded' })
      const technique = page.getByRole('region', { name: 'Техника движения', exact: true })
      const settings = page.getByRole('region', { name: 'Параметры упражнения', exact: true })
      await expect(page.getByRole('heading', { name: 'Касания коленей', exact: true })).toBeVisible()
      await expect(technique.locator('video')).toHaveCount(count)
      await expect(technique.getByRole('listitem')).toHaveText(getExerciseDetails(slugs[0]).shortSteps)
      await expectWholePanel(technique)
      await expectWholePanel(settings)
      await expect(settings.getByRole('region', { name: 'Дальше в тренировке' }).getByRole('listitem')).toHaveCount(3)
      expect((await technique.boundingBox())!.y).toBeCloseTo((await settings.boundingBox())!.y, 0)
      await expectSetupVideosFillCells(technique)
      for (const instruction of await technique.getByRole('listitem').all()) {
        await expect(instruction).toBeInViewport({ ratio: 1 })
      }
      await expectFitsKiosk(page)
      if (count === 2) {
        const clips = technique.locator('video')
        await expect.poll(() => clips.evaluateAll(nodes => nodes.every(node => (node as HTMLVideoElement).videoWidth > 0))).toBe(true)
        const [first, second] = await Promise.all([clips.first().boundingBox(), clips.last().boundingBox()])
        expect(first!.x + first!.width).toBeLessThanOrEqual(second!.x)
        expect(first!.width).toBeGreaterThanOrEqual(page.viewportSize()!.width * .32)
        expect(second!.width).toBeCloseTo(first!.width, 0)
        await page.screenshot({ path: testInfo.outputPath('knee-taps-setup-4k.png') })
        await page.getByRole('button', { name: 'Увеличить: Длительность' }).click()
        await expect(settings.getByRole('list', { name: 'План подходов' }).locator('strong')).toHaveText('1 мин 10 сек')
        await page.getByRole('button', { name: 'Запустить упражнение' }).click()
        await expect(page).toHaveURL(/\/exercise-session\?/)
        const timer = page.getByRole('group', { name: 'Таймер подхода' })
        await expect(timer.getByRole('timer')).toHaveText('1:10')
        const camera = page.getByRole('button', { name: 'Переключить видео упражнения' })
        const firstAngle = await camera.innerText()
        await camera.click()
        await expect(camera).not.toHaveText(firstAngle)
        await expect.poll(() => camera.locator('video').evaluate(node => (node as HTMLVideoElement).videoWidth)).toBeGreaterThan(0)
        await expectWholePanel(page.getByRole('complementary', { name: 'План упражнения' }))
        await expectFitsKiosk(page)
        await page.screenshot({ path: testInfo.outputPath('knee-taps-session-4k.png') })
        await timer.getByRole('button', { name: 'Старт' }).click()
        await expect(timer.getByRole('timer')).not.toHaveText('1:10')
        await timer.getByRole('button', { name: 'Пауза' }).click()
        await timer.getByRole('button', { name: 'Сбросить' }).click()
        await expect(timer.getByRole('timer')).toHaveText('1:10')
      }
    }
  })

  test('exercise summary has a clear result and next step', async ({ page }, testInfo) => {
    await openApp(page)
    await page.route('**/api/exercises/push-up?*', (route) => route.fulfill({ json: getExerciseDetails('push-up') }))
    await installLocalRuntimeApi(page)
    await page.goto('/exercise-setup?source=catalog&slug=push-up', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Запустить упражнение', exact: true }).click()
    await page.waitForURL(/\/exercise-session\?/)
    const finish = page.getByRole('button', { name: 'Завершить подход', exact: true })
    await expect(finish).toBeInViewport({ ratio: 1 })
    await expectFitsKiosk(page)
    await page.screenshot({ path: testInfo.outputPath('exercise-session-4k.png') })

    for (let step = 0; step < 12 && !/\/exercise-summary/.test(page.url()); step++) {
      if (/\/exercise-session/.test(page.url())) {
        const reps = page.getByRole('textbox', { name: 'Повторы' })
        await reps.fill(step === 0 ? '5' : '10')
        await reps.press('Enter')
        await page.getByRole('button', { name: 'Завершить подход', exact: true }).click()
        await page.waitForURL(/\/(rest|exercise-summary)\?/)
      } else {
        const next = page.getByRole('group', { name: 'Действия во время отдыха' }).getByRole('button', { name: 'Начать подход сейчас', exact: true })
        await expect(next).toBeInViewport({ ratio: 1 })
        await expectFitsKiosk(page)
        await expectWholePanel(page.locator('.rt-rest-body'))
        await expectWholePanel(page.locator('.rt-rest-details'))
        await expect(page.getByRole('button', { name: 'Дискомфорт · 7/10' })).toBeInViewport({ ratio: 1 })
        if (step === 1) await page.screenshot({ path: testInfo.outputPath('rest-4k.png') })
        await next.click()
        await page.waitForURL(/\/exercise-session\?/)
      }
    }

    await expect(page).toHaveURL(/\/exercise-summary\?/)
    await expect(page.getByRole('list', { name: 'Итоги упражнения' })).toBeInViewport()
    await expectWholePanel(page.getByRole('table', { name: 'Результаты подходов' }))
    await expect(page.getByRole('button', { name: 'Открыть итог тренировки', exact: true })).toBeInViewport()
    await expectFitsKiosk(page)

    const screenshot = testInfo.outputPath('exercise-summary.png')
    await page.screenshot({ path: screenshot })
    await testInfo.attach('exercise-summary', { path: screenshot, contentType: 'image/png' })
    await page.getByRole('button', { name: 'Подробно', exact: true }).click()
    await expect(page.getByRole('dialog').getByRole('table')).toBeInViewport({ ratio: 1 })
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Открыть итог тренировки' }).click()
    await expect(page.getByText('Результат сохранён в календаре')).toBeVisible()
    const results = page.getByRole('region', { name: 'Результаты упражнений' })
    await expect(results.locator('.rt-summary-item')).toHaveCount(1)
    await expect(results).toContainText('Отжимания')
    await expectWholePanel(results.getByRole('table', { name: 'Результаты подходов' }))
    await expectWholePanel(page.getByRole('region', { name: 'Усталость после тренировки' }))
    await expectFitsKiosk(page)
    await page.screenshot({ path: testInfo.outputPath('workout-summary-4k.png') })
  })

  test('forty workout awards fit beside six exercise results and open only on demand', async ({ page }, testInfo) => {
    const session = createRuntimeSession({ source: 'builder' })
    session.exercises = dayBExercises.map((slug, index) => buildRuntimeExercisePlan(slug, index + 1))
    session.workoutTitle = 'День B – Верх груди · Широчайшие · Задняя поверхность бедра'
    session.view = 'workout-summary'
    session.backendWorkoutSaved = true
    session.workoutSummary = {
      ...session.workoutSummary, workoutSessionId: 42, outcome: 'partial', subtitle: session.workoutTitle,
      metrics: [
        { label: 'длительность', value: '1 минута', hint: 'итог тренировки' },
        { label: 'энергия', value: '≈ 1 ккал', hint: '21 с работы · по времени подходов' },
        { label: 'упражнений', value: '0 / 6', hint: 'по плану' }, { label: 'подходов', value: '1 / 16', hint: 'засчитано' },
        { label: 'повторов', value: '0', hint: 'суммарно' }, { label: 'объём', value: '0 кг', hint: 'общий объём' },
      ],
      exercises: session.exercises.map((exercise, i) => ({
        exerciseId: exercise.id, name: exercise.name, result: i === 0 ? '21 сек' : '',
        status: i === 0 ? 'partial' : 'moved', remainingSetCount: i === 0 ? 0 : 3,
      })),
      muscleLoad: ['Икры', 'Квадрицепсы', 'Сгибатели бедра', 'Ягодицы', 'Пресс', 'Бицепс бедра']
        .map(name => ({ name, status: 'light', score: 1 })),
    }
    const titles = ['Это уже не пробный период', 'Месяц прочитан до дыр', 'Официант зовёт тренера', 'Рама представила родителей']
    const awards: AchievementAward[] = Array.from({ length: 40 }, (_, i) => ({
      grantId: i + 1, definitionId: `journal.workout-${i}`, group: 'journal', sourceWorkoutId: 42,
      status: 'earned', isNew: true, earnedAt: null, awardedAt: '2026-11-19T08:00:00Z',
      unit: 'тренировка', description: `Сохраните результат ${i + 1} тренировок.`,
      tier: { id: `journal.workout-${i}:t3`, tier: 3, tierName: 'Мастерство', threshold: i + 1, title: titles[i] ?? `Награда ${i + 1}`,
        phrase: `Фраза награды ${i + 1}`, rarity: 'rare', imageUrl: null, thumbnailUrl: null, audioUrl: null,
        imageState: 'missing', audioState: 'missing', earned: true, earnedAt: null, awardedAt: null, status: 'earned' },
    }))
    let rebuilding = true
    await page.route('**/api/runtime/workouts/42/awards?*', route => route.fulfill({ json: {
      workoutId: 42, awards: rebuilding ? [] : awards, isRebuilding: rebuilding,
    } }))
    await page.route('**/api/achievements/*/receipts/detail?*', route => route.fulfill({ json: { isNew: false } }))
    await openApp(page)
    await page.addInitScript(saved => {
      localStorage.setItem('egym-runtime-store', JSON.stringify({ state: { session: saved }, version: 0 }))
    }, session)
    await page.goto('/workout-summary', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('Обновляем достижения…')).toBeVisible()
    rebuilding = false
    const strip = page.getByRole('region', { name: 'Новые достижения' })
    const all = strip.getByRole('button', { name: 'Все достижения тренировки, 40' })
    await expect(all).toBeVisible()
    await page.evaluate(() => document.fonts.ready)
    await expect(strip.locator('.ach-award-name')).toHaveText(titles)
    await expect(strip.locator('.ach-image')).toHaveCount(4)
    await expect(strip.getByText('Мастерство', { exact: false })).toHaveCount(0)
    const report = page.locator('.rt-workout-summary-screen .rt-summary-body')
    const results = report.getByRole('region', { name: 'Результаты упражнений' })
    await expect(results.locator('.rt-summary-item')).toHaveCount(6)
    await expectWholePanel(report)
    await expectWholePanel(strip)
    const [metrics, firstResult, lastResult, fatigue, awardsBox, footer] = await Promise.all([
      report.getByRole('listitem').first(), results.getByRole('heading'), results.locator('.rt-summary-item').last(),
      report.getByRole('region', { name: 'Усталость после тренировки' }), strip, page.getByRole('group', { name: 'Действия после тренировки' }),
    ].map(locator => locator.boundingBox()))
    expect(metrics!.y + metrics!.height).toBeLessThan(firstResult!.y)
    expect(Math.max(lastResult!.y + lastResult!.height, fatigue!.y + fatigue!.height)).toBeLessThan(awardsBox!.y)
    expect(awardsBox!.y + awardsBox!.height).toBeLessThan(footer!.y)
    await expectFitsKiosk(page)
    await page.screenshot({ path: testInfo.outputPath('workout-awards-4k.png') })

    const fourth = strip.getByRole('button', { name: titles[3], exact: true })
    await fourth.click()
    const dialog = page.getByRole('dialog', { name: 'Достижения тренировки' })
    await expect(dialog.getByRole('heading', { name: titles[3], exact: true })).toBeVisible()
    await expect(dialog.getByText(awards[3].description)).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeInViewport({ ratio: 1 })
    await page.keyboard.press('Escape')
    await expect(fourth).toBeFocused()
    await all.click()
    const list = dialog.getByRole('region', { name: 'Все награды 40' })
    await expect(list.getByRole('button')).toHaveCount(40)
    await list.getByRole('button', { name: 'Награда 40', exact: true }).click()
    await expect(dialog.getByRole('heading', { name: 'Награда 40', exact: true })).toBeInViewport({ ratio: 1 })
    await expect(dialog.getByText('«Фраза награды 40»')).toBeInViewport({ ratio: 1 })
    await expect(dialog.getByRole('link', { name: 'В коллекцию наград' })).toHaveAttribute('href', '/achievements/journal.workout-39?tier=3')
    await page.screenshot({ path: testInfo.outputPath('workout-award-detail-4k.png') })
    await dialog.getByRole('button', { name: 'Закрыть' }).click()
    await expect(all).toBeFocused()
    await expect(results.getByRole('button').last()).toBeInViewport({ ratio: 1 })
  })

  test('muscle hints stay inside the dashboard map and clear the active region', async ({ page }, testInfo) => {
    const fixture = buildDashboardScenario()
    fixture.muscles = [
      { name: 'Грудь', status: 'critical', score: 90 },
      { name: 'Широчайшие', status: 'no_data', score: 0 },
      { name: 'Икры', status: 'ready', score: 0 },
    ]
    await page.route((url) => url.pathname === '/api/dashboard', route => route.fulfill({ json: fixture }))
    await openApp(page)
    const map = page.getByRole('region', { name: 'Восстановление мышц' })
    const tooltip = map.getByRole('tooltip')
    for (const [view, name] of [['front', 'Грудь'], ['back', 'Широчайшие'], ['back', 'Икры']]) {
      const muscle = map.locator(`.home-recovery-figure[id$="-${view}"]`).getByRole('button', { name: new RegExp(`^${name}:`) }).first()
      await muscle.locator('path').first().hover()
      await expect(tooltip.locator('strong')).toHaveText(name)
      const card = (await map.boundingBox())!
      const hint = (await tooltip.boundingBox())!
      const region = (await muscle.boundingBox())!
      expect(hint.x).toBeGreaterThan(card.x)
      expect(hint.y).toBeGreaterThan(card.y)
      expect(hint.x + hint.width).toBeLessThan(card.x + card.width)
      expect(hint.y + hint.height).toBeLessThan(card.y + card.height)
      expect(hint.y + hint.height <= region.y || hint.y >= region.y + region.height).toBe(true)
      if (name === 'Широчайшие') await map.screenshot({ path: testInfo.outputPath('dashboard-muscle-hint.png') })
      await map.getByRole('heading').hover()
      await expect(tooltip).toHaveCount(0)
    }
  })

  test('home cards show eight complete exercise names and keep the ninth in the full plan', async ({ page }, testInfo) => {
    const fixture = buildDashboardScenario()
    const plans = [
      { id: 'day-a', title: 'День A – Грудь · Спина · Квадрицепсы', minutes: 42, daysAgo: 24, slugs: [
        'cardio-quick-feet', 'smith-machine-bench-press', 'smith-machine-overhand-row', 'smith-machine-squat',
        'smith-machine-upright-row', 'smith-machine-calf-raise', 'dumbbell-bulgarian-split-squat', 'smith-machine-assisted-pullup',
      ] },
      { id: 'day-b', title: 'День B – Верх груди · Широчайшие · Задняя поверхность бедра', minutes: 42, daysAgo: 0, slugs: [
        'cardio-knee-taps', 'smith-machine-incline-bench-press', 'smith-machine-inverted-row', 'smith-machine-romanian-deadlift',
        'smith-machine-drag-curl', 'smith-machine-skullcrusher', 'single-legged-romanian-deadlifts', 'machine-plate-loaded-low-incline-bench-press',
      ] },
      { id: 'day-c', title: 'День C – Плечи · Спина · Ноги · Трицепсы', minutes: 48, daysAgo: 26, slugs: [
        'butt-kick', 'smith-machine-seated-overhead-press', 'underhand-pulldown', 'smith-machine-narrow-stance-squat',
        'smith-machine-close-grip-bench-press', 'smith-machine-romanian-deadlift', 'cable-rope-overhead-tricep-extension', 'smith-machine-staggered-deadlift',
      ] },
    ]
    fixture.workouts = plans.map(({ id, title, minutes, daysAgo, slugs }) => ({
      id, title, duration: `≈ ${minutes + 8} минут`, lastStatus: 'completed',
      lastPerformedAt: daysAgo ? new Date(Date.now() - daysAgo * 86_400_000).toISOString() : null,
      exercises: slugs.map((slug) => ({ slug, name: getExerciseDetails(slug).name })),
    }))
    const active = plans[1]
    const session = createRuntimeSession({ source: 'builder', programId: active.id })
    session.exercises = active.slugs.map((slug, index) => {
      const exercise = buildRuntimeExercisePlan(slug, index + 1)
      return { ...exercise, plan: exercise.plan.slice(0, index === 0 ? 1 : 3) }
    })
    session.workoutTitle = active.title
    session.currentExerciseId = session.exercises[0].id
    await page.route((url) => url.pathname === '/api/dashboard', route => route.fulfill({ json: fixture }))
    await openApp(page)
    async function loadExample() {
      await page.evaluate(value => localStorage.setItem('egym-runtime-store', JSON.stringify({ version: 0, state: { session: value } })), session)
      await page.reload()
      await expect(page.locator('.home-resume')).toContainText('Касания коленей · подход 1')
      await page.evaluate(() => document.fonts.ready)
    }

    const cards = page.locator('.home-workout-grid .home-workout-card')
    async function expectCardsToFit() {
      await expect(cards).toHaveCount(fixture.workouts!.length)
      const firstTop = (await cards.first().boundingBox())!.y
      const viewport = page.viewportSize()!
      for (const [index, workout] of fixture.workouts!.entries()) {
        const card = cards.nth(index)
        const names = card.locator('.home-card-exercise-name')
        await expect(names).toHaveText(workout.exercises.map(({ name }) => name))
        await expect(card.locator('.home-card-more')).toHaveCount(0)
        const clipped = await names.evaluateAll(nodes => nodes.filter(node => {
          const range = document.createRange()
          range.selectNodeContents(node)
          const row = node.parentElement!.getBoundingClientRect()
          return [...range.getClientRects()].some(rect => rect.left < row.left - 1 || rect.right > row.right + 1 ||
            rect.top < row.top - 1 || rect.bottom > row.bottom + 1)
        }).map(node => node.textContent))
        expect(clipped, `Full exercise names at ${viewport.width}px`).toEqual([])
        expect(await card.evaluate(node => Math.max(node.scrollHeight - node.clientHeight, node.scrollWidth - node.clientWidth)),
          'All content including the footer fits inside its card').toBeLessThanOrEqual(1)
        if (Math.abs((await card.boundingBox())!.y - firstTop) < 1) {
          await expect(card, `Whole first row at ${viewport.width}×${viewport.height}`).toBeInViewport({ ratio: 1 })
          await expect(card.locator('.home-card-footer')).toBeInViewport({ ratio: 1 })
        }
      }
      if (Math.abs((await cards.last().boundingBox())!.y - firstTop) < 1) {
        const grid = page.locator('.home-workout-grid')
        expect(await grid.evaluate(node => node.scrollHeight - node.clientHeight),
          `A single row has no scrollbar at ${viewport.width}×${viewport.height}`).toBeLessThanOrEqual(1)
      }
    }

    await loadExample()
    const artwork = page.locator('.home-card-equipment, .home-broadcast-hero-art img')
    await expect(artwork).toHaveCount(4)
    await artwork.evaluateAll(nodes => Promise.all(nodes.map(node => (node as HTMLImageElement).decode())))
    expect(new Set(await artwork.evaluateAll(nodes => nodes.map(node => (node as HTMLImageElement).src))).size).toBe(4)
    await page.mouse.move(1, 1)
    await expectCardsToFit()
    await page.screenshot({ path: testInfo.outputPath('home-eight-full-screen.png') })

    const threeWorkouts = fixture.workouts
    fixture.workouts = [...threeWorkouts, ...threeWorkouts.map(workout => ({ ...workout, id: `extra-${workout.id}` }))]
    await loadExample()
    await expectCardsToFit()

    const longestExercises = [...generatedExerciseEntries].sort((left, right) => right.nameRu.length - left.nameRu.length)
      .slice(0, 8).map(({ slug, nameRu }) => ({ slug, name: nameRu }))
    fixture.workouts = [{ ...threeWorkouts[0], exercises: longestExercises }, ...threeWorkouts.slice(1)]
    await loadExample()
    await expectCardsToFit()
    fixture.workouts = threeWorkouts.map((workout, index) => ({
      ...workout, duration: `≈ ${plans[index].minutes} минут`, exercises: workout.exercises.slice(0, 6),
    }))
    session.exercises = session.exercises.slice(0, 6)
    await loadExample()
    await expectCardsToFit()
    await page.screenshot({ path: testInfo.outputPath('home-six-full-screen.png') })

    fixture.workouts = threeWorkouts
    const ninth = getExerciseDetails('smith-machine-hip-thrust')
    fixture.workouts[0].exercises.push({ slug: ninth.slug, name: ninth.name })
    await page.reload()
    await expect(cards.first().locator('.home-card-more')).toHaveText('+ ещё 1')
    await expect(cards.first().locator('.home-card-exercise-name')).toHaveCount(8)
    await cards.first().click()
    await expect(page.getByRole('dialog').getByRole('list', { name: 'План тренировки' }).getByText(ninth.name)).toBeVisible()
  })

  test('recovery map fits the 4K kiosk before and after resuming a workout', async ({ page }) => {
    const session = createRuntimeSession({ source: 'builder', programId: 'resume-layout' })
    const fixture = buildDashboardScenario()
    fixture.workouts = [{
      id: session.programId!, title: session.workoutTitle, duration: '45 минут',
      exercises: session.exercises.map(({ slug, name }) => ({ slug, name })),
    }]
    await page.route((url) => url.pathname === '/api/dashboard', (route) => route.fulfill({ json: fixture }))
    await openApp(page)
    const map = page.locator('.home-recovery')
    const resume = page.locator('.home-resume')
    await expect(map.locator('.home-recovery-figure svg').first()).toBeVisible()
    await expect(resume).toHaveCount(0)
    await page.evaluate(() => document.fonts.ready)
    async function checkArtwork() {
      await expectFitsKiosk(page)
      const pictures = map.locator('svg[data-figure="portrait"] > image')
      await expect(pictures).toHaveCount(2)
      const header = (await map.locator('.home-recovery-heading').boundingBox())!
      const front = (await pictures.first().boundingBox())!
      const back = (await pictures.last().boundingBox())!
      const legend = (await map.locator('.home-recovery-scale').boundingBox())!
      for (const figure of [front, back]) {
        expect(figure.height).toBeGreaterThan(0)
        expect(figure.y).toBeGreaterThanOrEqual(header.y + header.height - 1)
        expect(figure.y + figure.height).toBeLessThanOrEqual(legend.y + 1)
      }
      expect(front.x + front.width).toBeLessThanOrEqual(back.x + 1)
      expect(Math.abs(front.y + front.height / 2 - back.y - back.height / 2)).toBeLessThanOrEqual(1)
      await expect(map.locator('.home-recovery-scale')).toBeInViewport({ ratio: 1 })
    }
    await checkArtwork()
    const before = await map.boundingBox()
    await page.evaluate((session) => {
      localStorage.setItem('egym-runtime-store', JSON.stringify({ version: 0, state: { session } }))
    }, session)
    await page.reload()
    await expect(resume).toBeVisible()
    await expect(map.locator('.home-recovery-figure svg').first()).toBeVisible()
    await page.evaluate(() => document.fonts.ready)
    expect(await map.boundingBox()).toEqual(before)
    await checkArtwork()
  })
})
