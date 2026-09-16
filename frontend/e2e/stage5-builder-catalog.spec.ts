import { expect } from '@playwright/test'
import { openAppAsAlexey, savedBrowserState, test } from './fixtures/navigation'

for (const viewport of [{ width: 3840, height: 2160 }, { width: 1920, height: 1080 }]) {
  test(`workouts list, central editor and add flow at ${viewport.width}x${viewport.height}`, async ({ page, navigationApi }, testInfo) => {
    await page.setViewportSize(viewport)
    await openAppAsAlexey(page)
    const state = await savedBrowserState(page)
    await page.goto('/builder')

    // BUILD-1: list first, editor only after a choice.
    await expect(page.getByRole('heading', { level: 1, name: 'Мои тренировки' })).toBeVisible()
    const card = page.getByRole('button', { name: `Открыть тренировку «${navigationApi.builder.info.name}»` })
    await expect(card).toBeInViewport({ ratio: 1 })
    await expect(page.getByRole('button', { name: /Выбрать упражнение/ })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'JSON', exact: true })).toHaveCount(0)
    const listShot = testInfo.outputPath('builder-list.png')
    await page.screenshot({ path: listShot })
    await testInfo.attach('builder-list', { path: listShot, contentType: 'image/png' })

    await card.click()
    await expect(page).toHaveURL(/\/builder\?programId=e2e-saved-workout$/)
    await expect(page.getByRole('heading', { level: 1, name: new RegExp(navigationApi.builder.info.name) })).toBeVisible()
    const main = page.locator('main')
    expect(await main.evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(2)

    // BUILD-2/3: compact list on the side, one expanded exercise in the centre.
    const side = page.getByRole('complementary', { name: 'Упражнения тренировки' })
    const items = side.getByRole('button', { name: /^Выбрать упражнение / })
    expect(await items.count()).toBeGreaterThanOrEqual(2)
    const stage = page.getByRole('region', { name: 'Выбранное упражнение' })
    await expect(stage.getByRole('heading', { level: 2 })).toBeVisible()
    await expect(stage.getByRole('group', { name: 'Повторы' })).toHaveCount(1)
    await expect(page.getByRole('group', { name: 'Повторы' })).toHaveCount(1)
    for (const item of await items.all()) {
      const box = (await item.boundingBox())!
      expect(box.height).toBeGreaterThanOrEqual(64)
    }

    // BUILD-4: big −/+ controls with an explicit unit.
    const weight = stage.getByRole('group', { name: 'Вес' })
    await expect(weight.getByText('кг')).toBeVisible()
    for (const name of ['Уменьшить: Вес', 'Увеличить: Вес']) {
      const button = weight.getByRole('button', { name })
      await expect(button).toBeInViewport()
      expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(64)
    }

    // BUILD-6/7: no JSON, persistent bottom actions with separated delete.
    await expect(page.getByRole('button', { name: 'JSON', exact: true })).toHaveCount(0)
    const actions = page.getByRole('group', { name: 'Действия с тренировкой' })
    await expect(actions.getByRole('button', { name: 'Готово', exact: true })).toBeInViewport()
    await expect(actions.getByRole('button', { name: 'Удалить тренировку', exact: true })).toBeInViewport()
    const doneBox = (await actions.getByRole('button', { name: 'Готово', exact: true }).boundingBox())!
    const deleteBox = (await actions.getByRole('button', { name: 'Удалить тренировку', exact: true }).boundingBox())!
    expect(deleteBox.x - (doneBox.x + doneBox.width)).toBeGreaterThan(200)
    const actionsBox = (await actions.boundingBox())!
    expect(actionsBox.y + actionsBox.height).toBeLessThanOrEqual(viewport.height)
    const stopBox = (await page.getByRole('button', { name: 'Аварийная остановка', exact: true }).boundingBox())!
    expect(stopBox.y + stopBox.height).toBeLessThanOrEqual(actionsBox.y)

    const editorShot = testInfo.outputPath('builder-editor.png')
    await page.screenshot({ path: editorShot })
    await testInfo.attach('builder-editor', { path: editorShot, contentType: 'image/png' })

    // BUILD-5: add is a two-step central scenario; cancel writes nothing.
    // The saved plan already contains the only fixture exercise, so expose a second one locally.
    const base = navigationApi.exercise
    const extra = { ...base, slug: 'e2e-second-exercise', name: 'Второе упражнение e2e', secondaryName: 'Second e2e' }
    await page.route((url) => url.pathname === '/api/exercises', (route) => route.fulfill({ json: { items: [base, extra], total: 2, availableFilters: { muscles: [], equipment: [], difficulty: [], force: [], mechanic: [], grips: [] } } }))
    await page.route((url) => url.pathname === '/api/exercises/e2e-second-exercise', (route) => route.fulfill({ json: extra }))
    await side.getByRole('button', { name: 'Добавить упражнение' }).first().click()
    const picker = page.getByRole('dialog', { name: 'Добавить упражнение' })
    await expect(picker).toBeVisible()
    await expect(picker.getByText(/Шаг 1 из 2/)).toBeVisible()
    await picker.getByRole('button', { name: 'Выбрать Второе упражнение e2e', exact: true }).click()
    await expect(page.getByRole('dialog', { name: 'Настройте подходы' })).toBeVisible()
    await expect(page.getByText(/шаг 2 из 2/)).toBeVisible()
    await expect(page.getByRole('group', { name: 'Подходы' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Добавить в тренировку', exact: true })).toBeInViewport()
    const pickerShot = testInfo.outputPath('builder-picker.png')
    await page.screenshot({ path: pickerShot })
    await testInfo.attach('builder-picker', { path: pickerShot, contentType: 'image/png' })
    await page.getByRole('button', { name: 'К списку', exact: true }).click()
    await expect(page.getByRole('dialog', { name: 'Добавить упражнение' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)

    // Deleting requires confirmation and is cancellable.
    await actions.getByRole('button', { name: 'Удалить тренировку', exact: true }).click()
    const confirm = page.getByRole('dialog', { name: /Удалить тренировку/ })
    await expect(confirm.getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeInViewport()
    await confirm.getByRole('button', { name: 'Отмена', exact: true }).click()
    await expect(confirm).toHaveCount(0)

    await actions.getByRole('button', { name: 'Готово', exact: true }).click()
    await expect(page).toHaveURL(/\/builder$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Мои тренировки' })).toBeVisible()
    expect(await savedBrowserState(page)).toEqual(state)
    expect(navigationApi.requests.filter(({ method }) => method !== 'GET' && method !== 'POST')).toEqual([])
    expect(navigationApi.requests.filter(({ path }) => path.startsWith('/api/runtime'))).toEqual([])
  })

  test(`catalog search, collapsed filters, translated categories and add-to-workout at ${viewport.width}x${viewport.height}`, async ({ page, navigationApi }, testInfo) => {
    await page.setViewportSize(viewport)
    await openAppAsAlexey(page)
    await page.goto('/catalog')
    await expect(page.getByRole('heading', { level: 1, name: 'Каталог упражнений' })).toBeVisible()

    // CAT-1: large central search; CAT-2: three compact filter entries plus a panel.
    const search = page.getByRole('searchbox', { name: 'Поиск упражнения' })
    const searchBox = (await search.locator('..').boundingBox())!
    expect(searchBox.height).toBeGreaterThanOrEqual(64)
    expect(Math.abs(searchBox.x + searchBox.width / 2 - viewport.width / 2)).toBeLessThan(40)
    for (const name of ['Мышцы', 'Оборудование', 'Избранное', 'Все фильтры']) await expect(page.getByRole('button', { name, exact: true })).toBeInViewport()
    await expect(page.getByText('Быстрые действия')).toHaveCount(0)
    await expect(page.getByText('Как выбрать упражнение')).toHaveCount(0)

    // CAT-3/4: no raw English category tokens on tiles; one action per card.
    const card = page.getByRole('article', { name: 'Тяга верхнего блока в тренажёре' })
    await expect(card).toBeVisible()
    await expect(card.getByText('Machine Pulldown')).toHaveCount(0)
    await expect(card.getByText(/^(Machine|Bodyweight|Abdominals|Front-Shoulders|Bosu-Ball|Intermediate)$/)).toHaveCount(0)
    await expect(card.getByRole('button', { name: /^Открыть/ })).toHaveCount(1)
    await expect(card.getByRole('button', { name: /избранно/ })).toHaveCount(1)
    expect((await card.boundingBox())!.height).toBeGreaterThanOrEqual(viewport.width === 3840 ? 320 : 220)
    const catalogShot = testInfo.outputPath('catalog.png')
    await page.screenshot({ path: catalogShot })
    await testInfo.attach('catalog', { path: catalogShot, contentType: 'image/png' })

    await page.getByRole('button', { name: 'Мышцы', exact: true }).click()
    const filters = page.getByRole('dialog', { name: 'Мышцы' })
    await expect(filters).toBeVisible()
    await expect(filters.locator('.picker-chip', { hasText: /^[A-Za-z-]+$/ })).toHaveCount(0)
    const firstChip = filters.locator('.picker-chip').first()
    const chipName = await firstChip.textContent()
    await firstChip.click()
    await expect(firstChip).toHaveAttribute('aria-pressed', 'true')
    await filters.getByRole('button', { name: 'Готово', exact: true }).click()
    await expect(filters).toHaveCount(0)
    const active = page.getByLabel('Активные фильтры')
    await expect(active.getByRole('button', { name: `Убрать фильтр Мышцы: ${chipName}` })).toBeVisible()
    await expect(page).toHaveURL(/muscles=/)
    await active.getByRole('button', { name: 'Сбросить всё', exact: true }).click()
    await expect(active).toHaveCount(0)
    await expect(page).not.toHaveURL(/muscles=/)

    // CAT-5: two actions in details; add goes through a workout choice and lands on the configuration step.
    await card.getByRole('button', { name: /^Открыть/ }).click()
    const details = page.getByRole('dialog', { name: 'Тяга верхнего блока в тренажёре' })
    await expect(details.getByRole('button', { name: 'Начать упражнение', exact: true })).toBeVisible()
    await expect(details.getByRole('button', { name: 'Добавить в тренировку', exact: true })).toBeVisible()
    await expect(details.getByRole('button', { name: 'Открыть полную карточку' })).toHaveCount(0)
    await details.getByRole('button', { name: 'Добавить в тренировку', exact: true }).click()
    const choose = page.getByRole('dialog', { name: 'В какую тренировку добавить?' })
    await choose.getByRole('button', { name: new RegExp(navigationApi.builder.info.name) }).click()
    await expect(page).toHaveURL(/\/builder\?programId=e2e-saved-workout&add=machine-pulldown$/)
    await expect(page.getByRole('dialog', { name: 'Настройте подходы' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Добавить в тренировку', exact: true })).toBeInViewport()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page).toHaveURL(/\/builder\?programId=e2e-saved-workout$/)
    expect(navigationApi.requests.filter(({ method }) => method !== 'GET' && method !== 'POST')).toEqual([])
  })
}
