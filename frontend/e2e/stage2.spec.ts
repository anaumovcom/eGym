import { expect, type Page } from '@playwright/test'
import { openCatalogExerciseSetup, savedBrowserState, test } from './fixtures/navigation'

async function openAppAsAlexey(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: 'Кто тренируется?' })).toBeVisible()
  await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
  await expect(page).toHaveURL(/\/dashboard/)
}

test('catalog card reaches exercise setup without starting hardware', async ({ page }) => {
  await openAppAsAlexey(page)
  await openCatalogExerciseSetup(page)
})

test('calendar is read-only with no start, plan or add actions', async ({ page }) => {
  await openAppAsAlexey(page)

  await page.getByRole('link', { name: 'Календарь' }).click()
  await expect(page.getByRole('heading', { name: 'Май 2026' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Начать|Запустить|Планировать|Запланировать|Назначить|Добавить|Сгенерировать|Скопировать|Неделя|Месяц/ })).toHaveCount(0)

  await page.getByRole('button', { name: 'Предыдущий месяц' }).click()
  await expect(page).toHaveURL(/\/calendar\?month=2026-04$/)
  await expect(page.getByRole('heading', { name: 'Апрель 2026' })).toBeVisible()
  await page.getByRole('button', { name: 'Сегодня', exact: true }).click()
  await expect(page).toHaveURL(/\/calendar$/)
  await expect(page.getByRole('button', { name: /Начать|Запустить|Планировать|Запланировать|Назначить|Добавить|Сгенерировать|Скопировать/ })).toHaveCount(0)
})

test('legacy programs redirects to builder without changing saved data', async ({ page, navigationApi }) => {
  await openAppAsAlexey(page)
  const savedState = await savedBrowserState(page)
  const savedPlan = structuredClone(navigationApi.builder)

  await page.goto('/programs?selected=old-template&programId=legacy-template', { waitUntil: 'domcontentloaded' })
  await expect(page).toHaveURL(/\/builder$/)
  await expect(page.getByRole('heading', { name: 'Мои тренировки' })).toBeVisible()
  await expect(page.getByRole('button', { name: `Открыть тренировку «${savedPlan.info.name}»`, exact: true })).toBeVisible()
  expect(await savedBrowserState(page)).toEqual(savedState)
  expect(navigationApi.builder).toEqual(savedPlan)
  expect(navigationApi.requests.filter(({ path }) => path === '/api/builder').every(({ search }) => !new URLSearchParams(search).has('programId'))).toBe(true)
})