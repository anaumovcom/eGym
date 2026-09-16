import { expect } from '@playwright/test'
import { openAppAsAlexey, savedBrowserState, test } from './fixtures/navigation'

for (const viewport of [{ width: 3840, height: 2160 }, { width: 1920, height: 1080 }]) {
  test(`monthly workout journal at ${viewport.width}x${viewport.height}`, async ({ page, navigationApi }, testInfo) => {
    await page.setViewportSize(viewport)
    await openAppAsAlexey(page)
    const state = await savedBrowserState(page)
    await page.goto('/calendar')
    await expect(page.getByRole('heading', { level: 1, name: 'Май 2026' })).toBeVisible()
    const main = page.locator('main')
    const grid = page.getByRole('grid', { name: 'Выполненные тренировки: Май 2026' })
    await expect(grid.getByRole('row')).toHaveCount(6)
    await expect(grid.getByRole('gridcell')).toHaveCount(42)
    await expect(page.getByRole('button', { name: /Начать|Добавить|Запланировать|Назначить|Неделя|Месяц|Убрать|Изменить план/ })).toHaveCount(0)
    await expect(page.getByText(/Запланировано|Пропущено|Отдых|Баланс мышечных групп|Быстрые действия/)).toHaveCount(0)

    // Whole month fits in the stage without scrolling; rows are tall enough for TV reading.
    expect(await main.evaluate((node) => node.scrollHeight - node.clientHeight)).toBeLessThanOrEqual(2)
    expect(await main.evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(2)
    const cells = grid.getByRole('gridcell')
    for (const cell of await cells.all()) await expect(cell).toBeInViewport({ ratio: 1 })
    const firstCell = (await cells.first().boundingBox())!
    expect(firstCell.height).toBeGreaterThanOrEqual(viewport.width === 3840 ? 200 : 90)
    const mainBox = (await main.boundingBox())!
    const gridBox = (await grid.boundingBox())!
    expect(gridBox.height).toBeGreaterThanOrEqual(mainBox.height * 0.7)

    const today = grid.locator('[data-today="true"]')
    await expect(today).toHaveCount(1)
    await expect(today).toContainText('сегодня')
    const dayButton = today.getByRole('button', { name: /14 мая 2026 г\., 2 тренировки/ })
    await expect(dayButton).toBeInViewport()
    expect((await dayButton.boundingBox())!.height).toBeGreaterThanOrEqual(64)

    const shot = testInfo.outputPath('calendar-month.png')
    await page.screenshot({ path: shot })
    await testInfo.attach('calendar-month', { path: shot, contentType: 'image/png' })

    await dayButton.press('Enter')
    const dialog = page.getByRole('dialog', { name: /Четверг, 14 мая 2026 г\./ })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('article')).toHaveCount(2)
    await expect(dialog.getByText(/только просмотр/)).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeInViewport()
    await expect(page.getByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveCount(1)
    await expect(dialog.getByRole('button', { name: /Начать|Изменить|Убрать|Удалить|Повторить/ })).toHaveCount(0)
    const panel = (await page.locator('.calendar-day-panel').boundingBox())!
    const dock = (await page.locator('.forma-system-dock').boundingBox())!
    expect(panel.y).toBeGreaterThanOrEqual(dock.y + dock.height)
    expect(panel.y + panel.height).toBeLessThanOrEqual(viewport.height)
    const dayShot = testInfo.outputPath('calendar-day.png')
    await page.screenshot({ path: dayShot })
    await testInfo.attach('calendar-day', { path: dayShot, contentType: 'image/png' })
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(dayButton).toBeFocused()

    await page.getByRole('button', { name: 'Предыдущий месяц' }).click()
    await expect(page).toHaveURL(/\/calendar\?month=2026-04$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Апрель 2026' })).toBeVisible()
    expect(await main.evaluate((node) => node.scrollHeight - node.clientHeight)).toBeLessThanOrEqual(2)
    await page.getByRole('button', { name: 'Сегодня', exact: true }).click()
    await expect(page).toHaveURL(/\/calendar$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Май 2026' })).toBeVisible()

    expect(await savedBrowserState(page)).toEqual(state)
    expect(navigationApi.requests.filter(({ method }) => method !== 'GET' && method !== 'POST')).toEqual([])
    expect(navigationApi.requests.filter(({ path }) => path.startsWith('/api/runtime'))).toEqual([])
    const calendarRequests = navigationApi.requests.filter(({ path }) => path === '/api/calendar')
    expect(calendarRequests.every(({ search }) => new URLSearchParams(search).get('userId') === 'alexey')).toBe(true)
    expect(calendarRequests.some(({ search }) => new URLSearchParams(search).get('month') === '2026-04')).toBe(true)
  })
}
