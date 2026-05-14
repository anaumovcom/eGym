import { expect, test } from '@playwright/test'

test('user can choose a profile and reach dashboard', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: 'Кто тренируется?' })).toBeVisible()
  await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()

  await expect(page).toHaveURL(/\/dashboard/)
  await expect(page.getByText('Добрый день, Алексей')).toBeVisible()
  await expect(page.getByText('Статус тренажёра')).toBeVisible()
})