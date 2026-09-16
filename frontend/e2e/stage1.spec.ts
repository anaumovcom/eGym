import { expect } from '@playwright/test'
import { expectPrimaryNavigation, test } from './fixtures/navigation'

test('user can choose a profile and reach dashboard', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: 'Кто тренируется?' })).toBeVisible()
  await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()

  await expect(page).toHaveURL(/\/dashboard/)
  await expectPrimaryNavigation(page)
  await expect(page.getByText('Добрый день, Алексей')).toHaveCount(0)
  await expect(page.getByText('Статус тренажёра')).toHaveCount(0)
})