import { expect, type Page } from '@playwright/test'
import { expectPrimaryNavigation, openAppAsAlexey, primaryNavigation, savedBrowserState, test } from './fixtures/navigation'

async function expectLockedService(page: Page) {
  await expect(page.getByRole('heading', { name: 'Сервисный раздел', exact: true })).toBeVisible()
  await expect(page.getByRole('checkbox', { name: 'Понимаю риски изменения технических настроек' })).not.toBeChecked()
  await expect(page.getByRole('button', { name: 'Открыть сервисный раздел', exact: true })).toBeDisabled()
  await expect(page.getByRole('navigation', { name: 'Сервисные настройки' })).toHaveCount(0)
  await expect(page.getByText('Диагностика завершена успешно')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Подключение', exact: true })).toHaveCount(0)
  await expect(page.getByRole('main')).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveCount(1)
}

test('six primary tabs navigate without starting a workout or changing saved data', async ({ page, navigationApi }) => {
  await openAppAsAlexey(page)
  const savedState = await savedBrowserState(page)

  for (const [name, path] of [...primaryNavigation.slice(1), primaryNavigation[0]]) {
    const link = page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link', { name, exact: true })
    await link.click()
    await expect(page).toHaveURL(new URL(path, page.url()).href)
    await expectPrimaryNavigation(page)
    await expect(link).toHaveAttribute('aria-current', 'page')
    await expect(page.getByRole('main')).toHaveCount(1)
    if (path === '/modbus') {
      await expect(page.getByRole('heading', { name: /Lichuan A6/ })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveCount(1)
    }
  }

  expect(await savedBrowserState(page)).toEqual(savedState)
  // Opening the Modbus page only reads ports/status; it never connects or writes.
  expect(navigationApi.requests.filter(({ method, path }) => path.startsWith('/api/modbus') && method !== 'GET')).toEqual([])
})

test('legacy Modbus URLs redirect to the standalone page', async ({ page, navigationApi }) => {
  await openAppAsAlexey(page)
  for (const legacy of ['/modbus-debug', '/settings/service/modbus']) {
    await page.goto(legacy, { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(/\/modbus$/)
    await expect(page.getByRole('heading', { name: /Lichuan A6/ })).toBeVisible()
    await expectPrimaryNavigation(page)
  }
  expect(navigationApi.requests.filter(({ method, path }) => path.startsWith('/api/modbus') && method !== 'GET')).toEqual([])
})

test('avatar menu opens profile and settings outside the primary tabs', async ({ page }) => {
  await openAppAsAlexey(page)
  const menu = page.getByRole('navigation', { name: 'Меню пользователя' })
  const avatar = page.getByRole('button', { name: 'Меню профиля: Алексей' })
  await expect(menu).toHaveCount(0)
  await avatar.click()
  await expect(menu.getByRole('link')).toHaveCount(2)
  await expect(menu.getByRole('link', { name: 'Профиль', exact: true })).toHaveAttribute('href', '/profile')
  await expect(menu.getByRole('link', { name: 'Настройки', exact: true })).toHaveAttribute('href', '/settings')
  await page.keyboard.press('Escape')
  await expect(menu).toHaveCount(0)

  for (const [name, path] of [['Профиль', '/profile'], ['Настройки', '/settings']]) {
    await avatar.click()
    await menu.getByRole('link', { name, exact: true }).click()
    await expect(page).toHaveURL(new URL(path, page.url()).href)
    if (path === '/profile') {
      await expect(page.getByRole('button', { name: 'Редактировать', exact: true })).toBeVisible()
    } else {
      await expect(page.getByRole('main').getByText('Настройки', { exact: true })).toBeVisible()
    }
    await expect(menu).toHaveCount(0)
    await expectPrimaryNavigation(page)
  }
})

for (const [legacy, destination, heading] of [
  ['/today?scenario=planned', '/dashboard', null],
  ['/quick-start?selected=old-exercise', '/catalog', 'Каталог упражнений'],
  ['/programs?selected=old-template', '/builder', 'Мои тренировки'],
  ['/fatigue?mode=7d&muscle=back', '/progress?mode=7d&muscle=back&tab=recovery', 'Усталость мышц'],
] as const) {
  test(`legacy ${legacy} redirects without saved-data mutations`, async ({ page, navigationApi }) => {
    await openAppAsAlexey(page)
    const savedState = await savedBrowserState(page)
    const savedPlan = structuredClone(navigationApi.builder)

    await page.goto(legacy, { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL((url) => `${url.pathname}${url.search}` === destination)
    await expectPrimaryNavigation(page)
    if (destination === '/builder') await expect(page.getByRole('heading', { name: heading!, exact: true })).toBeVisible()
    else if (heading) await expect(page.getByText(heading, { exact: true })).toBeVisible()
    expect(await savedBrowserState(page)).toEqual(savedState)
    expect(navigationApi.builder).toEqual(savedPlan)
    expect(navigationApi.requests.some(({ path }) => ['/api/programs', '/api/quick-start', '/api/today'].includes(path))).toBe(false)
  })
}

for (const route of [
  '/settings?tab=service',
  '/settings?tab=mechanics',
  '/settings?tab=diagnostics',
  '/settings?tab=calibrations',
  '/settings?tab=journal',
]) {
  test(`service gate cannot auto-unlock at ${route}`, async ({ page, navigationApi }) => {
    // These are test responses, never settings applied to the device.
    navigationApi.snapshot.serviceMode = true
    navigationApi.settings.service.unlocked = true
    navigationApi.settings.safety.servicePin = false
    await openAppAsAlexey(page)
    const spoofedAccess = 'unlocked=true&serviceMode=true&pin=1234'
    await page.goto(`${route}${route.includes('?') ? '&' : '?'}${spoofedAccess}`, { waitUntil: 'domcontentloaded' })

    await expectLockedService(page)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expectLockedService(page)
  })
}

test('service access requires checkbox and confirm, then resets after reload and history return', async ({ page }) => {
  await openAppAsAlexey(page)
  await page.goto('/settings?tab=diagnostics', { waitUntil: 'domcontentloaded' })
  await expectLockedService(page)
  const acknowledge = page.getByRole('checkbox', { name: 'Понимаю риски изменения технических настроек' })
  const confirm = page.getByRole('button', { name: 'Открыть сервисный раздел', exact: true })

  await acknowledge.check()
  await expect(confirm).toBeEnabled()
  await expect(page.getByText('Диагностика завершена успешно')).toHaveCount(0)
  await acknowledge.uncheck()
  await expect(confirm).toBeDisabled()
  await acknowledge.check()
  await page.getByRole('link', { name: 'Отмена — к настройкам' }).click()
  await expect(page).toHaveURL(/\/settings\?tab=overview$/)
  await page.getByRole('navigation', { name: 'Настройки', exact: true }).getByRole('button', { name: 'Сервис', exact: true }).click()
  await expectLockedService(page)

  const savedState = await savedBrowserState(page)
  await acknowledge.check()
  await confirm.click()
  await page.getByRole('navigation', { name: 'Сервисные настройки' }).getByRole('button', { name: 'Диагностика', exact: true }).click()
  await expect(page.getByText('Диагностика завершена успешно', { exact: true }).first()).toBeVisible()
  expect(await savedBrowserState(page)).toEqual(savedState)

  // Only read existing diagnostics. Do not click any hardware action, including STOP.
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expectLockedService(page)
  await acknowledge.check()
  await confirm.click()
  await expect(page.getByText('Диагностика завершена успешно', { exact: true }).first()).toBeVisible()
  await page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link', { name: 'Главная', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  // Wait for React to unmount SettingsLayout, not only for history.pushState.
  await expect(page.getByRole('heading', { name: 'Какую тренировку выберете?' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Сервисные настройки' })).toHaveCount(0)
  await page.goBack()
  await expect(page).toHaveURL(/\/settings\?tab=diagnostics$/)
  await expectLockedService(page)
})

for (const viewport of [{ width: 3840, height: 2160 }, { width: 1920, height: 1080 }]) {
  test(`recovery has one main and one navigation at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await openAppAsAlexey(page)
    await page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link', { name: 'Прогресс', exact: true }).click()
    await page.getByRole('button', { name: 'Восстановление', exact: true }).click()
    await expect(page).toHaveURL(/\/progress\?tab=recovery$/)
    await expect(page.getByText('Карта мышечной усталости', { exact: true })).toBeVisible()
    await expect(page.getByRole('main')).toHaveCount(1)
    await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toHaveCount(1)
    await expectPrimaryNavigation(page)
    const stop = page.getByRole('button', { name: 'Аварийная остановка', exact: true })
    await expect(stop).toHaveCount(1)
    await expect(stop).toBeInViewport()
    const navigation = page.getByRole('navigation', { name: 'Основная навигация' })
    for (const link of await navigation.getByRole('link').all()) await expect(link).toBeInViewport()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width)
  })
}