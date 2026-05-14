import { expect, test } from '@playwright/test'

async function openAppAsAlexey(page: Parameters<typeof test>[0]['page']) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: 'Кто тренируется?' })).toBeVisible()
  await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
  await expect(page).toHaveURL(/\/dashboard/)
}

test('quick start runtime reaches workout summary', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Быстрый старт' }).click()
  await page.getByText(/^Начать:/).first().click()

  await expect(page).toHaveURL(/\/exercise-setup/)
  await page.getByRole('button', { name: 'Запустить упражнение' }).click()

  await expect(page).toHaveURL(/\/exercise-session/)
  await page.getByRole('button', { name: 'Завершить подход' }).click()

  await expect(page).toHaveURL(/\/rest/)
  await page.getByRole('button', { name: 'Начать следующий подход' }).click()
  await page.getByRole('button', { name: 'Завершить подход' }).click()

  await expect(page).toHaveURL(/\/rest/)
  await page.getByRole('button', { name: 'Начать следующий подход' }).click()
  await page.getByRole('button', { name: 'Завершить подход' }).click()

  await expect(page).toHaveURL(/\/exercise-summary/)
  await page.getByRole('button', { name: 'Открыть итог тренировки' }).click()

  await expect(page).toHaveURL(/\/workout-summary/)
  await expect(page.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible()
})

test('today flow auto-opens photo progress before setup', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Сегодня' }).click()
  await page.getByRole('button', { name: 'Начать тренировку' }).click()

  await expect(page).toHaveURL(/\/photo-progress/)
  await expect(page.getByRole('heading', { name: 'Фото до тренировки' })).toBeVisible()

  await page.getByRole('button', { name: 'Сделать снимок' }).click()
  await page.getByRole('button', { name: 'Сделать снимок' }).click()
  await page.getByRole('button', { name: 'Сделать снимок' }).click()
  await page.getByRole('button', { name: 'Продолжить к настройке' }).click()

  await expect(page).toHaveURL(/\/exercise-setup/)
  await expect(page.getByRole('heading', { name: 'Настройка упражнения' })).toBeVisible()
})

test('builder exposes group runtime scenario', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Конструктор' }).click()
  await page.getByRole('button', { name: 'Запустить runtime группы' }).click()

  await expect(page).toHaveURL(/\/exercise-setup/)
  await page.getByRole('button', { name: 'Запустить упражнение' }).click()

  await expect(page).toHaveURL(/\/exercise-session/)
  await expect(page.getByText('Группа / суперсет')).toBeVisible()
})