import { expect, test, type Page } from '@playwright/test'
import { openCatalogExerciseSetup, test as readOnlyTest } from './fixtures/navigation'

async function openAppAsAlexey(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: 'Кто тренируется?' })).toBeVisible()
  await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
  await expect(page).toHaveURL(/\/dashboard/)
}

test('catalog standalone runtime reaches workout summary', async ({ page }) => {
  await openAppAsAlexey(page)

  await openCatalogExerciseSetup(page)

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

for (const photo of ['before', 'after']) {
  for (const route of ['exercise-setup', 'photo-progress']) {
    readOnlyTest(`legacy photo=${photo} at ${route} stays in setup without camera`, async ({ page, navigationApi }) => {
      await openAppAsAlexey(page)
      await page.goto(`/${route}?source=catalog&slug=machine-pulldown&photo=${photo}`, { waitUntil: 'domcontentloaded' })
      await expect(page).toHaveURL(new RegExp(`/exercise-setup\\?source=catalog&slug=machine-pulldown&photo=${photo}$`))
      await expect(page.getByRole('heading', { name: 'Настройка упражнения' })).toBeVisible()
      await expect(page.getByRole('heading', { name: /Фото до тренировки|Фото после тренировки/ })).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Сделать снимок' })).toHaveCount(0)

      await page.reload({ waitUntil: 'domcontentloaded' })
      await expect(page).toHaveURL(/\/exercise-setup\?/)
      await expect(page.getByRole('heading', { name: 'Настройка упражнения' })).toBeVisible()
      expect(navigationApi.cameraRequests).toEqual([])
    })
  }
}

test('builder exposes group runtime scenario', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Мои тренировки' }).click()
  await page.getByRole('button', { name: 'Запустить runtime группы' }).click()

  await expect(page).toHaveURL(/\/exercise-setup/)
  await page.getByRole('button', { name: 'Запустить упражнение' }).click()

  await expect(page).toHaveURL(/\/exercise-session/)
  await expect(page.getByText('Группа / суперсет')).toBeVisible()
})