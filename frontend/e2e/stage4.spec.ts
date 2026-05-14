import { expect, test } from '@playwright/test'

async function openAppAsAlexey(page: Parameters<typeof test>[0]['page']) {
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

  await page.getByRole('button', { name: 'Фото прогресса' }).click()
  await expect(page.getByText('История фотофиксаций')).toBeVisible()
})

test('fatigue route renders muscle map and recommendation', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Усталость' }).click()
  await expect(page).toHaveURL(/\/fatigue/)
  await expect(page.getByText('Карта мышечной усталости')).toBeVisible()

  await page.getByRole('button', { name: /Спина:/ }).click()
  await expect(page.getByText('Рекомендация Forma')).toBeVisible()
})

test('profile screen supports editing and settings screen shows diagnostics', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Профиль' }).click()
  await expect(page).toHaveURL(/\/profile/)
  await expect(page.getByRole('button', { name: 'Редактировать профиль' })).toBeVisible()
  await page.getByRole('button', { name: 'Редактировать профиль' }).click()
  await page.getByRole('button', { name: 'Общее' }).click()
  await page.getByRole('textbox', { name: 'Имя' }).fill('Алексей QA')
  await page.getByRole('button', { name: 'Сохранить изменения' }).click()
  await expect(page.getByText('Алексей QA').first()).toBeVisible()

  await page.getByRole('link', { name: 'Настройки' }).click()
  await expect(page).toHaveURL(/\/settings/)
  await page.getByRole('button', { name: 'Диагностика' }).click()
  await expect(page.getByText('Диагностика завершена успешно')).toBeVisible()
})