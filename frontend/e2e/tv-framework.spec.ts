import { expect, type Page } from '@playwright/test'
import { createRuntimeSession } from '../src/mocks/stage3-data'
import { expectPrimaryNavigation, openAppAsAlexey, primaryNavigation, test } from './fixtures/navigation'
import { kioskViewport as viewport } from './kiosk-display.mjs'

function menuAppearance(band: Element) {
  return [band, ...band.querySelectorAll('header, .forma-brand-mark, .forma-header-wordmark, nav, nav a, nav svg, nav span, button, .forma-profile-avatar, .forma-machine-status-text, .forma-motor-force')].map(node => {
    const { x, y, width, height } = node.getBoundingClientRect()
    const style = getComputedStyle(node)
    return {
      x, y, width, height, font: style.font, radius: style.borderRadius,
      ...(node.closest('nav a') ? {} : { color: style.color, background: style.background, border: style.borderBottom }),
    }
  })
}

async function assertGeometry(page: Page, width: number, height: number) {
  const main = page.getByRole('main')
  const header = page.locator('.forma-navigation')
  const dock = page.getByRole('group', { name: 'Состояние тренажёра и безопасность' })
  const mainBox = await main.boundingBox()
  const headerBox = await header.boundingBox()
  const stop = dock.getByRole('button', { name: 'Аварийная остановка', exact: true })
  const stopBox = await stop.boundingBox()
  expect(mainBox).not.toBeNull()
  expect(headerBox).not.toBeNull()
  expect(stopBox).not.toBeNull()
  expect(Math.abs(mainBox!.x + mainBox!.width / 2 - width / 2)).toBeLessThan(2)
  // No bottom dock any more: the work area starts under the header and reaches the bottom gutter.
  expect(mainBox!.y).toBeGreaterThanOrEqual(headerBox!.y + headerBox!.height)
  expect(mainBox!.y + mainBox!.height).toBeGreaterThan(height * 0.85)
  expect(stopBox!.y + stopBox!.height).toBeLessThanOrEqual(headerBox!.y + headerBox!.height)
  expect(mainBox!.width).toBeCloseTo(headerBox!.width, 0)
  expect(await main.evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(2)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(height)
  await expect(stop).toHaveCount(1)
  await expect(stop).toBeInViewport({ ratio: 1 })
  expect(stopBox!.height).toBeGreaterThanOrEqual(64)
  await expect(dock.getByRole('status')).toBeVisible()
}

test.describe('Kiosk navigation', () => {
  test('all primary menus match fatigue on the 4K kiosk at 150% OS scale', async ({ page, navigationApi }, testInfo) => {
    test.slow()
    await openAppAsAlexey(page)
    expect(await page.evaluate(() => [innerWidth, innerHeight, screen.width, screen.height, devicePixelRatio]))
      .toEqual([2560, 1440, 2560, 1440, 1.5])
    const header = page.locator('.forma-menu-band')
    const nav = header.getByRole('navigation', { name: 'Основная навигация' })
    const routes = new Set(['/fatigue', ...primaryNavigation.map(([, path]) => path),
      '/catalog/machine-pulldown', '/achievements/start.first_set', '/profile', '/settings', '/modbus', '/modbus/settings',
      '/exercise-setup?source=catalog&slug=machine-pulldown', '/workout-summary', '/motor-calibration', '/settings/legacy'])
    const completed = createRuntimeSession({ source: 'catalog', slug: 'machine-pulldown' })
    completed.view = 'workout-summary'
    completed.backendWorkoutSaved = true
    await page.addInitScript(session => {
      if (location.pathname === '/workout-summary') {
        localStorage.setItem('egym-runtime-store', JSON.stringify({ state: { session }, version: 0 }))
      }
    }, completed)
    let reference: ReturnType<typeof menuAppearance> | undefined
    for (const path of routes) {
      const tab = primaryNavigation.find(([, href]) => href === path)
      if (tab) {
        await nav.getByRole('link', { name: tab[0], exact: true }).click()
        await page.mouse.move(0, 0)
      } else {
        await page.goto(path, { waitUntil: 'domcontentloaded' })
      }
      await expect(page).toHaveURL(url => url.pathname === path.split('?')[0])
      await expectPrimaryNavigation(page)
      await expect(header.getByRole('status')).toHaveText(navigationApi.snapshot.machine.machineLabel)
      await page.evaluate(() => document.fonts.ready)
      await assertGeometry(page, viewport.width, viewport.height)
      const firstLink = (await nav.getByRole('link').first().boundingBox())!
      for (const link of await nav.getByRole('link').all()) {
        await expect(link).toBeInViewport({ ratio: 1 })
        const box = (await link.boundingBox())!
        expect(box.y).toBe(firstLink.y)
        expect(box.height).toBeGreaterThanOrEqual(64)
      }
      const section = primaryNavigation.find(([, href]) => path === href || path.startsWith(href + '/'))
      const active = nav.locator('[aria-current="page"]')
      await expect(active).toHaveCount(section ? 1 : 0)
      if (section) {
        await expect(active).toHaveAttribute('href', section[1])
        await expect(active).toHaveCSS('color', 'rgb(192, 221, 255)')
        await expect(active).toHaveCSS('background-color', 'rgb(17, 45, 67)')
        await expect(active).toHaveCSS('border-color', 'rgb(40, 82, 116)')
      }
      const inactive = nav.locator('a:not([aria-current])').first()
      await expect(inactive).toHaveCSS('color', 'rgb(179, 196, 208)')
      await expect(inactive).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
      const appearance = await header.evaluate(menuAppearance)
      if (!reference) {
        reference = appearance
        await testInfo.attach('fatigue-menu', { body: await header.screenshot(), contentType: 'image/png' })
      } else {
        expect(appearance, `Menu on ${path} matches /fatigue`).toEqual(reference)
      }
    }
  })

  test('all seven links and STOP fit alongside service and reset actions', async ({ page, navigationApi }) => {
    navigationApi.snapshot.serviceMode = true
    navigationApi.snapshot.machine = { ...navigationApi.snapshot.machine, machineState: 'blocked', machineLabel: 'Тренажёр заблокирован' }
    await openAppAsAlexey(page)
    const header = page.getByRole('banner')
    for (const name of ['Отключить сервисный режим', 'Сбросить ошибку', 'Аварийная остановка']) {
      await expect(header.getByRole('button', { name, exact: true })).toBeInViewport({ ratio: 1 })
    }
    const nav = header.getByRole('navigation', { name: 'Основная навигация' })
    expect(await nav.evaluate(node => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(1)
    for (const link of await nav.getByRole('link').all()) await expect(link).toBeInViewport({ ratio: 1 })
  })

  test('keyboard focus, secondary disclosure and modal preserve safety space', async ({ page, navigationApi }, testInfo) => {
    await openAppAsAlexey(page)
    const links = page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link')
    await links.first().focus()
    await page.keyboard.press('Shift+Tab')
    await page.keyboard.press('Tab')
    const linkCount = await links.count()
    for (let i = 0; i < linkCount; i++) {
      const link = links.nth(i)
      await expect(link).toBeFocused()
      await expect(link).toHaveCSS('outline-width', '2px')
      await page.keyboard.press('Tab')
    }
    await expect(page.getByRole('button', { name: 'Меню профиля: Алексей' })).toBeFocused()
    await page.goto('/catalog')
    const status = page.getByRole('button', { name: /^Состояние тренажёра:/ })
    await status.press('Enter')
    const details = page.getByRole('dialog').filter({ hasText: 'Состояние тренажёра' })
    await expect(details).toBeVisible()
    await expect(page.getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeInViewport({ ratio: 1 })
    await page.keyboard.press('Escape')
    await expect(details).toHaveCount(0)
    await expect(status).toBeFocused()
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
      const stopped = structuredClone(navigationApi.snapshot)
      stopped.safety.state = 'emergency_stop'
      stopped.machine.safety = 'emergency_stop'
      await route.fulfill({ json: { snapshot: stopped } })
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
