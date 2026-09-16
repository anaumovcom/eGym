import { expect, test, type Page } from '@playwright/test'
import { expectPrimaryNavigation, openCatalogExerciseSetup, test as readOnlyTest } from './fixtures/navigation'

async function openAppAsAlexey(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })

  const selectionHeading = page.getByRole('heading', { name: 'Кто тренируется?' })
  const entryState = await Promise.race<"selection" | "dashboard">([
    selectionHeading.waitFor({ state: 'visible', timeout: 10000 }).then(() => 'selection'),
    page.waitForURL(/\/dashboard/, { timeout: 10000 }).then(() => 'dashboard'),
  ])

  if (entryState === 'selection') {
    await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
  }

  await expect(page).toHaveURL(/\/dashboard/)
}

readOnlyTest('dashboard survives hard reload with persisted user selection', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.reload({ waitUntil: 'domcontentloaded' })

  await expect(page).toHaveURL(/\/dashboard/)
  await expectPrimaryNavigation(page)
  await expect(page.getByRole('button', { name: 'Меню профиля: Алексей' })).toBeVisible()
})

test('runtime session survives reload and STOP aborts workout from rest state', async ({ page }) => {
  await openAppAsAlexey(page)

  await openCatalogExerciseSetup(page)
  await expect(page).toHaveURL(/\/exercise-setup/)

  await page.getByRole('button', { name: 'Амплитуда сохранена' }).click()
  await expect(page.getByRole('button', { name: 'Запустить упражнение' })).toBeEnabled()
  await page.getByRole('button', { name: 'Запустить упражнение' }).click()
  await expect(page).toHaveURL(/\/exercise-session/)
  await expect(page.getByRole('button', { name: 'Завершить подход' })).toBeVisible()

  await page.reload({ waitUntil: 'domcontentloaded' })

  await expect(page).toHaveURL(/\/exercise-session/)
  await expect(page.getByRole('button', { name: 'Завершить подход' })).toBeVisible()
  await expect(page.getByText(/Подход 1 из/i)).toBeVisible()

  await page.getByRole('button', { name: 'Завершить подход' }).click()
  await expect(page).toHaveURL(/\/rest/)
  await expect(page.getByRole('button', { name: 'Начать следующий подход' })).toBeVisible()

  await page.getByRole('button', { name: 'СТОП' }).click()
  await expect(page.getByText('Аварийная остановка активна')).toBeVisible()
  await page.getByRole('button', { name: 'Завершить тренировку как прерванную' }).click()

  await expect(page).toHaveURL(/\/workout-summary/)
  await expect(page.getByRole('heading', { name: 'Тренировка завершена частично' })).toBeVisible()
})

test('progress screen shows blocking error when backend is unavailable', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.route('**/api/progress**', async (route) => {
    await route.abort('internetdisconnected')
  })

  await page.getByRole('link', { name: 'Прогресс' }).click()

  await expect(page).toHaveURL(/\/progress/)
  await expect(page.getByText('Не удалось загрузить прогресс. Попробуйте открыть его ещё раз.')).toBeVisible()
})