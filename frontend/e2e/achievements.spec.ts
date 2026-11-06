import { readFileSync } from 'node:fs'
import { expect } from '@playwright/test'
import { test } from './fixtures/navigation'

type Tier = Record<string, unknown> & { id: string; tier: number; title: string; minimumEvidenceDays?: number }
type Line = Record<string, unknown> & { id: string; description: string; tiers: Tier[] }

const read = (path: string) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'))
const source = read('../../backend/app/services/achievements/content/v2/catalog.json')
const manifest = read('../../backend/media/achievements/v2/manifest.json')
const byId = (id: string): Line => source.lines.find((line: Line) => line.id === id)
const imageUrl = (tier: Tier) => `/api/achievements/tiers/${encodeURIComponent(tier.id)}/image?userId=alexey`

// A line with its first `earned` tiers earned; the rest is redacted exactly like the backend does.
function projected(id: string, earned: number, extra: Record<string, unknown> = {}): Line {
  const item = byId(id)
  const next = item.tiers[earned]
  return {
    ...item, description: earned ? item.description : '', currentValue: earned ? item.tiers[earned - 1].threshold : 0,
    evidenceDays: earned ? 30 : 0, highestTier: earned, state: 'available', isNew: false,
    nextTierId: next?.id ?? null, progressPercent: next ? 42 : 100,
    tiers: item.tiers.map((tier, index) => index < earned
      ? { ...tier, imageUrl: imageUrl(tier), thumbnailUrl: imageUrl(tier), audioUrl: `/audio/${tier.id}`, imageState: 'ready', audioState: 'ready',
        earned: true, earnedAt: '2026-11-05T12:00:00Z', awardedAt: '2026-11-05T12:00:00Z', status: 'earned' }
      : { ...tier, title: '', phrase: '', imageUrl: null, thumbnailUrl: null, audioUrl: null, imageState: 'locked', audioState: 'locked',
        earned: false, earnedAt: null, awardedAt: null, status: 'not_started' }),
    ...extra,
  }
}

const full = projected('practice.workouts', byId('practice.workouts').tiers.length, { isNew: true })
const earnedIds = ['practice.workouts', 'start.first_set', 'start.first_workout', 'muscle.front-shoulders', 'rhythm.active_days']
const cards = [
  full,
  projected('start.first_set', 2), projected('start.first_workout', 1), projected('muscle.front-shoulders', 3), projected('rhythm.active_days', 4),
  ...source.lines.filter((line: Line) => !earnedIds.includes(line.id)).slice(0, 19).map((line: Line) => projected(line.id, 0)),
]
const counts = { lines: source.lines.length, tiers: source.lines.reduce((sum: number, row: Line) => sum + row.tiers.length, 0), images: 0, audio: 0 }

// 4K display at Windows scale 150 % = 2560x1440 CSS px, dpr 1.5. Other sizes are out of scope.
test.use({ viewport: { width: 2560, height: 1440 }, deviceScaleFactor: 1.5 })

test('achievement collection (4K @150%) and six-tier detail', async ({ page }) => {
  const consoleErrors: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  // Scale-provider heartbeats are fulfilled locally too; no actual device/API.
  await page.route((url) => url.pathname.startsWith('/api/scales/'), async (route) => {
    await route.fulfill({ json: { connected: false, state: 'disconnected', active: false } })
  })
  // Page routes override the read-only navigation fixture. No real API/DB/device.
  await page.route((url) => url.pathname.startsWith('/api/achievements/'), async (route) => {
    const path = new URL(route.request().url()).pathname
    const tier = decodeURIComponent(path.split('/')[4] ?? '')
    if (path.includes('/tiers/') && path.endsWith('/image')) {
      const file = manifest.assets[tier]?.image?.['512']
      await route.fulfill(file
        ? { contentType: 'image/webp', body: readFileSync(new URL(`../../backend/media/achievements/v2/images/${file}`, import.meta.url)) }
        : { status: 404 })
    } else if (path.endsWith('/overview')) {
      await route.fulfill({ json: { earnedTiers: 16, totalTiers: counts.tiers, completedLines: 1,
        totalLines: counts.lines, activeDays: 400, recent: [], upcoming: [], computedThrough: null,
        isRebuilding: false, media: counts } })
    } else if (path.endsWith('/catalog')) {
      await route.fulfill({ json: { lines: cards, total: cards.length, nextCursor: null,
        computedThrough: null, isRebuilding: false, groups: [...new Map(source.lines.map((line: Line & { group: string; groupName: string }) => [line.group, { id: line.group, name: line.groupName }])).values()], media: counts } })
    } else {
      await route.fulfill({ json: full })
    }
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.goto('/achievements')
  await expect(page.getByRole('heading', { name: 'Достижения', exact: true })).toBeVisible()
  await expect(page.getByLabel('Получено ступеней: 6 из 6')).toBeVisible()
  await expect(page.locator('.discovery-count')).toContainText(`Найдено: ${cards.length}`)

  // Every earned tier of a card has its icon and the title underneath.
  const sixTiers = page.locator('.ach-earned-tiers').first().locator('li')
  await expect(sixTiers).toHaveCount(full.tiers.length)
  for (let index = 0; index < full.tiers.length; index += 1) {
    const item = sixTiers.nth(index)
    await expect(item.locator('.ach-image')).toBeVisible()
    await expect(item.locator('.ach-earned-title')).toHaveText(full.tiers[index].title)
    const [icon, text] = await Promise.all([item.locator('.ach-image').boundingBox(), item.locator('.ach-earned-title').boundingBox()])
    expect(text!.y).toBeGreaterThanOrEqual(icon!.y + icon!.height - 1)
  }
  // Locked data never reaches the DOM: no hidden titles/descriptions and no audio elements of unknown lines.
  const hidden = byId(cards[6].id)
  await expect(page.getByText(hidden.description, { exact: false })).toHaveCount(0)
  await expect(page.getByText(hidden.tiers[0].title, { exact: true })).toHaveCount(0)
  await expect(page.locator('audio')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Неизвестное достижение' }).first()).toBeVisible()

  const overflowing = await page.locator('.ach-card').evaluateAll((nodes) => nodes.flatMap((card) => {
    const bounds = card.getBoundingClientRect()
    return [...card.querySelectorAll<HTMLElement>('*')].filter((element) => {
      const rect = element.getBoundingClientRect()
      return rect.width > 0 && rect.height > 0 && (rect.left < bounds.left - 1 || rect.right > bounds.right + 1)
    }).map((element) => `${card.querySelector('h3')?.textContent}:${element.className}`)
  }))
  expect(overflowing).toEqual([])
  const columns = await page.locator('.ach-grid').evaluate((grid) => getComputedStyle(grid).gridTemplateColumns.split(' ').length)
  expect(columns).toBeGreaterThanOrEqual(3)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/achievements-collection-4k150.png' })
  await page.locator('.ach-card-unknown').nth(3).scrollIntoViewIfNeeded()
  await page.screenshot({ path: 'test-results/achievements-unknown-4k150.png' })
  await page.locator('.forma-main').evaluate((element) => element.scrollTo({ top: 0 }))

  await page.getByRole('link', { name: `Открыть достижение «${full.tiers[full.tiers.length - 1].title}»` }).click()
  await expect(page.getByRole('heading', { name: full.tiers[full.tiers.length - 1].title, exact: true }).first()).toBeVisible()
  await expect(page.getByText(`Получено ступеней: ${full.tiers.length} из ${full.tiers.length}`, { exact: true })).toBeVisible()
  await expect(page.locator('.ach-tier-detail')).toHaveCount(full.tiers.length)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/achievements-detail-4k150.png' })
  expect(consoleErrors.filter((text) => !/favicon|WebSocket|ECONNREFUSED/i.test(text))).toEqual([])
})
