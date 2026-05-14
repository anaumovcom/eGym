import { expect, test } from '@playwright/test'

async function openAppAsAlexey(page: Parameters<typeof test>[0]['page']) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: 'Кто тренируется?' })).toBeVisible()
  await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
  await expect(page).toHaveURL(/\/dashboard/)
}

test('quick start flow reaches exercise setup', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Быстрый старт' }).click()
  await expect(page.getByRole('heading', { name: 'Быстрый старт' })).toBeVisible()

  await page.getByText(/^Начать:/).first().click()

  await expect(page).toHaveURL(/\/exercise-setup/)
  await expect(page.getByRole('heading', { name: 'Настройка упражнения' })).toBeVisible()
})

test('calendar flow opens runtime setup', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Календарь' }).click()
  await expect(page.getByRole('heading', { name: 'Календарь тренировок' })).toBeVisible()

  await page.getByRole('button', { name: 'Начать тренировку' }).click()

  await expect(page).toHaveURL(/\/photo-progress|\/exercise-setup/)
  await expect(page.getByRole('heading', { name: /Фото до тренировки|Настройка упражнения/ })).toBeVisible()
})

test('program library supports adapt and calendar actions', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Программы' }).click()
  await expect(page.getByRole('heading', { name: 'Библиотека готовых программ' })).toBeVisible()

  await page.getByRole('button', { name: 'Адаптировать под меня' }).click()
  await expect(page.getByRole('heading', { name: 'Конструктор тренировок' })).toBeVisible()

  await page.getByRole('link', { name: 'Программы' }).click()
  await page.getByRole('button', { name: 'Назначить в календарь' }).click()

  await expect(page).toHaveURL(/\/calendar/)
  await expect(page.getByRole('heading', { name: 'Календарь тренировок' })).toBeVisible()
})