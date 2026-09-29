import { expect, type Page } from '@playwright/test'
import { test } from './fixtures/navigation'

async function openAppAsAlexey(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: 'Кто тренируется?' })).toBeVisible()
  await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
  await expect(page).toHaveURL(/\/dashboard/)
}

test('progress route renders analytics and photo tab', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Прогресс' }).click()
  await expect(page).toHaveURL(/\/progress/)
  await expect(page.getByText('Динамика объёма')).toBeVisible()

  await page.getByRole('button', { name: 'Фото', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Фотофиксация', exact: true })).toBeVisible()
})

test('fatigue route renders muscle map and recommendation', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Усталость мышц' }).click()
  await expect(page).toHaveURL(/\/fatigue$/)
  await expect(page.getByText('Карта мышечной усталости')).toBeVisible()

  // The paired SVG paths have a gap at their shared bounding-box centre.
  await page.getByRole('button', { name: /Спина:/ }).first().press('Enter')
  await expect(page).toHaveURL(/\/fatigue\?muscle=back$/)
  await expect(page.getByRole('button', { name: /Спина:/ }).first()).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('Рекомендация Forma')).toBeVisible()
})

test('profile screen supports editing and settings screen shows diagnostics', async ({ page }) => {
  await openAppAsAlexey(page)
  const updates: unknown[] = []
  await page.route((url) => url.pathname === '/api/users/alexey/profile', async (route) => {
    updates.push(route.request().postDataJSON())
    await route.fulfill({ json: { id: 'alexey', name: 'Алексей QA', role: 'member', readinessPercent: 78, accent: 'gold', profile: { birthDate: null, heightCm: 183, weightKg: 92.4, photoUrl: null, notes: '' }, goals: [] } })
  })

  await page.getByRole('button', { name: 'Меню профиля: Алексей' }).click()
  await page.getByRole('navigation', { name: 'Меню пользователя' }).getByRole('link', { name: 'Профиль', exact: true }).click()
  await expect(page).toHaveURL(/\/profile/)
  await expect(page.getByRole('button', { name: 'Редактировать', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Редактировать', exact: true }).click()
  const edit = page.getByRole('dialog', { name: 'Редактировать профиль' })
  await edit.getByRole('textbox', { name: 'Имя' }).fill('Алексей QA')
  await edit.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect.poll(() => updates.length).toBe(1)
  expect(updates[0]).toEqual(expect.objectContaining({ name: 'Алексей QA' }))

  await page.getByRole('button', { name: 'Меню профиля: Алексей' }).click()
  await page.getByRole('navigation', { name: 'Меню пользователя' }).getByRole('link', { name: 'Настройки', exact: true }).click()
  await expect(page).toHaveURL(/\/settings/)
  await page.getByRole('navigation', { name: 'Настройки', exact: true }).getByRole('button', { name: 'Сервис', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Открыть сервисный раздел', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Диагностика', exact: true })).toHaveCount(0)
  await page.getByRole('checkbox', { name: 'Понимаю риски изменения технических настроек' }).check()
  await expect(page.getByRole('button', { name: 'Диагностика', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Открыть сервисный раздел', exact: true }).click()
  await page.getByRole('button', { name: 'Диагностика' }).click()
  // View stored diagnostics only; never click tests, repeat or hardware commands.
  await expect(page.getByText('Диагностика завершена успешно', { exact: true }).first()).toBeVisible()
})