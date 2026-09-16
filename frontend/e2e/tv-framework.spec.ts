import { expect, type Page } from '@playwright/test'
import { openAppAsAlexey, test } from './fixtures/navigation'

async function assertGeometry(page: Page, width: number, height: number) {
  const main = page.getByRole('main')
  const header = page.locator('.forma-navigation')
  const dock = page.getByRole('group', { name: 'Состояние тренажёра и безопасность' })
  const mainBox = await main.boundingBox()
  const headerBox = await header.boundingBox()
  const dockBox = await dock.boundingBox()
  expect(mainBox).not.toBeNull()
  expect(headerBox).not.toBeNull()
  expect(dockBox).not.toBeNull()
  expect(Math.abs(mainBox!.x + mainBox!.width / 2 - width / 2)).toBeLessThan(2)
  // No bottom dock any more: the work area starts under the header and reaches the bottom gutter.
  expect(mainBox!.y).toBeGreaterThanOrEqual(headerBox!.y + headerBox!.height)
  expect(mainBox!.y + mainBox!.height).toBeGreaterThan(height * 0.85)
  expect(dockBox!.y + dockBox!.height).toBeLessThanOrEqual(headerBox!.y + headerBox!.height + 1)
  expect(mainBox!.width).toBeLessThanOrEqual(width * (width === 3840 ? 0.75 : 0.9))
  expect(await main.evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(2)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(height)
  const stop = page.getByRole('button', { name: 'Аварийная остановка', exact: true })
  await expect(stop).toHaveCount(1)
  await expect(stop).toBeInViewport()
  expect((await stop.boundingBox())!.height).toBeGreaterThanOrEqual(64)
  await expect(dock.getByRole('status')).toBeVisible()
}

for (const viewport of [{ width: 3840, height: 2160 }, { width: 1920, height: 1080 }]) {
  test.describe(`${viewport.width}x${viewport.height} TV framework`, () => {
    test.use({ viewport, deviceScaleFactor: 1 })

    test('key screens stay centred above STOP, with readable controls', async ({ page }, testInfo) => {
      await openAppAsAlexey(page)
      for (const path of ['/dashboard', '/catalog', '/calendar', '/builder', '/profile', '/progress', '/settings']) {
        await page.goto(path)
        await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible()
        await expect(page.getByRole('main')).not.toHaveText(/^(Загрузка.*)?$/)
        await assertGeometry(page, viewport.width, viewport.height)
        for (const link of await page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link').all()) {
          await expect(link).toBeInViewport()
          expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(64)
        }
        if (viewport.width === 3840) {
          expect(await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize))).toBe(24)
          const heading = page.locator('main h1').first()
          if (await heading.count()) {
            const size = await heading.evaluate((node) => parseFloat(getComputedStyle(node).fontSize))
            expect(size).toBeGreaterThanOrEqual(42)
            expect(size).toBeLessThanOrEqual(64)
          }
        }
        const screenshot = testInfo.outputPath(`${path.slice(1)}.png`)
        await page.screenshot({ path: screenshot })
        await testInfo.attach(path.slice(1), { path: screenshot, contentType: 'image/png' })
      }
    })

    test('keyboard focus, secondary disclosure and modal preserve safety space', async ({ page, navigationApi }, testInfo) => {
      await openAppAsAlexey(page)
      const links = page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link')
      await links.first().focus()
      const linkCount = await links.count()
      for (let i = 0; i < linkCount; i++) {
        const link = links.nth(i)
        await expect(link).toBeFocused()
        expect(await link.evaluate((node) => parseFloat(getComputedStyle(node).outlineWidth))).toBeGreaterThanOrEqual(3)
        await page.keyboard.press('Tab')
      }
      await expect(page.getByRole('button', { name: 'Меню профиля: Алексей' })).toBeFocused()
      await page.goto('/catalog')
      // CAT-2: detailed filters live in a large panel, not a permanent side column.
      const filters = page.getByRole('button', { name: 'Все фильтры', exact: true })
      await expect(page.getByRole('dialog', { name: 'Все фильтры' })).toHaveCount(0)
      await filters.press('Enter')
      const filtersDialog = page.getByRole('dialog', { name: 'Все фильтры' })
      await expect(filtersDialog).toBeVisible()
      await expect(filtersDialog.getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeInViewport()
      await page.keyboard.press('Escape')
      await expect(filtersDialog).toHaveCount(0)
      await expect(filters).toBeFocused()
      await assertGeometry(page, viewport.width, viewport.height)
      const search = page.getByPlaceholder('Найти упражнение...')
      expect((await search.locator('..').boundingBox())!.height).toBeGreaterThanOrEqual(64)

      await page.goto('/catalog?selected=machine-pulldown')
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      const stop = dialog.getByRole('button', { name: 'Аварийная остановка', exact: true })
      await expect(stop).toBeVisible()
      await expect(page.getByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveCount(1)
      // Check real hit testing but never issue STOP to the live backend.
      await stop.click({ trial: true })
      await stop.focus()
      await expect(stop).toBeFocused()
      const panel = await page.locator('.forma-dialog-panel').boundingBox()
      const dock = await page.locator('.forma-system-dock').boundingBox()
      expect(panel!.y).toBeGreaterThanOrEqual(dock!.y + dock!.height)
      expect(panel!.y + panel!.height).toBeLessThanOrEqual(viewport.height)
      expect(await page.locator('.forma-dialog-panel').evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(2)
      const screenshot = testInfo.outputPath('exercise-modal.png')
      await page.screenshot({ path: screenshot })
      await testInfo.attach('exercise-modal', { path: screenshot, contentType: 'image/png' })
      // STOP's provider also sends a command: intercept and assert this one
      // expected request locally. All other writes still fail the base fixture.
      const stopCommands: unknown[] = []
      await page.route('**/api/hardware/commands', async (route) => {
        const payload = route.request().postDataJSON()
        expect(payload.action).toBe('trigger_emergency_stop')
        stopCommands.push(payload)
        await route.fulfill({ json: { snapshot: navigationApi.snapshot } })
      })
      await stop.click()
      const emergency = page.getByRole('dialog', { name: 'Аварийная остановка активна' })
      await expect(emergency).toBeVisible()
      await expect.poll(() => stopCommands.length).toBe(1)
      await emergency.getByRole('button', { name: 'Закрыть оверлей' }).click()
      await expect(emergency).toHaveCount(0)
      await expect(stop).toBeFocused()
      for (const key of ['Tab', 'Tab', 'Shift+Tab', 'Shift+Tab']) {
        await page.keyboard.press(key)
        expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true)
      }
      await page.keyboard.press('Escape')
      await expect(dialog).toHaveCount(0)
      await assertGeometry(page, viewport.width, viewport.height)

      await page.goto('/catalog?selected=machine-pulldown')
      await expect(dialog).toBeVisible()
      await page.mouse.click(50, 250)
      await expect(dialog).toHaveCount(0)
    })
  })
}