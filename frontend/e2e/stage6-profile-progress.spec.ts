import { expect } from '@playwright/test'
import { openAppAsAlexey, savedBrowserState, test } from './fixtures/navigation'

for (const viewport of [{ width: 3840, height: 2160 }, { width: 1920, height: 1080 }]) {
  test(`compact profile and progress at ${viewport.width}x${viewport.height}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport)
    await openAppAsAlexey(page)
    const state = await savedBrowserState(page)
    await page.route((url) => url.pathname === '/api/photo-progress', (route) => route.fulfill({ json: { photos: [{ id: 1, mode: 'manual', view: 'front', takenAt: '2026-09-15T08:00:00Z', imageUrl: '/male-muscles-front.svg', thumbnailUrl: '/male-muscles-front.svg', width: 1200, height: 1600, note: null }] } }))

    await page.goto('/profile')
    await expect(page.getByRole('heading', { level: 1, name: 'Алексей' })).toBeVisible()
    const profileTabs = page.getByRole('navigation', { name: 'Разделы профиля' })
    await expect(profileTabs.getByRole('button')).toHaveCount(4)
    for (const label of ['Обзор', 'Измерения', 'Фото', 'Ограничения']) await expect(profileTabs.getByRole('button', { name: label, exact: true })).toBeInViewport()
    await expect(page.getByText('Основная информация')).toHaveCount(0)
    await expect(page.getByText('Краткая сводка')).toHaveCount(0)
    expect(await page.locator('main').evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(2)
    const profileShot = testInfo.outputPath('profile.png')
    await page.screenshot({ path: profileShot })
    await testInfo.attach('profile', { path: profileShot, contentType: 'image/png' })

    await profileTabs.getByRole('button', { name: 'Ограничения', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Исключённые упражнения' })).toBeVisible()
    await expect(page.getByText('Жим лёжа в тренажёре Смита')).toBeVisible()
    await expect(page.getByText('smith-machine-bench-press')).toHaveCount(0)

    await page.goto('/progress')
    const progressTabs = page.getByRole('navigation', { name: 'Разделы прогресса' })
    await expect(progressTabs.getByRole('button')).toHaveCount(4)
    for (const label of ['Обзор', 'Сила', 'Тело', 'Фото']) await expect(progressTabs.getByRole('button', { name: label, exact: true })).toBeInViewport()
    await expect(page.getByRole('combobox', { name: 'Период прогресса' })).toHaveCount(1)
    await expect(page.locator('.progress-metrics article')).toHaveCount(4)
    await expect(page.getByRole('button', { name: /Сводка|Упражнения|Регулярность|Мышцы|Фото прогресса/ })).toHaveCount(0)
    expect(await page.locator('main').evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(2)
    const progressShot = testInfo.outputPath('progress.png')
    await page.screenshot({ path: progressShot })
    await testInfo.attach('progress', { path: progressShot, contentType: 'image/png' })

    await page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link', { name: 'Усталость мышц', exact: true }).click()
    await expect(page.getByText('Карта мышечной усталости')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveCount(1)
    await page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link', { name: 'Прогресс', exact: true }).click()
    await progressTabs.getByRole('button', { name: 'Фото', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Фотофиксация', exact: true })).toBeVisible()
    await expect(page.getByText('История фотофиксаций')).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Открыть галерею' })).toHaveAttribute('href', '/profile?tab=photo')
    expect(await savedBrowserState(page)).toEqual(state)
  })
}

for (const viewport of [{ width: 3840, height: 2160 }, { width: 1920, height: 1080 }, { width: 1536, height: 768 }, { width: 1280, height: 720 }, { width: 1024, height: 600 }, { width: 390, height: 844 }]) {
  test(`photo capture stays modal at ${viewport.width}x${viewport.height}`, async ({ page, navigationApi }, testInfo) => {
    await page.setViewportSize(viewport)
    // Photo layout is independent of the navigation inventory and live-coach API.
    await page.route('**/api/coach/**', (route) => route.fulfill({ status: 404, json: { detail: 'Coach is not used in photo tests' } }))
    await page.goto('/')
    await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
    const state = await savedBrowserState(page)
    await page.goto('/profile?tab=photo')

    // Replace the fixture's camera sentinel with an in-page fake stream for this explicit camera test.
    await page.evaluate(() => {
      Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => {
        const canvas = document.createElement('canvas')
        canvas.width = 1280; canvas.height = 720
        const context = canvas.getContext('2d')!
        context.fillStyle = '#172333'
        context.fillRect(0, 0, canvas.width, canvas.height)
        return canvas.captureStream(1)
      } })
    })
    await page.getByRole('button', { name: 'Фотофиксация', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Фотофиксация' })
    await expect(dialog).toBeVisible()
    await expect(page).toHaveURL(/\/profile\?tab=photo$/)
    await expect(dialog.getByRole('tab')).toHaveCount(3)
    await expect(dialog.getByRole('button', { name: 'Снять через 5 с', exact: true })).toBeInViewport()
    await expect(dialog.getByRole('button', { name: 'Снять серию', exact: true })).toBeInViewport({ ratio: 1 })
    await expect(dialog.getByRole('group', { name: 'Таймер съёмки' })).toBeInViewport()
    await expect(dialog.getByRole('button', { name: '5 с', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(dialog.getByRole('button', { name: 'Сохранить', exact: false })).toBeDisabled()
    await expect(dialog.getByRole('button', { name: /^Аварийная остановка/ })).toBeInViewport()
    await expect(page.getByRole('button', { name: /^Аварийная остановка/ })).toHaveCount(1)
    const panel = (await page.locator('.photo-capture-panel').boundingBox())!
    const dock = (await page.locator('.forma-dialog-dock .forma-system-dock').boundingBox())!
    expect(panel.y).toBeGreaterThanOrEqual(dock.y + dock.height)
    expect(panel.y + panel.height).toBeLessThanOrEqual(viewport.height)
    expect(panel.width).toBeGreaterThanOrEqual(viewport.width * .95)
    expect(await page.locator('.photo-capture-panel').evaluate((node) => ({ x: node.scrollWidth - node.clientWidth, y: node.scrollHeight - node.clientHeight }))).toEqual({ x: 0, y: 0 })
    for (const button of await dialog.getByRole('button').all()) await expect(button).toBeInViewport({ ratio: 1 })
    const preview = (await page.locator('.photo-capture-preview').boundingBox())!
    const controls = (await page.locator('.photo-capture-side').boundingBox())!
    const actions = (await page.locator('.photo-capture-actions').boundingBox())!
    expect(preview.height).toBeGreaterThan(100)
    expect(controls.y + controls.height).toBeLessThanOrEqual(actions.y)
    const shot = testInfo.outputPath('photo-modal.png')
    await page.screenshot({ path: shot })
    await testInfo.attach('photo-modal', { path: shot, contentType: 'image/png' })
    await dialog.getByRole('button', { name: '3 с', exact: true }).click()
    await dialog.getByRole('button', { name: 'Снять через 3 с', exact: true }).click()
    await expect(dialog.getByRole('timer')).toContainText('3')
    await expect(dialog.getByRole('button', { name: 'Отменить снимок' })).toBeInViewport({ ratio: 1 })
    await expect(dialog.getByRole('tab', { name: 'Сбоку' })).toBeDisabled()
    await expect(dialog.getByRole('img', { name: 'Предпросмотр: спереди' })).toBeVisible({ timeout: 5000 })
    await expect(dialog.getByRole('timer')).toHaveCount(0)
    await expect(dialog.getByRole('button', { name: 'Сохранить', exact: true })).toBeEnabled()
    await dialog.getByRole('button', { name: 'Снять серию', exact: true }).click()
    await expect(dialog.getByRole('timer')).toContainText('Серия · кадр 1 из 3 · Спереди')
    await expect(dialog.getByRole('button', { name: 'Отменить серию' })).toBeInViewport({ ratio: 1 })
    await expect(dialog.getByRole('timer')).toContainText('Серия · кадр 2 из 3 · Сбоку', { timeout: 5000 })
    await expect(dialog.getByRole('timer')).toContainText('Серия · кадр 3 из 3 · Сзади', { timeout: 5000 })
    await expect(dialog.getByRole('img', { name: 'Предпросмотр: сзади' })).toBeVisible({ timeout: 5000 })
    await expect(dialog.getByRole('button', { name: 'Сохранить (3)' })).toBeEnabled()
    await dialog.getByRole('button', { name: 'Закрыть', exact: true }).click()
    await expect(dialog).toHaveCount(0)
    await expect(page).toHaveURL(/\/profile\?tab=photo$/)
    expect(navigationApi.requests.filter(({ path }) => path.startsWith('/api/runtime'))).toEqual([])
    expect(await savedBrowserState(page)).toEqual(state)

    await page.goto('/photo-progress?source=profile&photo=manual')
    await expect(page).toHaveURL(/\/profile\?tab=photo$/)
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })
}
